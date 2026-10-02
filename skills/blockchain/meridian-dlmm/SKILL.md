---
name: meridian-dlmm
category: blockchain
description: Meridian DLMM LP Bot - Auto liquidity provision on Meteora Solana pools
trigger: Use when running or managing the Meridian Dynamic Liquidity Market Maker bot on Meteora Solana pools.
---

# Meridian DLMM LP Bot

**Trigger**: Use when running or managing the Meridian Dynamic Liquidity Market Maker bot on Meteora Solana pools.

**One-line behavior**: Auto-screens Meteora DLMM pools with fee/TVL, organic score, and holder filters; opens/closes/rebalances concentrated liquidity positions; harvests fees; sends Telegram alerts.

---

## Configuration
- **Config path**: `~/.hermes/profiles/prpo_ai/agent-meridian/config.json`
- **Environment**: `~/.hermes/profiles/prpo_ai/.env` (requires `SOLANA_PRIVATE_KEY`, `TELEGRAM_BOT_TOKEN`)
- **RPC**: Helius primary, fallback to mainnet-beta.solana.com
- **LLM**: `nvidia/nemotron-3-ultra-550b-a55b` via `https://integrate.api.nvidia.com/v1` (default in Hermes config)

### Key Params (from user config integration)
| Param | Value | Description |
|-------|-------|-------------|
| `max_positions` | `1` | Max concurrent DLMM positions |
| `per_position_sol` | `0.15` | SOL per position |
| `min_tvl_usd` | `10000` | Minimum total value locked |
| `max_tvl_usd` | `100000` | Maximum total value locked |
| `min_volume_24h_usd` | `1000` | Minimum 24h volume |
| `min_fee_tvl_ratio_pct` | `7.0` | Fee to TVL ratio threshold |
| `min_organic_score` | `55` | Organic score threshold |
| `min_quote_organic_score` | `55` | Minimum quote organic score |
| `min_market_cap_usd` | `80000` | Minimum market cap |
| `max_market_cap_usd` | `2000000` | Maximum market cap |
| `min_holders` | `400` | Minimum holder count |
| `max_bundle_pct` | `18` | Max bundle percentage |
| `max_top10_pct` | `45` | Max top 10 holders percentage |
| `temperature` | `0.373` | LLM temperature |
| `max_tokens` | `4096` | Max LLM tokens |
| `max_steps` | `20` | Max agent steps |
| `darwin_enabled` | `true` | Darwin AI scoring enabled |
| `darwin_window_days` | `60` | Darwin scoring window (days) |
| `darwin_recalc_every` | `5` | Darwin recalculation interval (hours) |
| `darwin_boost` | `1.08` | Darwin boost factor |
| `darwin_decay` | `0.92` | Darwin decay factor |
| `darwin_floor` | `0.3` | Darwin minimum score floor |
| `darwin_ceiling` | `2.5` | Darwin maximum score ceiling |
| `darwin_min_samples` | `10` | Minimum Darwin samples |

### Telegram
- **Bot token**: Read from env `TELEGRAM_BOT_TOKEN`
- **Chat ID**: `1963809645`
- **Alerts**: Position open/close, harvest, errors

### Risk Controls
- **MIN_WALLET_SOL**: 0.05 (bot won't trade below this)
- **Max daily loss**: 0.01 SOL
- **Max drawdown**: 20%
- **Emergency exit**: 0.005 SOL
- **Max hold hours**: 168 (7 days)

## Pool Screening Logic
The bot scans Meteora DLMM pools and applies the following filters:
1. TVL between min/max thresholds
2. 24h volume ≥ min_volume
3. Fee/TVL ratio ≥ min_fee_tvl_ratio_pct
4. Organic score ≥ min_organic_score
5. Market cap between min/max thresholds
6. Holder count ≥ min_holders
7. Bundle % ≤ max_bundle_pct
8. Top 10 holders % ≤ max_top10_pct

Pools are scored and the best ones get positions opened.

## Position Management
- **Entry**: Open concentrated liquidity position with configurable bin width (default 10 bps)
- **Harvest**: Claim accumulated fees when ≥ harvest_threshold_usd ($5 default)
- **Rebalance**: If price drifts beyond rebalance_threshold_pct (15%), reposition
- **Stop-loss**: 12% loss triggers position close
- **Trailing TP**: Active if enabled; trigger at 5%, drop at 2%
- **Max hold**: 168 hours (7 days) after which position auto-closes

## LLM Integration
The bot can use the configured LLM model for:
- Pool analysis and scoring
- Market condition assessment
- Trade decision support
- Darwin AI score calculation

Temperature 0.373 provides focused, deterministic output suitable for trading decisions.

## Files in this Skill
- `references/meteora-api.md` - Meteora API endpoints and response formats
- `references/telegram-setup.md` - Telegram bot configuration
- `scripts/scan-pools.py` - Pool scanning script
- `scripts/health-check.py` - Health check script

## Usage
```bash
# Test run (dry run, no real trades)
SOLANA_PRIVATE_KEY="your_key" python3 bot.py --once

# Live run (24/7)
SOLANA_PRIVATE_KEY="your_key" python3 bot.py

# Run with dry-run mode
python3 bot.py --dry-run test
```

## Known Pitfalls
- Wallet must have ≥ 0.05 SOL for fees + priority fees
- LLM API key must be configured in Hermes profile
- Telegram token must be valid and chat ID must accept messages
- Meteora API may rate-limit; bot has fallback to cached data
- Simulation does not equal send success; use `skipPreflight: true` for fresh pools

## Lessons Learned
- Wallet balance is critical: test with `--once` first before live 24/7
- Simulation ≠ send success on fresh pools; `skipPreflight: true` required
- Priority fee 0.001 SOL ensures TX inclusion for new token swaps
- Shared aiohttp session reduces RPC latency significantly
- Minimum wallet balance enforcement prevents the "$8.5 → $0.07" drain scenario
- Always verify Telegram notifications before starting live mode

## Update History
- 2026-08-27: Initial creation - integrated user config parameters, Telegram notification support, LLM model configuration
- 2026-08-27: Added Darwin AI scoring parameters, trailing take profit, cooldown mechanisms
- 2026-08-27: Fixed MIN_WALLET_SOL enforcement to prevent balance drainage
- 2026-08-27: Migrated from old sniper bot (drained wallet on 20+ failed TXs)