#!/bin/bash
# Setup Gmail App Password for XH Agents ad-engine email.
# Run this YOURSELF on the VPS. Your password is NOT echoed and NOT sent to anyone.
# Prerequisite: generate App Password at https://myaccount.google.com/apppasswords
# (Google Account > Security > 2-Step Verification > App passwords)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$DIR/.gmail_pass"
echo "=== XH Agents Gmail App Password Setup ==="
echo "Do NOT paste your normal Gmail password. Use a 16-char App Password from:"
echo "  https://myaccount.google.com/apppasswords"
echo ""
read -s -p "Paste Gmail App Password (16 chars, no spaces, hidden): " PW
echo ""
# strip any spaces the user might include
PW=$(echo "$PW" | tr -d '[:space:]')
if [ ${#PW} -lt 16 ]; then
  echo "ERROR: password too short (expected 16 chars). Aborted."
  exit 1
fi
printf '%s' "$PW" > "$OUT"
chmod 600 "$OUT"
chown ubuntu:ubuntu "$OUT" 2>/dev/null || true
echo "Saved to $OUT (mode 600). Backend will use it to send emails."
echo "Restart the service to load: sudo systemctl restart xh-adengine"
