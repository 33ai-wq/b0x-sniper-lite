// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/// @title LitCount Pool — Save & Win DeFi Pool
/// @notice Pool staking 0.1 zkLTC per user. Every 21 hours:
///         - 1 Lucky Winner = 70% of pool
///         - All stakers  = 20% shared proportionally
///         - Protocol fee = 10%
///         Minimum 21 users required for draw.
contract LitCountPool is ReentrancyGuard, Ownable, Pausable {
    using SafeERC20 for IERC20;

    // ─────────────────────────────────────────────────
    //  CONSTANTS
    // ─────────────────────────────────────────────────
    uint256 public constant STAKE_AMOUNT      = 0.1 ether;   // 0.1 zkLTC
    uint256 public constant POOL_DURATION     = 21 hours;
    uint256 public constant DRAW_WINDOW       = 21 minutes;
    uint256 public constant MIN_USERS         = 21;

    uint256 public constant WINNER_PCT        = 70;  // 70% to jackpot winner
    uint256 public constant STAKER_PCT        = 20;  // 20% shared to all stakers
    uint256 public constant PROTOCOL_PCT      = 10;  // 10% protocol fee

    // ─────────────────────────────────────────────────
    //  STATE
    // ─────────────────────────────────────────────────
    IERC20  public immutable zkLTC;
    address public           treasury;

    uint256 public currentRound;
    uint256 public roundStartTime;
    uint256 public roundEndTime;       // timestamp when draw phase started
    bool    public isDrawPhase;        // true = 21-min draw window
    bool    public drawExecuted;       // winner picked for this round?

    struct Round {
        uint256 id;
        uint256 startTime;
        uint256 endTime;
        uint256 totalPool;
        uint256 userCount;
        address winner;
        uint256 winnerReward;
        uint256 sharesPerStaker;
        bool    settled;
    }

    struct UserInfo {
        bool    isActive;          // currently in pool
        uint256 roundJoined;       // which round
        bool    rewardClaimed;     // claimed staker share?
    }

    mapping(uint256 => Round)                   public rounds;
    mapping(uint256 => address[])               public roundParticipants;
    mapping(uint256 => mapping(address => UserInfo)) public userInfo;

    // ─────────────────────────────────────────────────
    //  EVENTS
    // ─────────────────────────────────────────────────
    event PoolJoined(address indexed user, uint256 indexed round, uint256 timestamp);
    event DrawPhaseStarted(uint256 indexed round, uint256 userCount, uint256 totalPool);
    event DrawSkipped(uint256 indexed round, uint256 userCount, string reason);
    event WinnerSelected(uint256 indexed round, address indexed winner, uint256 reward);
    event StakerRewardClaimed(address indexed user, uint256 indexed round, uint256 amount);
    event RoundSettled(uint256 indexed round, uint256 totalPool, address winner);
    event NewRoundStarted(uint256 indexed round, uint256 startTime);

    // ─────────────────────────────────────────────────
    //  CONSTRUCTOR
    // ─────────────────────────────────────────────────
    constructor(address _zkLTC, address _treasury) Ownable(msg.sender) {
        require(_zkLTC   != address(0), "Invalid token");
        require(_treasury != address(0), "Invalid treasury");
        zkLTC    = IERC20(_zkLTC);
        treasury = _treasury;
        _startNewRound();
    }

    // ─────────────────────────────────────────────────
    //  JOIN POOL
    // ─────────────────────────────────────────────────

    /// @notice Stake 0.1 zkLTC to join the current pool round
    function joinPool() external nonReentrant whenNotPaused {
        require(!isDrawPhase, "Pool: Draw phase active, please wait 21 min");
        require(
            !userInfo[currentRound][msg.sender].isActive,
            "Pool: Already joined this round"
        );

        Round storage round = rounds[currentRound];
        require(!round.settled, "Pool: Round already settled");

        // Transfer 0.1 zkLTC from user
        zkLTC.safeTransferFrom(msg.sender, address(this), STAKE_AMOUNT);

        // Register user
        roundParticipants[currentRound].push(msg.sender);
        userInfo[currentRound][msg.sender] = UserInfo({
            isActive:      true,
            roundJoined:   currentRound,
            rewardClaimed: false
        });

        round.totalPool  += STAKE_AMOUNT;
        round.userCount  += 1;

        emit PoolJoined(msg.sender, currentRound, block.timestamp);
    }

    // ─────────────────────────────────────────────────
    //  TRIGGER DRAW (called after 21 hours)
    // ─────────────────────────────────────────────────

    /// @notice Anyone can trigger draw phase after 21 hours
    function triggerDrawPhase() external whenNotPaused {
        Round storage round = rounds[currentRound];
        require(!round.settled,    "Pool: Already settled");
        require(!isDrawPhase,      "Pool: Already in draw phase");
        require(
            block.timestamp >= round.startTime + POOL_DURATION,
            "Pool: 21 hours not elapsed yet"
        );

        isDrawPhase  = true;
        roundEndTime = block.timestamp;

        emit DrawPhaseStarted(currentRound, round.userCount, round.totalPool);
    }

    // ─────────────────────────────────────────────────
    //  EXECUTE DRAW (called during 21-min draw window)
    // ─────────────────────────────────────────────────

    /// @notice Execute the draw after draw phase starts
    /// @dev Uses commit-reveal style pseudo-random (upgrade to Chainlink VRF in mainnet)
    function executeDraw() external nonReentrant whenNotPaused {
        require(isDrawPhase,    "Pool: Not in draw phase");
        require(!drawExecuted,  "Pool: Draw already executed");

        Round storage round = rounds[currentRound];

        // ── Case: Not enough users ──
        if (round.userCount < MIN_USERS) {
            emit DrawSkipped(
                currentRound,
                round.userCount,
                "Less than 21 users. Pool continues."
            );
            // Reset draw phase, pool continues — existing users stay
            isDrawPhase  = false;
            round.startTime = block.timestamp; // reset 21hr timer
            return;
        }

        // ── Case: Enough users → pick winner ──
        drawExecuted = true;

        uint256 totalPool     = round.totalPool;
        uint256 winnerReward  = (totalPool * WINNER_PCT)   / 100;
        uint256 stakerPool    = (totalPool * STAKER_PCT)   / 100;
        uint256 protocolFee   = (totalPool * PROTOCOL_PCT) / 100;
        uint256 sharesEach    = stakerPool / round.userCount;

        // Pick pseudo-random winner
        address winner = _pickWinner(currentRound);

        round.winner          = winner;
        round.winnerReward    = winnerReward;
        round.sharesPerStaker = sharesEach;
        round.settled         = true;

        // Send winner reward
        zkLTC.safeTransfer(winner, winnerReward);

        // Send protocol fee to treasury
        zkLTC.safeTransfer(treasury, protocolFee);

        emit WinnerSelected(currentRound, winner, winnerReward);
        emit RoundSettled(currentRound, totalPool, winner);

        // Start next round automatically
        isDrawPhase  = false;
        drawExecuted = false;
        _startNewRound();
    }

    // ─────────────────────────────────────────────────
    //  CLAIM STAKER REWARD
    // ─────────────────────────────────────────────────

    /// @notice Stakers claim their 20% share after round is settled
    function claimStakerReward(uint256 roundId) external nonReentrant {
        Round storage round = rounds[roundId];
        require(round.settled, "Pool: Round not settled yet");

        UserInfo storage info = userInfo[roundId][msg.sender];
        require(info.isActive,       "Pool: Not a participant");
        require(!info.rewardClaimed, "Pool: Already claimed");

        info.rewardClaimed = true;
        info.isActive      = false;

        uint256 reward = round.sharesPerStaker;
        require(reward > 0, "Pool: No reward available");

        // Return stake + staker share
        uint256 totalReturn = STAKE_AMOUNT + reward;
        zkLTC.safeTransfer(msg.sender, totalReturn);

        emit StakerRewardClaimed(msg.sender, roundId, reward);
    }

    // ─────────────────────────────────────────────────
    //  VIEW FUNCTIONS
    // ─────────────────────────────────────────────────

    function getCurrentRoundInfo() external view returns (
        uint256 id,
        uint256 startTime,
        uint256 userCount,
        uint256 totalPool,
        bool    inDrawPhase,
        uint256 timeUntilDraw,
        bool    canTriggerDraw
    ) {
        Round storage r = rounds[currentRound];
        uint256 elapsed  = block.timestamp - r.startTime;
        uint256 remaining = elapsed >= POOL_DURATION ? 0 : POOL_DURATION - elapsed;

        return (
            currentRound,
            r.startTime,
            r.userCount,
            r.totalPool,
            isDrawPhase,
            remaining,
            elapsed >= POOL_DURATION && !isDrawPhase && !r.settled
        );
    }

    function getParticipants(uint256 roundId) external view returns (address[] memory) {
        return roundParticipants[roundId];
    }

    function isUserInCurrentPool(address user) external view returns (bool) {
        return userInfo[currentRound][user].isActive;
    }

    function getPoolProgress() external view returns (
        uint256 current,
        uint256 minimum,
        uint256 percentage
    ) {
        uint256 count = rounds[currentRound].userCount;
        uint256 pct   = count >= MIN_USERS ? 100 : (count * 100) / MIN_USERS;
        return (count, MIN_USERS, pct);
    }

    function getRoundWinner(uint256 roundId) external view returns (address, uint256) {
        Round storage r = rounds[roundId];
        return (r.winner, r.winnerReward);
    }

    // ─────────────────────────────────────────────────
    //  INTERNAL
    // ─────────────────────────────────────────────────

    function _startNewRound() internal {
        currentRound += 1;
        roundStartTime = block.timestamp;
        rounds[currentRound] = Round({
            id:            currentRound,
            startTime:     block.timestamp,
            endTime:       0,
            totalPool:     0,
            userCount:     0,
            winner:        address(0),
            winnerReward:  0,
            sharesPerStaker: 0,
            settled:       false
        });
        emit NewRoundStarted(currentRound, block.timestamp);
    }

    /// @dev Pseudo-random winner selection
    /// @notice For mainnet, replace with Chainlink VRF
    function _pickWinner(uint256 roundId) internal view returns (address) {
        address[] storage participants = roundParticipants[roundId];
        uint256 seed = uint256(
            keccak256(
                abi.encodePacked(
                    block.timestamp,
                    block.prevrandao,
                    roundId,
                    participants.length,
                    rounds[roundId].totalPool
                )
            )
        );
        return participants[seed % participants.length];
    }

    // ─────────────────────────────────────────────────
    //  ADMIN
    // ─────────────────────────────────────────────────

    function setTreasury(address _treasury) external onlyOwner {
        require(_treasury != address(0), "Invalid treasury");
        treasury = _treasury;
    }

    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    /// @notice Emergency withdraw if contract is paused
    function emergencyWithdraw(uint256 roundId) external nonReentrant whenPaused {
        UserInfo storage info = userInfo[roundId][msg.sender];
        require(info.isActive,       "Not a participant");
        require(!info.rewardClaimed, "Already claimed");
        info.isActive      = false;
        info.rewardClaimed = true;
        zkLTC.safeTransfer(msg.sender, STAKE_AMOUNT);
    }
}
