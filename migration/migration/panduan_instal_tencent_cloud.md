# Panduan Instal prpo_ai di Tencent Cloud Lighthouse Ubuntu
> Langkah lengkap deploy prpo_ai (Hermes Agent) di VPS Tencent Cloud Linux Ubuntu.

## Prerequisites
- Akun Tencent Cloud aktif (B0x70 sudah punya)
- Lighthouse instance: Ubuntu 22.04 LTS, Singapore region
- Spec minimal: 2 vCPU, 4GB RAM
- SSH access ke instance

## Langkah 1: Setup Awal VPS
ssh root@IP_VPS
apt update && apt upgrade -y
apt install -y curl wget git unzip zip htop tree jq ufw

## Langkah 2: Install Python & Node.js
apt install -y python3.12 python3.12-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node --version
python3 --version

## Langkah 3: Install Hermes Agent
git clone https://github.com/33ai-wq/prpo_ai.git /root/prpo_ai
curl -o- https://raw.githubusercontent.com/NousResearch/Hermes/main/install.sh | bash
which hermes && hermes --version

## Langkah 4: Setup Python venv
cd /root/prpo_ai
python3.12 -m venv venv && source venv/bin/activate
pip install -U pip

## Langkah 5: Konfigurasi Environment
cat > /root/prpo_ai/.env << 'EOF'
LLM_API_KEY=your_nvidia_api_key_here
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=minimaxai/minimax-m3
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
POLYGON_EOA=0x0c3dc9eca78D2F245c0d7e30620d80EAF0caDF47
PAYOUT_WALLET=0x57EEC...
EOF
chmod 600 /root/prpo_ai/.env

## Langkah 6: Setup Hermes Profile
hermes auth
hermes config set profile.prpo_ai.llm_provider=nvidia
hermes config set profile.prpo_ai.llm_model=minimaxai/minimax-m3

## Langkah 7: Verifikasi Deployment
cd /root/prpo_ai && source venv/bin/activate
hermes chat --profile prpo_ai --system-prompt "Kamu adalah prpo_ai. Konfirmasi kamu online."

## Langkah 8: Setup pm2 Keep-Alive (optional)
npm install -g pm2
pm2 start hermes --name prpo_ai -- --profile prpo_ai
pm2 save && pm2 startup

## Langkah 9: Deploy CF Workers
cd /root/prpo_ai/b0x402_data/cf-worker && npx wrangler deploy
cd /root/prpo_ai/hood_sniper/worker && npx wrangler deploy
cd /root/prpo_ai/b0xlight_bridge && npx wrangler deploy
cd /root/prpo_ai/b0xm4-worker && npx wrangler deploy
cd /root/prpo_ai/bx02_cf_worker && npx wrangler deploy
cd /root/prpo_ai/ebook-store-worker && npx wrangler deploy

## Langkah 10: Domain + SSL (Tencent Console)
1. Lighthouse → Instance → Bind IPv4
2. DNS A record ke IP VPS
3. certbot --nginx atau Tencent SSL certificate free

## Troubleshooting
hermes doctor
hermes logs --profile prpo_ai
pm2 list && pm2 restart prpo_ai
wrangler tail --status error

## Migration Package Location
Local: /root/prpo_ai/migration/migration/
Obsidian: /mnt/sdcard/Documents/B0x70/Hermes Prpo AI/projects/migration-vps-tencent/

Copy dari HP ke VPS:
rsync -avz /mnt/sdcard/Documents/B0x70/Hermes\ Prpo\ AI/projects/migration-vps-tencent/ root@IP_VPS:/root/prpo_ai/migration/migration/