#!/bin/bash
# Helper: load NVIDIA_API_KEY from .env and run the probe.
set -e
cd /home/ubuntu/prpo_ai
KEY="$(grep -E '^NVIDIA_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
if [ -z "$KEY" ]; then
  echo "ERROR: NVIDIA_API_KEY not found in .env" >&2
  exit 2
fi
export NVIDIA_NIM_API_KEY="$KEY"
echo "key loaded, len=${#KEY}"
exec python3 probe_nvidia_nim.py
