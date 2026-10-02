"use client";

import { useEffect, useRef } from "react";
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { CONTRACTS, POOL_CONFIG } from "@/lib/config";
import { LITCOUNT_POOL_ABI } from "@/lib/abi";
import { usePoolData } from "./usePoolData";

/**
 * useAutoDraw — watches pool state and triggers draw automatically.
 *
 * Logic:
 *  - Pool phase: if timeLeft == 0 AND >= MIN_USERS → triggerDrawPhase()
 *  - Draw phase: if drawTimeLeft > 0 AND not executed → executeDraw()
 *  - Draw expired: if drawTimeLeft == 0 AND not executed → forceReset()
 *
 * Uses a `triggered` ref to prevent duplicate calls (frontend only).
 * For production, use the auto_draw.py cron script as backup.
 */
export function useAutoDraw() {
  const { address, isConnected } = useAccount();
  const { writeContract } = useWriteContract();

  const {
    timeLeft,
    inDrawPhase,
    drawTimeLeft,
    participantCount,
    isLoading,
  } = usePoolData();

  const triggerRef   = useRef(false);
  const executeRef   = useRef(false);
  const resetRef     = useRef(false);

  // ── Trigger Draw Phase ───────────────────────────────────────────
  useEffect(() => {
    if (!isConnected) return;
    if (isLoading)    return;
    if (triggerRef.current) return;

    const canTrigger =
      timeLeft === 0 &&
      participantCount >= POOL_CONFIG.MIN_USERS &&
      !inDrawPhase;

    if (canTrigger) {
      triggerRef.current = true;
      console.log("[useAutoDraw] ⏰ Triggering draw phase...");
      try {
        writeContract({
          address:    CONTRACTS.LitCountPool,
          abi:        LITCOUNT_POOL_ABI,
          functionName: "triggerDrawPhase",
        });
      } catch (e) {
        console.error("[useAutoDraw] triggerDrawPhase failed:", e);
        triggerRef.current = false; // retry on next block
      }
    }
  }, [timeLeft, participantCount, inDrawPhase, isConnected, isLoading, writeContract]);

  // ── Execute Draw ─────────────────────────────────────────────────
  useEffect(() => {
    if (!isConnected) return;
    if (isLoading)    return;
    if (executeRef.current) return;

    const canExecute =
      inDrawPhase &&
      drawTimeLeft > 0 &&
      participantCount >= POOL_CONFIG.MIN_USERS;

    if (canExecute) {
      executeRef.current = true;
      console.log("[useAutoDraw] 🎲 Executing draw...");
      try {
        writeContract({
          address:    CONTRACTS.LitCountPool,
          abi:        LITCOUNT_POOL_ABI,
          functionName: "executeDraw",
        });
      } catch (e) {
        console.error("[useAutoDraw] executeDraw failed:", e);
        executeRef.current = false;
      }
    }
  }, [inDrawPhase, drawTimeLeft, participantCount, isConnected, isLoading, writeContract]);

  // ── Force Reset (draw window expired without execution) ────────────
  useEffect(() => {
    if (!isConnected) return;
    if (isLoading)    return;
    if (resetRef.current) return;

    const canReset =
      inDrawPhase &&
      drawTimeLeft === 0 &&
      participantCount > 0; // pool has participants

    if (canReset) {
      resetRef.current = true;
      console.log("[useAutoDraw] ⚠️ Draw window expired — forceReset");
      try {
        writeContract({
          address:    CONTRACTS.LitCountPool,
          abi:        LITCOUNT_POOL_ABI,
          functionName: "forceReset",
        });
      } catch (e) {
        console.error("[useAutoDraw] forceReset failed:", e);
        resetRef.current = false;
      }
    }
  }, [inDrawPhase, drawTimeLeft, participantCount, isConnected, isLoading, writeContract]);

  return {
    triggerRef,
    executeRef,
    resetRef,
    canTrigger: timeLeft === 0 && participantCount >= POOL_CONFIG.MIN_USERS && !inDrawPhase,
    canExecute: inDrawPhase && drawTimeLeft > 0 && participantCount >= POOL_CONFIG.MIN_USERS,
    canReset:   inDrawPhase && drawTimeLeft === 0 && participantCount > 0,
  };
}