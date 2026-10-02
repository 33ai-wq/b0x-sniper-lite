# b0x402 — Marketplace Listings

**Seller URL:** https://x402-cf-worker.mulberry-boar.workers.dev
**Auto-discovery:** https://x402-cf-worker.mulberry-boar.workers.dev/.well-known/x402.json
**OpenAPI:** https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json

---

## One-Liner Pitch

AI-powered crypto intelligence — meme signals, DeFi sentiment, market equilibrium, wallet profiling. Pay per call in USDC on Base via x402.

---

## Tagline Variants

**Short (≤140 char):**
> AI crypto intel you call by the byte. Meme pumps, DeFi mood, market equilibrium, wallet profiling — $0.01–$0.10 USDC/call on Base. x402-native.

**Medium:**
> Four paid endpoints, one worker. /v1/meme-hunter surfaces DexScreener signals with score+volume+liq. /v1/defi-sentiment returns bullish/bearish/neutral readings. /v1/dinalibrium runs equilibrium math on user-supplied pairs. /v1/wallet-profile traces addresses with PnL + risk. All priced in USDC atomic amounts, no subscription, no API key.

**Long (marketplace form):**
> b0x402 is an x402 V2-compliant seller on Cloudflare Workers serving real-time crypto intelligence for AI agents. Five endpoints total: four paid in USDC on Base (meme-hunter $0.01, defi-sentiment $0.01, dinalibrium $0.01, wallet-profile $0.10) plus a free /health probe. Implementation uses the Coinbase x402 V2 invoice format with Payment-Required header, bazaar extension, and OpenAPI 3.1.0 spec at /openapi.json. Settlement address 0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357. Built for autonomous agent consumption — every call returns deterministic JSON, no auth headers beyond x-payment, latency <300ms.

---

## Listing JSON Payload (for forms that accept structured input)

```json
{
  "name": "b0x402",
  "url": "https://x402-cf-worker.mulberry-boar.workers.dev",
  "category": "ai-crypto-intelligence",
  "payment_protocol": "x402-v2",
  "network": "base",
  "currency": "USDC",
  "pricing": {
    "/v1/meme-hunter":    "0.01",
    "/v1/defi-sentiment": "0.01",
    "/v1/dinalibrium":    "0.01",
    "/v1/wallet-profile": "0.10"
  },
  "settlement_address": "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
  "discovery": {
    "openapi":        "/openapi.json",
    "x402_json":      "/.well-known/x402.json"
  },
  "endpoints": [
    "/v1/meme-hunter",
    "/v1/defi-sentiment",
    "/v1/dinalibrium",
    "/v1/wallet-profile",
    "/health"
  ],
  "tags": ["x402","ai-agents","defi","meme","wallet","sentiment","base","usdc"],
  "contact": "@fortycrypto on Telegram, boss@b0x70 via Twitter/X"
}
```

---

## Outreach DM Template (for agent buyers)

```
hey — built an x402 API for crypto intel, useful for AI agents:

• /v1/meme-hunter     $0.01 — DexScreener pulses + scores
• /v1/defi-sentiment  $0.01 — market mood per pair
• /v1/dinalibrium     $0.01 — equilibrium math on (token_a, token_b)
• /v1/wallet-profile  $0.10 — PnL/risk per address

base USDC, no signup, x402 V2 compliant.
openapi.json: https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json
sample: curl https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter
(returns 402 + invoice header — pay with any x402 client)

worth a slot in your stack?
```

---

## Channel Targets

| # | Channel | Type | Form/URL | Status |
|---|---------|------|----------|--------|
| 1 | x402scan.com | x402 directory | https://www.x402scan.com/resources/register | TODO |
| 2 | x402bazaar.org | x402 directory | https://x402bazaar.org/submit (TBD) | TODO |
| 3 | x402discovery.com | x402 directory | web form / GitHub PR | TODO |
| 4 | MCP.so | MCP marketplace | https://mcp.so/server/new | TODO |
| 5 | Glama.ai | MCP directory | https://glama.ai/mcp/servers/submit | TODO |
| 6 | mcpmarket.com | MCP dir | /server/x402-bazaar (existing slot) | TODO |
| 7 | awesome-x402 (GitHub) | curated list | PR to repo | TODO |
| 8 | daydreamsai/clawdvine | direct DM | X/TG channels | TODO |
| 9 | aixbt-related feeds | direct ping | X mentions | TODO |
| 10 | Sensecape / Kluster-style agents | direct DM | TG/DM | TODO |

---

## Verification Commands

```bash
# Runtime health (402 = good)
curl -si https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter | head -5

# Discovery
curl -s https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json | jq '.info'
curl -s https://x402-cf-worker.mulberry-boar.workers.dev/.well-known/x402.json | jq '.endpoints | length'
curl -s https://x402-cf-worker.mulberry-boar.workers.dev/health
```

Expected: 402 + Payment-Required header (V2), openapi returns 200, x402.json has 4 paid + 1 free endpoint, health returns ok+timestamp.
