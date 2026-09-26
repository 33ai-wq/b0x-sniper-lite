#!/usr/bin/env bash
# set_alchemy_key.sh — simpan API key Alchemy (Base Mainnet) ke VPS, mode 600, lalu sambungkan
# ke semua service yang berbicara dengan RPC Base.
#
# Cara pakai (dari SSH Boss, bukan lewat chat):
#     bash /home/ubuntu/prpo_ai/keys/set_alchemy_key.sh
# Script akan meminta key dua kali (tersembunyi, tidak di-echo, tidak masuk history).
#
# Yang ditulis:
#     keys/alchemy.key          (mode 600) — key mentah saja
#     keys/alchemy_env          (mode 600) — siap di-source: XH_BASE_RPC + fallback
#     /etc/systemd/system/<unit>.service.d/alchemy.conf  — EnvironmentFile untuk tiap service
set -euo pipefail

KEY_DIR="/home/ubuntu/prpo_ai/keys"
KEY_FILE="$KEY_DIR/alchemy.key"
ENV_FILE="$KEY_DIR/alchemy_env"
HOST_TMPL="https://base-mainnet.g.alchemy.com/v2/%s"
UNITS=(xh-api xh-adengine xh-chatengine xh-kb)

echo "=== Alchemy API key untuk XH Agents (Base Mainnet) ==="
echo "Tempel key-nya di sini (tidak akan terlihat saat diketik):"
read -rs KEY1; echo
echo "Ulangi sekali lagi untuk memastikan tidak salah tempel:"
read -rs KEY2; echo

if [ "$KEY1" != "$KEY2" ]; then
  echo "!! Kedua input berbeda — dibatalkan, tidak ada yang ditulis."
  exit 1
fi
unset KEY2

# Alchemy key: alfanumerik/underscore/dash, panjang wajar (biasanya 32)
if ! [[ "$KEY1" =~ ^[A-Za-z0-9_-]{20,64}$ ]]; then
  echo "!! Format key tidak wajar (harus 20-64 karakter alfanumerik/-/_), dibatalkan."
  exit 1
fi

RPC_URL="$(printf "$HOST_TMPL" "$KEY1")"

mkdir -p "$KEY_DIR"; chmod 700 "$KEY_DIR"
umask 077
printf '%s\n' "$KEY1" > "$KEY_FILE"; chmod 600 "$KEY_FILE"
cat > "$ENV_FILE" <<EOF
# dibaca oleh XH Agents services (systemd EnvironmentFile) — mode 600
XH_BASE_RPC=$RPC_URL
XH_BASE_RPC_FALLBACKS=https://base-rpc.publicnode.com,https://mainnet.base.org
ALCHEMY_API_KEY=$KEY1
EOF
chmod 600 "$ENV_FILE"

# sambungkan ke service (systemd drop-in, tidak mengubah unit aslinya)
NEEDS_SUDO=0
for u in "${UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$u.service" ]; then
    if sudo -n true 2>/dev/null || [ "$(id -u)" = "0" ]; then
      sudo mkdir -p "/etc/systemd/system/$u.service.d"
      printf '[Service]\nEnvironmentFile=-%s\n' "$ENV_FILE" | sudo tee "/etc/systemd/system/$u.service.d/alchemy.conf" >/dev/null
      sudo chmod 644 "/etc/systemd/system/$u.service.d/alchemy.conf"
      echo "   drop-in dipasang untuk $u"
    else
      NEEDS_SUDO=1
      echo "   (butuh sudo untuk $u — jalankan bagian sudo di bawah setelah ini)"
    fi
  fi
done

if [ "$NEEDS_SUDO" = "1" ]; then
  echo
  echo "Jalankan ini sekali (akan minta password sudo):"
  for u in "${UNITS[@]}"; do
    [ -f "/etc/systemd/system/$u.service" ] || continue
    echo "  sudo mkdir -p /etc/systemd/system/$u.service.d && printf '[Service]\\nEnvironmentFile=-$ENV_FILE\\n' | sudo tee /etc/systemd/system/$u.service.d/alchemy.conf >/dev/null"
  done
  echo "  sudo systemctl daemon-reload"
fi

echo
echo "Verifikasi RPC baru (tidak menampilkan key):"
if command -v jq >/dev/null; then
  curl -s -X POST "$RPC_URL" -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' --max-time 25 | jq -c .
else
  curl -s -X POST "$RPC_URL" -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' --max-time 25 | head -c 200; echo
fi

echo
echo "Selesai. Ringkasan:"
echo "  key tersimpan : $(stat -c '%a' "$KEY_FILE") mode, ${#KEY1} karakter (preview ${KEY1:0:4}...${KEY1: -4})"
echo "  env           : $ENV_FILE (mode $(stat -c '%a' "$ENV_FILE"))"
echo
echo "Langkah terakhir (aktifkan di service):"
echo "  sudo systemctl daemon-reload && sudo systemctl restart ${UNITS[*]}"
echo "  curl -s http://127.0.0.1:8991/health"
