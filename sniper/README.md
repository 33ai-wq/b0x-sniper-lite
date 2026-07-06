# b0x-sniper-lite — top-level (monorepo)

Build 2026-07-06 by prpo_ai (B0x70's autonomous AI employee).

This is the **monorepo** for `b0xSniperLITE — Capital-Preserving Solana Memecoin
Sniper`. Capital preservation is the design constraint; edge hunting is not.

```
/                           ← you are here
├── sniper/                 ← Python sniper core (lite-1.0.0)
│   ├── sniper.py           ← main scanner + scoring + watcher
│   ├── config.json         ← all parameters (trade caps, filters, RPC)
│   ├── run.sh              ← startup wrapper (--auto default)
│   ├── requirements.txt    ← aiohttp, base58, solana, solders
│   └── README.md           ← operational manual
└── worker/                 ← Cloudflare Worker (x402 monetization)
    ├── src/index.js        ← fetch handler + 402 invoice logic
    ├── wrangler.jsonc      ← CF Workers config (vars.PRIMARY_WALLET)
    ├── package.json        ← CF deps
    └── README.md           ← endpoint docs
```

## What it does

1. **Scans** new Solana pairs every 25 s via DexScreener (`/latest/dex/search?q=solana new pair`)
2. **Scores** each pair on 7 dimensions (liquidity, txn count, FDV, age, price action, metadata, holders)
3. **Filters** — only pairs with score ≥ 65 qualify
4. **Auto-buy** (`--auto`) via Jupiter v6 swap, capped at 0.0033 SOL/trade (~$0.66)
5. **Daily loss lock** at 0.005 SOL — bot pauses trading if hit
6. **Safety floor** — aborts entirely if wallet < 0.0125 SOL

## Risk profile (hard-coded)

| Parameter | Value | Meaning |
|---|---|---|
| max_per_trade_sol | 0.0033 | per-buy cap ($0.66) |
| max_trades_per_day | 5 | trade count cap |
| daily_loss_lock_sol | 0.005 | stop-loss hit = pause 24h |
| wallet_safety_floor_sol | 0.0125 | abort entirely if wallet below |
| take_profit_pcts | [20, 50, 100] | scaling TP |
| stop_loss_pct | 30 | catastrophic exit |
| exit_seconds_after_buy | 60 | forced close, no exceptions |

## Quick start

```bash
# Python (monitor-only, no tx)
python3 sniper/sniper.py --quiet

# Python (auto-buy, default production)
python3 sniper/sniper.py --auto

# Or via wrapper
MODE=auto   bash sniper/run.sh
MODE=monitor bash sniper/run.sh
```

## Cloudflare Worker (x402 monetization)

3 endpoints, paid per call in USDC on Base:

| Endpoint | Price | What you get |
|---|---|---|
| `GET /sniper/scan?wallet=…&min_score=65` | $0.001 / call | scan + scored pairs |
| `GET /sniper/quote?output_mint=…&input_sol=0.0033` | $0.005 / call | scan + Jupiter v6 quote |
| `GET /sniper/alert?wallet=…` | $0.010 / call | alert when score ≥ 65 |

Worker source: [`worker/src/index.js`](./worker/src/index.js).
Live URL (after deploy): see `worker/wrangler.jsonc` → `routes`.

## Capital-preserving design (why "Lite")

Lite v1.0 is **deliberately boring**:

- ✅ 7-dim scoring with DexScreener + Helius + Jupiter (all zero-key sources)
- ✅ Hard daily caps so a bad day can never drain the wallet
- ✅ Forced exit 60s after buy, no bag-holding
- ❌ **No** whale-copy layer (roadmap v2.0+)
- ❌ **No** pump.fun direct API (sub-DexScreener latency)
- ❌ **No** testnet shadow-trade backtest layer

Win small, lose small, scale only after evidence.

## Author

`prpo_ai` — autonomous AI employee.
Creator: B0x70.
Wallet (canonical): `7P7w3M9yQs5PCH2WbfmMxVWnkrobVsq1ARZBFfJ5W5zN` (44 chars → 32 bytes; verify before each tx-use).

## License

MIT
