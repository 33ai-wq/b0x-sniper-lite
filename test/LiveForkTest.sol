// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract LiveForkTest is Test {
    zkLTC        public token;
    LitCountPool public pool;

    address owner    = address(0xFd283b0e775eb2A7a2D8b99D4070CFb0c46cD328); // deployer from .env
    address treasury = address(0xF34900299e6f526c4e1b5967b87A880fB880d2B7);

    address[21] public users;
    uint256 public constant USER_COUNT = 21;
    uint256 public constant STAKE_AMOUNT = 0.1 ether;

    function setUp() public {
        // Attach to already deployed contracts at known addresses
        token = zkLTC(0x40a7a0C8560492626D9bCA97C1eAf284b953098b);
        pool  = LitCountPool(0x437F3401e3C45fe385873D3Cf5651D403ECADeE4);

        // Create 21 test accounts (deterministic)
        for (uint256 i = 0; i < USER_COUNT; i++) {
            users[i] = address(uint160(i + 1)); // 0x0000000000000000000000000000000000000001 etc.
        }
    }

    function test_LiveForkDistribution() public {
        // Record initial balances
        uint256[21] memory initBalances;
        for (uint256 i = 0; i < USER_COUNT; i++) {
            initBalances[i] = token.balanceOf(users[i]);
        }

        // Each user claims from faucet to get tokens
        for (uint256 i = 0; i < USER_COUNT; i++) {
            vm.startPrank(users[i]);
            token.faucet(); // claims 10 zkLTC
            vm.stopPrank();
        }

        // Verify each user has at least 10 zkLTC (from faucet)
        for (uint256 i = 0; i < USER_COUNT; i++) {
            assertGe(token.balanceOf(users[i]), 10 ether, "User should have faucet amount");
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
            uint256 expectedIncrease = STAKE_AMOUNT + expectedStakerEach; // stake back + share
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
