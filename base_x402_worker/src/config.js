/**
 * src/config.js - Base x402 Worker config
 * Migrated from CF Worker (cf-worker/src/index.js)
 */
import "dotenv/config";

export const CFG = {
  payoutAddress: "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
  usdcContract: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  network: "eip155:8453",
  rpcUrl: "https://mainnet.base.org",
  invoiceTTL: 300,
  baseUrl: "https://pronomad.duckdns.org",
  port: 3001,
};

export const PRICES = {
  "/b0x402/v1/meme-hunter": 10_000,      // $0.01
  "/b0x402/v1/defi-sentiment": 10_000,   // $0.01
  "/b0x402/v1/dinalibrium": 10_000,      // $0.01
  "/b0x402/v1/wallet-profile": 100_000,  // $0.10
};

// Bazaar metadata
export const BAZAAR = {
  "/b0x402/v1/meme-hunter": {
    info: {
      tags: ["crypto", "defi", "meme", "signals"],
      summary: "Top-ranked meme-coin signals from DexScreener (Base chain). $0.01 USDC/call.",
    },
  },
  "/b0x402/v1/defi-sentiment": {
    info: {
      tags: ["crypto", "defi", "sentiment", "macro"],
      summary: "Macro DeFi market sentiment - bullish/bearish/neutral. $0.01 USDC/call.",
    },
  },
  "/b0x402/v1/dinalibrium": {
    info: {
      tags: ["crypto", "defi", "equilibrium", "onchain"],
      summary: "ETH/stablecoin equilibrium ratio. $0.01 USDC/call.",
    },
  },
  "/b0x402/v1/wallet-profile": {
    info: {
      tags: ["crypto", "wallet", "onchain", "forensics"],
      summary: "On-chain wallet profiling. $0.10 USDC/call.",
      requiresAddress: true,
    },
  },
};

// OpenAPI parameter definitions per endpoint
export const OPENAPI_PARAMS = {
  "/b0x402/v1/meme-hunter": [
    { name: "limit", in: "query", required: false, schema: { type: "integer", default: 10, minimum: 1, maximum: 30 } },
  ],
  "/b0x402/v1/defi-sentiment": [
    { name: "topic", in: "query", required: false, schema: { type: "string", default: "base", description: "Market topic filter (e.g. 'base', 'defi')" } },
  ],
  "/b0x402/v1/dinalibrium": [],
  "/b0x402/v1/wallet-profile": [
    { name: "address", in: "query", required: true, schema: { type: "string", pattern: "^0x[a-fA-F0-9]{40}$" } },
  ],
};
