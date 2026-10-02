// Public-mint execution with no OpenSea in the loop.
// Source: adapted from solotop999/opensea-nft-public-mint

import chalk from "chalk";
import { performance } from "perf_hooks";
import { JsonRpcProvider, Wallet, formatEther } from "ethers";
import { LocalMintPlan } from "./seadrop-public";

export interface LocalSnipeOpts {
  nftContract: string;
  quantity: number;
  walletKeys: string[];
  rpcUrls: string[];
  maxFeePerGas: bigint;
  maxPriorityFee: bigint;
  gasLimit: number;
  targetStart: Date | null;
  plan: LocalMintPlan;
  dryRun: boolean;
}

export async function localPublicSnipe(opts: LocalSnipeOpts): Promise<void> {
  const {
    nftContract,
    quantity,
    walletKeys,
    rpcUrls,
    maxFeePerGas,
    maxPriorityFee,
    gasLimit,
    targetStart,
    plan,
    dryRun,
  } = opts;

  const provider = new JsonRpcProvider(rpcUrls[0]);
  const wallets = walletKeys.map((k) => new Wallet(k, provider));

  console.log(chalk.bold.magenta("\n── PUBLIC MINT CỤC BỘ (không dùng OpenSea) ──"));
  console.log(chalk.gray(` SeaDrop: ${plan.to}`));
  console.log(chalk.gray(` NFT: ${nftContract}`));
  console.log(chalk.gray(` Người nhận phí: ${plan.feeRecipient}`));
  console.log(
    chalk.gray(
      ` Giá: ${formatEther(plan.drop.mintPrice)} × ${quantity} = ${formatEther(plan.value)} mỗi ví`
    )
  );
  console.log(chalk.gray(` Calldata: ${(plan.data.length - 2) / 2} byte (giống nhau cho mọi ví)`));
  console.log(chalk.gray(` Gas limit: ${gasLimit} | Max fee: ${Number(maxFeePerGas / 1000000000n)} gwei | Priority: ${Number(maxPriorityFee / 1000000000n)} gwei`));

  if (dryRun) {
    console.log(chalk.bold.yellow("\n ⚠ DRY-RUN MODE: Simulating only, no transactions will be broadcast"));
  }

  // ── Warm sockets and pre-fetch everything the signature depends on ──
  await warmConnections(rpcUrls);
  const [nonces, network] = await Promise.all([
    Promise.all(wallets.map((w) => provider.getTransactionCount(w.address, "pending"))),
    provider.getNetwork(),
  ]);
  const chainId = network.chainId;
  console.log(chalk.gray(` Nonces: [${nonces.join(", ")}] | chainId: ${chainId}`));

  // Verify chain ID matches expected (4663 for Robinhood Chain)
  if (chainId !== 4663n) {
    console.log(chalk.red(` ✗ Chain ID mismatch! Expected 4663 (Robinhood Chain), got ${chainId}`));
    throw new Error(`Chain ID verification failed: expected 4663, got ${chainId}`);
  }
  console.log(chalk.green(` ✓ Chain ID verified: ${chainId} (Robinhood Chain)`));

  // ── Sign everything now, well before the stage opens ──
  const signStart = performance.now();
  const prepared: { idx: number; address: string; signedTx: string }[] = [];

  for (let i = 0; i < wallets.length; i++) {
    const rawTx = await wallets[i].signTransaction({
      to: plan.to,
      data: plan.data,
      value: plan.value,
      nonce: nonces[i],
      maxFeePerGas,
      maxPriorityFeePerGas: maxPriorityFee,
      gasLimit: gasLimit || 250_000,
      type: 2,
      chainId,
    });
    prepared.push({ idx: i, address: wallets[i].address, signedTx: rawTx });
  }

  console.log(
    chalk.green(
      ` ✓ Đã ký ${prepared.length} giao dịch trong ${(performance.now() - signStart).toFixed(1)}ms`
    )
  );

  if (dryRun) {
    console.log(chalk.bold.cyan("\n── DRY-RUN SIMULATION ──"));
    for (const p of prepared) {
      // Simulate via eth_call to estimate gas used
      try {
        const result = await provider.call({
          to: plan.to,
          data: plan.data,
          value: plan.value,
          from: p.address,
          gasLimit: gasLimit || 250_000,
        });
        const resultStr = typeof result === 'string' ? result : JSON.stringify(result);
        console.log(chalk.green(` [W${p.idx}] ${p.address} — Simulation OK (result: ${resultStr.slice(0, 20)}...)`));
      } catch (err: any) {
        console.log(chalk.red(` [W${p.idx}] ${p.address} — Simulation failed: ${err.message?.slice(0, 100)}`));
      }
    }
    console.log(chalk.bold.cyan("\n=== DRY-RUN COMPLETE (no transactions broadcast) ==="));
    return;
  }

  // ── Wait for the stage, then blast pre-built bytes ──
  if (targetStart) {
    await waitForMintTime(targetStart);
  } else {
    console.log(chalk.bold.yellow("\n 🚀 Đang gửi ngay..."));
  }

  const stageStartMs = targetStart ? targetStart.getTime() : Date.now();
  const dispatchStart = performance.now();

  const fired = prepared.map(({ idx, address, signedTx }) => {
    // Broadcast to all RPC endpoints
    const promises = rpcUrls.map((url) =>
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "eth_sendRawTransaction", params: [signedTx], id: 1 }),
      })
        .then((r) => r.json() as Promise<{ result?: string; error?: { message: string } }>)
        .then((data) => ({ txHash: data.result ?? null, error: data.error?.message ?? null }))
        .catch((err) => ({ txHash: null, error: err.message }))
    );
    return { idx, address, responses: promises };
  });

  const dispatchMs = (performance.now() - dispatchStart).toFixed(2);
  const sinceStage = Math.max(0, Date.now() - stageStartMs);
  console.log(chalk.bold.green(` ĐÃ GỬI ${fired.length} giao dịch (${dispatchMs}ms, +${sinceStage}ms sau khi đợt mint mở)`));

  // Wait for responses
  const settled = await Promise.all(
    fired.map(async (f) => {
      const results = await Promise.all(f.responses);
      return { ...f, results };
    })
  );

  const accepted = settled.filter(({ results }) =>
    results.some((r) => r.txHash !== null && !r.error)
  );
  const rejected = settled.filter((s) => !accepted.includes(s));

  for (const { idx, results } of rejected) {
    const reasons = [...new Set(results.map((r) => r.error).filter(Boolean))];
    console.log(chalk.bold.red(`\n ✗ [W${idx}] Bị tất cả RPC từ chối — chưa được phát lên mạng.`));
    for (const reason of reasons) console.log(chalk.red(` ${reason}`));
    if (reasons.some((r) => (r ?? "").includes("less than block base fee"))) {
      console.log(chalk.yellow(" → Phí tối đa thấp hơn base fee của chain. Hãy tăng phí và chạy lại."));
    }
  }

  if (accepted.length === 0) {
    console.log(chalk.bold.red("\n===== KHÔNG GIAO DỊCH NÀO ĐƯỢC PHÁT — KHÔNG CÓ RECEIPT ĐỂ CHỜ =====\n"));
    return;
  }

  // ── Receipts (only for txs an endpoint actually accepted) ──
  console.log(chalk.gray("\n Đang chờ receipt..."));
  await Promise.all(
    accepted.map(async ({ idx, address, results }) => {
      const successResult = results.find((r) => r.txHash !== null && !r.error);
      if (!successResult?.txHash) return;

      const txHash = successResult.txHash;
      console.log(chalk.gray(` [W${idx}] ${txHash} — waiting for receipt...`));

      const receipt = await waitForReceipt(txHash, rpcUrls[0], 60_000);
      if (!receipt) {
        console.log(chalk.yellow(` [W${idx}] HẾT THỜI GIAN CHỜ — kiểm tra explorer`));
        return;
      }

      const color = receipt.status === 1 ? chalk.bold.green : chalk.bold.red;
      console.log(
        color(` [W${idx}] Block: ${receipt.blockNumber} | Gas used: ${receipt.gasUsed} | ${receipt.status === 1 ? "THÀNH CÔNG" : "THẤT BẠI"}`)
      );
    })
  );

  console.log(chalk.bold.white("\n===== HOÀN TẤT PUBLIC MINT CỤC BỘ ====="));
}

// Warm up connections to all RPC endpoints
async function warmConnections(rpcUrls: string[]): Promise<void> {
  await Promise.all(
    rpcUrls.map(async (url) => {
      try {
        await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", method: "eth_blockNumber", params: [], id: 1 }),
        });
      } catch {
        // Ignore warm-up failures
      }
    })
  );
}

async function waitForMintTime(targetStart: Date, bufferMs: number = 0): Promise<void> {
  const now = Date.now();
  const targetMs = targetStart.getTime() - bufferMs;
  if (targetMs <= now) return;

  const waitMs = targetMs - now;
  console.log(chalk.gray(` ⏳ Waiting ${Math.ceil(waitMs / 1000)}s until mint opens...`));
  await new Promise((resolve) => setTimeout(resolve, waitMs));
}

async function waitForReceipt(
  txHash: string,
  rpcUrl: string,
  timeoutMs: number
): Promise<{ blockNumber: number; gasUsed: bigint; status: number } | null> {
  const provider = new JsonRpcProvider(rpcUrl);
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    try {
      const receipt = await provider.getTransactionReceipt(txHash);
      if (receipt) {
        return {
          blockNumber: receipt.blockNumber,
          gasUsed: receipt.gasUsed,
          status: receipt.status ?? 0,
        };
      }
    } catch {
      // Ignore RPC errors
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  return null;
}