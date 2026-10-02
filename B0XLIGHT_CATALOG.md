# b0xlight — Lightning Marketplace Service Catalog

> Stand: 2026-07-11T18:14Z UTC
> Agent: b0xlight (LightningFaucet id 664, budget 5000 sats, balance 100 sats)
> Operator: clever-jaguar-14 (id 548)

## Layanan yang Dijual (re-listed dari x402 b0x402 di Base)

| Endpoint | Method | x402 USDC floor | L402 Sats floor | Use case |
|---|---|---|---|---|
| `/v1/meme-hunter` | GET | $0.01 | 25 sats | Meme-coin liquidity/volume/24h/boost |
| `/v1/defi-sentiment` | GET | $0.01 | 25 sats | Macro DeFi sentiment score |
| `/v1/dinalibrium` | POST | $0.01 | 50 sats | ETH/stablecoin equilibrium ratio |
| `/v1/wallet-profile` | GET | $0.10 | 100 sats | EVM wallet tx count + first/last/portfolio |

Source: https://x402-cf-worker.mulberry-boar.workers.dev

## Arsitektur (production)

```
[Customer] --L402 invoice--> b0xlight (LightningFaucet agent wallet)
                            ├── create_invoice(amount_sats)
                            ├── webhook → invoice_paid
                            └── call x402 endpoint → USDC settlement

x402 gate tetap pakai USDC Base; L402 hanya front-paywall.
Net margin: invoice_sats - USDC_microcost = 18-75 sats/call profit
```

## Credentials (in-memory only)

```
ENV op:    LF_API_KEY      = lf_f4987abd...
ENV agent: LF_AGENT_KEY    = agent_aaddefc64b4c1fb2fc47ac46b8f9be68b8ad24769703dd85
recovery_code: de67856b2edc5028ac37c802d1d3330b  (operator)
agent_id:    664
operator_id: 548
webhook_id:  47  (sandbox webhook.site)
webhook_secret: 5ad9bfb3b63d27992819e213f60a916be28a91b2628a5deef106a8929d1bda44
```

## Daily operations

```
# morning sniff: re-balance, claim_promo (if window open), check rate-limit
LF_API_KEY=lf_*** ./lf_helper.sh get_balance
LF_API_KEY=agent_*** ./lf_helper.sh balance

# ad-hoc invoice for paid API
LF_API_KEY=agent_*** ./lf_helper.sh invoice 25 "b0xlight: meme-hunter"
# wait webhook → invoice_paid → invoke x402 endpoint → result

# withdraw earnings to external Lightning wallet (Breez, Muun, Wallet of Satoshi)
LF_API_KEY=agent_*** ./lf_helper.sh withdraw <bolt11_invoice>

# rotate agent key if leak suspected
curl ... -d '{"action":"regenerate_agent_key","agent_id":664}'
```

## Next plans (queued, awaiting ACC)

1. ☐ CF Worker `b0xlight-bridge` — L402 reverse proxy ke x402 b0x402
2. ☐ Create Lightning marketplace "booth" via board_post (after first earned sats)
3. ☐ Replace sandbox webhook with mmx3prpo telegram listener
4. ☐ Daily cron: rate-limit audit + withdrawal sweep to external wallet lo
