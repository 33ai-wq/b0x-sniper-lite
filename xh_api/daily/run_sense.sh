#!/usr/bin/env bash
# XH Daily Drop — 06:00 WIB body. Rebuilds the dated brief and prints what landed.
# Cron job (no_agent): stdout is delivered by the Hermes gateway, so the script itself stays quiet.
set -uo pipefail
export PATH="/home/ubuntu/.local/bin:$PATH"
export XH_DAILY_NO_TELEGRAM=1
cd /home/ubuntu/prpo_ai/xh_api/daily || exit 1
exec python3 daily_engine.py morning
