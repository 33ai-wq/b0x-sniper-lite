# Active Projects — prpo_ai
> Status terakhir. Carry forward ke VPS Tencent Cloud.

## Income-Generating (Primary)

### b0x402 (x402scan)
- Type: CF Worker x402 API seller
- URL: https://www.x402scan.com/server/d43eaf95-accd-49a0-a613-96b275d9dfeb
- Status: ACTIVE — primary income
- Source: /root/prpo_ai/b0x402_data/cf-worker/
- Revenue: $0.005-$0.10 per x402 API call (USDC)
- Payout: 0x57EEC... (Base)

### hood-sniper
- Type: CF Worker multi-source RH Chain radar
- URL: hood-sniper.mulberry-boar.workers.dev
- Status: ACTIVE
- Source: /root/prpo_ai/hood_sniper/worker/
- Endpoints: /radar/feed (FREE), /radar ($0.005 USDC Base)
- Payout: 0x57EEC...

## Infrastructure Workers

### b0xlight-bridge
- Source: /root/prpo_ai/b0xlight_bridge/ (204MB)
- Status: ACTIVE

### b0xm4-solana-x402-worker
- Source: /root/prpo_ai/b0xm4-worker/
- Status: ACTIVE

### bx02-cf-worker
- Source: /root/prpo_ai/bx02_cf_worker/ (256MB)
- Status: ACTIVE

### ebook-store-worker
- Source: /root/prpo_ai/ebook-store-worker/
- Status: ACTIVE

## Supporting

### marketplace_listings
- Source: /root/prpo_ai/marketplace_listings/
- Status: ACTIVE — price labels match live CF Workers

### b0x402_repo_mirror
- GitHub: 33ai-wq/b0x402-data
- Status: Synced, push done

## Agent System
- Location: /root/prpo_ai/
- Hermes profile: prpo_ai
- Model: minimaxai/minimax-m3 via Nvidia
- LLM: https://integrate.api.nvidia.com/v1

## Suspended / Blocked
- Meridian LP bot (pm2 stopped) — waiting account verification
- All auto-trading — suspended until capital >= $10-20

## Next Steps
1. Resume b0x402 maintenance after VPS migration
2. Monitor hood-sniper daily feeds
3. Evaluate bx02 GitHub automation for prpo_ai autonomy
4. Explore Solana x402 integration for b0xm4