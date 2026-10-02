# b0x402 — Listing Action Plan (June 29 2026)

Worker live and verified. Sprint listing blocked by tooling limits (no browser, no third-party session creds, no paid X/Twitter API), so deliverable = copy-paste artifacts B0x70 can fire at his side.

## Step 1 — x402scan (highest priority, estimate 90s)
Open: https://www.x402scan.com/resources/register

Paste into the form:
```
Seller URL: https://x402-cf-worker.mulberry-boar.workers.dev
```
(No trailing slash, no path)

Click "Register". x402scan will automatically:
- fetch https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json
- probe each endpoint for V2 402 + bazaar extension
- list in `/resources` index

Already-formed verification (all PRE-CHECKED 2026-06-29):
- 402 status + Payment-Required header + X-Payment-Version: 2 + bazaar ext → PASS
- openapi.json / .well-known/x402.json both 200 → PASS
- /health 200 → PASS

## Step 2 — x402bazaar.org/submit (90s)
Open: https://www.x402bazaar.org/submit

Form fields (copy from listing_pack.md Section "Listing JSON Payload" verbatim):
```json
{
  "name": "b0x402",
  "url": "https://x402-cf-worker.mulberry-boar.workers.dev",
  ...
}
```

Currently 95% revenue share per their for-providers page.

## Step 3 — CDP Bazaar (passive, automatic)
No action. When first settlement flows through Coinbase CDP Facilitator with valid x402+bazaar metadata, the worker shows up at docs.cdp.coinbase.com/x402/bazaar search. Outside-bazaar configured = won't auto-index. **Required next step:** configure worker to use CDP facilitator OR manually request indexing via CDP Discord once first revenue hits.

## Step 4 — GitHub awesome-x402 PR (5 min)
Two list repos likely accepting:
- https://github.com/x402scan/awesome-x402 (verify)
- https://github.com/coinbase/x402 (issues/PRs for ecosystem subfolders)

Open PR with one-line addition:
```
- [b0x402](https://x402-cf-worker.mulberry-boar.workers.dev) — AI crypto intel. Meme signals, DeFi sentiment, market equilibrium, wallet profiling. $0.01–$0.10 USDC/call on Base.
```

## Step 5 — Direct outreach (post-launch, 3-5 mins each)
Template in listing_pack.md. Use Telegram @fortycrypto or B0x70's X handle. Targets:
1. daydreamsai — agents consuming sentiment feeds
2. aixbt team — adjacent sentiment-use case
3. clawdvine — meme-coin agent
4. CDPAgentKit devs (Coinbase ecosystem)
5. Kluster / Sentient-style agent personas

Send only after `https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json` is confirmed indexed by x402scan — buyers trust listed sellers.

## Step 6 — Full-feature enable (turned ON when ready)
- [ ] Enable CDP facilitator so x402bazaar indexes automatically
- [ ] Add a /bazaar.json resource metadata file for first-class discovery
- [ ] Track first 100 calls (free /health probe or paid everything) → publish call stats to attract integrators
- [ ] Add more endpoints (trending tokens, gas oracle, etc.) once revival base established

## VERIFICATION ARTIFACTS
All already pre-checked 2026-06-29:
```
curl -si https://x402-cf-worker.mulberry-boar.workers.dev/v1/meme-hunter | head -5
→ 402, Payment-Required header, X-Payment-Version: 2 (V2 ✓)

curl -s https://x402-cf-worker.mulberry-boar.workers.dev/openapi.json | jq '.info'
→ {"title":"b0x402 API","version":"1.0.0",...}

curl -s https://x402-cf-worker.mulberry-boar.workers.dev/.well-known/x402.json | jq '.endpoints | length'
→ 5  (4 paid + 1 free)
```

Save this file as `/root/prpo_ai/marketplace_listings/action_plan.md`.
