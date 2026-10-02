"use client";

import { useReadContract } from "wagmi";
import { CONTRACTS } from "@/lib/config";
import { LITCOUNT_POOL_ABI } from "@/lib/abi";
import { formatEther } from "viem";
import { Trophy, X, Clock } from "lucide-react";

export function PoolHistory() {
  const { data: history } = useReadContract({
    address: CONTRACTS.LitCountPool as `0x${string}`,
    abi: LITCOUNT_POOL_ABI,
    functionName: "getPoolHistory",
    query: { refetchInterval: 10000 },
  });

  const rounds = (history as any[]) ?? [];

  if (rounds.length === 0) {
    return (
      <div className="card-glow p-6 text-center">
        <Clock size={32} className="mx-auto mb-3 text-gray-600" />
        <p className="text-gray-500 text-sm">No completed rounds yet</p>
        <p className="text-gray-600 text-xs mt-1">Be the first to participate!</p>
      </div>
    );
  }

  return (
    <div className="card-glow p-6 space-y-4" id="history">
      <h3 className="font-bold text-white">Round History</h3>
      <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
        {[...rounds].reverse().map((r: any, i: number) => (
          <RoundRow key={i} round={r} />
        ))}
      </div>
    </div>
  );
}

function RoundRow({ round }: { round: any }) {
  const held      = Boolean(round.drawHeld);
  const date      = new Date(Number(round.timestamp) * 1000);
  const jackpot   = parseFloat(formatEther(round.jackpot)).toFixed(2);
  const perStaker = parseFloat(formatEther(round.stakerRewardPerUser)).toFixed(4);
  const shortAddr = round.winner !== "0x0000000000000000000000000000000000000000"
    ? `${round.winner.slice(0, 6)}...${round.winner.slice(-4)}`
    : null;

  return (
    <div className="flex items-center gap-3 p-3 rounded-xl" style={{
      background: held ? "rgba(34,197,94,0.04)" : "rgba(255,255,255,0.02)",
      border: `1px solid ${held ? "rgba(34,197,94,0.12)" : "rgba(255,255,255,0.05)"}`,
    }}>
      <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
        style={{ background: held ? "rgba(34,197,94,0.12)" : "rgba(255,255,255,0.05)" }}>
        {held ? <Trophy size={14} style={{ color: "#22c55e" }} /> : <X size={14} className="text-gray-500" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-white text-sm font-medium">Round #{Number(round.poolId)}</span>
          {held ? (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e" }}>
              Draw held
            </span>
          ) : (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(245,158,11,0.1)", color: "#f59e0b" }}>
              No draw
            </span>
          )}
        </div>
        <p className="text-gray-500 text-xs truncate">
          {held
            ? `Winner: ${shortAddr} · Jackpot: ${jackpot} zkLTC · Stakers: +${perStaker}`
            : `${Number(round.totalParticipants)} users · Minimum not reached`}
        </p>
      </div>
      <span className="text-gray-600 text-xs shrink-0">
        {date.toLocaleDateString()}
      </span>
    </div>
  );
}
