// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract DeployLitCount is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy zkLTC token
        zkLTC token = new zkLTC();
        console.log("zkLTC deployed at:", address(token));

        // 2. Deploy LitCount Pool (treasury = deployer for testnet)
        LitCountPool pool = new LitCountPool(address(token), deployer);
        console.log("LitCountPool deployed at:", address(pool));

        // 3. Fund pool contract with reward tokens
        // Pool needs zkLTC to pay out staker rewards and jackpots
        // The contract uses staked amounts directly, so this is just a safety reserve
        uint256 reserveAmount = 10_000 ether; // 10,000 zkLTC reserve
        token.adminMint(address(pool), reserveAmount);
        console.log("Pool funded with:", reserveAmount / 1e18, "zkLTC");

        // 4. Log deployment summary
        console.log("=== LitCount Deployment Summary ===");
        console.log("Network: LitVM Testnet");
        console.log("Deployer:", deployer);
        console.log("zkLTC Token:", address(token));
        console.log("LitCount Pool:", address(pool));
        console.log("Treasury:", deployer);
        console.log("Stake Amount: 0.1 zkLTC");
        console.log("Pool Duration: 21 hours");
        console.log("Draw Window: 21 minutes");
        console.log("Min Users: 21");
        console.log("Jackpot Share: 70%");
        console.log("Staker Share: 20%");
        console.log("Protocol Fee: 10%");

        vm.stopBroadcast();
    }
}
