// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/zkLTC.sol";
import "../src/LitCountPool.sol";

contract LitCountPoolTest is Test {
    zkLTC        public token;
    LitCountPool public pool;

    address public deployer = address(0x1);
    address public treasury = address(0x2);
    address[] public users;

    uint256 constant STAKE = 0.1 ether;
    uint256 constant MIN   = 21;

    function setUp() public {
        // Warp ke waktu realistis dulu
        vm.warp(1_700_000_000);

        vm.startPrank(deployer);
        token = new zkLTC();
        pool  = new LitCountPool(address(token), treasury);
        vm.stopPrank();

        for (uint256 i = 0; i < 30; i++) {
            address u = address(uint160(100 + i));
            users.push(u);
            vm.prank(deployer);
            token.adminMint(u, 1 ether);
            vm.prank(u);
            token.approve(address(pool), type(uint256).max);
        }
    }

    function test_JoinPool() public {
        vm.prank(users[0]);
        pool.joinPool();
        assertEq(pool.getParticipantCount(), 1);
        assertTrue(pool.hasJoined(users[0]));
    }

    function test_CannotJoinTwice() public {
        vm.prank(users[0]);
        pool.joinPool();
        vm.prank(users[0]);
        vm.expectRevert("LitCount: Already in this pool");
        pool.joinPool();
    }

    function test_CannotJoinDuringDraw() public {
        _fillUsers(MIN);
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        vm.prank(users[25]);
        vm.expectRevert("LitCount: Draw phase active, pool closed");
        pool.joinPool();
    }

    function test_TriggerDrawPhase() public {
        _fillUsers(5);
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        assertTrue(pool.isDrawPhase());
    }

    function test_DrawSkippedBelowMinimum() public {
        _fillUsers(10);
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        pool.executeDraw();
        assertFalse(pool.isDrawPhase());
        assertEq(pool.currentPoolId(), 2);
        LitCountPool.PoolResult[] memory history = pool.getPoolHistory();
        assertEq(history.length, 1);
        assertFalse(history[0].drawHeld);
    }

    function test_DrawExecutedWithMinimum() public {
        _fillUsers(MIN);
        uint256 totalPool = MIN * STAKE;
        vm.warp(block.timestamp + 21 hours + 1);
        pool.triggerDrawPhase();
        pool.executeDraw();
        assertFalse(pool.isDrawPhase());
        assertEq(pool.currentPoolId(), 2);
        LitCountPool.PoolResult[] memory history = pool.getPoolHistory();
        assertEq(history.length, 1);
        assertTrue(history[0].drawHeld);
        assertEq(history[0].totalParticipants, MIN);
        uint256 expectedJackpot = (totalPool * 7000) / 10000;
        assertEq(history[0].jackpot, expectedJackpot);
        uint256 expectedFee = (totalPool * 1000) / 10000;
        assertEq(token.balanceOf(treasury), expectedFee);
    }

    function test_GetPoolStatus() public {
        _fillUsers(5);
        (
            uint256 poolId,
            uint256 count,
            uint256 totalStaked,
            uint256 timeLeft,
            bool inDraw,
            uint256 jackpotEst,
            uint256 stakerEst
        ) = pool.getPoolStatus();
        assertEq(poolId, 1);
        assertEq(count, 5);
        assertEq(totalStaked, 5 * STAKE);
        assertGt(timeLeft, 0);
        assertFalse(inDraw);
        assertEq(jackpotEst, (5 * STAKE * 7000) / 10000);
        assertGt(stakerEst, 0);
    }

    function test_Faucet() public {
        address freshUser = makeAddr("freshUser");
        vm.prank(freshUser);
        token.faucet();
        assertEq(token.balanceOf(freshUser), 10 ether);
    }

    function test_FaucetCooldown() public {
        address freshUser = makeAddr("freshUser2");
        vm.prank(freshUser);
        token.faucet();
        assertEq(token.balanceOf(freshUser), 10 ether);
        vm.prank(freshUser);
        vm.expectRevert("zkLTC: Faucet cooldown active");
        token.faucet();
    }

    function _fillUsers(uint256 count) internal {
        for (uint256 i = 0; i < count; i++) {
            vm.prank(users[i]);
            pool.joinPool();
        }
    }
}
