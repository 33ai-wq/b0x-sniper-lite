# The Onchain Operator's Playbook — Store

Self-hosted crypto ebook store. No KYC. No marketplace. Direct USDC payment → instant EPUB delivery.

## Live Store
**URL:** `https://ebook-store.<B0x70-subdomain>.workers.dev`

## Product
- **Name:** The Onchain Operator's Playbook
- **Subtitle:** Build Paid APIs. Run Crypto Infrastructure. Earn.
- **Price:** 10 USDC ($9.99)
- **Format:** EPUB (DRM-free)
- **Words:** 6,708 (~22 paperback pages)

## Payment Flow
```
1. Buyer visits store URL
2. Clicks "Pay with USDC on Base"
3. Checkout page shows:
   - Recipient address (B0x70 Treasury: 0x57EE...F357)
   - Amount: 10 USDC
   - x402 headers to include
4. Buyer sends exact 10 USDC from any Base/Ethereum wallet
5. Buyer clicks "Check Payment & Download"
6. On-chain verification via Base RPC
7. EPUB delivered instantly if payment confirmed
```

## Infrastructure
- **Worker:** Cloudflare Workers (free tier)
- **Storage:** Cloudflare KV (ebook + invoice store)
- **Payment:** USDC on Base (eip155:8453)
- **Recipient:** 0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357 (B0x70 Treasury)

## Files
```
ebook-store-worker/
├── src/index.js          # Worker source
├── wrangler.toml         # Deploy config
└── README.md             # This file

/root/amazon_products/b0x_operator_playbook/
├── playbook.epub         # ✅ Ready (34.7 KB)
├── playbook.docx         # ✅ Ready (40 KB)
├── covers/cover.png      # ✅ Ready (1600x2560 @ 300 DPI, 166 KB)
├── PUBLISH_GUIDE.md      # Alternative: manual KDP listing
└── manuscript/           # 10 chapter source files
```

## Deploy Steps
```bash
# 1. Upload EPUB to KV
wrangler kv:key put ebook:epub --namespace-id=<KV_ID> --path=playbook.epub

# 2. Set EPUB base64 in secrets (fallback)
wrangler secret put EPUB_BASE64

# 3. Deploy worker
cd ebook-store-worker && wrangler deploy

# 4. Custom domain (optional)
wrangler routes update --zone-name=<domain> --route="ebook.domain.com/*"
```

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Landing page + buy button |
| POST | `/checkout` | Returns x402 invoice + download token |
| GET | `/download/:token?tx=0x...` | Verify tx + deliver EPUB |
| GET | `/health` | Store status + config |

## Revenue Tracking
Monitor treasury address: https://basescan.io/address/0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357

Every 10 USDC sale = $9.99 USD equivalent to B0x70 treasury. No platform fees, no KYC.