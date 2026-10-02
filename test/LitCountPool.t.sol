// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract LitCountPoolTest is Test {
    zkLTC        public token;
    LitCountPool public pool;

    address owner    = address(0xA);
    address treasury = address(0xB);

    address[] users;

    function setUp() public {
        vm.startPrank(owner);
        token = new zkLTC();
        pool  = new LitCountPool(address(token), treasury);
        token.mintForPool(address(pool), 10_000 ether);
        vm.stopPrank();

        // Create 25 test users and give them zkLTC
        for (uint256 i = 1; i <= 25; i++) {
            address u = address(uint160(i + 100));
            users.push(u);
            deal(address(token), u, 1 ether); // give 1 zkLTC each
        }
    }

    function test_JoinPool() public {
        address user = users[0];
        vm.startPrank(user);
        token.approve(address(pool), 0.1 ether);
        pool.joinPool();
        vm.stopPrank();

        assertTrue(pool.isUserInCurrentPool(user));
        (,, uint256 count,,,,) = pool.getCurrentRoundInfo();
        assertEq(count, 1);
    }

    function test_CannotJoinTwice() public {
        address user = users[0];
        vm.startPrank(user);
        token.approve(address(pool), 0.2 ether);
        pool.joinPool();
        vm.expectRevert("Pool: Already joined this round");
        pool.joinPool();
        vm.stopPrank();
    }

    function test_DrawSkippedIfLessThanMinUsers() public {
        // Only 5 users join (< 21 minimum)
        for (uint256 i = 0; i < 5; i++) {
            vm.startPrank(users[i]);
            token.approve(address(pool), 0.1 ether);
            pool.joinPool();
            vm.stopPrank();
        }

        // Fast forward 21 hours
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();

        // Execute draw — should skip (< 21 users)
        pool.executeDraw();

        // Pool should NOT be settled, same round
        (uint256 id,,,, bool inDraw,,) = pool.getCurrentRoundInfo();
        assertEq(id, 1); // still round 1
        assertFalse(inDraw);
    }

    function test_FullRoundWith21Users() public {
        // 21 users join
        for (uint256 i = 0; i < 21; i++) {
            vm.startPrank(users[i]);
            token.approve(address(pool), 0.1 ether);
            pool.joinPool();
            vm.stopPrank();
        }

        uint256 expectedPool = 21 * 0.1 ether; // 2.1 zkLTC

        // Fast forward 21 hours
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        pool.executeDraw();

        // Should have moved to round 2
        (uint256 id,,,,,,) = pool.getCurrentRoundInfo();
        assertEq(id, 2);

        // Check round 1 winner exists
        (address winner, uint256 reward) = pool.getRoundWinner(1);
        assertTrue(winner != address(0));
        assertEq(reward, (expectedPool * 70) / 100);
    }

    function test_StakerClaimReward() public {
        // 21 users join
        for (uint256 i = 0; i < 21; i++) {
            vm.startPrank(users[i]);
            token.approve(address(pool), 0.1 ether);
            pool.joinPool();
            vm.stopPrank();
        }

        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        pool.executeDraw();

        // Non-winner staker claims reward
        address staker = users[0]; // might not be winner
        (address winner,) = pool.getRoundWinner(1);

        if (staker != winner) {
            uint256 balBefore = token.balanceOf(staker);
            vm.prank(staker);
            pool.claimStakerReward(1);
            uint256 balAfter = token.balanceOf(staker);
            // Should receive stake back + share of 20%
            assertTrue(balAfter > balBefore);
        }
    }

    function test_EmergencyWithdrawWhenPaused() public {
        address user = users[0];
        vm.startPrank(user);
        token.approve(address(pool), 0.1 ether);
        pool.joinPool();
        vm.stopPrank();

        vm.prank(owner);
        pool.pause();

        uint256 balBefore = token.balanceOf(user);
        vm.prank(user);
        pool.emergencyWithdraw(1);
        uint256 balAfter = token.balanceOf(user);

        assertEq(balAfter - balBefore, 0.1 ether);
    }
}
