# PROJECT REGISTRY -- prpo_ai

> Read this file FIRST before starting work or creating a new project.
> Last updated: 2026-08-30
> Active models: nvidia/nemotron-3-super-120b-a12b (primary, NIM)

## How to use this file
- Every project folder inside `prpo_ai/` must have one entry here.
- Status values used:
  - `ACTIVE`   -> current main focus, can be worked on daily
  - `LIVE`     -> already running on its own, low-touch, only touch if there's an issue
  - `DORMANT`  -> paused, not yet decided whether to continue
  - `ARCHIVED` -> moved to `prpo_ai/archive/`, outside Hermes' active scope

## Active Priority (max 1-2 projects here)
| # | Project | Path | Goal | Next action |
|---|---|---|---|---|
| 1 | **XH Agents Monetization** | `prpo_ai/BossyFactory/` + `prpo_ai/adengine/` | Monetize all prototypes via xhagents.xyz with x402 USDC payment gate | Traffic acquisition + advertiser outreach (see NOTE70) |
| 2 | **nGRND Ecosystem Analyzer** | `prpo_ai/sniper/rh/ngrnd_analyzer.py` | Safe monitoring of nGRND ecosystem news — alerts to `@sangatbit_bot` | Bot live, polling 1h; add Airdrop tracker via official nGRND API when available |

## Live / Low-touch (MONETIZED)
| Project | Path | Monetize Model | Status |
|---|---|---|---|
| **Ad Engine** | `prpo_ai/adengine/` | Ad space $35-60/mo via USDC | LIVE on xhagents.xyz, pipeline verified, awaiting advertiser |
| **AI Trading Assistant** | `BossyFactory/trading-agent/` | Pay-per-message $0.10 USDC | LIVE on xhagents.xyz/trading/, NIM working, balance gate active |
| RH Chain Sniper Monitor | `prpo_ai/sniper/rh/` | Telegram alert bot | LIVE, 9min interval, @N0xte70_bot |
| Dinalibrium ($DINA) | `prpo_ai/dinalibrium/` | Token live on pump.fun | No routine maintenance |

## Dormant / Monetable (needs packaging)
| Project | Path | Monetize Potential | Status |
|---|---|---|---|
| **b0x402 API** | `prpo_ai/b0x402_repo/` | Pay-per-call $0.01-0.10 (4 endpoints: meme-hunter, defi-sentiment, dinalibrium, wallet-profile) | Code complete, CF worker + Base x402, needs listings + buyer traffic |
| **RH Chain NFT Sniper** | `prpo_ai/rh-chain-nft-sniper/` | Tool/SaaS for NFT snipers | Dry-run verified, test collection ready |
| **Auto Sniper (Solana Jupiter)** | `prpo_ai/auto_sniper/` | Bot execution service | Ready for live trade (needs wallet funding >=0.05 SOL) |
| **MCP Sniper (TradingView+DEX)** | `prpo_ai/mcp_sniper/` | Alert service / SaaS | LIVE, sends to Telegram, 8 candidates per scan |
| **Ebook Store** | `prpo_ai/ebook-store-worker/` | $9.99 USDC ebook | Worker ready, Cloudflare deploy needed |
| **Hood Sniper** | `prpo_ai/hood_sniper/` | Token discovery SaaS | Worker + engine built, needs deployment |
| **Ataraxia** | `/home/ubuntu/ataraxia/ataraxia-react` (+ `server/`) | 0.10 USDC per film (Base) | LIVE — quiet room on Base: free breathing + 4 paid XH Animations (109 s). Base App-ready (SIWE + wagmi/viem), Builder Code attribution pending. Rewards: 25% of daily revenue, wallet `0x3726570F9F73a7dB7437fEE42C8B4887A59E1dcC` (key mode 600), payout dry-run only |
| LitCount | `prpo_ai/litcount_repo/` | — | DORMANT |
| Agent Meridian (LP bot) | `prpo_ai/skills/blockchain/meridian-dlmm/` | — | DORMANT |

## Tools / Infra (not standalone income projects)
| Tool | Path | Purpose |
|---|---|---|
| opportunity_scanner | `prpo_ai/opportunity_scanner/` | Scans yield/trending opportunities |
| b0x402_repo_mirror | `prpo_ai/b0x402_repo_mirror/` | Backup of b0x402 (can archive) |
| x402_lib | `prpo_ai/x402_lib/` | Shared x402 invoice/payment lib |
| cf-worker / bx02_cf_worker / solana_x402_worker / base_x402_worker | Various | Cloudflare Worker variants for b0x402 endpoints |
| Obsidian vault | (on Android, separate) | Knowledge/integration layer |

## Archived
| Project | New path | Archived on | Reason |
|---|---|---|---|
| migration | `prpo_ai/migration/` | 2026-08-30 | Old memory exports, no longer needed |

---
### Rule for Hermes
1. Before starting a work session or being asked to "find opportunities" / "continue project X", check this file first.
2. If starting a new project, MUST add an entry here first and set its priority -- don't start working silently without logging it.
3. If unsure about a project's status, ask the operator (Philo) instead of assuming.
4. Reports and any communication sent to the Boss (Philo) must still be written in Bahasa Indonesia -- this file's language is English only for internal instruction clarity.
