/**
 * hood-sniper · worker/src/index.js
 * Cloudflare Worker — Robinhood Chain discovery radar, x402 paid (USDC on Base).
 *
 * Multi-source aggregation in the WORKER (no Python dependency):
 *   • Arcus REST  /v1/markets        — universe + 24h volume
 *   • Blockscout  /api/v2/contracts  — recent contract deploys on chain 4663
 *   • Robidy.app HTML                — Next.js streaming payload, launch phases
 *
 * Endpoints:
 *   GET /health                       — FREE  liveness probe
 *   GET /.well-known/x402             — FREE  x402scan discovery doc
 *   GET /openapi.json                 — FREE  OpenAPI 3.1 spec
 *   GET /v1/hood-sniper/radar/feed    — FREE  top-N events (no auth, capped)
 *   GET /v1/hood-sniper/radar         — PAID  full ranked radar ($0.005 USDC)
 *   GET /                              — FREE  landing page (HTML)
 *
 * Pricing follows B0x70's 2026 floor ($0.005/call) — shared with b0x402/b0xM4/b0xlight
 * via the constraint that micro-call USDC ticks are the standardized unit.
 */

const CFG = {
  payoutAddress: "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
  bypass:        false,
  usdcContract:  "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  network:       "eip155:8453",
  rpcUrl:        "https://base.gateway.tenderly.co",
  invoiceTTL:    300,
  baseUrl:       "https://hood-sniper.mulberry-boar.workers.dev",
  arcusBase:     "https://api.arcus.xyz",
  blockscoutBase:"https://robinhoodchain.blockscout.com",
  robidyBase:    "https://robidy.app",
  radarTTL:      60,
  freeEventLimit: 5,
};

const PRICES = {
  "/v1/hood-sniper/radar":     5_000,    // $0.005 USDC — discovery listing radar
};

const BAZAAR = {
  "/v1/hood-sniper/radar": {
    info: { input: { type: "http", method: "GET" } },
    schema: {
      type: "object",
      properties: {
        limit:   { type: "integer", default: 25,  description: "Max events to return (default 25)" },
        severity:{ type: "string",  default: "all", description: "Filter: alpha|alert|watch|info|all" },
        source:  { type: "string",  default: "all", description: "Filter: arcus|blockscout|robidy|all" },
      },
    },
  },
};

// Per-isolate state — KV-free for v0.1; CF Workers KV upgrade optional later.
const invoices = new Map();
let radarCache = { payload: null, ts: 0 };

// ───────────────────────── Helpers ──────────────────────────────

function parseAuthHeader(value) {
  const parts = {};
  const re = /(\w+)=(?:"([^"]*)"|([^,\s]+))/g;
  let m;
  while ((m = re.exec(value)) !== null) parts[m[1]] = m[2] ?? m[3];
  return parts;
}

function nowSeconds() { return Math.floor(Date.now() / 1000); }
function nowIso()     { return new Date().toISOString(); }

function makeNonce() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return Array.from(b, x => x.toString(16).padStart(2, "0")).join("");
}

async function fetchJson(url, opts = {}) {
  try {
    const r = await fetch(url, {
      cf: opts.cache ? { cacheTtl: opts.cache } : undefined,
      ...opts,
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (_) { return null; }
}

async function fetchText(url) {
  try {
    const r = await fetch(url, { cf: { cacheTtl: 30 } });
    if (!r.ok) return null;
    return await r.text();
  } catch (_) { return null; }
}

// ─────────────────── Source pollers ─────────────────────────────

async function pollArcus() {
  const data = await fetchJson(`${CFG.arcusBase}/v1/markets`);
  if (!data || !Array.isArray(data.markets)) return [];
  return data.markets.map((m) => ({
    source: "arcus",
    market_id:    m.marketId || "",
    market_name:  m.marketDisplayName || "?",
    status:       (m.status || "").toUpperCase(),
    volume_24h:   Number(m.volume24h || 0),
    oi:           Number(m.openInterest || 0),
    funding:      Number(m.fundingRate || 0),
  }));
}

async function pollBlockscout(limit = 25) {
  const url = `${CFG.blockscoutBase}/api/v2/contracts?filter=solidity%7Cvyper&sort=created_on&order=desc`;
  const data = await fetchJson(url, { cache: 30 });
  if (!data || !Array.isArray(data.items)) return [];
  return data.items.slice(0, limit).map((c) => ({
    source: "blockscout",
    address:  c.hash || "",
    name:     c.name || "(anon)",
    creator:  (c.creator || {}).hash || "",
    compiler: c.compiler || "",
    created_at: c.created_at || "",
  }));
}

async function pollRobidy() {
  const html = await fetchText(CFG.robidyBase);
  if (!html) return [];
  // Pull Next.js streaming payload
  const payloadMatch = html.match(/<script[^>]*>(self\.__next_f\.push[^<]{0,200000})<\/script>/);
  if (!payloadMatch) return [];
  const body = payloadMatch[1];
  const phases = [...body.matchAll(/"name"\s*:\s*"([^"]+)"[^}]*?"startsAt"\s*:\s*"([^"]+)"[^}]*?"endsAt"\s*:\s*"([^"]+)"(?=[^}]*?"price(?:Eth)?"?\s*:\s*"([^"]*)")?/g)]
    .map((m) => ({
      source: "robidy",
      name:      m[1],
      starts_at: m[2],
      ends_at:   m[3],
      price_eth: m[4] || "",
    }));
  return phases;
}

// ─────────────────── Scoring engine ────────────────────────────

function scoreAndDedup(candidates, prevBaseline) {
  const events = [];
  const baselineByMarket = (prevBaseline && prevBaseline.arcusByMarket) || {};
  const baselineStatus   = (prevBaseline && prevBaseline.arcusStatus) || {};

  for (const c of candidates) {
    if (c.source === "arcus") {
      const prevV = baselineByMarket[c.market_id] || 0;
      const prevStatus = baselineStatus[c.market_id];
      let severity = "info";
      const links = [`https://app.arcus.xyz/markets/${c.market_id}`];
      if (prevV > 0 && c.volume_24h >= prevV * 5 && c.volume_24h >= 1000) {
        severity = "watch";
      }
      if (prevStatus && prevStatus !== c.status && c.status === "ONLINE") {
        severity = "alert";
      }
      events.push({
        id:      `arcus-${c.market_id}`,
        ts:      nowIso(),
        source:  c.source,
        kind:    "market_status",
        severity,
        title:   `${c.market_name} (${c.status}) vol24h $${Math.round(c.volume_24h).toLocaleString()}`,
        url:     links[0],
        chain_id: 4663,
        context: c,
      });
    } else if (c.source === "blockscout") {
      events.push({
        id:       `deploy-${c.address}`,
        ts:       c.created_at || nowIso(),
        source:   c.source,
        kind:     "new_contract",
        severity: "alert",
        title:    `New contract: ${c.name}`,
        url:      `${CFG.blockscoutBase}/address/${c.address}`,
        chain_id: 4663,
        context:  c,
      });
    } else if (c.source === "robidy") {
      events.push({
        id:       `robidy-${c.name}-${c.starts_at}`,
        ts:       nowIso(),
        source:   c.source,
        kind:     "robidy_phase",
        severity: "alpha",
        title:    `Robidy launch: ${c.name} (starts ${c.starts_at})`,
        url:      CFG.robidyBase,
        chain_id: 4663,
        context:  c,
      });
    }
  }

  const seen = new Set();
  const dedup = [];
  for (const e of events) {
    if (seen.has(e.id)) continue;
    seen.add(e.id);
    dedup.push(e);
  }
  const order = { alpha: 0, alert: 1, watch: 2, info: 3 };
  dedup.sort((a, b) => (order[a.severity] - order[b.severity]) || (a.ts < b.ts ? 1 : -1));
  return dedup;
}

async function buildRadar() {
  const [arcus, blockscout, robidy] = await Promise.all([
    pollArcus(),
    pollBlockscout(),
    pollRobidy(),
  ]);
  const allCandidates = [
    ...arcus.map((a) => ({ source: "arcus", ...a })),
    ...blockscout.map((b) => ({ source: "blockscout", ...b })),
    ...robidy.map((r) => ({ source: "robidy", ...r })),
  ];
  const prevBaseline = radarCache.payload && radarCache.payload.baseline;
  const events = scoreAndDedup(allCandidates, prevBaseline);

  const newBaseline = {
    arcusByMarket: Object.fromEntries(arcus.map((a) => [a.market_id, a.volume_24h])),
    arcusStatus:   Object.fromEntries(arcus.map((a) => [a.market_id, a.status])),
    ts:            nowIso(),
  };
  const sourcesPolled = [];
  if (arcus.length)      sourcesPolled.push("arcus");
  if (blockscout.length) sourcesPolled.push("blockscout");
  if (robidy.length)     sourcesPolled.push("robidy");

  return {
    generated_at:   nowIso(),
    sources_polled: sourcesPolled,
    events,
    stats: {
      events_total:      events.length,
      alpha:             events.filter((e) => e.severity === "alpha").length,
      alert:             events.filter((e) => e.severity === "alert").length,
      watch:             events.filter((e) => e.severity === "watch").length,
      sources_polled:    sourcesPolled.length,
    },
    baseline: newBaseline,
  };
}

async function getRadarCached() {
  if (radarCache.payload && (Date.now() - radarCache.ts) < CFG.radarTTL * 1000) {
    return radarCache.payload;
  }
  const fresh = await buildRadar();
  radarCache = { payload: fresh, ts: Date.now() };
  return fresh;
}

// ───────────────── x402 payment gate ────────────────────────────

async function verifyTransfer(toAddress, minAmount) {
  const toTopic = "0x" + toAddress.toLowerCase().replace("0x", "").padStart(64, "0");
  const fromBlockReq = await fetch(CFG.rpcUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", method: "eth_blockNumber", params: [], id: 1 }),
  });
  const latestJson = await fromBlockReq.json().catch(() => ({}));
  const latest = parseInt(latestJson.result || "0x0", 16);
  const fromBlock = "0x" + Math.max(0, latest - 1000).toString(16);
  const body = {
    jsonrpc: "2.0",
    method:  "eth_getLogs",
    params: [{
      fromBlock,
      toBlock: "latest",
      address: CFG.usdcContract,
      topics: [
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        null,
        toTopic,
      ],
    }],
    id: 1,
  };
  try {
    const r = await fetch(CFG.rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    for (const log of (data.result || [])) {
      if (parseInt(log.data, 16) >= minAmount) return true;
    }
  } catch (_) {}
  return false;
}

async function checkX402(path, paymentHdr) {
  if (CFG.bypass) return { err: null, paid: true };
  if (!PRICES[path]) return { err: null, paid: true };
  if (!paymentHdr) {
    const nonce  = makeNonce();
    const amount = PRICES[path];
    const resource = CFG.baseUrl + path;
    const extra = { name: "USD Coin", version: "2", bazaar: BAZAAR[path] };

    invoices.set(nonce, {
      _amount:  amount,
      _expires: nowSeconds() + CFG.invoiceTTL,
      scheme:   "exact",
      network:  CFG.network,
      maxAmountRequired: String(amount),
      resource,
      payTo:    CFG.payoutAddress,
      asset:    CFG.usdcContract,
      maxTimeoutSeconds: CFG.invoiceTTL,
    });

    const body = {
      x402Version: 2,
      accepts: [{
        scheme: "exact",
        network: CFG.network,
        maxAmountRequired: String(amount),
        payTo: CFG.payoutAddress,
        asset: CFG.usdcContract,
        maxTimeoutSeconds: CFG.invoiceTTL,
        resource,
        description: `Hood Sniper radar —> ${path}`,
        mimeType: "application/json",
        outputSchema: { type: "object" },
        extra,
      }],
    };
    const hdrPayload = {
      x402Version: 2,
      scheme: "exact",
      network: CFG.network,
      nonce,
      maxAmountRequired: String(amount),
      resource,
      payTo: CFG.payoutAddress,
      asset: CFG.usdcContract,
      maxTimeoutSeconds: CFG.invoiceTTL,
      extra,
    };
    return {
      err: new Response(JSON.stringify(body), {
        status: 402,
        headers: {
          "Content-Type": "application/json",
          "Payment-Required": btoa(JSON.stringify(hdrPayload)),
          "X-Payment-Version": "2",
          "Cache-Control": "no-store",
          "Access-Control-Expose-Headers": "Payment-Required, X-Payment-Version",
        },
      }),
      paid: false,
    };
  }
  const parsed = parseAuthHeader(paymentHdr);
  const inv = invoices.get(parsed.nonce);
  if (!inv) {
    return {
      err: new Response(JSON.stringify({ error: "invalid_nonce" }), {
        status: 402,
        headers: { "Content-Type": "application/json" },
      }),
      paid: false,
    };
  }
  if (nowSeconds() > inv._expires) {
    invoices.delete(parsed.nonce);
    return {
      err: new Response(JSON.stringify({ error: "invoice_expired" }), {
        status: 402,
        headers: { "Content-Type": "application/json" },
      }),
      paid: false,
    };
  }
  const ok = await verifyTransfer(CFG.payoutAddress, inv._amount);
  if (!ok) {
    return {
      err: new Response(JSON.stringify({ error: "payment_not_verified" }), {
        status: 402,
        headers: { "Content-Type": "application/json" },
      }),
      paid: false,
    };
  }
  invoices.delete(parsed.nonce);
  return { err: null, paid: true };
}

// ───────────────── Routing ──────────────────────────────────────

async function handleRequest(request) {
  const url = new URL(request.url);
  const path = url.pathname;
  const params = url.searchParams;
  const paymentHdr = request.headers.get("x-payment");

  // ── favicon
  if (path === "/favicon.ico") {
    const png = Uint8Array.from(
      atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="),
      c => c.charCodeAt(0)
    );
    return new Response(png, { headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=86400" } });
  }

  // ── Landing page
  if (path === "/" || path === "/index.html") {
    return new Response(LANDING_HTML, {
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300" },
    });
  }

  // ── Health
  if (path === "/health") {
    return Response.json({ status: "ok", service: "hood-sniper", version: "0.1.0", time: nowIso() });
  }

  // ── Discovery doc (x402scan)
  if (path === "/.well-known/x402.json" || path === "/.well-known/x402") {
    const resources = Object.keys(PRICES).map((p) => CFG.baseUrl + p);
    return Response.json({
      version: 1,
      resources,
      ownershipProofs: [],
      instructions: "Pay $0.005 USDC on Base per radar call. Hit endpoint without x-payment to receive 402 invoice.",
    });
  }

  // ── OpenAPI doc
  if (path === "/openapi.json") {
    return Response.json(BUILD_OPENAPI());
  }

  // ── Free radar (capped)
  if (path === "/v1/hood-sniper/radar/feed") {
    const radar = await getRadarCached();
    const limit = Math.min(parseInt(params.get("limit") || `${CFG.freeEventLimit}`, 10), 5);
    const sev = (params.get("severity") || "all").toLowerCase();
    let events = radar.events.slice();
    if (sev !== "all") events = events.filter((e) => e.severity === sev);
    events = events.slice(0, limit);
    return Response.json({
      generated_at:   radar.generated_at,
      sources_polled: radar.sources_polled,
      events,
      stats: { ...radar.stats, served: "free_feed", events_total: events.length },
      note: "Free tier — top-N only. Full radar at /v1/hood-sniper/radar ($0.005 USDC each).",
    });
  }

  // ── Paid radar (full)
  if (path === "/v1/hood-sniper/radar") {
    const { err } = await checkX402(path, paymentHdr);
    if (err) return err;
    const radar = await getRadarCached();
    const limit = Math.min(parseInt(params.get("limit") || "25", 10), 100);
    const sev = (params.get("severity") || "all").toLowerCase();
    const src = (params.get("source")  || "all").toLowerCase();
    let events = radar.events.slice();
    if (sev !== "all") events = events.filter((e) => e.severity === sev);
    if (src !== "all") events = events.filter((e) => e.source  === src);
    events = events.slice(0, limit);
    return Response.json({
      generated_at:   radar.generated_at,
      sources_polled: radar.sources_polled,
      events,
      stats: { ...radar.stats, served: "paid_full", events_total: events.length },
      baseline: radar.baseline,
    });
  }

  return Response.json({
    error: "not_found",
    endpoints: ["/health", "/v1/hood-sniper/radar/feed", "/v1/hood-sniper/radar", "/openapi.json", "/.well-known/x402"],
  }, { status: 404 });
}

function BUILD_OPENAPI() {
  return {
    openapi: "3.1.0",
    info: {
      title:       "Hood Sniper — RH Chain Discovery Radar",
      version:     "0.1.0",
      description: "Multi-source Robinhood Chain (chain 4663) discovery radar. Polls Arcus REST, Blockscout new-contract feed, and Robidy.app launchpad. Returns ranked events with severity ladder: alpha > alert > watch > info.",
      contact:     { email: "yusliarifn78@gmail.com" },
      "x-guidance":"GET /v1/hood-sniper/radar/feed for a free top-5 feed. GET /v1/hood-sniper/radar returns the full ranked feed for $0.005 USDC per call. RCS: chain 4663 ETH-style L2 (Arbitrum tech).",
    },
    components: {
      securitySchemes: {
        x402: {
          type: "apiKey", in: "header", name: "x-payment",
          description: "x402 V2 USDC payment payload.",
        },
      },
    },
    paths: {
      "/v1/hood-sniper/radar/feed": {
        get: {
          operationId: "radarFeed", summary: "Free top-N feed",
          tags: ["Radar"], security: [],
          parameters: [
            { name: "limit", in: "query", schema: { type: "integer", default: 5 } },
            { name: "severity", in: "query", schema: { type: "string", default: "all" } },
          ],
          responses: { "200": { description: "OK" } },
        },
      },
      "/v1/hood-sniper/radar": {
        get: {
          operationId: "radarFull", summary: "Full ranked radar",
          description: "Returns every event from all three sources, ranked by severity then recency.",
          tags: ["Radar"],
          security: [{ x402: [] }],
          "x-payment-info": {
            price: { mode: "fixed", currency: "USD", amount: "0.005" },
            protocols: ["x402"], network: CFG.network, asset: CFG.usdcContract,
            payTo: CFG.payoutAddress,
          },
          "x-agent": {
            accepts: [{
              resource:        { uri: `${CFG.baseUrl}/v1/hood-sniper/radar` },
              scheme:          "exact",
              network:         CFG.network,
              asset:           CFG.usdcContract,
              payTo:           CFG.payoutAddress,
              maxTimeoutSeconds: CFG.invoiceTTL,
            }],
          },
          "extensions": {
            bazaar: { schema: BAZAAR["/v1/hood-sniper/radar"].schema },
          },
          parameters: [
            { name: "limit", in: "query", schema: { type: "integer", default: 25 } },
            { name: "severity", in: "query", schema: { type: "string", default: "all" } },
            { name: "source", in: "query", schema: { type: "string", default: "all" } },
          ],
          responses: { "200": { description: "Radar events" }, "402": { description: "Payment Required" } },
        },
      },
    },
  };
}

const LANDING_HTML = `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Hood Sniper — RH Chain Discovery Radar</title><meta name="description" content="Multi-source Robinhood Chain (chain 4663) discovery radar. Real-time listings, contract deploys, launchpad phases. Pay $0.005 USDC per full feed."/><meta property="og:title" content="Hood Sniper — RH Chain Discovery Radar"/><meta property="og:description" content="Multi-source RH Chain listings radar."/><meta property="og:type" content="website"/><meta property="og:url" content="https://hood-sniper.mulberry-boar.workers.dev"/><link rel="icon" href="/favicon.ico" type="image/png"/><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0a0a0a; color:#e5e5e5; line-height:1.6; }
.wrap { max-width:880px; margin:0 auto; padding:64px 24px; }
.badge { display:inline-block; padding:4px 12px; background:#1c1c1c; border:1px solid #2a2a2a; border-radius:999px; font-size:12px; color:#a1a1aa; margin-bottom:24px; font-family:ui-monospace,'SF Mono',monospace; }
h1 { font-size:48px; font-weight:800; line-height:1.1; letter-spacing:-0.03em; color:#fafafa; margin-bottom:16px; }
h1 .accent { background:linear-gradient(135deg,#3b82f6 0%,#8b5cf6 50%,#ec4899 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.sub { font-size:18px; color:#a1a1aa; margin-bottom:48px; max-width:620px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; margin-bottom:48px; }
.card { background:#141414; border:1px solid #262626; border-radius:12px; padding:20px; transition:border-color .15s,transform .15s; text-decoration:none; color:inherit; }
.card:hover { border-color:#3b82f6; transform:translateY(-2px); }
.card h3 { font-size:15px; font-weight:600; color:#fafafa; margin-bottom:6px; font-family:ui-monospace,'SF Mono',monospace; }
.card h3 .method { color:#60a5fa; margin-right:6px; }
.card p { font-size:14px; color:#a1a1aa; }
.price { display:inline-block; margin-top:12px; padding:4px 10px; background:#052e16; color:#4ade80; border:1px solid #14532d; border-radius:6px; font-size:13px; font-family:ui-monospace,monospace; font-weight:600; }
.price.free { background:#0c1d41; color:#60a5fa; border-color:#1e3a8a; }
.section { background:#141414; border:1px solid #262626; border-radius:12px; padding:24px; margin-bottom:16px; }
.section h2 { font-size:16px; font-weight:700; color:#fafafa; margin-bottom:14px; font-family:ui-monospace,monospace; }
.section ul { list-style:none; padding-left:0; }
.section ul li { padding:4px 0; padding-left:20px; position:relative; color:#a1a1aa; font-size:14px; }
.section ul li::before { content:"→"; position:absolute; left:0; color:#52525b; }
.tag { display:inline-block; font-family:ui-monospace,monospace; font-size:11px; padding:2px 8px; background:#1c1c1c; border-radius:4px; color:#71717a; margin-right:6px; }
.footer { margin-top:56px; padding-top:24px; border-top:1px solid #1f1f1f; font-size:13px; color:#52525b; display:flex; justify-content:space-between; flex-wrap:wrap; gap:12px; }
</style></head><body><div class="wrap">
<span class="badge">● OPERATIONAL · RH Chain (chain 4663) · x402 V2</span>
<h1><span class="accent">Hood Sniper</span><br/>RH Chain discovery radar.</h1>
<p class="sub">Aggregator router across Arcus REST, Blockscout new-contract feed, and Robidy launchpad. Real-time listings, deployments, and launchpad windows on Robinhood Chain.</p>
<div class="grid">
<a class="card" href="/v1/hood-sniper/radar/feed"><h3><span class="method">GET</span>/v1/hood-sniper/radar/feed</h3><p>Free top-N feed — last 5 events by severity. Capped preview for trial.</p><span class="price free">FREE · 5 events</span></a>
<a class="card" href="/v1/hood-sniper/radar"><h3><span class="method">GET</span>/v1/hood-sniper/radar</h3><p>Full ranked radar from all three sources. Filter by severity & source.</p><span class="price">$0.005 USDC / call</span></a>
</div>
<div class="section"><h2>Severity ladder</h2>
<ul>
<li><strong style="color:#a855f7">alpha</strong> &mdash; Robidy launchpad phases or multi-source corroboration.</li>
<li><strong style="color:#f87171">alert</strong> &mdash; Status flip OFFLINE&rarr;ONLINE / new contract deploys in the last 24h.</li>
<li><strong style="color:#facc15">watch</strong> &mdash; 24h volume greater than 5&times; baseline AND greater than $1k.</li>
<li><strong style="color:#71717a">info</strong> &mdash; Baseline-only signal (every market listed this tick).</li>
</ul></div>
<div class="section"><h2>Quick example</h2>
<p class="sub" style="margin-bottom:0;font-size:14px;"><code>curl -i https://hood-sniper.mulberry-boar.workers.dev/v1/hood-sniper/radar/feed</code> &rarr; HTTP 200 + JSON event list</p>
<p style="margin-top:14px;font-size:14px;">OpenAPI: <a href="/openapi.json" style="color:#60a5fa">/openapi.json</a> &middot; Discovery: <a href="/.well-known/x402" style="color:#60a5fa">/.well-known/x402</a></p>
</div>
<div class="footer"><div>Built by <strong>b0x70</strong> &middot; autonomous seller agent</div><div><span class="tag">x402 V2</span><span class="tag">chain 4663</span><span class="tag">USDC</span><span class="tag">no API key</span></div></div>
</div></body></html>`;

export default {
  async fetch(request, env, ctx) {
    if (env.X402_PAYOUT_ADDRESS) CFG.payoutAddress = env.X402_PAYOUT_ADDRESS;
    if (env.X402_BYPASS !== undefined) CFG.bypass = env.X402_BYPASS === "true";
    if (env.RADAR_TTL_SECONDS)    CFG.radarTTL = parseInt(env.RADAR_TTL_SECONDS, 10);
    if (env.RADAR_FREE_EVENT_LIMIT) CFG.freeEventLimit = parseInt(env.RADAR_FREE_EVENT_LIMIT, 10);
    if (env.ARCUS_BASE_URL)        CFG.arcusBase = env.ARCUS_BASE_URL;
    if (env.BLOCKSCOUT_BASE_URL)   CFG.blockscoutBase = env.BLOCKSCOUT_BASE_URL;
    if (env.ROBIDY_BASE_URL)       CFG.robidyBase = env.ROBIDY_BASE_URL;
    return handleRequest(request);
  },
};
