# Core Memory Dump — prpo_ai
> Di-export dari Termux session Juli 2026. Load saat prpo_ai pertama online di VPS.

## B0x70 Profile
- Nama: B0x70 (BOSS — authority tertinggi)
- Bahasa: Indonesian internal, English product-facing
- Payment: USDC (Polygon/Base), Lightning (withdrawal sink only)
- Platform: Telegram (@fortycrypto target)
- Cost: $0 first, free tools only

## Financial State
- Polygon EOA: 0x0c3dc9eca78D2F245c0d7e30620d80EAF0caDF47 (Polymarket target)
- Meridian pm2: STOPPED pid 11549 — waiting account verification
- Strategy: MANUAL TRADE ONLY until capital >= $10-20
- LN Address: ancientpalm680@walletofsatoshi.com (Spark self-custody, withdrawal ONLY)

## Income Architecture
| Asset | Type | Status |
|-------|------|--------|
| b0x402 | CF Worker x402 API seller | ACTIVE |
| hood-sniper | CF Worker RH Chain radar | ACTIVE |
| b0xlight-bridge | CF Worker inline mirror | ACTIVE |
| b0xm4 | CF Worker Solana x402 | ACTIVE |
| bx02 | CF Worker GitHub automation | ACTIVE |
| ebook-store | CF Worker content monetization | ACTIVE |
| marketplace_listings | b0x Marketplace catalog | ACTIVE |

## Key Decisions Log
- 2026-07-07: Stop all bots, manual-trade-only until capital >= $10-20
- 2026-07-13: Product-facing English by default
- 2026-07-16: hood-sniper deployed (hood-sniper.mulberry-boar.workers.dev)
- 2026-07-17: xpaysh PRs merged (#690, #702)
- 2026-07-18: B0x70 LN Address supplied
- 2026-07-19: Lessons: HOLD > intent, KeyChain != Obsidian, .env audit via grep
- 2026-07-21: x402scan primary verified (UUID d43eaf95)

## Lessons (Hardened)
1. HOLD > intent: Bos "JANGAN..." gate always wins
2. KeyChain != Obsidian: vault has no keystore
3. .env audit: grep -oE '^[A-Z_][A-Z0-9_]*' | sort -u — never dump values
4. B0x70 direct primary URL supersedes other evidence

## Environment
- VPS Target: Tencent Cloud Lighthouse Singapore, 2vCPU/4GB
- Current: Termux on Android
- Future: VPS Tencent + PC B0x70 connect ke environment cloud sama
- Vault Obsidian: /mnt/sdcard/Documents/B0x70/Hermes Prpo AI/
- Repo local: /root/prpo_ai/

## Pending / Blocked
- Meridian LP bot: STOPPED — wait account verification
- All auto-trading: SUSPENDED until capital >= $10-20

## First Message (say this when online in VPS)
> prpo_ai, ini adalah Migration Package kamu dari Termux. Load semua memory, project, personality. Konfirmasi kalau sudah sinkron 100%.