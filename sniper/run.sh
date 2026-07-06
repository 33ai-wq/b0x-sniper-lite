#!/bin/bash
# b0xSniperLITE startup wrapper
#
# Default: --auto (AUTO-BUY enabled, capital at risk per safety config)
#  - max per trade = config.trade.max_per_trade_sol (0.0033)
#  - max trades/day = config.trade.max_trades_per_day (5)
#  - daily loss lock = config.trade.daily_loss_lock_sol (0.005)
#  - wallet safety floor = config.trade.wallet_safety_floor_sol (0.0125)
#  → if wallet below floor, abort & log to state/aborted_runs.txt
#
# To run monitor-only instead: MODE=monitor bash run.sh
#
# Path resolution: prefers the env-var $B0X_SNIPER_ROOT so this works inside
# a fresh checkout too. Falls back to the production install at
# /root/prpo_ai/bosnyasniperlite if B0X_SNIPER_ROOT is unset.

set -u
ROOT="${B0X_SNIPER_ROOT:-/root/prpo_ai/bosnyasniperlite}"
cd "$ROOT" || exit 1
WALLET="${SOLANA_WALLET:-7P7w3M9yQs5PCH2WbfmMxVWnkrobVsq1ARZBFfJ5W5zN}"

MODE="${MODE:-auto}"   # "auto" or "monitor"
APPEND=""
if [ "$MODE" = "auto" ]; then
  APPEND="--auto"
elif [ "$MODE" = "monitor" ]; then
  APPEND="--quiet"
else
  APPEND="--quiet"   # fallback safe
fi

exec python3 sniper.py $APPEND
