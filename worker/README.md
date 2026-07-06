# b0x-sniper-lite — Cloudflare Worker
# Monorepo location: worker/  ·  Pricing in USDC on Base via x402 V2

`src/index.js` is the fetch handler with three monetization endpoints
(see root `README.md` and `../sniper/README.md` for surface docs).

| Endpoint | Price | What it returns |
|---|---|---|
| `GET /sniper/scan?wallet=…&min_score=65` | $0.001 | latest scored Solana new pairs |
| `GET /sniper/quote?output_mint=…&input_sol=0.0033` | $0.005 | scan + Jupiter v6 quote |
| `GET /sniper/alert?wallet=…` | $0.010 | alert stream when score ≥ 65 |

`PRIMARY_WALLET` in `wrangler.jsonc` is read-write public address only — never
embed a private key here or anywhere in the source tree.

## Deploy

```bash
cd worker
npx wrangler deploy
```

Requires `CLOUDFLARE_API_TOKEN` in your shell env (do not commit).
