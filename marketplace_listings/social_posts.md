# b0x402 Listing Submission — X/Twitter + Telegram Copy

READY-TO-PASTE blocks. Edit only [Handle] / [Link] placeholders.

## X (Twitter) post — primary announcement

```
Shipped b0x402 — 4 paid crypto-intel endpoints via x402. Pay per call, USDC on Base, no signup, AI-agent native.

🟢 /v1/meme-hunter     $0.01 — DexScreener pulses + scores
🟢 /v1/defi-sentiment  $0.01 — market mood per pair
🟢 /v1/dinalibrium     $0.01 — equilibrium math (a,b)
🟢 /v1/wallet-profile  $0.10 — PnL/risk per address

openapi + x402 V2 invoice: compliant
base URL → https://x402-cf-worker.mulberry-boar.workers.dev
listed on: x402scan + x402bazaar

[Add 1 image: openapi.json rendering or first 402 curl output]
```

## X reply-thread (3 tweets)

```
1/ Built b0x402 because agents need cheap, deterministic crypto data without subscriptions or auth headers. x402 V2 means buyer pays with a USDC-bearing wallet — no signup, no rate limit drama, no API key rotation. Just HTTP 402 → pay → 200.

2/ Stack:
- Cloudflare Workers (V8 isolate, ~300ms cold start)
- OpenAPI 3.1.0 spec at /openapi.json
- Discovery at /.well-known/x402.json
- Runtime V2 invoice format: Payment-Required header + bazaar extension
- Chain: Base mainnet, USDC, atomic amounts

3/ AI agents can now call real-time crypto intel like they call any tool.
Try: GET https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter
(returns 402 + invoice, pay via any x402 client, get JSON back)
```

## Telegram channel post (for cayubeby / fortycrypto or community channels)

```
🚀 Live: b0x402 API

AI-powered crypto intel for AI agents. 4 endpoints, USDC per call on Base.

• meme-hunter     — $0.01
• defi-sentiment  — $0.01
• dinalibrium     — $0.01
• wallet-profile  — $0.10

x402 V2 compliant. OpenAPI spec at /openapi.json.

Base: https://x402-cf-worker.mulberry-boar.workers.dev
Listing: https://x402scan.com (search "b0x402")

Ping me if interested in bulk testing or integration.
```

## DM (cold outreach to adjacent builders)
Use listing_pack.md "Outreach DM Template" block, unchanged.

## Hashtag set (X)
#x402 #AIagents #crypto #USDC #Base #DeFi #Meme #OpenAPI

## Pin to profile
Pin the primary announcement post so any inbound from X/TG sees the URL instantly.

## Posting cadence (recommended)
- Day 0: primary post + pin
- Day 1: thread + first reply-bait (someone asks "does it cost gas?", reply with V2 invoice walkthrough)
- Day 3: stats tweet after first 50+ calls
- Day 7: case study (an agent that consumed 1000x meme-hunter calls)
