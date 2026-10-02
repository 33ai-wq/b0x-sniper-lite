// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title zkLTC - Testnet Mock Token for LitCount
/// @notice ERC20 token used as staking asset in LitCount pool
contract zkLTC is ERC20, Ownable {
    uint256 public constant FAUCET_AMOUNT = 10 ether; // 10 zkLTC per claim
    uint256 public constant FAUCET_COOLDOWN = 24 hours;

    mapping(address => uint256) public lastFaucetClaim;

    event FaucetClaimed(address indexed user, uint256 amount);

    constructor() ERC20("zkLTC Testnet", "zkLTC") Ownable(msg.sender) {
        // Mint initial supply to deployer for pool funding
        _mint(msg.sender, 1_000_000 ether);
    }

    /// @notice Faucet: anyone can claim 10 zkLTC every 24 hours
    function faucet() external {
        require(
            block.timestamp >= lastFaucetClaim[msg.sender] + FAUCET_COOLDOWN,
            "zkLTC: Faucet cooldown active"
        );
        lastFaucetClaim[msg.sender] = block.timestamp;
        _mint(msg.sender, FAUCET_AMOUNT);
        emit FaucetClaimed(msg.sender, FAUCET_AMOUNT);
    }

    /// @notice Admin mint for pool reward funding
    function adminMint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    /// @notice Check cooldown remaining for an address
    function cooldownRemaining(address user) external view returns (uint256) {
        uint256 nextClaim = lastFaucetClaim[user] + FAUCET_COOLDOWN;
        if (block.timestamp >= nextClaim) return 0;
        return nextClaim - block.timestamp;
    }
}
