#!/usr/bin/env bash
# XH Daily Drop — 08:00 WIB body. Composes the day's X post (draft only) and prints it.
set -uo pipefail
export PATH="/home/ubuntu/.local/bin:$PATH"
export XH_DAILY_NO_TELEGRAM=1
cd /home/ubuntu/prpo_ai/xh_api/daily || exit 1
exec python3 daily_engine.py distribute
