#!/usr/bin/env bash
# XH Daily Drop — 23:55 WIB body. On-chain treasury reconciliation for the last 24h
# plus our own paid-call counts, with the $1/day target.
set -uo pipefail
export PATH="/home/ubuntu/.local/bin:$PATH"
export XH_DAILY_NO_TELEGRAM=1
cd /home/ubuntu/prpo_ai/xh_api/daily || exit 1
exec python3 daily_engine.py treasury 24
