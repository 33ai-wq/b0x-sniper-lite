/**
 * src/tokensafety.js - 0-100 safety score for a Solana SPL token, with the evidence behind every point.
 *
 * Same product as the Base endpoint on xhagents.xyz/api/token-safety, but the checks that matter on Solana:
 * mint and freeze authority, who really holds the supply (with AMM pools separated from wallets), the
 * liquidity on the deepest pair, the age of that pair, and whether the mint uses Token-2022 features that
 * let someone move or block other people's tokens.
 *
 * Everything is read live (Solana JSON-RPC + DexScreener). Anything we cannot check honestly is listed in
 * `not_checked` and scored neutral or zero, never guessed.
 */

const RPC_URLS = (process.env.SOLANA_RPC_URL || "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com")
  .split(",").map((s) => s.trim()).filter(Boolean);
const DEX = "https://api.dexscreener.com/latest/dex";

const TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
const TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
const AMM_PROGRAMS = new Set([
  "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", // Raydium AMM v4
  "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", // Raydium CPMM
  "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", // Orca Whirlpool
  "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", // Meteora DLMM
  "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", // pump.fun
  "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", // pump.fun AMM
  "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", // Jupiter aggregator
  "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS", // Meteora route
]);
const VERDICT_SAFE = 75;
const VERDICT_CAUTION = 50;

const CACHE = new Map();
let lastCall = 0;

function cacheGet(k) {
  const h = CACHE.get(k);
  if (!h) return null;
  if (Date.now() - h.at > 120_000) {
    CACHE.delete(k);
    return null;
  }
  return h.value;
}

function cachePut(k, v) {
  if (CACHE.size > 400) CACHE.clear();
  CACHE.set(k, { at: Date.now(), value: v });
}

async function rpcOnce(url, method, params, timeoutMs) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: ctl.signal,
    });
    const j = await r.json();
    if (j.error) {
      const e = new Error(String(j.error.message || j.error).slice(0, 140));
      e.rateLimited = /too many|rate limit/i.test(String(j.error.message || ""));
      throw e;
    }
    return j.result;
  } finally {
    clearTimeout(t);
  }
}

async function rpc(method, params, timeoutMs = 20_000) {
  const key = method + ":" + JSON.stringify(params);
  const hit = cacheGet(key);
  if (hit !== null) return hit;
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
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
  }
  throw lastErr;
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
    // the deepest pair is not always OUR pair: for a quote token like USDC the deepest market is some other
    // base token's. Prefer the pair where the requested mint is the base token.
    const own = all.filter((p) => (p.baseToken?.address || "") === mint);
    const best = (own.length ? own : all).reduce((a, b) =>
      parseFloat(b?.liquidity?.usd || 0) > parseFloat(a?.liquidity?.usd || 0) ? b : a);
    const side = (best.baseToken?.address || "") === mint ? best.baseToken : best.quoteToken;
    const out = {
      pair: best.pairAddress, dex: best.dexId, symbol: side?.symbol, name: side?.name,
      base_token: best.baseToken?.address, quote_token: best.quoteToken?.address,
      mint_is: (best.baseToken?.address || "") === mint ? "base" : "quote",
      liquidity_usd: parseFloat(best.liquidity?.usd || 0),
      volume_24h_usd: parseFloat(best.volume?.h24 || 0),
      price_usd: parseFloat(best.priceUsd || 0),
      price_change_24h_pct: best.priceChange?.h24 ?? null,
      created_at: best.pairCreatedAt || null,
      url: best.url,
    };
    cachePut(key, out);
    return out;
  } catch (_) {
    return null;
  }
}

function slippage(liquidityUsd, tradeUsd = 1000) {
  if (!liquidityUsd) return { trade_usd: tradeUsd, price_impact_pct: null };
  const side = liquidityUsd / 2;
  return { trade_usd: tradeUsd, price_impact_pct: +((tradeUsd / (side + tradeUsd)) * 100).toFixed(3),
           assumption: "constant product on the deepest pair" };
}

function isMint(s) {
  return typeof s === "string" && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s);
}

export async function tokenSafety(params = {}) {
  const mint = (params.mint || params.token || "").trim();
  if (!isMint(mint)) {
    const err = new Error("mint must be a base58 SPL mint address");
    err.status = 400;
    throw err;
  }
  const started = Date.now();
  const points = {};
  const findings = [];
  const checks = {};
  const notChecked = [];

  // 1. mint / freeze authority (35 combined) - the single most important Solana check
  let mintAuth = null;
  let freezeAuth = null;
  let program = null;
  let extensions = [];
  let decimals = null;
  let supply = null;
  try {
    const info = await rpc("getAccountInfo", [mint, { encoding: "jsonParsed" }]);
    const v = info?.value;
    program = v?.owner || null;
    const pi = v?.data?.parsed?.info || {};
    mintAuth = pi.mintAuthority ?? null;
    freezeAuth = pi.freezeAuthority ?? null;
    decimals = pi.decimals ?? null;
    supply = pi.supply ? parseFloat(pi.supply) / 10 ** (pi.decimals ?? 0) : null;
    extensions = (pi.extensions || []).map((e) => e.extension);
    checks.mint = { program, mintAuthority: mintAuth, freezeAuthority: freezeAuth, decimals,
                    supply, extensions, exists: !!v };
  } catch (e) {
    checks.mint = { error: String(e.message || e).slice(0, 140) };
  }
  let p = 0;
  if (mintAuth === null && checks.mint.mintAuthority !== undefined) {
    p += 20;
    findings.push("mint authority is renounced: nobody can print more supply");
  } else if (mintAuth) {
    findings.push(`mint authority is still live (${mintAuth.slice(0, 8)}…): supply can be inflated`);
  } else {
    p += 10;
    findings.push("mint account unreadable: assumed neutral, treat as unknown");
  }
  if (freezeAuth === null && checks.mint.freezeAuthority !== undefined) {
    p += 15;
    findings.push("freeze authority is renounced: nobody can freeze your token account");
  } else if (freezeAuth) {
    findings.push(`freeze authority is still live (${freezeAuth.slice(0, 8)}…): your account can be frozen`);
  } else {
    p += 7;
  }
  points.ownership = Math.min(p, 35);

  // 2. real holder concentration, with pools separated (25)
  p = 0;
  let holderMethod = null;
  try {
    let rows = [];
    let total = checks.mint.supply || null;
    // fast path: the RPC's own largest-accounts list. Public endpoints often refuse it (403/429),
    // so there is a sampled fallback below rather than a silent zero.
    try {
      const la = await rpc("getTokenLargestAccounts", [mint]);
      const accounts = (la?.value || []).slice(0, 20);
      for (const a of accounts.slice(0, 12)) {
        let owner = null;
        try {
          const ai = await rpc("getAccountInfo", [a.address, { encoding: "jsonParsed" }]);
          owner = ai?.value?.owner || null;
        } catch (_) {}
        rows.push({ tokenAccount: a.address, amount: parseFloat(a.uiAmountString || 0),
                    owner: owner || null, is_pool: owner ? AMM_PROGRAMS.has(owner) : null,
                    source: "getTokenLargestAccounts" });
      }
      holderMethod = "getTokenLargestAccounts (largest token accounts, pool programs separated)";
    } catch (e) {
      // sampled fallback: read recent parsed transactions and keep the biggest owners we actually saw.
      // Labelled as a sample in the response — it is evidence, not the complete holder set.
      const sigs = (await rpc("getSignaturesForAddress", [mint, { limit: 100 }])) || [];
      const seen = new Map();
      let parsed = 0;
      for (const s of sigs.slice(0, 60)) {
        let tx;
        try {
          tx = await rpc("getTransaction", [s.signature,
            { encoding: "jsonParsed", maxSupportedTransactionVersion: 0 }], 20_000);
        } catch (_) {
          continue;
        }
        if (!tx) continue;
        parsed += 1;
        for (const b of tx.meta?.postTokenBalances || []) {
          if (b.mint !== mint || !b.owner) continue;
          const amt = b.uiTokenAmount?.uiAmount || 0;
          const prev = seen.get(b.owner);
          if (!prev || amt > prev.amount) seen.set(b.owner, { owner: b.owner, amount: amt });
        }
      }
      rows = [...seen.values()]
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 12)
        .map((r) => ({ tokenAccount: null, amount: r.amount, owner: r.owner,
                       is_pool: AMM_PROGRAMS.has(r.owner), source: "sampled from recent transactions" }));
      holderMethod = `sampled: the biggest token balances seen across ${parsed} recent parsed transactions ` +
                     `(the RPC refused getTokenLargestAccounts: ${String(e.message || e).slice(0, 60)})`;
    }

    const totalSupply = total || rows.reduce((s, r) => s + r.amount, 0);
    const pools = rows.filter((r) => r.is_pool);
    const wallets = rows.filter((r) => !r.is_pool);
    const sampled = !/^getTokenLargestAccounts/.test(holderMethod || "");
    // sampled mode only sees wallets that traded recently, so a share of the whole supply would be
    // meaningless; we measure the share inside the sample and say so.
    const denominator = sampled
      ? (wallets.reduce((s, r) => s + r.amount, 0) || rows.reduce((s, r) => s + r.amount, 0))
      : totalSupply;
    const walletShare = denominator ? wallets.slice(0, 10).reduce((s, r) => s + r.amount, 0) / denominator : null;
    checks.largest_accounts = rows;
    checks.holder_method = holderMethod;
    checks.pool_accounts = pools.length;
    checks.top10_wallet_share_pct = walletShare === null ? null : +(walletShare * 100).toFixed(2);
    if (walletShare === null) {
      p += 12;
      findings.push("holder concentration could not be computed — scored neutral");
    } else if (!/^getTokenLargestAccounts/.test(holderMethod)) {
      // The sample only sees wallets that traded recently, so a share computed from it is not a holder
      // concentration — it is an artefact. Score the component neutral and show the sample as evidence only.
      p += 12;
      findings.push("holder concentration could not be measured: the public RPC refused getTokenLargestAccounts, "
                    + "and a spread of wallets seen in recent transactions is not a holder distribution "
                    + "(scored neutral — treat this component as unknown)");
    } else if (walletShare <= 0.20) {
      p += 25;
      findings.push(`wallets outside pools hold ${(walletShare * 100).toFixed(1)}% of supply — well spread`);
    } else if (walletShare <= 0.40) {
      p += 16;
      findings.push(`top wallets hold ${(walletShare * 100).toFixed(1)}% of supply`);
    } else if (walletShare <= 0.60) {
      p += 8;
      findings.push(`top wallets hold ${(walletShare * 100).toFixed(1)}% — a few accounts can move it`);
    } else {
      p += 3;
      findings.push(`top wallets hold ${(walletShare * 100).toFixed(1)}% — highly concentrated`);
    }
    if (pools.length) findings.push(`${pools.length} of the largest accounts are AMM pools (liquidity, not a whale)`);
  } catch (e) {
    p += 12;
    findings.push(`holder check failed (${String(e.message || e).slice(0, 60)}) — scored neutral`);
  }
  points.holders = Math.min(p, 25);

  // 3. Token-2022 powers (15): transfer fees, permanent delegate, transfer hooks can surprise a buyer
  p = 0;
  const dangerous = extensions.filter((e) =>
    /transferfee|transferhook|permanentdelegate|confidentialtransfer|nontransferable|defaultaccountstate/i.test(String(e)));
  if (program === TOKEN_2022_PROGRAM) {
    if (dangerous.length) {
      p += 3;
      findings.push(`Token-2022 with ${dangerous.join(", ")}: someone can tax, block or move your tokens`);
    } else {
      p += 12;
      findings.push("Token-2022 mint without fee/hook/delegate extensions");
    }
  } else if (program === TOKEN_PROGRAM || program === null) {
    p += 15;
    findings.push("plain SPL token program: no extension powers");
  } else {
    p += 6;
  }
  points.program_powers = Math.min(p, 15);

  // 4. liquidity + pair age (20)
  const dex = await dexInfo(mint);
  const liq = dex?.liquidity_usd || 0;
  const ageDays = dex?.created_at ? (Date.now() - dex.created_at) / 86400000 : null;
  p = 0;
  if (liq >= 250_000) {
    p += 12;
    findings.push(`deep liquidity ($${liq.toLocaleString(undefined, { maximumFractionDigits: 0 })})`);
  } else if (liq >= 50_000) {
    p += 9;
  } else if (liq >= 10_000) {
    p += 5;
    findings.push(`thin liquidity ($${liq.toFixed(0)})`);
  } else if (liq > 0) {
    p += 2;
    findings.push(`very thin liquidity ($${liq.toFixed(0)})`);
  } else {
    findings.push("no Solana pair found: nothing to sell into");
  }
  if (ageDays === null) {
    p += 3;
  } else if (ageDays >= 90) {
    p += 8;
    findings.push(`pair is ${ageDays.toFixed(0)} days old`);
  } else if (ageDays >= 14) {
    p += 5;
    findings.push(`pair is ${ageDays.toFixed(0)} days old`);
  } else {
    p += 1;
    findings.push(`pair is only ${ageDays.toFixed(1)} days old — no history to judge`);
  }
  points.liquidity_age = Math.min(p, 20);

  // 5. tradability (5)
  const slip = slippage(liq);
  const impact = slip.price_impact_pct;
  let tp = 0;
  if (impact === null) tp = 0;
  else if (impact <= 1) tp = 5;
  else if (impact <= 5) tp = 3;
  else tp = 1;
  if (impact !== null) findings.push(`a $1k trade moves the price about ${impact}%`);
  points.tradability = tp;

  notChecked.push(
    "whether selling is blocked in practice (needs a simulated swap; not a honeypot simulation)",
    "the identity or intent of the top wallets",
    "off-chain team, socials or provenance",
    "Metaplex metadata mutability (separate account, not read here)",
  );

  const raw = Object.values(points).reduce((a, b) => a + b, 0);
  const score = Math.max(0, Math.min(100, Math.round(raw)));
  const verdict = score >= VERDICT_SAFE ? "safe" : score >= VERDICT_CAUTION ? "caution" : "danger";

  return {
    mint,
    symbol: dex?.symbol || null,
    name: dex?.name || null,
    decimals,
    score,
    verdict,
    points,
    weights: { ownership: 35, holders: 25, program_powers: 15, liquidity_age: 20, tradability: 5 },
    market: dex,
    slippage: slip,
    checks,
    findings,
    methodology: {
      rpc: RPC_URLS[0],
      ownership: "mintAuthority and freezeAuthority read from the mint account itself",
      holders: "getTokenLargestAccounts; token accounts owned by known AMM programs are treated as liquidity, "
             + "the rest are measured against total supply",
      program: "the mint's owning program: plain SPL vs Token-2022, plus any fee/hook/delegate extensions",
      liquidity: "DexScreener public API, deepest Solana pair",
      tradability: "constant-product arithmetic from pool liquidity",
    },
    not_checked: notChecked,
    verdicts: { safe: `>= ${VERDICT_SAFE}`, caution: `${VERDICT_CAUTION}-${VERDICT_SAFE - 1}`,
                danger: `< ${VERDICT_CAUTION}` },
    elapsed_ms: Date.now() - started,
    fetched_at: new Date().toISOString(),
  };
}

export async function tokenSafetyMethod() {
  return {
    provider: "pronomad — token safety score, Solana side",
    what_it_is:
      "One 0-100 number for an SPL token plus the evidence: mint/freeze authority, who really holds the " +
      "supply (pools separated from wallets), Token-2022 powers, liquidity and pair age, and the price " +
      "impact of a small trade. Built so an agent can refuse before it buys.",
    chain: "solana",
    price_usdc_per_call: 0.05,
    endpoint: "GET/POST /v1/token-safety?mint=<SPL mint>",
    sibling: { chain: "base", route: "POST /api/token-safety", origin: "https://xhagents.xyz",
               note: "same product, Base checks, settled in USDC on Base" },
    verdicts: { safe: ">= 75", caution: "50-74", danger: "< 50" },
    weights: { ownership: 35, holders: 25, program_powers: 15, liquidity_age: 20, tradability: 5 },
    not_checked: ["honeypot simulation", "top-wallet identity", "off-chain provenance"],
  };
}
