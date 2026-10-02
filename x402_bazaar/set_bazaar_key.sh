#!/usr/bin/env bash
# set_bazaar_key.sh — simpan private key (0x57ee...f357, treasury Base x402) utk sign x402bazaar
# DIPEROLEH dari Boss (mode 600). Dipakai utk sign quick-register ke x402bazaar.org.
#
# Usage:  bash set_bazaar_key.sh
# Setelah jalan: key di  /home/ubuntu/prpo_ai/x402_bazaar/.bazaar_key  (mode 600)
#                sourceable: /home/ubuntu/prpo_ai/x402_bazaar/.bazaar_env  (mode 600)
set -euo pipefail
D="/home/ubuntu/prpo_ai/x402_bazaar"
mkdir -p "$D"; chmod 700 "$D"

KEY_FILE="$D/.bazaar_key"
ENV_FILE="$D/.bazaar_env"

echo "=== x402bazaar key setup ==="
if [ -f "$KEY_FILE" ] && [ -s "$KEY_FILE" ]; then
  echo "Key sudah ada di $KEY_FILE. Skip. (Hapus dulu kalau mau ganti.)"
  exit 0
fi

echo "Paste private key treasury Base x402 (0x57ee...f357) — input hidden (mode 600): "
PRIV=""
stty -echo; IFS= read -r PRIV; stty echo; echo

case "$PRIV" in
  0x[a-fA-F0-9][a-fA-F0-9]* ) ;;
  *) echo "WARN: tidak diawali 0x/panjang tidak 66 — tetap simpan, verifikasi address di script." ;;
esac

echo "$PRIV" > "$KEY_FILE"
chmod 600 "$KEY_FILE"

cat > "$ENV_FILE" <<EOF
export BAZAAR_PRIVATE_KEY="$PRIV"
export BAZAAR_OWNER_ADDRESS="0x57eec52d76a4a78d4562fc2564101a4bd2e3f357"
EOF
chmod 600 "$ENV_FILE"

echo
echo "Tersimpan: $KEY_FILE / $ENV_FILE (mode 600)"
echo "Verifikasi address di langkah berikut (quick_register.py) sebelum POST."