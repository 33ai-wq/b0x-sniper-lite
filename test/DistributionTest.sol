// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract DistributionTest is Test {
    zkLTC        public token;
    LitCountPool public pool;

    address owner    = address(0xA);
    address treasury = address(0xB);

    address[21] public users;
    uint256 public constant USER_COUNT = 21;
    uint256 public constant STAKE_AMOUNT = 0.1 ether;

    function setUp() public {
        vm.startPrank(owner);
        token = new zkLTC();
        pool  = new LitCountPool(address(token), treasury);
        // Mint enough tokens for pool and users
        token.mintForPool(address(pool), USER_COUNT * STAKE_AMOUNT * 2); // extra for safety
        // Give each user some tokens
        for (uint256 i = 0; i < USER_COUNT; i++) {
            address u = address(uint160(i + 100));
            users[i] = u;
            deal(address(token), u, STAKE_AMOUNT * 2); // give 2x stake amount
        }
        vm.stopPrank();
    }

    function test_DistributionWith21Users() public {
        // Record initial balances
        uint256[21] memory initBalances;
        for (uint256 i = 0; i < USER_COUNT; i++) {
            initBalances[i] = token.balanceOf(users[i]);
        }

        // All users join the pool
        for (uint256 i = 0; i < USER_COUNT; i++) {
            vm.startPrank(users[i]);
            token.approve(address(pool), STAKE_AMOUNT);
            pool.joinPool();
            vm.stopPrank();
        }

        // Verify pool has 21 participants
        (uint256 roundId, , uint256 userCountBefore,,,,) = pool.getCurrentRoundInfo();
        assertEq(userCountBefore, USER_COUNT, "Should have 21 users");

        // Calculate expected total pool
        uint256 expectedTotalPool = USER_COUNT * STAKE_AMOUNT;

        // Fast forward time >21 hours
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();

        // Execute draw
        vm.startPrank(owner); // anyone can call
        pool.executeDraw();
        vm.stopPrank();

        // After draw, pool should have reset (new round)
        (uint256 newPoolId,,,,,,) = pool.getCurrentRoundInfo();
        assertEq(newPoolId, roundId + 1, "Should have moved to next round");

        // Get round results for the round that just ended (roundId)
        (address winner, uint256 winnerReward) = pool.getRoundWinner(roundId);
        assertTrue(winner != address(0), "Winner should be set");

        // Verify winner is among participants
        bool winnerIsParticipant = false;
        for (uint256 i = 0; i < USER_COUNT; i++) {
            if (users[i] == winner) {
                winnerIsParticipant = true;
                break;
            }
        }
        assertTrue(winnerIsParticipant, "Winner must be a participant");

        // Calculate expected rewards
        uint256 expectedJackpot = (expectedTotalPool * 70) / 100; // 70%
        uint256 expectedStakerTotal = (expectedTotalPool * 20) / 100; // 20%
        uint256 expectedProtocolFee = (expectedTotalPool * 10) / 100; // 10%
        uint256 expectedStakerEach = expectedStakerTotal / USER_COUNT;

        // Check jackpot amount
        assertEq(winnerReward, expectedJackpot, "Jackpot amount incorrect");

        // Now each user claims their staker reward (stake back + share)
        for (uint256 i = 0; i < USER_COUNT; i++) {
            vm.startPrank(users[i]);
            pool.claimStakerReward(roundId);
            vm.stopPrank();
        }

        // Verify final balances
        for (uint256 i = 0; i < USER_COUNT; i++) {
            address user = users[i];
            uint256 finalBalance = token.balanceOf(user);
            uint256 initBalance = initBalances[i];
            uint256 expectedIncrease = expectedStakerEach; // Only the reward portion, stake was already in wallet after join
            if (user == winner) {
                expectedIncrease += expectedJackpot; // winner also gets jackpot
            }
            assertGe(finalBalance - initBalance, expectedIncrease, "User balance increase too low");
        }

        // Verify protocol treasury received fee
        uint256 treasuryBalance = token.balanceOf(treasury);
        assertEq(treasuryBalance, expectedProtocolFee, "Protocol fee incorrect");
    }
}
