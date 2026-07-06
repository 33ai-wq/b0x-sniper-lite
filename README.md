# b0xSniperLITE — Solana Memecoin Sniper (Lite)
**By B0x70 / prpo_ai · Build 2026-07-06 · Lite v1.0.0**

> Capital-preserving sniper bot for Solana memecoin launches. Default mode:
> 7-dimension quality scoring + bounded auto-buy at $0.66/trade cap.

---

## What it does

1. **Scans** new Solana pairs every 25 seconds via DexScreener
2. **Scores** each pair on 7 dimensions (liquidity, txns, holders, FDV, age, price action, metadata) → 0-100
3. **Filters**: only score ≥ 65 qualifies
4. **Auto-buy** (in `--auto` mode) via Jupiter v6 swap, capped at 0.0033 SOL/trade
5. **Daily loss lock** at 0.005 SOL ($1.00) — bot auto-pauses if exceeded
6. **Safety floor** 0.0125 SOL — bot aborts entirely if wallet below

Risk profile:
- Per-trade cap: 0.0033 SOL (~$0.66)
- Daily trade limit: 5
- Daily loss lock: 0.005 SOL/day
- Stop if wallet < 0.0125 SOL

---

## Quick start

```bash
# Monitor-only (no tx)
python3 sniper.py --quiet

# Auto-buy (default production mode)
python3 sniper.py --auto

# Restart-on-crash watchdog (cron every 3 min)
bash /root/.hermes/profiles/prpo_ai/scripts/sniper_watchdog.sh
```

## Configuration

`config.json` — all parameters. See source for full schema.

## Cloudflare Worker

The same scoring engine is exposed via a Worker endpoint for monetization:

```bash
# Public health README
GET /

# Scan Solana pairs (filter by min_score)
GET /sniper/scan?wallet=7P7...&min_score=65

# Get Jupiter quote for buy
GET /sniper/quote?output_mint=ABC...&input_sol=0.0033
```

Pricing (x402 USDC payable):
- `scan-only`: $0.001 / call
- `scan+quote`: $0.005 / call
- `alert stream`: $0.010 / subscription

## Skill registry

The pattern + filter logic lives in skill:
`/root/.hermes/profiles/prpo_ai/skills/crypto-automation/b0x-sniper-lite/SKILL.md`

## What this is NOT

This is a CAPITAL-PRESERVING lite v1 — not a trading-empire edge-hunter.
What's missing (roadmap v2.0+):
- Whale-copy 2nd layer (track profitable wallets via gmgn.ai)
- Pump.fun direct API (sub-DexScreener latency)
- Live testnet shadow-trade backtesting
- Dev-wallet history rug detection

Built with restraint. Win small, lose small, scale only after evidence.

---

## License

MIT © B0x70 / prpo_ai
