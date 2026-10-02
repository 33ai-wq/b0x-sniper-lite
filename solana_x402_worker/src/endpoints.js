/**
 * src/endpoints.js - 6 paid endpoint handlers for Solana x402 Worker
 *
 * Endpoints (parallel to existing Base CF worker + 2 new):
 *   GET  /v1/meme-hunter      — Solana meme-coin signals from DexScreener
 *   GET  /v1/defi-sentiment   — Solana DeFi market mood signal
 *   POST /v1/dinalibrium      — Solana stablecoin ratios + TVL
 *   GET  /v1/wallet-profile   — Solana wallet on-chain profile
 *   GET  /v1/b0x402-data       — Multichain live gas prices (Solana + Base + ETH + Arbitrum)
 *   GET  /v1/honeypot-check   — Solana SPL token honeypot check (mint/freeze auth)
 */

const fetchFn = globalThis.fetch || (await import("node-fetch")).default;
const SOLSCAN_BASE = "https://public-api.solscan.io";
const DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex";

// ── 1. /v1/meme-hunter ──────────────────────────────────────────────
export async function memeHunter(params) {
  const limit = Math.min(parseInt(params.limit || "10"), 50);
  const sortBy = params.sort_by || "score";
  try {
    const resp = await fetchFn(
      `${DEXSCREENER_BASE}/search?q=solana&limit=100`
    );
    const data = await resp.json();
    const pairs = (data.pairs || []).filter((p) => p?.chainId === "solana");

    const signals = pairs
      .map((p) => {
        try {
          const base = p.baseToken || {};
          const priceUsd = parseFloat(p.priceUsd || 0);
          const change = parseFloat(p.priceChange?.h24 || 0);
          const volume = parseFloat(p.volume?.h24 || 0);
          const liquidity = parseFloat(p.liquidity?.usd || 0);
          const score = Math.min(
            100,
            Math.abs(change) * 0.5 + liquidity / 1000 + volume / 500
          );
          return {
            token_address: base.address || "",
            name: base.name || "Unknown",
            symbol: base.symbol || "??",
            price_usd: parseFloat(priceUsd.toFixed(priceUsd < 0.001 ? 8 : 4)),
            change_24h_pct: parseFloat(change.toFixed(2)),
            volume_24h: parseFloat(volume.toFixed(2)),
            liquidity_usd: parseFloat(liquidity.toFixed(2)),
            pair_created: p.pairCreatedAt || null,
            dex: p.dexId || "unknown",
            boosted: !!p.boosted,
            score: parseFloat(score.toFixed(1)),
            link: `https://dexscreener.com/solana/${base.address || ""}`,
          };
        } catch (_) {
          return null;
        }
      })
      .filter(Boolean);

    const sortFns = {
      volume: (s) => s.volume_24h,
      change: (s) => Math.abs(s.change_24h_pct),
      liquidity: (s) => s.liquidity_usd,
      score: (s) => s.score,
      boosted: (s) => (s.boosted ? 1 : 0),
    };
    const fn = sortFns[sortBy] || sortFns.score;
    signals.sort((a, b) => fn(b) - fn(a));

    return {
      count: signals.length,
      signals: signals.slice(0, limit),
      fetched_at: new Date().toISOString(),
      chain: "solana",
    };
  } catch (e) {
    return { count: 0, signals: [], error: e.message, chain: "solana" };
  }
}

// ── 2. /v1/defi-sentiment ───────────────────────────────────────────
export async function defiSentiment(params) {
  const topic = params.topic || "solana";
  // Solana-specific sentiment: combine SOL price action + DEX volume trends
  try {
    const solResp = await fetchFn(
      "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
    );
    const solData = await solResp.json();
    const sol = solData?.solana || {};
    const change24h = sol.usd_24h_change || 0;
    const vol24h = sol.usd_24h_vol || 0;

    let signal = "neutral";
    let score = 0.5;
    if (change24h > 5) { signal = "bullish"; score = Math.min(0.95, 0.6 + change24h / 50); }
    else if (change24h < -5) { signal = "bearish"; score = Math.max(0.05, 0.4 + change24h / 50); }
    else if (vol24h > 1_000_000_000) { signal = "active"; score = 0.65; }

    return {
      signal,
      score: parseFloat(score.toFixed(3)),
      timestamp: new Date().toISOString(),
      data: { topic, sol_change_24h_pct: change24h, sol_volume_24h_usd: vol24h },
      chain: "solana",
    };
  } catch (e) {
    return { signal: "neutral", score: 0.5, timestamp: new Date().toISOString(), chain: "solana", error: e.message };
  }
}

// ── 3. /v1/dinalibrium (POST) ──────────────────────────────────────
export async function dinalibrium(body) {
  const stablecoin = body?.stablecoin || "USDC";
  const window = body?.window || "7d";
  try {
    // Query CoinGecko for SOL + stablecoin ratios
    const coins = stablecoin === "USDC" ? "solana,usd-coin,tether" : "solana,usd-coin";
    const resp = await fetchFn(
      `https://api.coingecko.com/api/v3/simple/price?ids=${coins}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true`
    );
    const data = await resp.json();

    const sol = data.solana || {};
    const usdc = data["usd-coin"] || {};
    const solStableRatio = sol.usd / (usdc.usd || 1);

    return {
      sol_stablecoin_ratio: parseFloat(solStableRatio.toFixed(4)),
      sol_change_24h_pct: sol.usd_24h_change || 0,
      stablecoin_supply_change_pct_7d: 0, // CoinGecko free tier doesn't supply this
      timestamp: new Date().toISOString(),
      window,
      stablecoin,
      chain: "solana",
    };
  } catch (e) {
    return {
      sol_stablecoin_ratio: 0,
      timestamp: new Date().toISOString(),
      window,
      stablecoin,
      chain: "solana",
      error: e.message,
    };
  }
}

// ── 4. /v1/wallet-profile ──────────────────────────────────────────
export async function walletProfile(params) {
  const address = params.address;
  if (!address) return { error: "missing_address" };
  try {
    // Use public Solana RPC (no API key needed for basic queries)
    const resp = await fetchFn(config.rpc.mainnet, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "getAccountInfo",
        params: [address, { encoding: "jsonParsed" }],
      }),
    });
    const acc = (await resp.json())?.result?.value;
    if (!acc) return { error: "address_not_found", address };

    // Get transaction count
    const txCountResp = await fetchFn(config.rpc.mainnet, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0", id: 2, method: "getSignaturesForAddress",
        params: [address, { limit: 1000 }],
      }),
    });
    const sigs = (await txCountResp.json())?.result || [];

    return {
      address,
      lamports: acc.lamports,
      sol_balance: parseFloat((acc.lamports / 1e9).toFixed(6)),
      owner: acc.owner,
      executable: acc.executable,
      rent_epoch: acc.rentEpoch,
      tx_count_sampled: sigs.length,
      first_seen: sigs.length > 0 ? null : null, // need deeper query for first_seen
      last_seen: sigs.length > 0 ? sigs[0]?.blockTime : null,
      timestamp: new Date().toISOString(),
      chain: "solana",
    };
  } catch (e) {
    return { error: e.message, address, chain: "solana" };
  }
}

// ── 5. /v1/b0x402-data — Multichain live gas prices ───────────────
export async function b0x402Data(params) {
  const chains = (params.chains || "solana,base,ethereum,arbitrum").split(",");
  const results = {};

  await Promise.all(chains.map(async (chain) => {
    try {
      if (chain === "solana") {
        const resp = await fetchFn(config.rpc.mainnet, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0", id: 1, method: "getRecentBlockhash",
            params: [],
          }),
        });
        const data = await resp.json();
        const feesPerSig = data?.result?.feeCalculator?.lamportsPerSignature || 5000;
        results.solana = {
          chain: "solana",
          base_fee_lamports: feesPerSig,
          base_fee_sol: parseFloat((feesPerSig / 1e9).toFixed(9)),
          priority_fee_lamports: 0,
          unit: "lamports",
          timestamp: new Date().toISOString(),
        };
      } else if (chain === "base" || chain === "ethereum" || chain === "arbitrum") {
        // Use public RPC for EVM chains
        const rpcUrls = {
          base:      "https://mainnet.base.org",
          ethereum:  "https://eth.llamarpc.com",
          arbitrum:  "https://arb1.arbitrum.io/rpc",
        };
        const resp = await fetchFn(rpcUrls[chain], {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0", id: 1, method: "eth_gasPrice", params: [],
          }),
        });
        const data = await resp.json();
        const gasWei = BigInt(data.result || "0x0");
        const gasGwei = Number(gasWei / 1000000000n);
        results[chain] = {
          chain,
          gas_price_wei: gasWei.toString(),
          gas_price_gwei: gasGwei,
          unit: "gwei",
          timestamp: new Date().toISOString(),
        };
      }
    } catch (e) {
      results[chain] = { chain, error: e.message };
    }
  }));

  return {
    multichain_gas: results,
    fetched_at: new Date().toISOString(),
  };
}

// ── 6. /v1/honeypot-check — Solana SPL token honeypot detection ──
export async function honeypotCheck(params) {
  const mintAddress = params.mint;
  if (!mintAddress) return { error: "missing_mint" };
  try {
    // Query Solana RPC for mint account info
    const resp = await fetchFn(config.rpc.mainnet, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0", id: 1, method: "getAccountInfo",
        params: [mintAddress, { encoding: "jsonParsed" }],
      }),
    });
    const mintInfo = (await resp.json())?.result?.value;
    if (!mintInfo) return { mint: mintAddress, is_honeypot: false, reason: "mint_not_found" };

    const parsed = mintInfo.data?.parsed?.info;
    if (!parsed) return { mint: mintAddress, is_honeypot: false, reason: "not_spl_mint" };

    // Honeypot red flags:
    // 1. Mint authority still enabled (creator can print more tokens)
    // 2. Freeze authority still enabled (creator can freeze wallets)
    // 3. Supply concentration (large holders)
    const hasMintAuthority = !!parsed.mintAuthority;
    const hasFreezeAuthority = !!parsed.freezeAuthority;

    const riskFlags = [];
    if (hasMintAuthority) riskFlags.push("mint_authority_active");
    if (hasFreezeAuthority) riskFlags.push("freeze_authority_active");

    const isHoneypot = riskFlags.length >= 2;

    return {
      mint: mintAddress,
      is_honeypot: isHoneypot,
      risk_flags: riskFlags,
      mint_authority: parsed.mintAuthority || null,
      freeze_authority: parsed.freezeAuthority || null,
      supply: parsed.supply,
      decimals: parsed.decimals,
      timestamp: new Date().toISOString(),
      chain: "solana",
    };
  } catch (e) {
    return { mint: mintAddress, error: e.message, chain: "solana" };
  }
}
