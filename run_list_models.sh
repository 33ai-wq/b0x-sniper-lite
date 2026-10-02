#!/bin/bash
set -e
cd /home/ubuntu/prpo_ai
export NVIDIA_NIM_API_KEY="$(grep -E '^NVIDIA_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d "'\"")"
exec python3 list_nim_models.py
