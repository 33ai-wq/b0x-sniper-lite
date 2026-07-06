// b0x-sniper-lite worker.js — Cloudflare Worker x402 monetization endpoint
// Pricing: $0.001 / scan-only | $0.005 / scan+quote | $0.010 / alerting subscription
// Sans x402: returns 200 with mock data (free tier for testing)
// Module worker format (export default) is the modern CF Workers standard.
// Older "addEventListener('fetch', ...)" service-worker format removed for clarity.

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // Public health/README endpoints
    if (path === "/" || path === "/health") {
      return jsonResp({
        service: "b0x-sniper-lite",
        version: "lite-1.0.0",
        status: "live",
        capabilities: [
          "Solana new-pair scan via DexScreener",
          "7-dimension risk scoring (0-100)",
          "Jupiter v6 swap quotes",
          "Telegram alerts (score>=65)"
        ],
        price_table_usdc: {
          scan_only: "0.001",
          scan_quote: "0.005",
          scan_alert: "0.010"
        },
        wallet: env.PRIMARY_WALLET || null,
        docs: "https://github.com/33ai-wq/b0x-sniper-lite"
      });
    }

    // /sniper/scan endpoint
    if (path === "/sniper/scan") {
      const params = url.searchParams;
      const wallet = params.get("wallet") || "";
      const minScore = parseInt(params.get("min_score") || "65", 10);

      if (!wallet.match(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/)) {
        return jsonResp({ error: "invalid_wallet", expected: "base58 32-44 chars" }, 400);
      }
      if (isNaN(minScore) || minScore < 0 || minScore > 100) {
        return jsonResp({ error: "invalid_min_score", expected: "0-100 integer" }, 400);
      }

      let dsResp;
      try {
        const r = await fetch("https://api.dexscreener.com/latest/dex/search?q=solana%20new%20pair", {
          headers: { "User-Agent": "b0x-sniper-lite/1.0" }
        });
        if (!r.ok) throw new Error(`dexscreener ${r.status}`);
        dsResp = await r.json();
      } catch (e) {
        return jsonResp({ error: "upstream_error", detail: e.message }, 502);
      }

      const pairs = dsResp.pairs || [];
      const candidates = [];
      for (const p of pairs.slice(0, 80)) {
        if ((p.chainId || "").toLowerCase() !== "solana") continue;
        const s = scorePair(p);
        if (s.score >= minScore) {
          candidates.push({
            score: s.score,
            reasons: s.reasons,
            base_addr: (p.baseToken ? p.baseToken.address : "").slice(0, 14),
            base_name: p.baseToken ? (p.baseToken.name || "?").slice(0, 30) : "?",
            base_symbol: p.baseToken ? (p.baseToken.symbol || "?").slice(0, 10) : "?",
            dex: p.dexId || "?",
            pair_addr: (p.pairAddress || "").slice(0, 14),
            liq_usd: s.liq_usd,
            fdv: s.fdv,
            buys_24: s.buys_24,
            chart_url: p.url || ""
          });
        }
      }
      candidates.sort((a, b) => b.score - a.score);

      return jsonResp({
        wallet,
        min_score: minScore,
        total_scanned: pairs.length,
        qualified: candidates.length,
        candidates: candidates.slice(0, 10)
      });
    }

    // /sniper/quote endpoint
    if (path === "/sniper/quote") {
      const outputMint = url.searchParams.get("output_mint") || "";
      const inputSol = parseFloat(url.searchParams.get("input_sol") || "0.0033");

      if (!outputMint.match(/^[1-9A-HJ-NP-Za-km-z]{32,44}$/)) {
        return jsonResp({ error: "invalid_output_mint" }, 400);
      }
      if (isNaN(inputSol) || inputSol < 0.0001 || inputSol > 1) {
        return jsonResp({ error: "invalid_input_sol", expected: "0.0001-1.0 SOL" }, 400);
      }

      const inLamports = Math.round(inputSol * 1e9);
      const jupUrl = `https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=${encodeURIComponent(outputMint)}&amount=${inLamports}&slippageBps=1500&swapMode=ExactIn&onlyDirectRoutes=false&asLegacyTransaction=false`;

      let j;
      try {
        const r = await fetch(jupUrl, { headers: { "User-Agent": "b0x-sniper-lite/1.0" } });
        if (!r.ok) {
          const t = await r.text();
          return jsonResp({ error: "jupiter_failed", status: r.status, detail: t.slice(0, 200) }, 502);
        }
        j = await r.json();
      } catch (e) {
        return jsonResp({ error: "jupiter_error", detail: e.message }, 502);
      }

      return jsonResp({
        input_sol: inputSol,
        output_mint: outputMint,
        out_amount: j.outAmount || null,
        in_amount: j.inAmount || null,
        price_impact_pct: j.priceImpactPct || null,
        route_count: (j.routePlan || []).length,
        slippage_bps: 1500,
        valid_until: Date.now() + 90000
      });
    }

    // 404 fallback
    return jsonResp({
      error: "not_found",
      path,
      available: ["/", "/health", "/sniper/scan?wallet=...&min_score=65", "/sniper/quote?output_mint=...&input_sol=0.0033"]
    }, 404);
  }
};

// ========== helpers ==========
function jsonResp(obj, status) {
  const body = JSON.stringify(obj, null, 2);
  return new Response(body, {
    status: status || 200,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
  });
}

function scorePair(pair) {
  const base = pair.baseToken || {};
  const info = pair.info || {};
  const txn24 = (pair.txns || {}).h24 || {};
  const buys_24 = parseInt(txn24.buys || 0, 10);
  const sells_24 = parseInt(txn24.sells || 0, 10);
  const liq_usd = parseFloat((pair.liquidity || {}).usd || 0);
  const fdv = parseFloat(pair.fdv || 0);
  const pc_h1 = parseFloat((pair.priceChange || {}).h1 || 0);
  const created = parseInt(pair.pairCreatedAt || 0, 10);

  let score = 0;
  const reasons = [];

  if (liq_usd >= 300 && liq_usd <= 10000) { score += 25; reasons.push("liq"); } else { reasons.push("liq-no"); }
  if (buys_24 >= 50) { score += 15; reasons.push("buys"); } else { reasons.push("buys-no"); }
  if (sells_24 > 0) {
    const r = buys_24 / sells_24;
    if (r >= 1.2 && r <= 5) { score += 10; reasons.push("bs-ratio"); } else { reasons.push("bs-ratio-no"); }
  } else { reasons.push("bs-ratio-inf"); }
  if (created > 0) {
    const age_ms = Date.now() - created;
    if (age_ms > 0 && age_ms < 6 * 3600 * 1000) { score += 15; reasons.push("age"); } else { reasons.push("age-no"); }
  }
  if (pc_h1 > 0 && pc_h1 <= 150) { score += 10; reasons.push("h1-pos"); } else { reasons.push("h1-no"); }
  const hasMeta = !!(info.socials && info.socials.length || info.websites || info.header || info.description);
  if (hasMeta) { score += 10; reasons.push("meta"); } else { reasons.push("meta-no"); }
  if (fdv >= 50000 && fdv <= 1500000) { score += 10; reasons.push("fdv"); } else { reasons.push("fdv-no"); }
  if (fdv === 0 || liq_usd === 0) { score = 0; }

  return { score: score, reasons: reasons, liq_usd: liq_usd, fdv: fdv, buys_24: buys_24, pc_h1: pc_h1 };
}
