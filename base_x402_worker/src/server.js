/**
 * src/server.js — Express server, x402 v2 paid API (Base chain)
 */
import express from "express";
import cors from "cors";
import helmet from "helmet";
import { CFG, PRICES, BAZAAR, OPENAPI_PARAMS } from "./config.js";
import { issuePaymentRequired, verifyPayment } from "./payment.js";
import { walletProfile } from "./handlers/wallet-profile.js";
import { memeHunter } from "./handlers/meme-hunter.js";
import { defiSentiment } from "./handlers/defi-sentiment.js";
import { dinalibrium } from "./handlers/dinalibrium.js";

const app = express();
app.use(helmet());
app.use(cors());
app.use(express.json());

const HANDLERS = {
  "/b0x402/v1/wallet-profile": walletProfile,
  "/b0x402/v1/meme-hunter": memeHunter,
  "/b0x402/v1/defi-sentiment": defiSentiment,
  "/b0x402/v1/dinalibrium": dinalibrium,
};

app.get("/health", (_, res) => {
  res.json({ ok: true, uptime: process.uptime(), chain: "base", payouts: CFG.payoutAddress });
});

const openApiSpec = () => {
  const paths = {};
  for (const path of Object.keys(PRICES)) {
    const opName = path.split("/").pop();
    const info = BAZAAR[path]?.info;
    const params = OPENAPI_PARAMS[path] || [];
    paths[path] = {
      get: {
        operationId: opName,
        description: info?.summary || path,
        parameters: params,
        responses: {
          200: {
            description: "Success",
            content: { "application/json": { schema: { type: "object" } } },
          },
          402: {
            description: "Payment required",
            content: { "application/json": { schema: { type: "object" } } },
          },
        },
      },
    };
  }
  // Free endpoints (no pricing)
  paths["/health"] = {
    get: {
      operationId: "health",
      description: "Health probe — free, no payment required.",
      security: [],
      responses: { 200: { description: "OK" } },
    },
  };
  paths["/.well-known/x402"] = {
    get: {
      operationId: "x402Discovery",
      description: "x402 service discovery document — free.",
      security: [],
      responses: { 200: { description: "Discovery doc" } },
    },
  };
  paths["/openapi.json"] = {
    get: {
      operationId: "openapi",
      description: "OpenAPI spec — free.",
      security: [],
      responses: { 200: { description: "OpenAPI document" } },
    },
  };
  paths["/b0x402/openapi.json"] = {
    get: {
      operationId: "openapi_b0x402",
      description: "OpenAPI spec for b0x402 namespace — free.",
      security: [],
      responses: { 200: { description: "OpenAPI document" } },
    },
  };

  return {
    openapi: "3.0.0",
    info: {
      title: "pronomad Base x402 Worker",
      version: "1.0.0",
      description: "x402 v2 paid API on Base chain. Free discovery endpoints, paid x402 endpoints.",
      contact: {
        name: "Dina (Boss)",
        email: "yusliarifn78@gmail.com",
      },
    },
    servers: [{ url: CFG.baseUrl, description: "Production" }],
    components: {
      securitySchemes: {
        x402: {
          type: "apiKey",
          in: "header",
          name: "x-payment",
          description: `x402 v2 EIP-3009 USDC payment header. Network: ${CFG.network}, Asset: ${CFG.usdcContract}`,
        },
      },
    },
    paths,
  };
};

app.get("/openapi.json", (_, res) => res.json(openApiSpec()));
app.get("/b0x402/openapi.json", (_, res) => res.json(openApiSpec()));

app.get("/.well-known/x402", (_, res) => {
  const entries = Object.entries(PRICES).map(([path, amount]) => ({
    x402Version: 2,
    resource: {
      url: CFG.baseUrl + path,
      description: BAZAAR[path]?.info?.summary || path,
      mimeType: "application/json",
    },
    accepts: [{
      scheme: "exact", network: CFG.network, amount: String(amount),
      payTo: CFG.payoutAddress, asset: CFG.usdcContract, maxTimeoutSeconds: CFG.invoiceTTL,
      extra: { name: "USD Coin", version: "2" },
    }],
  }));
  res.json({ version: 1, entries });
});

app.use(async (req, res, next) => {
  const path = req.path;
  if (!PRICES[path]) return next();

  const paymentHdr = req.headers["x-payment"] || req.headers["payment"];

  if (!paymentHdr) {
    const { body, headerB64 } = issuePaymentRequired(path, PRICES[path], CFG.baseUrl + path, BAZAAR[path]);
    res.setHeader("payment-required", headerB64);
    res.setHeader("x-payment-version", "2");
    return res.status(402).json(body);
  }

  const result = await verifyPayment(paymentHdr);
  if (!result.ok) {
    return res.status(402).json({ error: result.reason });
  }
  // If action == buyer_must_submit, return instructions
  if (result.action === "buyer_must_submit") {
    return res.status(402).json({
      error: "payment_not_submitted",
      message: "Buyer must submit EIP-3009 transferWithAuthorization transaction",
      tx: { to: result.to, data: result.data },
    });
  }
  next();
});

app.get("/b0x402/v1/wallet-profile", async (req, res) => {
  res.json(await walletProfile(req.query));
});
app.get("/b0x402/v1/meme-hunter", async (req, res) => {
  res.json(await memeHunter(parseInt(req.query.limit) || 10));
});
app.get("/b0x402/v1/defi-sentiment", async (_, res) => {
  res.json(await defiSentiment());
});
app.get("/b0x402/v1/dinalibrium", async (_, res) => {
  res.json(await dinalibrium());
});

app.listen(CFG.port, () => {
  console.log(`base-x402-worker on :${CFG.port} → ${CFG.baseUrl}`);
});
