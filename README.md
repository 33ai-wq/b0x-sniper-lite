# b0x-sniper-lite

**Capital-preserving Solana memecoin sniper · Lite v1.0.0 · Built 2026-07-06**

Monorepo with two surfaces:

```
/
├── sniper/                 ← Python scanner + scoring + (optional) auto-buy
│   ├── sniper.py
│   ├── config.json
│   ├── run.sh
│   ├── requirements.txt
│   ├── README.md
│   └── .gitignore
└── worker/                 ← Cloudflare Worker (x402 monetization)
    ├── src/index.js
    ├── wrangler.jsonc
    ├── package.json
    └── README.md
```

## TL;DR

Scans Solana new-pair launches via DexScreener every 25 s, scores each on
7 dimensions (liquidity, txn count, FDV, age, price action, holders, metadata),
auto-buys the ones scoring ≥ 65 via Jupiter v6 swap, capped at 0.0033 SOL/trade.

Hard daily loss lock at 0.005 SOL. Hard wallet floor at 0.0125 SOL — bot
aborts entirely below. **Win small, lose small, scale after evidence.**

See [`sniper/README.md`](./sniper/README.md) for operational details and
[`worker/README.md`](./worker/README.md) for monetization endpoint docs.

## Risk profile

| Param | Value |
|---|---|
| Per-trade cap | 0.0033 SOL (~$0.66) |
| Daily trades | ≤ 5 |
| Daily loss lock | 0.005 SOL |
| Wallet safety floor | 0.0125 SOL |
| Slippage (auto-buy) | 1500 bps (15%) |
| Forced exit | 60 s after buy |

## Capital-preserving design

Lite v1.0 deliberately **lacks**:

- whale-copy 2nd layer
- pump.fun direct API
- social-quality vetting
- live testnet shadow-trade backtest

These are roadmap v2.0+ once Lite proves edge on mainnet.

## Author

`prpo_ai` — autonomous AI employee commissioned by B0x70.

## License

MIT
