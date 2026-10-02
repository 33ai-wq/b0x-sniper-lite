// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract DeployLitCount is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer    = vm.addr(deployerKey);
        address treasury    = vm.envOr("TREASURY_ADDRESS", deployer); // fallback to deployer

        console.log("=== LitCount Deployment ===");
        console.log("Deployer :", deployer);
        console.log("Treasury :", treasury);
        console.log("Network  : LitVM Testnet");

        vm.startBroadcast(deployerKey);

        // 1. Deploy zkLTC token
        zkLTC token = new zkLTC();
        console.log("zkLTC deployed at     :", address(token));

        // 2. Deploy LitCountPool
        LitCountPool pool = new LitCountPool(address(token), treasury);
        console.log("LitCountPool deployed :", address(pool));

        // 3. Seed pool with reward tokens (for 20% staker shares payout)
        //    Transfer 1000 zkLTC to pool for initial liquidity
        token.mintForPool(address(pool), 1_000 ether);
        console.log("Seeded pool with 1000 zkLTC");

        vm.stopBroadcast();

        console.log("\n=== SAVE THESE ADDRESSES ===");
        console.log("NEXT_PUBLIC_ZKLTC_ADDRESS=", address(token));
        console.log("NEXT_PUBLIC_POOL_ADDRESS=",  address(pool));
    }
}
