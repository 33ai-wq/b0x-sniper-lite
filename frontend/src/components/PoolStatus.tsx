"use client";

import { usePoolData } from "@/hooks/usePoolData";
import { useCountdown } from "@/hooks/useCountdown";
import { Users, Clock, Trophy, TrendingUp, AlertCircle, Zap } from "lucide-react";
import { POOL_CONFIG } from "@/lib/config";
import { useAccount, useWriteContract } from "wagmi";
import { LITCOUNT_POOL_ABI } from "@/lib/abi";
import { CONTRACTS } from "@/lib/config";
import { useState } from "react";

export function PoolStatus() {
  const {
    poolId, participantCount, totalStaked, timeLeft,
    inDrawPhase, jackpotEst, stakerEst, progress,
    drawTimeLeft, isLoading,
  } = usePoolData();

  const timer = useCountdown(inDrawPhase ? drawTimeLeft : timeLeft);
  const [triggering, setTriggering] = useState(false);
  const [triggered, setTriggered] = useState(false);
  const { writeContract } = useWriteContract();

  const canTrigger = !isLoading && timeLeft === 0 && participantCount >= POOL_CONFIG.MIN_USERS && !inDrawPhase;
  const canExecute = !isLoading && inDrawPhase && drawTimeLeft > 0 && participantCount >= POOL_CONFIG.MIN_USERS;
  const canReset   = !isLoading && inDrawPhase && drawTimeLeft === 0 && participantCount > 0;

  const handleTriggerDraw = async () => {
    setTriggering(true);
    try {
      writeContract({
        address:    CONTRACTS.LitCountPool,
        abi:        LITCOUNT_POOL_ABI,
        functionName: "triggerDrawPhase",
      });
      setTriggered(true);
    } catch (e) {
      console.error("triggerDrawPhase failed:", e);
    } finally {
      setTriggering(false);
    }
  };

  const handleExecuteDraw = async () => {
    setTriggering(true);
    try {
      writeContract({
        address:    CONTRACTS.LitCountPool,
        abi:        LITCOUNT_POOL_ABI,
        functionName: "executeDraw",
      });
      setTriggered(true);
    } catch (e) {
      console.error("executeDraw failed:", e);
    } finally {
      setTriggering(false);
    }
  };

  const handleForceReset = async () => {
    setTriggering(true);
    try {
      writeContract({
        address:    CONTRACTS.LitCountPool,
        abi:        LITCOUNT_POOL_ABI,
        functionName: "forceReset",
      });
      setTriggered(true);
    } catch (e) {
      console.error("forceReset failed:", e);
    } finally {
      setTriggering(false);
    }
  };

  // Pool expired but not enough users
  const poolExpiredNoDraw =
    !isLoading && timeLeft === 0 && participantCount < POOL_CONFIG.MIN_USERS && !inDrawPhase;

  return (
    <div className="card-active p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              background: inDrawPhase ? "#f59e0b" : "#22c55e",
              boxShadow: inDrawPhase ? "0 0 8px #f59e0b" : "0 0 8px #22c55e",
            }}
          />
          <span className="text-sm font-medium" style={{ color: inDrawPhase ? "#f59e0b" : "#22c55e" }}>
            {inDrawPhase ? "🎲 Draw Phase" : "⚡ Pool Active"} — Round #{poolId}
          </span>
        </div>
        <span className="text-xs text-gray-500">LitVM Testnet</span>
      </div>

      {/* Timer */}
      <div className="text-center py-4">
        <p className="text-xs text-gray-500 mb-2 uppercase tracking-widest">
          {inDrawPhase ? "Draw closes in" : "Pool closes in"}
        </p>
        <div className="font-mono-timer text-5xl font-bold text-white tracking-wider">
          {timer.formatted}
        </div>
        {inDrawPhase && (
          <p className="text-xs mt-2" style={{ color: "#f59e0b" }}>
            🎰 Winner being selected...
          </p>
        )}
      </div>

      {/* Auto-draw action panel */}
      {(canTrigger || canExecute || canReset || poolExpiredNoDraw) && (
        <div className="rounded-xl p-4 space-y-2" style={{
          background: "rgba(34,197,94,0.05)",
          border: "1px solid rgba(34,197,94,0.2)"
        }}>
          {canTrigger && (
            <>
              <div className="flex items-center gap-2 text-sm" style={{ color: "#22c55e" }}>
                <Zap size={16} />
                <span className="font-medium">Pool Ready for Draw!</span>
              </div>
              <p className="text-xs text-gray-400">
                {participantCount} participants — draw can now be triggered.
                Auto-draw will activate shortly, or trigger manually:
              </p>
              <button
                onClick={handleTriggerDraw}
                disabled={triggering || triggered}
                className="w-full py-2.5 rounded-lg font-bold text-sm transition-all"
                style={{
                  background: triggered ? "rgba(34,197,94,0.3)" : "linear-gradient(135deg, #22c55e, #16a34a)",
                  color: "#000",
                  opacity: triggering ? 0.6 : 1,
                  cursor: triggering || triggered ? "default" : "pointer",
                }}
              >
                {triggering ? "⏳ Triggering..." : triggered ? "✅ Draw Triggered!" : "🎲 Trigger Draw Phase"}
              </button>
            </>
          )}

          {canExecute && (
            <>
              <div className="flex items-center gap-2 text-sm" style={{ color: "#f59e0b" }}>
                <Zap size={16} />
                <span className="font-medium">Draw Window Open!</span>
              </div>
              <p className="text-xs text-gray-400">
                Executing draw with {participantCount} participants — winner will be selected on-chain.
              </p>
              <button
                onClick={handleExecuteDraw}
                disabled={triggering || triggered}
                className="w-full py-2.5 rounded-lg font-bold text-sm"
                style={{
                  background: triggered ? "rgba(245,158,11,0.3)" : "linear-gradient(135deg, #f59e0b, #d97706)",
                  color: "#000",
                  opacity: triggering ? 0.6 : 1,
                }}
              >
                {triggering ? "⏳ Executing..." : triggered ? "✅ Draw Executed!" : "🏆 Execute Draw Now"}
              </button>
            </>
          )}

          {canReset && (
            <>
              <div className="flex items-center gap-2 text-sm" style={{ color: "#ef4444" }}>
                <AlertCircle size={16} />
                <span className="font-medium">Draw Window Expired!</span>
              </div>
              <p className="text-xs text-gray-400">
                Draw not executed in time — force reset needed.
              </p>
              <button
                onClick={handleForceReset}
                disabled={triggering || triggered}
                className="w-full py-2.5 rounded-lg font-bold text-sm"
                style={{
                  background: "linear-gradient(135deg, #ef4444, #dc2626)",
                  color: "#fff",
                }}
              >
                {triggering ? "⏳ Resetting..." : "🔄 Force Reset Pool"}
              </button>
            </>
          )}

          {poolExpiredNoDraw && (
            <>
              <div className="flex items-center gap-2 text-sm text-amber-400">
                <AlertCircle size={16} />
                <span className="font-medium">Pool Timer Expired</span>
              </div>
              <p className="text-xs text-gray-400">
                Need {POOL_CONFIG.MIN_USERS - participantCount} more users to reach minimum draw threshold.
                Timer will auto-reset — pool stays open.
              </p>
            </>
          )}
        </div>
      )}

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-2">
          <span>{participantCount} users joined</span>
          <span>Min: {POOL_CONFIG.MIN_USERS} users</span>
        </div>
        <div className="w-full h-2 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
          <div
            className="h-2 rounded-full transition-all duration-500"
            style={{
              width: `${progress}%`,
              background: progress >= 100
                ? "linear-gradient(90deg, #22c55e, #86efac)"
                : "linear-gradient(90deg, #16a34a, #22c55e)",
              boxShadow: progress >= 100 ? "0 0 12px rgba(34,197,94,0.5)" : "none",
            }}
          />
        </div>
        {participantCount < POOL_CONFIG.MIN_USERS && (
          <div className="flex items-center gap-1 mt-2 text-xs text-amber-400">
            <AlertCircle size={12} />
            <span>Need {POOL_CONFIG.MIN_USERS - participantCount} more users for draw</span>
          </div>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard icon={<Users size={16} />} label="Participants" value={String(participantCount)} />
        <StatCard icon={<TrendingUp size={16} />} label="Total Staked" value={`${totalStaked.toFixed(1)} zkLTC`} />
        <StatCard icon={<Trophy size={16} />} label="🥇 Jackpot" value={`${jackpotEst} zkLTC`} highlight />
        <StatCard icon={<Clock size={16} />} label="👥 Your Share" value={`${stakerEst} zkLTC`} />
      </div>

      {/* Reward split visualization */}
      <div className="rounded-xl p-4 space-y-2" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
        <p className="text-xs text-gray-500 uppercase tracking-widest mb-3">Reward Distribution</p>
        <RewardBar label="🥇 Lucky winner" pct={70} color="#22c55e" />
        <RewardBar label="👥 All stakers" pct={20} color="#3b82f6" />
        <RewardBar label="🏦 Protocol"    pct={10} color="#6b7280" />
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, highlight }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-xl p-3" style={{
      background: highlight ? "rgba(34,197,94,0.05)" : "rgba(255,255,255,0.03)",
      border: `1px solid ${highlight ? "rgba(34,197,94,0.2)" : "rgba(255,255,255,0.06)"}`,
    }}>
      <div className="flex items-center gap-1.5 mb-1" style={{ color: highlight ? "#22c55e" : "#6b7280" }}>
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <p className="font-bold text-white text-sm">{value}</p>
    </div>
  );
}

function RewardBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-32">{label}</span>
      <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-medium text-white w-8 text-right">{pct}%</span>
    </div>
  );
}