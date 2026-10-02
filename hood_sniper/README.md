# Hood Sniper — RH Chain Discovery Radar

> Multi-source Robinhood Chain (chain 4663) listings/mints/launches radar.
> Cloudflare Worker, x402 paid ($0.005 USDC per call on Base).

## What it does

Pulls from three sources every ~60s, dedupes, scores, ranks, returns
ranked events to a paid x402 endpoint:

1. **Arcus REST** — `/v1/markets` (universe, 24h volume, status)
2. **Blockscout** — `/api/v2/contracts` (new contract deploys on chain 4663)
3. **Robidy.app** — `__next_f` streaming payload scan (launchpad phases)

## Surface

| Path                                    | Auth          | Cost          |
|-----------------------------------------|---------------|---------------|
| `/health`                               | free          | —             |
| `.well-known/x402`                      | free          | —             |
| `/openapi.json`                         | free          | —             |
| `/v1/hood-sniper/radar/feed`            | free          | top-5 capped  |
| `/v1/hood-sniper/radar`                 | **x402 USDC** | **$0.005**    |

## Severity ladder

| Severity | Meaning |
|----------|---------|
| `alpha`  | Robidy phase start / multi-source corroboration  |
| `alert`  | Status flip OFFLINE→ONLINE / new contract in last 24h |
| `watch`  | 24h volume > 5× baseline AND >$1k                  |
| `info`   | Baseline-only signal                                 |

## Local dev

```bash
# Python ticker (does NOT require DNS-resolved upstreams — gracefully no-ops)
cd /root/prpo_ai/hood_sniper
python3 -c "from src import engine; print(engine.tick('/tmp/b.json','/tmp/h.json'))"

# CF Worker locally
cd worker
npx wrangler dev
node ../scripts/smoke.js     # x402 gate unit smoke
```

## Deploy

```bash
cd worker
export CLOUDFLARE_API_TOKEN="..."
npx wrangler deploy
```

## Known limitations

* Worker is per-isolate cache only (no KV). Refresh is `RADAR_TTL_SECONDS`.
* Indo DNS hijack blocks canonical RH Chain RPC; Blockscout mirror covers
  that path. If user runs behind the same DNS layer, free radar still
  works but volume diff requires Arcus (Cloudflare-fronted, usually live).
* X/Twitter feed integration deferred to v0.2 (requires X API key).
* Arcus `/v1/account` and `/v1/orders` remain auth-gated and out of scope.

## Skills referenced

* `robinhood-chain-arcus-airdrop` — DNS-blocker patterns, FX fallback
* `meridian-preservation` — no Solana wallet touch (data only)
