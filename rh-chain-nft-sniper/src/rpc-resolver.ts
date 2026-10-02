// RPC resolver with chain ID verification and health checks
// Source: adapted from solotop999/opensea-nft-public-mint

import { JsonRpcProvider } from "ethers";
import { ChainProfile, resolveChain } from "./chains";
import { parseRpcEndpoints, ParsedRpcEndpoint, maskRpc } from "./rpc-blast";

export interface RpcPlan {
  urls: string[];
  source: string;
  dropped: { url: string; chainId: number }[];
  failures: { url: string; message: string }[];
  verified: boolean;
}

export function privateRpcsFromEnv(chainKey: string): string[] {
  const envKey = `RPC_URL_${chainKey.toUpperCase()}`;
  const val = process.env[envKey];
  if (!val) return [];
  return val.split(",").map((s) => s.trim()).filter(Boolean);
}

export async function getLatestBlock(rpcUrl: string): Promise<number | null> {
  try {
    const provider = new JsonRpcProvider(rpcUrl);
    const block = await provider.getBlockNumber();
    return block;
  } catch {
    return null;
  }
}

export async function checkChainId(rpcUrl: string, expectedChainId: number): Promise<{ ok: boolean; chainId?: number; error?: string }> {
  try {
    const provider = new JsonRpcProvider(rpcUrl);
    const network = await provider.getNetwork();
    const actualChainId = Number(network.chainId);
    return { ok: actualChainId === expectedChainId, chainId: actualChainId };
  } catch (err: any) {
    return { ok: false, error: err.message };
  }
}

export async function planRpcs(
  candidateUrls: string[],
  expectedChainId: number
): Promise<RpcPlan> {
  const parsed = parseRpcEndpoints(candidateUrls.join(","));
  const dropped: { url: string; chainId: number }[] = [];
  const failures: { url: string; message: string }[] = [];
  const verifiedUrls: string[] = [];

  console.log(chalk.gray(` Checking ${parsed.length} RPC endpoint(s)...`));

  for (const ep of parsed) {
    const check = await checkChainId(ep.url, expectedChainId);
    if (!check.ok) {
      const wrongChain = check.chainId !== undefined ? check.chainId : "unknown";
      dropped.push({ url: ep.url, chainId: wrongChain as any });
      console.log(chalk.red(` ✗ ${maskRpc(ep.url)} chain ID ${wrongChain} (expected ${expectedChainId}) — dropped`));
      continue;
    }
    if (check.chainId !== undefined && check.chainId !== expectedChainId) {
      dropped.push({ url: ep.url, chainId: check.chainId });
      console.log(chalk.red(` ✗ ${maskRpc(ep.url)} chain ID ${check.chainId} (expected ${expectedChainId}) — dropped`));
      continue;
    }
    verifiedUrls.push(ep.url);
    console.log(chalk.green(` ✓ ${maskRpc(ep.url)}`));
  }

  // If no verified URLs, try to include failed ones with warning
  if (verifiedUrls.length === 0 && parsed.length > 0) {
    const first = parsed[0];
    const check = await checkChainId(first.url, expectedChainId);
    if (check.chainId !== undefined && check.chainId !== expectedChainId) {
      failures.push({ url: first.url, message: `Chain ID ${check.chainId} (expected ${expectedChainId})` });
      console.log(chalk.yellow(` ⚠ No endpoint with correct chain ID. First endpoint has chain ID ${check.chainId}.`));
    } else {
      failures.push({ url: first.url, message: check.error || "Unknown error" });
      console.log(chalk.yellow(` ⚠ Could not verify chain ID for any endpoint.`));
    }
  }

  return {
    urls: verifiedUrls.length > 0 ? verifiedUrls : parsed.map((p) => p.url),
    source: verifiedUrls.length > 0 ? "verified" : "unverified (fallback)",
    dropped,
    failures,
    verified: verifiedUrls.length > 0,
  };
}

export async function resolveRpcsForChain(
  chainKey: string,
  manualRpcs: string = ""
): Promise<{ urls: string[]; source: string }> {
  const chain = resolveChain(chainKey);
  if (!chain) throw new Error(`Unknown chain: ${chainKey}`);

  const envRpcs = privateRpcsFromEnv(chainKey);
  const manualRpcsArray = manualRpcs.split(",").map((s) => s.trim()).filter(Boolean);
  const allRpcs = [...manualRpcsArray, ...envRpcs];

  // If no RPCs provided, use default
  if (allRpcs.length === 0) {
    return { urls: [chain.rpcDefault], source: "default" };
  }

  const plan = await planRpcs(allRpcs, chain.chainId);
  return { urls: plan.urls, source: plan.source };
}

// Need chalk for logging
import chalk from "chalk";