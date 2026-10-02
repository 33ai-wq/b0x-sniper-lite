// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/// @title LitCount Pool - Save & Win DeFi Pool
/// @notice Pool staking: stake zkLTC, win jackpot or earn base reward
contract LitCountPool is ReentrancyGuard, Ownable, Pausable {
    using SafeERC20 for IERC20;

    uint256 public constant STAKE_AMOUNT  = 0.1 ether;
    uint256 public constant POOL_DURATION = 21 hours;
    uint256 public constant DRAW_WINDOW   = 21 minutes;
    uint256 public constant MIN_USERS     = 21;

    uint256 public constant JACKPOT_BPS   = 7000;
    uint256 public constant STAKER_BPS    = 2000;
    uint256 public constant PROTOCOL_BPS  = 1000;
    uint256 public constant BPS_DENOM     = 10000;

    IERC20  public immutable zkLTCToken;
    address public protocolTreasury;

    uint256 public currentPoolId;
    uint256 public poolStartTime;
    bool    public isDrawPhase;
    bool    public drawExecuted;

    address[] public participants;
    mapping(address => bool)    public hasJoined;
    mapping(address => uint256) public stakedAmount;

    address public lastWinner;
    uint256 public lastJackpot;
    uint256 public lastStakerReward;

    struct PoolResult {
        uint256 poolId;
        address winner;
        uint256 jackpot;
        uint256 stakerRewardPerUser;
        uint256 totalParticipants;
        uint256 totalPool;
        uint256 timestamp;
        bool    drawHeld;
    }
    PoolResult[] public poolHistory;

    event Joined(address indexed user, uint256 poolId, uint256 total);
    event DrawPhaseStarted(uint256 poolId, uint256 participants, uint256 timestamp);
    event DrawExecuted(uint256 poolId, address winner, uint256 jackpot, uint256 stakerReward);
    event DrawSkipped(uint256 poolId, uint256 participants, string reason);
    event PoolReset(uint256 newPoolId, uint256 timestamp);

    constructor(address _token, address _treasury) Ownable(msg.sender) {
        require(_token    != address(0), "invalid token");
        require(_treasury != address(0), "invalid treasury");
        zkLTCToken       = IERC20(_token);
        protocolTreasury = _treasury;
        poolStartTime    = block.timestamp;
        currentPoolId    = 1;
    }

    function joinPool() external nonReentrant whenNotPaused {
        require(!isDrawPhase,           "LitCount: Draw phase active, pool closed");
        require(!hasJoined[msg.sender], "LitCount: Already in this pool");
        require(
            block.timestamp < poolStartTime + POOL_DURATION,
            "LitCount: Pool duration ended, trigger draw first"
        );
        zkLTCToken.safeTransferFrom(msg.sender, address(this), STAKE_AMOUNT);
        hasJoined[msg.sender]    = true;
        stakedAmount[msg.sender] = STAKE_AMOUNT;
        participants.push(msg.sender);
        emit Joined(msg.sender, currentPoolId, participants.length);
    }

    /// @notice Trigger draw phase — callable by anyone after 21 hours
    function triggerDrawPhase() external nonReentrant whenNotPaused {
        require(!isDrawPhase, "LitCount: Already in draw phase");
        require(
            block.timestamp >= poolStartTime + POOL_DURATION,
            "LitCount: Pool still running"
        );
        isDrawPhase  = true;
        drawExecuted = false;
        emit DrawPhaseStarted(currentPoolId, participants.length, block.timestamp);
    }

    /// @notice Execute draw or skip — callable during 21-min window
    function executeDraw() external nonReentrant whenNotPaused {
        require(isDrawPhase,   "LitCount: Not in draw phase");
        require(!drawExecuted, "LitCount: Draw already executed");
        require(
            block.timestamp <= poolStartTime + POOL_DURATION + DRAW_WINDOW,
            "LitCount: Draw window expired"
        );

        uint256 count = participants.length;

        // ── Not enough users: KEEP participants, just reset timer ──
        if (count < MIN_USERS) {
            poolHistory.push(PoolResult({
                poolId:              currentPoolId,
                winner:              address(0),
                jackpot:             0,
                stakerRewardPerUser: 0,
                totalParticipants:   count,
                totalPool:           count * STAKE_AMOUNT,
                timestamp:           block.timestamp,
                drawHeld:            false
            }));
            emit DrawSkipped(currentPoolId, count, "Minimum 21 users not reached");
            _continuePool(); // keep participants!
            return;
        }

        // ── Enough users: pick winner ──
        drawExecuted = true;
        uint256 totalPool   = count * STAKE_AMOUNT;
        uint256 jackpot     = (totalPool * JACKPOT_BPS)  / BPS_DENOM;
        uint256 stakerTotal = (totalPool * STAKER_BPS)   / BPS_DENOM;
        uint256 protocolFee = (totalPool * PROTOCOL_BPS) / BPS_DENOM;
        uint256 stakerEach  = stakerTotal / count;

        uint256 winnerIdx = _pseudoRandom(count);
        address winner    = participants[winnerIdx];

        lastWinner      = winner;
        lastJackpot     = jackpot;
        lastStakerReward = stakerEach;

        zkLTCToken.safeTransfer(winner, jackpot);
        zkLTCToken.safeTransfer(protocolTreasury, protocolFee);
        for (uint256 i = 0; i < count; i++) {
            if (stakerEach > 0) {
                zkLTCToken.safeTransfer(participants[i], stakerEach);
            }
        }

        poolHistory.push(PoolResult({
            poolId:              currentPoolId,
            winner:              winner,
            jackpot:             jackpot,
            stakerRewardPerUser: stakerEach,
            totalParticipants:   count,
            totalPool:           totalPool,
            timestamp:           block.timestamp,
            drawHeld:            true
        }));

        emit DrawExecuted(currentPoolId, winner, jackpot, stakerEach);
        _resetPoolFull();
    }

    /// @notice Safety reset if draw window expired without execution
    /// @dev If <21 users: KEEP participants. If >=21: refund all (edge case)
    function forceReset() external nonReentrant whenNotPaused {
        require(isDrawPhase, "LitCount: Not in draw phase");
        require(
            block.timestamp > poolStartTime + POOL_DURATION + DRAW_WINDOW,
            "LitCount: Draw window still open"
        );

        if (!drawExecuted) {
            if (participants.length >= MIN_USERS) {
                // Enough users but draw wasn't called — refund
                _refundAll();
                _resetPoolFull();
            } else {
                // Not enough users — KEEP participants, reset timer only
                _continuePool();
            }
        } else {
            _resetPoolFull();
        }
    }

    // ── Internal ──────────────────────────────────────────────────

    /// @dev Keep participants, only reset timer (for <21 users case)
    function _continuePool() internal {
        isDrawPhase   = false;
        drawExecuted  = false;
        poolStartTime = block.timestamp;
        currentPoolId++;
        emit PoolReset(currentPoolId, block.timestamp);
    }

    /// @dev Full reset — clear all participants
    function _resetPoolFull() internal {
        for (uint256 i = 0; i < participants.length; i++) {
            delete hasJoined[participants[i]];
            delete stakedAmount[participants[i]];
        }
        delete participants;
        isDrawPhase   = false;
        drawExecuted  = false;
        poolStartTime = block.timestamp;
        currentPoolId++;
        emit PoolReset(currentPoolId, block.timestamp);
    }

    function _refundAll() internal {
        for (uint256 i = 0; i < participants.length; i++) {
            address user   = participants[i];
            uint256 amount = stakedAmount[user];
            if (amount > 0) {
                zkLTCToken.safeTransfer(user, amount);
            }
        }
    }

    function _pseudoRandom(uint256 count) internal view returns (uint256) {
        return uint256(keccak256(abi.encodePacked(
            block.timestamp, block.prevrandao,
            participants.length, msg.sender
        ))) % count;
    }

    // ── View ──────────────────────────────────────────────────────

    function getParticipants() external view returns (address[] memory) {
        return participants;
    }

    function getParticipantCount() external view returns (uint256) {
        return participants.length;
    }

    function getPoolStatus() external view returns (
        uint256 poolId, uint256 participantCount, uint256 totalStaked,
        uint256 timeLeft, bool inDrawPhase,
        uint256 jackpotEstimate, uint256 stakerRewardEstimate
    ) {
        poolId           = currentPoolId;
        participantCount = participants.length;
        totalStaked      = participants.length * STAKE_AMOUNT;
        uint256 endTime  = poolStartTime + POOL_DURATION;
        timeLeft         = block.timestamp >= endTime ? 0 : endTime - block.timestamp;
        inDrawPhase      = isDrawPhase;
        uint256 pool     = participantCount * STAKE_AMOUNT;
        jackpotEstimate       = (pool * JACKPOT_BPS) / BPS_DENOM;
        stakerRewardEstimate  = participantCount > 0
            ? ((pool * STAKER_BPS) / BPS_DENOM) / participantCount : 0;
    }

    function getPoolHistory() external view returns (PoolResult[] memory) {
        return poolHistory;
    }

    function getDrawPhaseTimeLeft() external view returns (uint256) {
        if (!isDrawPhase) return 0;
        uint256 drawEnd = poolStartTime + POOL_DURATION + DRAW_WINDOW;
        if (block.timestamp >= drawEnd) return 0;
        return drawEnd - block.timestamp;
    }

    // ── Admin ─────────────────────────────────────────────────────

    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    function setTreasury(address _treasury) external onlyOwner {
        require(_treasury != address(0), "invalid treasury");
        protocolTreasury = _treasury;
    }

    function emergencyWithdraw() external onlyOwner whenPaused {
        uint256 bal = zkLTCToken.balanceOf(address(this));
        zkLTCToken.safeTransfer(owner(), bal);
    }
}
