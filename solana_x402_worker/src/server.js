/**
 * src/server.js - Express server for Solana x402 Worker
 * Listens on port 3000 (proxied by nginx on 443)
 */
import express from "express";
import helmet from "helmet";
import cors from "cors";
import config, { OPENAPI_PARAMS } from "./config.js";
import {
  issuePaymentRequired,
  verifyPayment,
} from "./payment.js";
import {
  memeHunter,
  defiSentiment,
  dinalibrium,
  walletProfile,
  b0x402Data,
  honeypotCheck,
} from "./endpoints.js";
import { hundredXHunter, hundredXMethod } from "./hundredx.js";
import { tokenSafety, tokenSafetyMethod } from "./tokensafety.js";

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json({ limit: "1mb" }));

// ── Health check ────────────────────────────────────────────────
app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    service: "solana-x402-worker",
    version: "1.0.0",
    treasury: config.treasury,
    network: config.network,
    timestamp: new Date().toISOString(),
  });
});

// ── Discovery endpoint ──────────────────────────────────────────
function sendDiscoveryManifest(res) {
  const entries = Object.entries(config.prices).map(([path, amount]) => ({
    x402Version: 2,
    resource: {
      url: config.baseUrl + path,
      description: `Solana x402 paid endpoint: ${path}`,
      mimeType: "application/json",
    },
    accepts: [{
      scheme: "exact",
      network: config.network,
      amount: String(amount),
      payTo: config.treasury,
      asset: config.usdcMint,
      maxTimeoutSeconds: config.invoiceTtl,
    }],
  }));

  res.json({
    version: 1,
    resources: entries.map((e) => e.resource.url),
    entries,
    info: {
      title: "pronomad Solana x402 Worker",
      description: "AI-powered crypto intelligence on Solana. 7 paid endpoints in USDC via x402 V2 protocol, including the seven-step cycle-wallet hunt ($0.15).",
      tags: ["crypto", "defi", "ai-agent", "x402-v2", "solana", "usdc"],
      homepage: config.baseUrl,
    },
    instructions: "All endpoints require x402 USDC payment on Solana. Hit any path without x-payment header to receive 402 invoice.",
  });
}

app.get("/.well-known/x402", (req, res) => sendDiscoveryManifest(res));
app.get("/.well-known/x402.json", (req, res) => sendDiscoveryManifest(res));
app.get("/x402.json", (req, res) => sendDiscoveryManifest(res));

// ── OpenAPI Spec ────────────────────────────────────────────────
app.get("/openapi.json", (_, res) => {
    const paths = {};
  for (const [path, amount] of Object.entries(config.prices)) {
    const opName = path.split("/").pop();
    const params = OPENAPI_PARAMS[path] || [];
    const isPost = path === "/v1/dinalibrium";
    
    const methodSpec = {
      operationId: opName,
      description: `Solana x402 paid endpoint: ${path}`,
      parameters: params,
      responses: {
        200: { description: "Success", content: { "application/json": { schema: { type: "object" } } } },
        402: { description: "Payment required", content: { "application/json": { schema: { type: "object" } } } },
      },
    };
    if (isPost) {
      methodSpec.requestBody = {
        required: false,
        content: {
          "application/json": {
            schema: {
              type: "object",
              properties: {
                stablecoin: { type: "string", default: "USDC", description: "USDC | USDT | DAI" },
                window: { type: "string", default: "7d", description: "1d | 7d | 30d" },
              },
            },
          },
        },
      };
    }
    paths[path] = { [isPost ? "post" : "get"]: methodSpec };
    // the cycle-wallet hunt answers GET and POST alike: body or query string, same product, same price
    if (path === "/v1/hundred-x-hunter" || path === "/v1/token-safety") {
      paths[path].post = { ...methodSpec, parameters: undefined,
        requestBody: { required: false, content: { "application/json": { schema: {
          type: "object",
          properties: path === "/v1/token-safety"
            ? { mint: { type: "string", description: "SPL mint address to score" } }
            : {
              mint: { type: "string", description: "SPL mint of a coin from a previous cycle" },
              window_days: { type: "integer", default: 30 },
              min_wallets: { type: "integer", default: 3 },
              limit: { type: "integer", default: 10 },
            },
          required: ["mint"],
        } } } } };
    }
  }
  paths["/v1/hundred-x-hunter/method"] = { get: {
    operationId: "hundredXHunterMethod",
    description: "The seven-step method, the scoring rubric and the threshold — free.",
    security: [],
    responses: { 200: { description: "Method, rubric, threshold and limits." } },
  } };
  paths["/v1/token-safety/method"] = { get: {
    operationId: "tokenSafetyMethod",
    description: "The token safety rubric, weights and verdict bands — free.",
    security: [],
    responses: { 200: { description: "Rubric, weights and verdict bands." } },
  } };
  
  // Free endpoints
  paths["/health"] = { get: { operationId: "health", description: "Health probe — free", security: [], responses: { 200: { description: "OK" } } } };
  paths["/.well-known/x402"] = { get: { operationId: "x402Discovery", description: "x402 service discovery — free", security: [], responses: { 200: { description: "Discovery doc" } } } };
  paths["/openapi.json"] = { get: { operationId: "openapi", description: "OpenAPI spec — free", security: [], responses: { 200: { description: "OpenAPI document" } } } };

  res.json({
    openapi: "3.0.0",
    info: {
      title: "pronomad Solana x402 Worker",
      version: "1.1.0",
      description: "x402 v2 paid API on Solana. 8 endpoints: meme-hunter, defi-sentiment, dinalibrium, wallet-profile, b0x402-data, honeypot-check, hundred-x-hunter (seven-step cycle-wallet method), token-safety (0-100 safety score).",
      contact: { name: "XH Agents", email: "basefortyblock@gmail.com" },
    },
    servers: [{ url: config.baseUrl, description: "Production" }],
    components: {
      securitySchemes: {
        x402: {
          type: "apiKey",
          in: "header",
          name: "x-payment",
          description: `x402 v2 USDC payment on Solana. Network: ${config.network}, Asset: ${config.usdcMint}`,
        },
      },
    },
    paths,
  });
});

// ── Paid endpoints ──────────────────────────────────────────────
const paidEndpoints = {
  "/v1/meme-hunter": { method: "GET", handler: memeHunter },
  "/v1/defi-sentiment": { method: "GET", handler: defiSentiment },
  "/v1/dinalibrium": { method: "POST", handler: dinalibrium },
  "/v1/wallet-profile": { method: "GET", handler: walletProfile },
  "/v1/b0x402-data": { method: "GET", handler: b0x402Data },
  "/v1/honeypot-check": { method: "GET", handler: honeypotCheck },
  // the seven-step cycle-wallet hunt: same method as the Base endpoint on xhagents.xyz, Solana data,
  // settled in USDC on Solana. Served on both GET (query string) and POST (JSON body).
  "/v1/hundred-x-hunter": { methods: ["GET", "POST"], handler: hundredXHunter },
  // 0-100 safety score for an SPL token: ownership powers, real holders, Token-2022 risks, liquidity.
  "/v1/token-safety": { methods: ["GET", "POST"], handler: tokenSafety },
};

// Free: the method itself, the rubric and the threshold.
app.get("/v1/hundred-x-hunter/method", async (req, res) => {
  try {
    res.json(await hundredXMethod());
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});
app.get("/v1/token-safety/method", async (req, res) => {
  try {
    res.json(await tokenSafetyMethod());
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Middleware: gate paid endpoints with x402 payment
async function x402Gate(req, res, next) {
  const path = req.path;
  if (!paidEndpoints[path]) return next();

  const paymentHdr = req.get("x-payment");

  if (!paymentHdr) {
    const invoice = issuePaymentRequired(path);
    if (!invoice) return next();
    const body = await invoice.text();
    res.status(402)
      .set(Object.fromEntries(invoice.headers.entries()))
      .set("Content-Type", "application/json")
      .send(body);
    return;
  }

  const result = await verifyPayment(paymentHdr, path);
  if (!result.ok) {
    res.status(402).json({ error: result.reason });
    return;
  }
  req.paymentTx = result.txHash;
  next();
}

// Apply gate to all paid endpoints (a path may accept more than one method)
for (const [path, info] of Object.entries(paidEndpoints)) {
  const methods = info.methods || [info.method];
  for (const m of methods) {
    app[m.toLowerCase()](path, x402Gate, async (req, res) => {
      try {
        const input = m === "GET" ? req.query : req.body;
        const data = await info.handler(input);
        res.json(data);
      } catch (e) {
        res.status(e.status || 500).json({ error: e.message });
      }
    });
  }
}

// ── Landing page ────────────────────────────────────────────────
app.get("/", (req, res) => {
  res.type("html").send(`
    <!DOCTYPE html>
    <html><head><title>pronomad Solana x402 Worker</title></head>
    <body style="background:#0a0a0a;color:#e5e5e5;font-family:sans-serif;padding:48px;max-width:720px;margin:auto">
      <h1 style="background:linear-gradient(135deg,#3b82f6,#8b5cf6,#ec4899);-webkit-background-clip:text;color:transparent">
        Pay-per-call crypto intelligence on Solana
      </h1>
      <p>7 paid x402 endpoints, USDC pricing, no subscriptions.</p>
      <ul>
        ${Object.entries(config.prices).map(([path, amount]) =>
          `<li><code>${path}</code> — $${(amount / 100000).toFixed(2)} USDC/call</li>`
        ).join("")}
      </ul>
      <p>Treasury: <code>${config.treasury}</code> · Network: <code>${config.network}</code></p>
      <p>Discovery: <a href="/.well-known/x402" style="color:#60a5fa">/.well-known/x402</a> · Health: <a href="/health" style="color:#60a5fa">/health</a></p>
    </body></html>
  `);
});

// 404 fallback
app.use((req, res) => {
  res.status(404).json({ error: "not_found", path: req.path });
});

app.listen(PORT, () => {
  console.log(`[solana-x402] listening on port ${PORT}`);
  console.log(`[solana-x402] treasury: ${config.treasury}`);
  console.log(`[solana-x402] baseUrl: ${config.baseUrl}`);
});
