"use client";

import { useState } from "react";
import { useAccount, useWriteContract, useReadContract } from "wagmi";
import { ConnectButton } from "@rainbow-me/rainbowkit";
import { usePoolData } from "@/hooks/usePoolData";
import { CONTRACTS, POOL_CONFIG } from "@/lib/config";
import { LITCOUNT_POOL_ABI, ZKLTC_ABI } from "@/lib/abi";
import { Zap, CheckCircle, Loader2, Gift, AlertTriangle } from "lucide-react";
import { parseEther, formatEther } from "viem";

type Step = "idle" | "approving" | "joining" | "done" | "error";

export function JoinCard() {
  const { address, isConnected } = useAccount();
  const { hasJoined, needsApproval, userBalance, hasFaucetCooldown, faucetWait, inDrawPhase, refetch } = usePoolData();
  const [step, setStep] = useState<Step>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const { writeContractAsync } = useWriteContract();

  const handleFaucet = async () => {
    try {
      setStep("approving");
      await writeContractAsync({
        address: CONTRACTS.zkLTC as `0x${string}`,
        abi: ZKLTC_ABI,
        functionName: "faucet",
      });
      // Poll balance until it increases (testnet faucet mints async — may take a few blocks)
      for (let i = 0; i < 6; i++) {
        await new Promise(r => setTimeout(r, 2000));
        await refetch();
        // Check if balance has changed from what we started with
        if (i === 5) {
          // Last attempt — one more refetch
          await refetch();
        }
      }
      setStep("idle");
    } catch (e: any) {
      setErrorMsg(e.message?.slice(0, 80) ?? "Faucet failed");
      setStep("error");
    }
  };

  const handleApprove = async () => {
    try {
      setStep("approving");
      await writeContractAsync({
        address: CONTRACTS.zkLTC as `0x${string}`,
        abi: ZKLTC_ABI,
        functionName: "approve",
        args: [CONTRACTS.LitCountPool as `0x${string}`, parseEther("999999")],
      });
      await refetch();
      setStep("idle");
    } catch (e: any) {
      setErrorMsg(e.message?.slice(0, 80) ?? "Approval failed");
      setStep("error");
    }
  };

  const handleJoin = async () => {
    try {
      setStep("joining");
      await writeContractAsync({
        address: CONTRACTS.LitCountPool as `0x${string}`,
        abi: LITCOUNT_POOL_ABI,
        functionName: "joinPool",
      });
      await refetch();
      setStep("done");
    } catch (e: any) {
      setErrorMsg(e.message?.slice(0, 80) ?? "Join failed");
      setStep("error");
    }
  };

  const formatWait = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    return `${h}h ${m}m`;
  };

  // NOT CONNECTED
  if (!isConnected) {
    return (
      <div className="card-glow p-8 flex flex-col items-center gap-5 text-center">
        <div style={{
          width: 64, height: 64, borderRadius: 18,
          background: "linear-gradient(135deg, #0f2d1a, #0a1a0c)",
          border: "1.5px solid rgba(34,197,94,0.4)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 0 20px rgba(34,197,94,0.15)",
        }}>
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
            <text x="50%" y="54%" dominantBaseline="middle" textAnchor="middle"
              fontFamily="system-ui" fontWeight="900" fontSize="16" fill="#22c55e">LC</text>
          </svg>
        </div>
        <div>
          <h3 className="font-bold text-white text-lg">Connect Wallet</h3>
          <p className="text-gray-400 text-sm mt-1">Connect to join the LitCount pool</p>
        </div>
        {/* Force English button */}
        <ConnectButton.Custom>
          {({ openConnectModal }) => (
            <button onClick={openConnectModal}
              className="px-8 py-3 rounded-xl font-bold text-sm w-full"
              style={{ background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#000" }}>
              Connect Wallet
            </button>
          )}
        </ConnectButton.Custom>
      </div>
    );
  }

  if (hasJoined) {
    return (
      <div className="card-active p-6 flex flex-col items-center gap-4 text-center">
        <CheckCircle size={48} style={{ color: "#22c55e" }} />
        <div>
          <h3 className="font-bold text-white text-lg">You&apos;re In! 🎉</h3>
          <p className="text-gray-400 text-sm mt-1">Staked 1 $zkLTC · Waiting for draw</p>
        </div>
        <div className="w-full rounded-xl p-4 text-sm"
          style={{ background: "rgba(34,197,94,0.05)", border: "1px solid rgba(34,197,94,0.2)" }}>
          <p style={{ color: "#22c55e" }}>Your position is secure. You will:</p>
          <ul className="text-gray-300 mt-2 space-y-1 text-left list-disc list-inside">
            <li>Automatically receive 20% staker share</li>
            <li>Have a chance to win the 70% jackpot</li>
          </ul>
        </div>
      </div>
    );
  }

  if (inDrawPhase) {
    return (
      <div className="card-glow p-8 flex flex-col items-center gap-3 text-center">
        <div className="text-4xl">🎲</div>
        <h3 className="font-bold text-white">Pool Closed for Draw</h3>
        <p className="text-gray-400 text-sm">Pool reopens after the draw phase. Come back soon!</p>
      </div>
    );
  }

  return (
    <div className="card-glow p-6 space-y-5">
      <div>
        <h3 className="font-bold text-white text-lg">Join Pool</h3>
        <p className="text-gray-400 text-sm mt-1">Stake 1 $zkLTC · Win or earn rewards</p>
      </div>
      <div className="flex justify-between items-center text-sm px-4 py-3 rounded-xl"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
        <span className="text-gray-400">Your balance</span>
        <span className="text-white font-medium">{userBalance} $zkLTC</span>
      </div>
      <button onClick={handleFaucet}
        disabled={hasFaucetCooldown || step !== "idle"}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium"
        style={{
          background: hasFaucetCooldown ? "rgba(255,255,255,0.03)" : "rgba(34,197,94,0.08)",
          border: `1px solid ${hasFaucetCooldown ? "rgba(255,255,255,0.06)" : "rgba(34,197,94,0.2)"}`,
          color: hasFaucetCooldown ? "#6b7280" : "#22c55e",
          cursor: hasFaucetCooldown ? "not-allowed" : "pointer",
        }}>
        <Gift size={14} />
        {hasFaucetCooldown ? `Faucet available in ${formatWait(faucetWait)}` : "Claim 10 $zkLTC from Faucet"}
      </button>
      <div className="rounded-xl px-4 py-2.5 text-xs text-amber-400"
        style={{ background: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.15)" }}>
        💡 Tip: Need testnet $zkLTC? Get it from the{" "}
        <a href="https://faucet.caldera.xyz/" target="_blank" rel="noopener noreferrer"
          className="underline font-medium hover:text-amber-300">Caldera LitVM Faucet</a>
        {" "}first, then claim from the in-app faucet.
      </div>
      <div className="flex items-center justify-between px-4 py-3 rounded-xl"
        style={{ background: "rgba(34,197,94,0.05)", border: "1px solid rgba(34,197,94,0.15)" }}>
        <span className="text-gray-300 text-sm">Stake amount</span>
        <span className="font-bold" style={{ color: "#22c55e" }}>1 $zkLTC</span>
      </div>
      <div className="rounded-xl p-4 space-y-2 text-sm"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}>
        <p className="text-gray-500 text-xs uppercase tracking-widest">Expected outcome</p>
        <div className="flex justify-between">
          <span className="text-gray-400">🥇 Win jackpot (lucky draw)</span>
          <span className="text-white font-medium">70% of pool</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">👥 Base reward (everyone)</span>
          <span className="text-white font-medium">20% ÷ participants</span>
        </div>
      </div>
      {step === "error" && (
        <div className="flex items-start gap-2 rounded-xl px-4 py-3 text-sm"
          style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#f87171" }}>
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}
      {step === "done" ? (
        <button className="w-full py-4 rounded-xl font-bold text-black flex items-center justify-center gap-2"
          style={{ background: "linear-gradient(135deg, #22c55e, #86efac)" }}>
          <CheckCircle size={18} /> Joined Successfully!
        </button>
      ) : needsApproval ? (
        <button onClick={handleApprove} disabled={step === "approving"}
          className="w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2"
          style={{ background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#000", opacity: step === "approving" ? 0.7 : 1 }}>
          {step === "approving" ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
          {step === "approving" ? "Approving..." : "Approve $zkLTC"}
        </button>
      ) : (
        <button onClick={handleJoin} disabled={step === "joining"}
          className="w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2"
          style={{ background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#000", opacity: step === "joining" ? 0.7 : 1 }}>
          {step === "joining" ? <Loader2 size={18} className="animate-spin" /> : <Zap size={18} />}
          {step === "joining" ? "Staking..." : "Stake & Join Pool"}
        </button>
      )}
    </div>
  );
}
