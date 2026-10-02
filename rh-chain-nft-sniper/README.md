# RH Chain NFT Mint Sniper

CLI sniper for public SeaDrop NFT mints on **Robinhood Chain (chain ID 4663)** — builds calldata on-chain, no OpenSea token required.

Adapted from [solotop999/opensea-nft-public-mint](https://github.com/solotop999/opensea-nft-public-mint) (MIT License).

## Features

- **On-chain calldata**: Builds mint calldata directly from SeaDrop singleton contract — no OpenSea API needed for the mint itself
- **Pre-sign transactions**: Sign all transactions before the mint opens, blast at T-0 via multiple RPC endpoints
- **Chain ID verification**: Confirms RPC returns chain ID 4663 (Robinhood Chain) before any signing
- **Dry-run mode**: Simulate via `eth_call` before broadcasting — safe testing
- **Multiple RPC support**: Blast to multiple endpoints for maximum inclusion probability
- **Interactive wizard**: Step-by-step CLI for keys, chain, quantity, target, RPC, gas, timing
- **Security first**: Private keys stay in memory only, hidden input, never written to disk

## Supported Chains

| Chain | Chain ID | Native Token | SeaDrop Singleton |
|-------|----------|--------------|-------------------|
| Robinhood Chain | 4663 | RH | 0x00005EA00Ac477B1030CE78506496e8C2dE24bf5 |
| Base | 8453 | ETH | 0x00005EA00Ac477B1030CE78506496e8C2dE24bf5 |
| Ethereum | 1 | ETH | 0x00005EA00Ac477B1030CE78506496e8C2dE24bf5 |

## Installation

```bash
cd rh-chain-nft-sniper
npm install
npm run build
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```bash
# REQUIRED: Robinhood Chain RPC URL
RPC_URL_ROBINHOOD=https://rpc.robinhood.com

# OPTIONAL: OpenSea API Key (for resolving slug/collection link to contract address)
# Get free key: curl -X POST https://api.opensea.io/api/v2/auth/keys
OPENSEA_API_KEY=your_key_here

# OPTIONAL: Default chain
CHAIN=robinhood

# OPTIONAL: Gas settings (gwei)
MAX_FEE_PER_GAS=2
MAX_PRIORITY_FEE=0.05
GAS_LIMIT=250000
```

## Usage

### Interactive Mode (Recommended)
```bash
npm start
# or
node dist/index.js
```

The wizard will guide you through:
1. **Private keys** — hidden input, one per line, verified by address
2. **Chain** — select Robinhood Chain (4663), Base, or Ethereum
3. **Quantity** — NFTs per wallet (respects per-wallet cap from contract)
4. **Target** — OpenSea link, slug, or contract address
5. **RPC endpoints** — comma-separated, or use default
6. **Gas settings** — max fee, priority fee, gas limit
7. **Timing** — wait for mint open / custom time / now
8. **Dry-run** — simulate first (default: yes)
9. **Confirm** — explicit `y` required before broadcast

### Dry-run Only
```bash
npm run dry-run
# or
node dist/index.js --dry-run
```

## Safety Features

| Feature | Description |
|---------|-------------|
| **Dry-run default** | Simulates via `eth_call`, shows expected results without broadcasting |
| **Chain ID verification** | Fails fast if RPC returns wrong chain ID (must be 4663 for RH Chain) |
| **Balance check** | Verifies each wallet has enough for `gasLimit × maxFee + mintValue` |
| **Per-wallet cap** | Respects `maxTotalMintableByWallet` from contract |
| **Private key handling** | In-memory only, readline hidden input, zero disk writes |
| **Explicit confirmation** | Requires `y` before any broadcast |

## Architecture

```
src/
├── index.ts           # Entry point, help banner
├── wizard.ts          # Interactive CLI wizard
├── seadrop-public.ts  # Calldata builder (SeaDrop singleton)
├── local-mint.ts      # Pre-sign + blast execution
├── chains.ts          # Chain profiles (incl. Robinhood Chain 4663)
├── rpc-resolver.ts    # RPC validation, chain ID verification
├── rpc-blast.ts       # RPC endpoint parsing
├── prompt.ts          # Hidden input, choices, confirmations
├── nft-link.ts        # OpenSea URL/slug/address parsing
├── slug-resolver.ts   # OpenSea API: slug → contract address
├── time-format.ts     # IST time formatting
└── local-mint.ts      # Main execution logic
```

## Security Audit

This codebase was audited before adaptation (2026-08-16):

- ✅ Dependencies: `ethers@6.9.0`, `dotenv`, `chalk`, `ora` — standard OSS
- ✅ Private keys: In-memory only, hidden input, never persisted to disk
- ✅ Network calls: RPC endpoints + optional OpenSea API (slug→contract only)
- ✅ No malware patterns: No obfuscation, no eval, no dynamic imports
- ✅ No data exfiltration: No telemetry, analytics, or phone-home
- ✅ License: MIT (forked from `morsyxbt/nft-public-mint`)

## Integration with Nomad 7

| Agent | Role |
|-------|------|
| **Scout** | Monitor OpenSea/RH Chain for new free SeaDrop collections |
| **Trader** | Execute mint via bot (gas from Treasury RH) |
| **Treasury** | Fund gas wallet (0x99cc2ca...) with RH native |
| **Sentinel** | Approve each mint action (gas cost vs value) |
| **Hermes** | Orchestrate, log to NOTE70.md |

## References

- Source Repo: https://github.com/solotop999/opensea-nft-public-mint
- Original Fork: https://github.com/morsyxbt/nft-public-mint
- Test Collection: https://opensea.io/collection/tadaaaaaa/overview (expires 08/2027)
- RH Chain Explorer: https://robinhoodchain.blockscout.com
- SeaDrop Singleton: 0x00005EA00Ac477B1030CE78506496e8C2dE24bf5 (verify on RH Chain)

## License

MIT — see LICENSE file.