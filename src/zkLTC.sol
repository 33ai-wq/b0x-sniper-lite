// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title zkLTC — Testnet Token for LitCount
/// @notice Mock ERC20 with faucet for testnet usage
contract zkLTC is ERC20, Ownable {
    uint256 public constant FAUCET_AMOUNT = 10 ether; // 10 zkLTC per claim
    uint256 public constant FAUCET_COOLDOWN = 24 hours;

    mapping(address => uint256) public lastFaucetClaim;

    event FaucetClaimed(address indexed user, uint256 amount);

    constructor() ERC20("zkLTC Testnet", "zkLTC") Ownable(msg.sender) {
        // Mint initial supply to deployer for seeding pool rewards
        _mint(msg.sender, 1_000_000 ether);
    }

    /// @notice Faucet: claim 10 zkLTC every 24 hours
    function faucet() external {
        require(
            block.timestamp >= lastFaucetClaim[msg.sender] + FAUCET_COOLDOWN,
            "zkLTC: Cooldown active, wait 24h"
        );
        lastFaucetClaim[msg.sender] = block.timestamp;
        _mint(msg.sender, FAUCET_AMOUNT);
        emit FaucetClaimed(msg.sender, FAUCET_AMOUNT);
    }

    /// @notice Owner can mint for pool seeding
    function mintForPool(address pool, uint256 amount) external onlyOwner {
        _mint(pool, amount);
    }
}
