# b0x402 — Telegram DM Targets

3 outbound DMs queued. Same template adapted per target. Sent ONLY after B0x70 explicit consent per-target.

## Template (universal)

```
hey — built a USDC-per-call crypto intel API on x402 V2, useful for AI agents:

• /v1/meme-hunter     $0.01 — DexScreener pulses + scores
• /v1/defi-sentiment  $0.01 — market mood per pair
• /v1/dinalibrium     $0.01 — equilibrium math on (a,b)
• /v1/wallet-profile  $0.10 — PnL + risk per address

base USDC, no signup, V2 compliant.
openapi: https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json
try: curl https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter
(returns 402 + invoice header, pay with any x402 client)

worth a slot in <TARGET>?
```

## Target 1 — daydreamsai (agent framework, sentiment consumer)
Handle: @daydreamsai_bot (TG) / @daydreamsai (X)
DM: direct TG message if bot handles inbound, else X DM.
Angle: replace their existing sentiment data source with one that's pay-per-call (no API key).

## Target 2 — aixbt / related sentiment agents
Handle: search "aixbt" via @aibt_bot (likely) or the @aixbt_portfolio TG.
Angle: complement their existing analysis with b0x402 defi-sentiment + wallet-profile.

## Target 3 — clawdvine (meme agent)
Handle: @clawdvine_bot (or whatever the public TG is for the meme-sniper agent).
Angle: bundle /v1/meme-hunter into their sniper logic. CHEAP at $0.01 — covers thousands of calls per $1.

## Send logic
- Pre-flight: TG bot can DM only users who've initiated conversation first OR bot is configured with privacy mode disabled.
- If TG_TOKEN = user bot (not gateway) → only responds to /start, can't initiate DM.
- If TG_TOKEN = our @mmx3prpo_bot → uses sendMessage but recipient must /start our bot first.

REALISTIC outbound path:
- Use XURL/Bird CLI for X DMs (needs X bearer + specific endpoint per target)
- TG: alternative is to ask B0x70 to drop a /start command to target bots, then gw can DM ONCE they've engaged.

## Recommended fallback
tg_dm target list = PENDING until B0x70 confirms:
(a) target bottles Lo udah /start-ed
(b) Lo prefer gw post ke public channel Lo aja (cayubeby) instead of cold DM
```

## Other valid channels if DM blocked
- @fortycrypto public channel post (Lo punya channel, gw post launch announcement)
- /r/aiagents / /r/cryptocurrency Reddit thread (No API needed for manual post)
