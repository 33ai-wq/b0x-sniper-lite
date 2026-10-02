"use client";

import { useReadContract, useReadContracts, useAccount } from "wagmi";
import { CONTRACTS, POOL_CONFIG } from "@/lib/config";
import { LITCOUNT_POOL_ABI, ZKLTC_ABI } from "@/lib/abi";
import { formatEther } from "viem";

export function usePoolData() {
  const { address } = useAccount();

  const poolContract = {
    address: CONTRACTS.LitCountPool as `0x${string}`,
    abi: LITCOUNT_POOL_ABI,
  };

  const tokenContract = {
    address: CONTRACTS.zkLTC as `0x${string}`,
    abi: ZKLTC_ABI,
  };

  const { data, isLoading, refetch } = useReadContracts({
    contracts: [
      { ...poolContract, functionName: "getPoolStatus" },
      { ...poolContract, functionName: "lastWinner" },
      { ...poolContract, functionName: "lastJackpot" },
      { ...poolContract, functionName: "getDrawPhaseTimeLeft" },
      ...(address
        ? [
            { ...poolContract, functionName: "hasJoined", args: [address] },
            { ...tokenContract, functionName: "balanceOf", args: [address] },
            {
              ...tokenContract,
              functionName: "allowance",
              args: [address, CONTRACTS.LitCountPool as `0x${string}`],
            },
            { ...tokenContract, functionName: "cooldownRemaining", args: [address] },
          ]
        : []),
    ],
    query: { refetchInterval: 5000 },
  });

  const status   = data?.[0]?.result as any;
  const winner   = data?.[1]?.result as string | undefined;
  const jackpot  = data?.[2]?.result as bigint | undefined;
  const drawLeft = data?.[3]?.result as bigint | undefined;
  const joined   = data?.[4]?.result as boolean | undefined;
  const balance  = data?.[5]?.result as bigint | undefined;
  const allowance = data?.[6]?.result as bigint | undefined;
  const faucetCooldown = data?.[7]?.result as bigint | undefined;

  const participantCount = status ? Number(status[1]) : 0;
  const totalStaked      = status ? Number(formatEther(status[2])) : 0;
  const timeLeft         = status ? Number(status[3]) : 0;
  const inDrawPhase      = status ? Boolean(status[4]) : false;
  const jackpotEst       = status ? parseFloat(formatEther(status[5])).toFixed(2) : "0";
  const stakerEst        = status ? parseFloat(formatEther(status[6])).toFixed(4) : "0";
  const poolId           = status ? Number(status[0]) : 1;

  const needsApproval =
    !allowance || allowance < POOL_CONFIG.STAKE_AMOUNT;
  const userBalance = balance ? parseFloat(formatEther(balance)).toFixed(2) : "0";
  const hasFaucetCooldown = faucetCooldown ? faucetCooldown > BigInt(0) : false;
  const faucetWait = faucetCooldown ? Number(faucetCooldown) : 0;

  const progress = Math.min(
    (participantCount / POOL_CONFIG.MIN_USERS) * 100,
    100
  );

  return {
    poolId,
    participantCount,
    totalStaked,
    timeLeft,
    inDrawPhase,
    jackpotEst,
    stakerEst,
    winner,
    jackpot: jackpot ? parseFloat(formatEther(jackpot)).toFixed(2) : "0",
    drawTimeLeft: drawLeft ? Number(drawLeft) : 0,
    hasJoined: joined ?? false,
    userBalance,
    needsApproval,
    hasFaucetCooldown,
    faucetWait,
    progress,
    isLoading,
    refetch,
  };
}
