# PR template: xpaysh/awesome-x402

## Title
Add b0x402 — pay-per-call crypto intel API on Cloudflare Workers

## File to modify
README.md → section "Production Servers / API Endpoints" (or wherever their list lives)

## One-line entry to add

```
- [b0x402](https://x402-cf-worker.mulberry-boar.workers.dev) — 4 paid endpoints: meme-hunter ($0.01), defi-sentiment ($0.01), dinalibrium ($0.01), wallet-profile ($0.10). USDC on Base. x402 V2 compliant.
```

## PR body (description)

Adding **b0x402** — a pay-per-call crypto intelligence API for AI agents, built on Cloudflare Workers running x402 V2 protocol.

**Endpoints (all priced in USDC atomic units, settled on Base mainnet chain id 8453):**
- `GET /v1/meme-hunter` — $0.01 — DexScreener-ranked meme token signals
- `GET /v1/defi-sentiment` — $0.01 — DeFi market mood readings  
- `POST /v1/dinalibrium` — $0.01 — token-pair equilibrium math
- `GET /v1/wallet-profile` — $0.10 — on-chain address forensics
- `GET /health` — free probe

**Settlement address**: `0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357`

**Spec & discovery:**
- OpenAPI 3.1.0: https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json
- `.well-known/x402.json` for AgentCash-style discovery
- bazaar extension populated per Coinbase x402 facilitator spec

**Buyer flow:**
1. Client GETs `/v1/meme-hunter` without x-payment header
2. Worker returns `HTTP 402` with `Payment-Required: <base64 invoice>` header (V2 spec) and `X-Payment-Version: 2`
3. Buyer pays USDC to payout address on Base
4. Buyer retries with `x-payment` header carrying payment proof (transaction receipt)
5. Worker verifies on-chain via `eth_getLogs`, returns signal data

**Compatible with:** PayAI facilitator, Coinbase CDP embedded wallet, x402-fetch npm, any EIP-3009 capable wallet.

**Architecture:** Cloudflare Workers free tier (100k req/day), single global V8 isolate, <300ms p50 latency. Zero subscription. Zero API key.

**Source:** github.com/33ai-wq/b0x402 (mirrors worker source)

**Verified live (2026-06-30):**
- all 4 endpoints emit valid V2 invoice
- OpenAPI declares `components.securitySchemes.x402`
- USDC contract: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`

---

## Alt PR body — single paragraph version (if maintainer prefers condensed)

b0x402 — pay-per-call crypto intel API for AI agents, 4 endpoints priced $0.01-$0.10 USDC/call on Base. x402 V2 compliant on Cloudflare Workers. OpenAPI + bazaar extensions populated. Compatible with PayAI, Coinbase CDP, x402-fetch npm.
