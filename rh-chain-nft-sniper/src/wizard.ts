// Interactive wizard for NFT mint sniper
// Source: adapted from solotop999/opensea-nft-public-mint

import chalk from "chalk";
import { JsonRpcProvider, Wallet, formatEther, getAddress, isAddress } from "ethers";
import { CHAINS, ChainProfile, resolveChain, getDefaultChain } from "./chains";
import { parseNftLink, extractSlugFromOpenseaUrl } from "./nft-link";
import { resolveSlug } from "./slug-resolver";
import { planRpcs, resolveRpcsForChain, privateRpcsFromEnv } from "./rpc-resolver";
import { parseRpcEndpoints } from "./rpc-blast";
import { buildLocalMintPlan, LocalMintPlan } from "./seadrop-public";
import { localPublicSnipe } from "./local-mint";
import { istTimeToDate, toIST } from "./time-format";
import {
  askChoice,
  askHidden,
  askNumber,
  askText,
  askYesNo,
  closePrompts,
} from "./prompt";

export async function runWizard(): Promise<void> {
  printBanner();

  // ── 1. Private keys ───────────────────────────────────────────────────
  const walletKeys = await promptKeys();

  // ── 2. Chain ──────────────────────────────────────────────────────────
  const defaultChain = getDefaultChain().key;
  const defaultIndex = CHAINS.findIndex((c) => c.key === defaultChain);
  let chainKey = await askChoice(
    "Chọn blockchain",
    CHAINS.map((c) => ({ label: c.name, value: c.key, hint: `chain id ${c.chainId}` })),
    Math.max(0, defaultIndex)
  );

  // ── 3. Quantity ───────────────────────────────────────────────────────
  const quantity = await promptQuantity(walletKeys.length);

  // ── 4. NFT link ───────────────────────────────────────────────────────
  const target = await promptTarget(chainKey);
  const nftContract = target.contract;
  chainKey = target.chainKey;
  const chainProfile = resolveChain(chainKey)!;

  // ── 5. RPC endpoints ──────────────────────────────────────────────────
  const manualRpcs = await promptRpc(chainProfile);
  const { urls: candidateRpcs, source } = await resolveRpcsForChain(chainKey, manualRpcs.join(","));
  console.log(chalk.gray(` Nguồn: ${source}`));
  console.log(chalk.gray(` Đang kiểm tra ${candidateRpcs.length} endpoint...`));

  const plan = await planRpcs(candidateRpcs, chainProfile.chainId);
  for (const bad of plan.dropped) {
    const wrong = resolveChainById(bad.chainId);
    console.log(
      chalk.red(` ✗ ${bad.url} thuộc chain ${bad.chainId}${wrong ? ` (${wrong.name})` : ""} — đã loại bỏ`)
    );
  }
  for (const ep of plan.urls) {
    const failure = plan.failures.find((f) => f.url === ep);
    if (failure) {
      const benign = /not allowed|does not exist|not supported|method not found/i.test(failure.message);
      const label = ep;
      console.log(
        benign
          ? chalk.gray(` • ${label} (chỉ gửi)`)
          : chalk.yellow(` ⚠ ${label} ${failure.message.slice(0, 90)}`)
      );
    } else {
      console.log(chalk.green(` ✓ ${ep}`));
    }
  }
  if (plan.urls.length === 0) {
    throw new Error(`Không có RPC endpoint khả dụng cho ${chainProfile.name}`);
  }
  if (!plan.verified) {
    console.log(chalk.yellow(` ⚠ Không endpoint nào xác nhận chain ID ${chainProfile.chainId}.`));
    if (!(await askYesNo("Vẫn tiếp tục?", false))) {
      throw new Error("Đã hủy — không thể xác minh chain của RPC");
    }
  } else {
    console.log(chalk.green(` ✓ Đã xác nhận chain ID ${chainProfile.chainId} (${chainProfile.name})`));
  }
  const rpcUrls = plan.urls;

  // ── 6. Read the public drop from chain ────────────────────────────────
  console.log(chalk.bold.white("\nĐợt mint"));
  const mintPlan = await buildLocalMintPlan(rpcUrls[0], nftContract, quantity);
  if (!mintPlan) {
    throw new Error(
      `Không đọc được đợt public SeaDrop của ${nftContract} trên ${chainProfile.name}.\n` +
      " Có thể đây không phải bộ sưu tập SeaDrop hoặc cấu hình được lưu trong token contract."
    );
  }
  const drop = mintPlan.drop;
  const startsAt = new Date(drop.startTime * 1000);
  const endsAt = new Date(drop.endTime * 1000);
  const live = Date.now() >= startsAt.getTime() && Date.now() < endsAt.getTime();
  console.log(chalk.green(" ✓ Đã tạo calldata từ SeaDrop on-chain — không cần token OpenSea"));
  console.log(chalk.gray(` Người nhận phí: ${mintPlan.feeRecipient}`));
  console.log(
    chalk.gray(
      ` Giá: ${formatEther(drop.mintPrice)} × ${quantity} = ${formatEther(mintPlan.value)} mỗi ví`
    )
  );
  console.log(chalk.gray(` Tối đa mỗi ví: ${drop.maxTotalMintableByWallet || "không giới hạn"}`));
  console.log(
    chalk.gray(
      ` Thời gian: ${toIST(startsAt)} → ${toIST(endsAt)} IST ${live ? chalk.green("(đang mở)") : chalk.yellow(`(mở sau ${formatRemaining(startsAt.getTime() - Date.now())})`)}`
    )
  );
  if (drop.maxTotalMintableByWallet > 0 && quantity > drop.maxTotalMintableByWallet) {
    console.log(
      chalk.yellow(` ⚠ Đợt mint chỉ cho phép ${drop.maxTotalMintableByWallet} NFT mỗi ví — giao dịch mint ${quantity} NFT sẽ bị revert.`)
    );
  }
  if (Date.now() >= endsAt.getTime()) {
    console.log(chalk.yellow(" ⚠ Đợt public mint này đã kết thúc on-chain."));
  }

  // ── 7. Gas ────────────────────────────────────────────────────────────
  const provider = new JsonRpcProvider(rpcUrls[0]);
  console.log(chalk.bold.white("\nGas"));
  const baseFeeGwei = await currentBaseFeeGwei(provider);
  if (baseFeeGwei !== null) {
    console.log(chalk.gray(` Base fee hiện tại của mạng: ${baseFeeGwei.toFixed(6)} gwei`));
  }
  const envMaxFee = Number(process.env.MAX_FEE_PER_GAS || (chainKey === "ethereum" ? 80 : 2));
  const envPriority = Number(process.env.MAX_PRIORITY_FEE || (chainKey === "ethereum" ? 5 : 0.05));

  let defaultMaxFee = envMaxFee;
  if (baseFeeGwei !== null) {
    const suggested = Math.ceil((baseFeeGwei * 2 + envPriority) * 1000) / 1000;
    if (envMaxFee < baseFeeGwei) defaultMaxFee = suggested;
    console.log(chalk.gray(` Phải từ ${baseFeeGwei.toFixed(6)} gwei; mức ${suggested} có khoảng dự phòng.`));
  }
  const maxFeeGwei = await askNumber("Phí gas tối đa (gwei) — mức trần", defaultMaxFee, {
    min: baseFeeGwei ?? 0,
  });
  const priorityDefault = Math.min(envPriority, maxFeeGwei);
  const priorityGwei = await askNumber("Phí ưu tiên / tiền tip (gwei)", priorityDefault, {
    min: 0,
    max: maxFeeGwei,
  });
  const maxFeePerGas = gweiToWei(maxFeeGwei);
  const maxPriorityFee = gweiToWei(priorityGwei);
  const gasLimit = parseInt(process.env.GAS_LIMIT || "0", 10) || 250_000;

  // ── 8. Timing ─────────────────────────────────────────────────────────
  const { targetStart, timingLabel } = await promptTiming(drop.startTime);

  // ── 9. Dry-run mode ───────────────────────────────────────────────────
  const dryRun = await askYesNo("Chạy Dry-run trước? (không broadcast, chỉ simulate)", true);

  // ── 10. Balances + affordability ──────────────────────────────────────
  console.log(chalk.bold.white("\nCác ví"));
  const wallets = walletKeys.map((k) => new Wallet(k));
  const balances = await Promise.all(
    wallets.map((w) => provider.getBalance(w.address).catch(() => null))
  );
  const symbol = chainProfile.nativeSymbol;
  const required = BigInt(gasLimit) * maxFeePerGas + mintPlan.value;
  wallets.forEach((w, i) => {
    const bal = balances[i];
    const text = bal === null ? "không đọc được số dư" : `${Number(formatEther(bal)).toFixed(6)} ${symbol}`;
    const short = bal !== null && bal < required;
    const line = ` [W${i}] ${w.address} ${text}`;
    console.log(short ? chalk.red(`${line} ✗ cần ${formatEther(required)}`) : chalk.gray(line));
  });
  const shortWallets = wallets.filter((_, i) => balances[i] !== null && (balances[i] as bigint) < required);
  if (shortWallets.length > 0) {
    console.log(
      chalk.gray(
        `\n Node yêu cầu mỗi ví có gasLimit × maxFee${mintPlan.value > 0n ? " + giá mint" : ""} = ${formatEther(required)} ${symbol}.`
      )
    );
    const poorest = balances
      .filter((b): b is bigint => b !== null)
      .reduce((a, b) => (a < b ? a : b));
    const affordable = Number((poorest - mintPlan.value) / BigInt(gasLimit)) / 1e9;
    if (affordable > 0) {
      console.log(
        chalk.yellow(` Hãy nạp thêm tiền hoặc chạy lại với phí tối đa không quá ${affordable.toFixed(4)} gwei.`)
      );
    }
    if (shortWallets.length === wallets.length) {
      throw new Error("Tất cả ví đều thiếu tiền — không thể phát giao dịch.");
    }
    console.log(chalk.yellow(" Những ví còn đủ tiền vẫn có thể gửi giao dịch."));
  }

  // ── 11. Confirm ───────────────────────────────────────────────────────
  console.log(chalk.bold.white("\n──────── SẴN SÀNG ────────"));
  line("Blockchain", `${chainProfile.name} (${chainProfile.chainId})`);
  line("RPC", `${rpcUrls[0]} + ${rpcUrls.length - 1} more`);
  line("Mục tiêu", target.label);
  line("Contract", nftContract);
  line("Số ví", `${wallets.length}`);
  line("Số lượng", `${quantity} mỗi ví → tổng ${quantity * wallets.length}`);
  line(
    "Tiền mint",
    `${formatEther(mintPlan.value)} mỗi ví → tổng ${formatEther(mintPlan.value * BigInt(wallets.length))} (+ gas)`
  );
  line("Gas", `${maxFeeGwei} / ${priorityGwei} gwei · limit ${gasLimit}`);
  line("Thời điểm", timingLabel);
  line("Mode", dryRun ? chalk.yellow("DRY-RUN (simulate only)") : chalk.green("LIVE (broadcast)"));
  console.log(chalk.bold.white("───────────────────────"));

  if (!(await askYesNo(chalk.bold(dryRun ? "Chạy Dry-run?" : "Gửi giao dịch?")), false)) {
    console.log(chalk.yellow("\n Đã hủy — chưa có gì được gửi.\n"));
    closePrompts();
    return;
  }

  closePrompts();
  await localPublicSnipe({
    nftContract,
    quantity,
    walletKeys,
    rpcUrls,
    maxFeePerGas,
    maxPriorityFee,
    gasLimit,
    targetStart,
    plan: mintPlan,
    dryRun,
  });
}

// ── Steps ───────────────────────────────────────────────────────────────

async function promptKeys(): Promise<string[]> {
  console.log(chalk.bold.white("Private key"));
  console.log(chalk.gray(" Dán mỗi dòng một key — nội dung nhập sẽ được ẩn. Để trống khi hoàn tất."));
  console.log(chalk.gray(" Mỗi key được xác nhận bằng địa chỉ ví. Không có dữ liệu nào được lưu xuống ổ đĩa."));
  const keys: string[] = [];
  const seen = new Set();
  for (;;) {
    const raw = await askHidden(chalk.gray(` › key thứ ${keys.length + 1}: `));
    if (!raw) {
      if (keys.length === 0) {
        console.log(chalk.red(" ✗ Cần nhập ít nhất một key."));
        continue;
      }
      break;
    }
    const normalized = raw.startsWith("0x") ? raw : `0x${raw}`;
    let wallet: Wallet;
    try {
      wallet = new Wallet(normalized);
    } catch {
      console.log(chalk.red(" ✗ Private key không hợp lệ — hãy thử lại."));
      continue;
    }
    if (seen.has(wallet.address.toLowerCase())) {
      console.log(chalk.yellow(` ⚠ Trùng với ${short(wallet.address)} — đã bỏ qua.`));
      continue;
    }
    seen.add(wallet.address.toLowerCase());
    keys.push(normalized);
    console.log(chalk.green(` ✓ [W${keys.length - 1}] ${wallet.address}`));
  }
  console.log(chalk.gray(` Đã nạp ${keys.length} ví.`));
  return keys;
}

async function promptQuantity(walletCount: number): Promise<number> {
  console.log(chalk.bold.white("\nSố lượng"));
  const qty = await askNumber("Số NFT mỗi ví", 1, { min: 1, max: 100 });
  if (walletCount > 1) {
    console.log(chalk.gray(` → ${qty} × ${walletCount} ví = tổng ${qty * walletCount}`));
  }
  return Math.floor(qty);
}

async function promptTarget(
  chainKey: string
): Promise<{ contract: string; label: string; chainKey: string }> {
  console.log(chalk.bold.white("\nNFT mục tiêu"));
  console.log(chalk.gray(" Dán liên kết OpenSea (bộ sưu tập hoặc NFT), slug hoặc địa chỉ contract."));
  let activeChain = chainKey;
  for (;;) {
    const raw = await askText("Liên kết NFT");
    if (!raw) {
      continue;
    }
    const parsed = parseNftLink(raw);
    if (parsed.type === "address") {
      return { contract: parsed.value, label: parsed.value, chainKey: activeChain };
    }
    if (parsed.type === "opensea") {
      const slug = extractSlugFromOpenseaUrl(parsed.value);
      if (!slug) {
        console.log(chalk.red(" ✗ Không trích xuất được slug từ URL OpenSea."));
        continue;
      }
      const apiKey = process.env.OPENSEA_API_KEY;
      const contract = await resolveSlug(slug, apiKey);
      if (!contract) {
        console.log(chalk.red(" ✗ Không resolve được contract từ slug. Hãy cung cấp OPENSEA_API_KEY hoặc dán trực tiếp contract address."));
        continue;
      }
      console.log(chalk.green(` ✓ Resolved ${slug} → ${contract}`));
      return { contract, label: `${slug} (${contract})`, chainKey: activeChain };
    }
    // slug
    const apiKey = process.env.OPENSEA_API_KEY;
    const contract = await resolveSlug(parsed.value, apiKey);
    if (!contract) {
      console.log(chalk.red(" ✗ Không resolve được contract từ slug. Hãy cung cấp OPENSEA_API_KEY hoặc dán trực tiếp contract address."));
      continue;
    }
    console.log(chalk.green(` ✓ Resolved ${parsed.value} → ${contract}`));
    return { contract, label: `${parsed.value} (${contract})`, chainKey: activeChain };
  }
}

async function promptRpc(chainProfile: ChainProfile): Promise<string[]> {
  console.log(chalk.bold.white("\nRPC endpoints"));
  console.log(chalk.gray(` Default: ${chainProfile.rpcDefault}`));
  console.log(chalk.gray(" Nhập URL RPC (cách nhau bằng dấu phẩy) hoặc để trống để dùng default."));
  const raw = await askText("RPC URL");
  if (!raw) return [];
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

async function promptTiming(
  startTime: number
): Promise<{ targetStart: Date | null; timingLabel: string }> {
  const startsInFuture = startTime * 1000 > Date.now();
  const at = new Date(startTime * 1000);
  const choices: { label: string; value: "wait" | "now" | "custom"; hint?: string }[] = [];
  if (startsInFuture) {
    choices.push({
      label: "Chờ đợt mint mở",
      value: "wait",
      hint: `${toIST(at)} IST · còn ${formatRemaining(at.getTime() - Date.now())} · gửi tại T-0`,
    });
  } else {
    choices.push({ label: "Gửi ngay", value: "now", hint: "đợt mint đang mở" });
  }
  choices.push({ label: "Thời gian tùy chỉnh", value: "custom", hint: "HH:MM, 24 giờ IST, hôm nay" });
  const pick = await askChoice("Khi nào gửi giao dịch?", choices, 0);
  if (pick === "wait") return { targetStart: at, timingLabel: `chờ đợt mint — ${toIST(at)} IST` };
  if (pick === "now") return { targetStart: null, timingLabel: "gửi ngay lập tức" };
  for (;;) {
    const raw = await askText("Thời gian (HH:MM, 24 giờ, IST)");
    try {
      const custom = istTimeToDate(raw);
      if (custom.getTime() < startTime * 1000) {
        console.log(chalk.bold.red(` ✗ Thời điểm này trước khi đợt mint mở (${toIST(at)} IST) — giao dịch sẽ revert.`));
        if (!(await askYesNo("Vẫn sử dụng thời điểm này?", false))) continue;
      }
      return { targetStart: custom, timingLabel: `tùy chỉnh — ${toIST(custom)} IST` };
    } catch (err: any) {
      console.log(chalk.red(` ✗ ${err.message}`));
    }
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────

function normalizeAddress(raw: string): { address: string; checksumWarning: boolean } | null {
  const value = raw.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(value)) return null;
  const body = value.slice(2);
  const mixedCase = /[a-f]/.test(body) && /[A-F]/.test(body);
  return {
    address: getAddress(value.toLowerCase()),
    checksumWarning: mixedCase && !isAddress(value),
  };
}

async function currentBaseFeeGwei(provider: JsonRpcProvider): Promise<number | null> {
  try {
    const fee = await provider.getFeeData();
    const wei = fee.gasPrice ?? fee.maxFeePerGas;
    return wei === null || wei === undefined ? null : Number(wei) / 1e9;
  } catch {
    return null;
  }
}

function gweiToWei(gwei: number): bigint {
  return BigInt(Math.round(gwei * 1e9));
}

function formatRemaining(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function short(addr: string): string {
  return addr.length > 12 ? `${addr.slice(0, 6)}…${addr.slice(-4)}` : addr;
}

function line(label: string, value: string): void {
  console.log(` ${chalk.gray(label.padEnd(10))} ${chalk.white(value)}`);
}

function printBanner(): void {
  console.log(
    chalk.bold.cyan(`
╔═══════════════════════════════════════╗
║   RH CHAIN NFT MINT SNIPER           ║
║   Public SeaDrop · On-chain calldata ║
╚═══════════════════════════════════════╝`)
  );
  console.log(chalk.gray(" Chỉ hỗ trợ đợt public SeaDrop. Nhấn Ctrl+C để thoát bất cứ lúc nào.\n"));
}

function resolveChainById(chainId: number): ChainProfile | undefined {
  return CHAINS.find((c) => c.chainId === chainId);
}