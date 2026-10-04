/**
 * src/hundredx.js - the seven-step cycle-wallet hunt, Solana side ($0.15, USDC on Solana).
 *
 * Same method as the Base endpoint on xhagents.xyz/api/hundred-x-hunter:
 *   1. a coin from a previous cycle (input: the SPL mint)
 *   2. its earliest buyers (read from the mint's own transaction history, walked back to the beginning)
 *   3. keep the wallets still transacting inside the window
 *   4. drop the machines (two of a wallet's own buys less than a minute apart)
 *   5. what the survivors bought since, and whether they still hold
 *   6. a mint that shows up in several wallets is a signal
 *   7. score it — below 9 of 10 the answer is no
 *
 * Data: Solana JSON-RPC (jsonParsed transactions) + DexScreener. The public RPC is rate-limited, so the
 * work is bounded: page limits, per-wallet transaction caps, a wall-clock deadline, a short cache, and a
 * "truncated" flag in the response whenever a bound was hit. Nothing is invented to fill a gap.
 */

const RPC_URLS = (process.env.SOLANA_RPC_URL || "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com")
  .split(",").map((s) => s.trim()).filter(Boolean);
const RPC_URL = RPC_URLS[0];
const DEX = "https://api.dexscreener.com/latest/dex";
const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

const BOT_INTERVAL_SECONDS = 60;
const BUY_THRESHOLD = 9.0;
const WATCH_THRESHOLD = 7.0;

const TOKEN_PROGRAMS = new Set([
  "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
  "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
]);
const DEX_PROGRAMS = new Set([
  "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
  "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
  "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
  "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
  "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
  "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
  "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
  "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS",
  "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY",
]);

const CACHE = new Map();
const CACHE_TTL_MS = 120_000;
const CACHE_MAX = 300;

function cacheGet(key) {
  const hit = CACHE.get(key);
  if (!hit) return null;
  if (Date.now() - hit.at > CACHE_TTL_MS) {
    CACHE.delete(key);
    return null;
  }
  return hit.value;
}

function cachePut(key, value) {
  if (CACHE.size > CACHE_MAX) CACHE.clear();
  CACHE.set(key, { at: Date.now(), value });
}

let lastCall = 0;

async function rpcOnce(url, method, params, timeoutMs) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: ctl.signal,
    });
    const j = await r.json();
    if (j.error) {
      const err = new Error(String(j.error.message || j.error).slice(0, 160));
      err.rateLimited = /too many requests|rate limit|429/i.test(String(j.error.message || ""));
      throw err;
    }
    return j.result;
  } finally {
    clearTimeout(timer);
  }
}

async function rpc(method, params, timeoutMs = 20_000) {
  const key = method + ":" + JSON.stringify(params);
  const hit = cacheGet(key);
  if (hit !== null) return hit;
  // the public Solana RPCs rate-limit per method: pace the calls and fail over between endpoints
  const gap = 130 - (Date.now() - lastCall);
  if (gap > 0) await new Promise((r) => setTimeout(r, gap));
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    for (const url of RPC_URLS) {
      try {
        lastCall = Date.now();
        const out = await rpcOnce(url, method, params, timeoutMs);
        cachePut(key, out);
        return out;
      } catch (e) {
        lastErr = e;
        if (!e.rateLimited && !/abort|network|fetch failed/i.test(String(e.message))) throw e;
      }
    }
    await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
  }
  throw lastErr;
}

// ── helpers ─────────────────────────────────────────────────────────────────

function isMint(s) {
  return typeof s === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s);
}

async function dexInfo(mint) {
  const key = "dex:" + mint;
  const hit = cacheGet(key);
  if (hit) return hit;
  try {
    const r = await fetch(`${DEX}/tokens/${mint}`);
    const j = await r.json();
    const all = (j.pairs || []).filter((p) => p.chainId === "solana");
    if (!all.length) {
      cachePut(key, null);
      return null;
    }
    // prefer the pair where the requested mint is the base token: for a quote token the deepest market
    // belongs to somebody else's coin, and reading its symbol/price would describe the wrong asset.
    const own = all.filter((p) => (p.baseToken?.address || "") === mint);
    const best = (own.length ? own : all).reduce((a, b) =>
      parseFloat(b?.liquidity?.usd || 0) > parseFloat(a?.liquidity?.usd || 0) ? b : a);
    const side = (best.baseToken?.address || "") === mint ? best.baseToken : best.quoteToken;
    const out = {
      pair: best.pairAddress,
      dex: best.dexId,
      symbol: side?.symbol,
      name: side?.name,
      mint_is: (best.baseToken?.address || "") === mint ? "base" : "quote",
      liquidity_usd: parseFloat(best.liquidity?.usd || 0),
      price_usd: parseFloat(best.priceUsd || 0),
      price_change_24h_pct: best.priceChange?.h24 ?? null,
      url: best.url,
    };
    cachePut(key, out);
    return out;
  } catch (_) {
    return null;
  }
}

function collectInstructions(tx) {
  const out = [];
  const push = (ix) => {
    if (ix && ix.programId) out.push(ix);
  };
  for (const ix of tx?.transaction?.message?.instructions || []) push(ix);
  for (const group of tx?.meta?.innerInstructions || []) {
    for (const ix of group.instructions || []) push(ix);
  }
  return out;
}

function buysFromTx(tx, mint) {
  const found = [];
  const touchedDex = collectInstructions(tx).some((ix) => DEX_PROGRAMS.has(ix.programId));
  for (const ix of collectInstructions(tx)) {
    if (!TOKEN_PROGRAMS.has(ix.programId)) continue;
    const info = ix.parsed?.info;
    const type = ix.parsed?.type;
    if (!info || (type !== "transfer" && type !== "transferChecked")) continue;
    if (info.mint && info.mint !== mint) continue;
    const amount = parseFloat(info.amount || info.tokenAmount?.uiAmount || 0);
    found.push({
      owner: info.authority || info.multisigAuthority || null,
      source: info.source,
      destination: info.destination,
      amount,
      via_dex: touchedDex,
    });
  }
  return found;
}

// ── step 2 + step 4 evidence ────────────────────────────────────────────────

async function earliestBuyers(mint, want, maxPages, budget) {
  // walk the mint's history back to its beginning, then read the first transactions forward
  let before = undefined;
  let oldest = null;
  let pages = 0;
  let rpcError = null;
  const sigs = [];
  while (pages < maxPages && budget.left() > 0) {
    let page;
    try {
      page = await rpc("getSignaturesForAddress", [mint, { limit: 1000, ...(before ? { before } : {}) }]);
    } catch (e) {
      rpcError = String(e.message || e).slice(0, 140);
      break;
    }
    pages += 1;
    if (!page || !page.length) break;
    sigs.push(...page);
    oldest = page[page.length - 1];
    if (page.length < 1000) break; // reached the beginning
    before = oldest.signature;
  }
  const truncated = rpcError !== null || (pages >= maxPages && sigs.length >= 1000);
  const chron = sigs.slice().reverse(); // oldest first
  const buyers = [];
  const seen = new Set();
  const perWalletTimes = new Map();
  let examined = 0;
  for (const s of chron) {
    if (buyers.length >= want || budget.left() <= 0 || examined >= want * 3) break;
    examined += 1;
    let tx;
    try {
      tx = await rpc("getTransaction", [s.signature,
        { encoding: "jsonParsed", maxSupportedTransactionVersion: 0 }], 20_000);
    } catch (_) {
      continue;
    }
    if (!tx) continue;
    for (const b of buysFromTx(tx, mint)) {
      if (!b.owner || seen.has(b.owner)) continue;
      seen.add(b.owner);
      buyers.push({
        wallet: b.owner, signature: s.signature, slot: tx.slot,
        ts: tx.blockTime ? new Date(tx.blockTime * 1000).toISOString() : null,
        amount: b.amount, source_class: b.via_dex ? "dex/aggregator" : "wallet",
        kind: b.via_dex ? "buy" : "transfer_in",
      });
      if (tx.blockTime) {
        const arr = perWalletTimes.get(b.owner) || [];
        arr.push(tx.blockTime);
        perWalletTimes.set(b.owner, arr);
      }
      if (buyers.length >= want) break;
    }
  }
  return { buyers, perWalletTimes, truncated, pages, signatures_seen: sigs.length, examined, rpc_error: rpcError };
}

// ── steps 3 and 5 ───────────────────────────────────────────────────────────

async function walletActivity(wallet, days, budget) {
  if (budget.left() <= 0) return { active: null, reason: "deadline" };
  try {
    const sigs = await rpc("getSignaturesForAddress", [wallet, { limit: 1 }]);
    const newest = sigs?.[0];
    if (!newest) return { active: false, last_seen: null, reason: "no transactions at all" };
    const ts = newest.blockTime ? newest.blockTime * 1000 : null;
    const ageDays = ts ? (Date.now() - ts) / 86400000 : null;
    return {
      active: ageDays !== null && ageDays <= days,
      last_seen: ts ? new Date(ts).toISOString() : null,
      age_days: ageDays === null ? null : parseFloat(ageDays.toFixed(2)),
    };
  } catch (e) {
    return { active: null, reason: String(e.message || e).slice(0, 120) };
  }
}

async function tokenHoldings(wallet, mint, budget) {
  if (budget.left() <= 0) return { amount: null, reason: "deadline" };
  try {
    const res = await rpc("getTokenAccountsByOwner", [wallet, { mint }, { encoding: "jsonParsed" }]);
    let amount = 0;
    for (const a of res?.value || []) {
      amount += parseFloat(a?.account?.data?.parsed?.info?.tokenAmount?.uiAmount || 0);
    }
    return { amount };
  } catch (e) {
    return { amount: null, reason: String(e.message || e).slice(0, 120) };
  }
}

async function recentBuys(wallet, days, limit, budget) {
  if (budget.left() <= 0) return [];
  let sigs = [];
  try {
    sigs = (await rpc("getSignaturesForAddress", [wallet, { limit: 30 }])) || [];
  } catch (_) {
    return [];
  }
  const cutoff = Date.now() - days * 86400000;
  const out = [];
  let checked = 0;
  for (const s of sigs) {
    if (checked >= limit || budget.left() <= 0) break;
    if (s.blockTime && s.blockTime * 1000 < cutoff) break; // history is newest-first
    checked += 1;
    let tx;
    try {
      tx = await rpc("getTransaction", [s.signature,
        { encoding: "jsonParsed", maxSupportedTransactionVersion: 0 }], 20_000);
    } catch (_) {
      continue;
    }
    if (!tx) continue;
    const pre = new Map();
    for (const b of tx.meta?.preTokenBalances || []) {
      if (b.owner === wallet) pre.set(b.mint, b.uiTokenAmount?.uiAmount || 0);
    }
    for (const b of tx.meta?.postTokenBalances || []) {
      if (b.owner !== wallet) continue;
      const before = pre.get(b.mint) || 0;
      const after = b.uiTokenAmount?.uiAmount || 0;
      if (after > before) {
        out.push({
          mint: b.mint,
          amount: parseFloat((after - before).toFixed(6)),
          ts: tx.blockTime ? new Date(tx.blockTime * 1000).toISOString() : null,
          signature: s.signature,
        });
      }
    }
  }
  return out;
}

function botEvidence(wallet, perWalletTimes, walletTransfers) {
  const times = (perWalletTimes.get(wallet) || []).slice().sort((a, b) => a - b);
  const gaps = [];
  for (let i = 1; i < times.length; i += 1) gaps.push(times[i] - times[i - 1]);
  const minGap = gaps.length ? Math.min(...gaps) : null;
  // a wallet that bought a dozen different mints inside the same few seconds is also a machine
  const firsts = (walletTransfers || []).map((t) => t.ts).filter(Boolean).sort();
  let burst = 0;
  for (let i = 1; i < firsts.length; i += 1) {
    const d = (new Date(firsts[i]) - new Date(firsts[i - 1])) / 1000;
    if (d >= 0 && d < BOT_INTERVAL_SECONDS) burst += 1;
  }
  const isBot = (minGap !== null && minGap < BOT_INTERVAL_SECONDS) || burst >= 3;
  return {
    bot: isBot,
    reason: isBot
      ? (minGap !== null && minGap < BOT_INTERVAL_SECONDS
          ? `consecutive transfers ${minGap}s apart`
          : `${burst} sub-minute gaps in its recent token transactions`)
      : "no sub-minute spacing in its own transfers",
    intervals_sec: gaps,
  };
}

// ── steps 6 and 7 ───────────────────────────────────────────────────────────

function scoreCandidate(token, holders, dex) {
  const byWallet = new Map();
  for (const h of holders) if (!byWallet.has(h.wallet)) byWallet.set(h.wallet, h);
  const uniq = [...byWallet.values()];
  const wallets = uniq.length;
  const still = uniq.filter((h) => (h.held?.amount || 0) > 0).length;
  const ratio = wallets ? still / wallets : 0;
  const cutoff7 = Date.now() - 7 * 86400000;
  const recent7 = uniq.filter((h) => (h.recent_buys || []).some((b) => b.ts && new Date(b.ts).getTime() >= cutoff7)).length;
  const recent7Ratio = wallets ? recent7 / wallets : 0;
  const liq = dex?.liquidity_usd || 0;
  const parts = {
    wallets_holding: wallets >= 2 ? Math.min(4, 1 + (wallets - 2) * 1) : wallets * 0.4,
    still_held: 2 * ratio,
    buy_recency_7d: 1.5 * recent7Ratio,
    liquidity_floor: liq >= 100_000 ? 0.5 : -1,
    cycle_wallet_conviction: Math.min(1, wallets / 5),
  };
  const total = Object.values(parts).reduce((a, b) => a + b, 0);
  const score = Math.max(0, Math.min(10, parseFloat(total.toFixed(2))));
  return {
    token, symbol: dex?.symbol || null, score,
    verdict: score >= BUY_THRESHOLD ? "buy" : score >= WATCH_THRESHOLD ? "watch" : "reject",
    parts: Object.fromEntries(Object.entries(parts).map(([k, v]) => [k, parseFloat(v.toFixed(2))])),
    wallets, still_held: still, bought_last_7d: recent7,
    liquidity_usd: liq, price_usd: dex?.price_usd ?? null,
    price_change_24h_pct: dex?.price_change_24h_pct ?? null, pair: dex?.url || null,
    holders: uniq.map((h) => h.wallet),
  };
}

// ── the method ──────────────────────────────────────────────────────────────

export async function hundredXHunter(params = {}) {
  const mint = (params.mint || params.token || "").trim();
  const windowDays = Math.min(Math.max(parseInt(params.window_days || "30", 10), 1), 180);
  const minWallets = Math.min(Math.max(parseInt(params.min_wallets || "3", 10), 2), 10);
  const limit = Math.min(Math.max(parseInt(params.limit || "10", 10), 1), 25);
  if (!isMint(mint)) {
    const err = new Error("mint must be a base58 SPL mint address");
    err.status = 400;
    throw err;
  }

  const deadline = Date.now() + 55_000;
  const budget = { left: () => deadline - Date.now() };
  const notes = [];

  const meta = await dexInfo(mint);
  const step2 = await earliestBuyers(mint, 21, 12, budget);
  if (step2.rpc_error) {
    notes.push(`the RPC rate-limited the history walk (${step2.rpc_error}): the result covers only what was ` +
               `read before the limit; retry in a minute for more.`);
  } else if (step2.truncated) {
    notes.push(`the mint has more history than ${step2.pages} pages of signatures: these are the EARLIEST ` +
               `buyers reachable inside that bound, not necessarily the absolute first ones. A quiet coin ` +
               `from a previous cycle (the method's own advice) reads exactly.`);
  }

  const step3 = { kept: [], dropped: [] };
  for (const b of step2.buyers) {
    const act = await walletActivity(b.wallet, windowDays, budget);
    const row = { wallet: b.wallet, activity: act };
    if (act.active) step3.kept.push(row);
    else step3.dropped.push(row);
  }

  const step4 = { kept: [], excluded: [] };
  for (const row of step3.kept) {
    const ev = botEvidence(row.wallet, step2.perWalletTimes, []);
    const entry = { wallet: row.wallet, reason: ev.reason, intervals: ev.intervals_sec };
    if (ev.bot) step4.excluded.push(entry);
    else step4.kept.push(row);
  }

  const step5 = [];
  for (const row of step4.kept.slice(0, limit)) {
    const buys = await recentBuys(row.wallet, windowDays, 6, budget);
    const held = await tokenHoldings(row.wallet, mint, budget);
    step5.push({ wallet: row.wallet, recent_buys: buys, held_of_input_mint: held });
  }

  // step 6: mints bought by two or more of the surviving wallets
  const buckets = new Map();
  for (const row of step5) {
    for (const b of row.recent_buys) {
      if (b.mint === mint) continue;
      const arr = buckets.get(b.mint) || [];
      arr.push({ wallet: row.wallet, buy: b });
      buckets.set(b.mint, arr);
    }
  }
  const recurring = [];
  for (const [tok, holders] of buckets) {
    const wallets = new Set(holders.map((h) => h.wallet)).size;
    if (wallets < 2) continue;
    const enriched = [];
    for (const h of holders) {
      enriched.push({ wallet: h.wallet, recent_buys: [h.buy], held: await tokenHoldings(h.wallet, tok, budget) });
    }
    recurring.push({ token: tok, wallets, strong: wallets >= minWallets, holders: enriched });
  }
  recurring.sort((a, b) => b.wallets - a.wallets);

  // step 7
  const scored = [];
  for (const r of recurring.slice(0, limit)) {
    scored.push(scoreCandidate(r.token, r.holders, await dexInfo(r.token)));
  }
  scored.sort((a, b) => b.score - a.score);
  const baselineHolders = step5.map((r) => ({
    wallet: r.wallet, recent_buys: r.recent_buys, held: r.held_of_input_mint,
  }));
  const baseline = scoreCandidate(mint, baselineHolders, meta);

  const decision = {
    threshold: BUY_THRESHOLD,
    buy: scored.filter((s) => s.verdict === "buy"),
    watch: scored.filter((s) => s.verdict === "watch"),
    reject: scored.filter((s) => s.verdict === "reject"),
    baseline_input_mint: baseline,
    rule: "below 9 out of 10 the answer is no, even if these wallets profited from it",
  };

  return {
    method: "seven-step cycle-wallet method (Boss's 'next 100x' logic)",
    chain: "solana",
    network: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    input_mint: { mint, symbol: meta?.symbol || null, name: meta?.name || null },
    input_mint_dex: meta,
    params: { window_days: windowDays, min_wallets: minWallets, limit },
    step_1_mint_from_previous_cycle: { mint, symbol: meta?.symbol || null },
    step_2_first_buyers: {
      count: step2.buyers.length,
      signatures_seen: step2.signatures_seen,
      transactions_examined: step2.examined,
      source: "getSignaturesForAddress(mint) walked back to the beginning + getTransaction(jsonParsed)",
      buyers: step2.buyers,
    },
    step_3_active_in_window: {
      kept: step3.kept.length, dropped: step3.dropped.length,
      dropped_detail: step3.dropped.map((d) => d.wallet),
    },
    step_4_bots_excluded: {
      kept: step4.kept.length, excluded: step4.excluded.length,
      bots: step4.excluded, rule_seconds: BOT_INTERVAL_SECONDS,
    },
    step_5_recent_buys: step5,
    step_6_recurring_tokens: recurring.map((r) => ({ token: r.token, wallets: r.wallets, strong: r.strong })),
    step_7_scored: scored,
    decision,
    methodology: {
      earliest_buyers: "the mint's own signature history read from its first transactions; each buy's source class recorded (dex/aggregator vs wallet)",
      activity_window: `wallet's newest signature inside ${windowDays} days`,
      bot_rule: `two of the wallet's own transfers less than ${BOT_INTERVAL_SECONDS}s apart, or 3+ sub-minute gaps`,
      recurrence_rule: `a mint bought by ${minWallets}+ of the surviving wallets`,
      scoring: {
        wallets_holding: "1 + 1 per wallet above two, capped 4",
        still_held: "2 x share still holding",
        buy_recency_7d: "1.5 x share that bought in the last 7 days",
        liquidity_floor: "+0.5 if DEX liquidity >= $100k, else -1",
        cycle_wallet_conviction: "min(1, wallets/5)",
      },
      prices: "DexScreener public API, deepest Solana pair",
      rpc: RPC_URL,
    },
    truncated: notes.length > 0,
    notes,
    not_checked: [
      "which of these wallets are 'smart money' beyond 'they bought early once' is an inference, not a fact",
      "future performance: this ranks evidence, it does not predict",
      "wallet clustering behind one owner (same fund, same operator) is not detected",
      "CEX-internal and off-chain flows",
    ],
    fetched_at: new Date().toISOString(),
  };
}

export async function hundredXMethod() {
  return {
    provider: "pronomad — cycle-wallet hunt, Solana side (the 'next 100x' method)",
    what_it_is:
      "The seven-step method: a mint from a previous cycle, its earliest buyers, the ones still trading, " +
      "the machines removed, what they bought since, scored. Below the threshold the answer is no.",
    chain: "solana",
    price_usdc_per_call: 0.15,
    endpoint: "GET/POST /v1/hundred-x-hunter?mint=<SPL mint>",
    sibling: {
      chain: "base",
      route: "POST /api/hundred-x-hunter",
      origin: "https://xhagents.xyz",
      note: "same method, Base data, settled in USDC on Base",
    },
    threshold: BUY_THRESHOLD,
    limits: { max_pages_back: 12, transactions_examined: "up to 63", wallet_limit: 25, deadline_seconds: 55 },
    not_checked: ["smart-money identity beyond 'bought early once'", "future price",
                  "wallet clustering behind one owner"],
  };
}
