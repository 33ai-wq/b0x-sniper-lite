import { createPublicClient, createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { LITVM_TESTNET } from "@/lib/config";
import { LITCOUNT_POOL_ABI } from "@/lib/abi";

const POOL_ADDRESS = "0x7903e5B54913Fd67dA541F478b17c8B342C82b83" as `0x${string}`;
const RPC_URL      = process.env.LITVM_RPC_URL || "https://liteforge.rpc.caldera.xyz/http";
const CHAIN        = LITVM_TESTNET as any;

export async function GET(request: Request) {
  // auth guard (Vercel cron sends bearer if CRON_SECRET is set in env)
  const auth = request.headers.get("authorization");
  if (process.env.CRON_SECRET && auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    if (!process.env.DEPLOYER_PRIVATE_KEY) {
      return Response.json({ error: "DEPLOYER_PRIVATE_KEY not set" }, { status: 500 });
    }
    const account = privateKeyToAccount(process.env.DEPLOYER_PRIVATE_KEY as `0x${string}`);

    const publicClient = createPublicClient({ chain: CHAIN, transport: http(RPC_URL) });
    const walletClient = createWalletClient({ account, chain: CHAIN, transport: http(RPC_URL) });

    // Single source of truth: getPoolStatus returns
    // [poolId, participantCount, totalStaked, timeLeft, inDrawPhase, jackpotEstimate, stakerRewardEstimate]
    const status = (await publicClient.readContract({
      address: POOL_ADDRESS,
      abi: LITCOUNT_POOL_ABI,
      functionName: "getPoolStatus",
    })) as readonly [bigint, bigint, bigint, bigint, boolean, bigint, bigint];

    const poolId = Number(status[0]);
    const count  = Number(status[1]);
    const timeLeft = Number(status[3]);
    const inDraw   = Boolean(status[4]);

    console.log(`[cron] pool=${poolId} timeLeft=${timeLeft}s inDraw=${inDraw} count=${count}`);

    // Phase 2/3: After 21h open window, trigger draw phase
    if (!inDraw && timeLeft === 0 && count > 0) {
      const hash = await walletClient.writeContract({
        address: POOL_ADDRESS,
        abi: LITCOUNT_POOL_ABI,
        functionName: "triggerDrawPhase",
        chain: CHAIN,
        account,
      });
      return Response.json({ action: "triggerDrawPhase", poolId, participants: count, hash });
    }

    if (inDraw) {
      const drawLeft = (await publicClient.readContract({
        address: POOL_ADDRESS,
        abi: LITCOUNT_POOL_ABI,
        functionName: "getDrawPhaseTimeLeft",
      })) as bigint;

      // Window open → executeDraw (winner pick or skip-if-low-count)
      if (Number(drawLeft) > 0) {
        const hash = await walletClient.writeContract({
          address: POOL_ADDRESS,
          abi: LITCOUNT_POOL_ABI,
          functionName: "executeDraw",
          chain: CHAIN,
          account,
        });
        return Response.json({ action: "executeDraw", poolId, participants: count, hash });
      }

      // Window consumed but draw never fired → admin forceReset clears stuck state
      const hash = await walletClient.writeContract({
        address: POOL_ADDRESS,
        abi: LITCOUNT_POOL_ABI,
        functionName: "forceReset",
        chain: CHAIN,
        account,
      });
      return Response.json({ action: "forceReset", poolId, participants: count, hash });
    }

    return Response.json({
      action: "none",
      message: "Pool still running",
      poolId,
      timeLeft,
      participants: count,
    });
  } catch (error: any) {
    console.error("Cron error:", error);
    return Response.json(
      { error: error?.shortMessage || error?.message || String(error) },
      { status: 500 },
    );
  }
}
