#!/usr/bin/env bash
# set_cdp_creds.sh — store Coinbase CDP API credentials on the VPS (mode 600)
#
# Coinbase CDP gives TWO keys; store both here:
#   1. SERVER (Secret) API key — used by backend/ad_engine on this VPS.
#      Downloaad from CDP dashboard as <name>.json containing "name" + "privateKey",
#      share the FILE into this project, or paste the private key below.
#   2. CLIENT API key id — short public string, used by frontend (OnchainKit/RPC).
#
# The CDP python SDK reads env vars: CDP_API_KEY_NAME, CDP_API_KEY_PRIVATE_KEY,
# CDP_PROJECT_ID (all project-level) and CDP_CLIENT_KEY_ID for onchain client use.
# Cell phone / 2FA is added later; this script only stores secrets.
#
# Usage:
#   METHOD A (recommended): drop the downloaded CDP json here:
#       cp /tmp/cdp_api_key.json /home/ubuntu/prpo_ai/cdp/cdp_api_key.json
#       bash set_cdp_creds.sh --from-file /home/ubuntu/prpo_ai/cdp/cdp_api_key.json
#   METHOD B (paste hidden): bash set_cdp_creds.sh
#
set -euo pipefail

CDP_DIR="/home/ubuntu/prpo_ai/cdp"
ENV_FILE="$CDP_DIR/.env.cdp"
mkdir -p "$CDP_DIR"
chmod 700 "$CDP_DIR"

proj_id() { :; }  # placeholder (avoid accidental eval)

echo "=== Coinbase CDP credential setup ==="

# --- Project ID (always needed) ---
read -r -p "CDP_PROJECT_ID (from dashboard, e.g. 02048d5d-....): " PROJECT_ID
[ -n "$PROJECT_ID" ] || { echo "Project ID required"; exit 1; }

if [[ "${1:-}" == "--from-file" && -n "${2:-}" && -f "$2" ]]; then
  SRC="$2"
  echo "Reading CDP secret file: $SRC"
  API_KEY_NAME=$(python3 -c "import json,sys;d=json.load(open('$SRC'));print(d.get('name',''))")
  PRIVATE_KEY=$(python3 -c "import json,sys;d=json.load(open('$SRC'));print(d.get('privateKey',''))")
  [ -n "$API_KEY_NAME" ] && [ -n "$PRIVATE_KEY" ] || { echo "malformed CDP json (need name+privateKey)"; exit 1; }
elif [[ "${1:-}" == "--from-file" ]]; then
  echo "ERROR: --from-file but no/second arg not a readable file"; exit 1
else
  echo "Paste SERVER API key NAME (api key nickname, e.g. xhagents):" ; read -r API_KEY_NAME
  echo "Paste SERVER API key PRIVATE KEY (hidden, multi-line ok, end with Ctrl-D when from stdin): "
  PRIVATE_KEY=$(stty -echo; cat; stty echo); echo
  [ -n "$PRIVATE_KEY" ] || { echo "private key required"; exit 1; }
fi

# --- Client API key (frontend/RPC) — optional, public string ---
echo "Client API key id (public string, e.g. xwy6u1....bEWn7). Leave empty to skip:"
read -r CLIENT_KEY_ID

# Atomic write to .env.cdp (mode 600)
cat > "$ENV_FILE.new" <<EOF
CDP_API_KEY_NAME=$API_KEY_NAME
CDP_API_KEY_PRIVATE_KEY=$PRIVATE_KEY
CDP_PROJECT_ID=$PROJECT_ID
CDP_CLIENT_KEY_ID=$CLIENT_KEY_ID
EOF
chmod 600 "$ENV_FILE.new"
mv "$ENV_FILE.new" "$ENV_FILE"

# Sanity previews (never full values)
echo
echo "=== Saved (preview): ==="
awk -F= '{
  k=$1; v=substr($2,1,8);
  if (length($2)==0) v="(empty)"
  printf "%s = %s... (len %d)\n", k, v, length($2)
}' "$ENV_FILE"

echo
echo "Stored at $ENV_FILE (mode 600)."
echo "In a step where the backend needs the creds, source it:"
echo "  set -a; source $ENV_FILE; set +a"