/**
 * src/config.js - Configuration for Solana x402 Worker
 * Boss's treasury address + Solana RPC + USDC contract
 */
import "dotenv/config";

// Boss's Solana treasury (from env vars set by set_private_key.sh)
const TREASURY_ADDRESS = process.env.SOLANA_TREASURY_PUBLIC_KEY ||
                         "GhFbGgNxERN6pQ7boSFLFJuPwXJuvJ8Tx7EgoJ9LV2Aw";

// USDC token on Solana mainnet (SPL token mint address)
const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

// USDC has 6 decimals on Solana (1 USDC = 1_000_000 base units)
const USDC_DECIMALS = 6;

// Solana RPC endpoints (public mainnet + devnet)
const SOLANA_RPC = {
  mainnet: process.env.SOLANA_RPC_URL || "https://api.mainnet-beta.solana.com",
  devnet:  process.env.SOLANA_RPC_DEVNET || "https://api.devnet.solana.com",
};

// Base URL for endpoint discovery (x402scan requires this)
const BASE_URL = process.env.BASE_URL ||
                 "https://pronomad.duckdns.org";

// Network identifier per CAIP-2 (Solana)
const NETWORK = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"; // mainnet-beta

// Invoice TTL (5 minutes standard for x402)
const INVOICE_TTL_SECONDS = 300;

// Pricing per endpoint (USDC base units, 6 decimals)
const PRICES = {
  "/v1/meme-hunter":     10_000,    // $0.01
  "/v1/defi-sentiment":  10_000,    // $0.01
  "/v1/dinalibrium":     10_000,    // $0.01
  "/v1/wallet-profile": 100_000,    // $0.10
  "/v1/b0x402-data":     50_000,    // $0.05 (multichain gas + honeypot combo)
  "/v1/honeypot-check":  20_000,    // $0.02 (single honeypot check)
  "/v1/hundred-x-hunter": 150_000,  // $0.15 (seven-step cycle-wallet hunt, the "next 100x" method)
  "/v1/token-safety":      50_000,  // $0.05 (0-100 SPL token safety score with evidence)
};

const config = {
  treasury: TREASURY_ADDRESS,
  usdcMint: USDC_MINT,
  usdcDecimals: USDC_DECIMALS,
  rpc: SOLANA_RPC,
  baseUrl: BASE_URL,
  network: NETWORK,
  invoiceTtl: INVOICE_TTL_SECONDS,
  prices: PRICES,
};

// OpenAPI parameter definitions per endpoint
export const OPENAPI_PARAMS = {
  "/v1/meme-hunter": [
    { name: "limit", in: "query", required: false, schema: { type: "integer", default: 10, minimum: 1, maximum: 50, description: "Results count (max 50)" } },
    { name: "sort_by", in: "query", required: false, schema: { type: "string", default: "score", enum: ["score","volume","change","liquidity","boosted"], description: "Sort key" } },
  ],
  "/v1/defi-sentiment": [
    { name: "topic", in: "query", required: false, schema: { type: "string", default: "base", description: "Market topic filter (e.g. 'base', 'defi')" } },
  ],
  "/v1/dinalibrium": [],
  "/v1/wallet-profile": [
    { name: "address", in: "query", required: true, schema: { type: "string", pattern: "^[A-Za-z0-9]{32,44}$", description: "Solana wallet address (base58)" } },
  ],
  "/v1/b0x402-data": [
    { name: "chain", in: "query", required: false, schema: { type: "string", default: "base", description: "Chain to query (base|solana|etc)" } },
  ],
  "/v1/honeypot-check": [
    { name: "mint", in: "query", required: true, schema: { type: "string", pattern: "^[1-9A-HJ-NP-Za-km-z]{32,44}$", description: "SPL mint address (base58)" } },
    { name: "address", in: "query", required: true, schema: { type: "string", pattern: "^[A-Za-z0-9]{32,44}$", description: "Token contract address (base58)" } },
  ],
  "/v1/hundred-x-hunter": [
    { name: "mint", in: "query", required: true, schema: { type: "string", pattern: "^[1-9A-HJ-NP-Za-km-z]{32,44}$", description: "SPL mint of a coin from a previous cycle" } },
    { name: "window_days", in: "query", required: false, schema: { type: "integer", default: 30, minimum: 1, maximum: 180, description: "Activity window in days" } },
    { name: "min_wallets", in: "query", required: false, schema: { type: "integer", default: 3, minimum: 2, maximum: 10, description: "How many surviving wallets must hold a mint for it to be a signal" } },
    { name: "limit", in: "query", required: false, schema: { type: "integer", default: 10, minimum: 1, maximum: 25, description: "Wallets examined in step 5" } },
  ],
  "/v1/token-safety": [
    { name: "mint", in: "query", required: true, schema: { type: "string", pattern: "^[1-9A-HJ-NP-Za-km-z]{32,44}$", description: "SPL mint address to score" } },
  ],
};

export default config;
