# LitCount Whitepaper
## Save & Win DeFi Pool Protocol

**Version:** 1.0  
**Network:** LitVM Testnet  
**Asset:** $zkLTC  
**Category:** DeFi — Pool Staking  
**Tagline:** *Just stake it dan get reward.*  
**About:** Becoming a Truly Rich Person

---

## Abstract

LitCount is a decentralized pool staking protocol built on LitVM Testnet that implements a novel "Save & Win" mechanism. Users stake a fixed amount of `$zkLTC` tokens into a communal pool, receive guaranteed base rewards for participation, and compete for a jackpot prize distributed through an on-chain random draw every 21 hours.

The protocol is designed around three core principles: **fairness** (every staker receives a reward), **excitement** (a jackpot creates engagement), and **simplicity** (single stake amount, clear rules, automatic execution).

---

## 1. Introduction

### 1.1 Problem Statement

Traditional DeFi staking protocols often suffer from:

- **Complexity** — Users must navigate complex tokenomics, vesting schedules, and variable APRs
- **Winner-takes-all** — High-yield strategies concentrate rewards among large holders
- **Low engagement** — Passive staking generates minimal user excitement or retention
- **Unfair distribution** — Large wallets disproportionately benefit from reward mechanisms

### 1.2 Solution

LitCount introduces the "Save & Win" model — a hybrid between prize-linked savings accounts and lottery pools. Every participant:

1. Stakes a fixed, equal amount (`0.1 $zkLTC`)
2. **Automatically** receives a proportional base reward from the pool
3. Participates in a random jackpot draw for a larger prize

This ensures no participant walks away empty-handed, while the jackpot element creates meaningful engagement and word-of-mouth viral growth.

---

## 2. Protocol Mechanics

### 2.1 Pool Structure

| Parameter | Value |
|---|---|
| Stake Amount | 1 $zkLTC per user |
| Pool Duration | 21 hours |
| Draw Window | 21 minutes |
| Minimum Users | 21 participants |
| Jackpot Share | 70% of total pool |
| Staker Share | 20% of total pool (split equally) |
| Protocol Fee | 10% of total pool |

### 2.2 Save & Win Reward Formula

Given `N` participants:

```
Total Pool     = N × 1 zkLTC

Jackpot        = Total Pool × 70%
               = N × 0.7 zkLTC  →  1 lucky winner

Staker Reward  = (Total Pool × 20%) ÷ N
               = 0.2 zkLTC per staker  →  everyone receives this

Protocol Fee   = Total Pool × 10%
               = N × 0.1 zkLTC  →  treasury
```

**Example with 500 participants:**

| Recipient | Formula | Amount |
|---|---|---|
| Jackpot winner | 500 × 1 × 70% | **350 zkLTC** |
| Each staker | (500 × 1 × 20%) ÷ 500 | **0.2 zkLTC** |
| Protocol | 500 × 1 × 10% | 50 zkLTC |

Every staker receives `0.2 zkLTC` guaranteed. The lucky winner receives an additional `350 zkLTC` jackpot on top of their staker reward.

### 2.3 Pool Lifecycle

```
Phase 1 — Open Pool (21 hours)
  → Users call joinPool() and stake 0.1 $zkLTC
  → Pool accepts new participants continuously

Phase 2 — Trigger Check
  → After 21 hours, anyone calls triggerDrawPhase()

Phase 3A — Draw Phase (if ≥ 21 users)
  → Pool closes for 21 minutes
  → executeDraw() selects random winner on-chain
  → Jackpot sent to winner
  → Base reward sent to all stakers
  → Protocol fee sent to treasury
  → Pool fully resets → new cycle begins

Phase 3B — No Draw (if < 21 users)
  → Pool remains open, timer resets
  → Existing participants stay in pool
  → New users can still join
  → No funds lost, no participant removed
```

### 2.4 Minimum User Rule

The minimum of 21 participants protects the jackpot mechanism's viability. If fewer than 21 users have staked when the draw is triggered:

- No draw is executed
- No funds are moved
- All participants **remain** in the pool
- The 21-hour timer restarts
- New participants can join the ongoing pool

This rule ensures the jackpot is meaningful (minimum `21 × 1 × 70% = 14.7 zkLTC`) and prevents manipulation by very small participant groups.

---

## 3. Smart Contract Architecture

### 3.1 Contract Overview

The protocol consists of two smart contracts:

**`zkLTC.sol`** — ERC20 Testnet Token
- Standard ERC20 implementation
- Built-in faucet (10 zkLTC per claim, 24-hour cooldown)
- Admin mint for pool seeding

**`LitCountPool.sol`** — Core Pool Logic
- Pool state management
- Participant tracking
- Draw execution
- Reward distribution
- Emergency pause mechanism

### 3.2 Security Design

| Feature | Implementation |
|---|---|
| Re-entrancy protection | `ReentrancyGuard` on all write functions |
| Safe token transfers | `SafeERC20` library |
| Emergency stop | `Pausable` pattern |
| Access control | `Ownable` for admin functions |
| Randomness | Pseudo-random (testnet); Chainlink VRF for mainnet |
| Emergency withdrawal | Only when contract is paused |

### 3.3 Randomness

For the testnet implementation, winner selection uses a pseudo-random function:

```solidity
uint256 randomIndex = uint256(
    keccak256(abi.encodePacked(
        block.timestamp,
        block.prevrandao,
        participants.length,
        msg.sender
    ))
) % count;
```

> **Mainnet Upgrade:** For production deployment, Chainlink VRF v2 will be integrated to provide verifiably random, manipulation-resistant winner selection.

### 3.4 Pool History

Every completed round (whether a draw was held or not) is recorded on-chain:

```solidity
struct PoolResult {
    uint256 poolId;
    address winner;
    uint256 jackpot;
    uint256 stakerRewardPerUser;
    uint256 totalParticipants;
    uint256 totalPool;
    uint256 timestamp;
    bool    drawHeld;
}
```

This creates a permanent, transparent record of all pool outcomes.

---

## 4. Token: $zkLTC

`$zkLTC` (zkLTC Testnet) is the native staking asset of the LitCount protocol on LitVM Testnet.

| Property | Value |
|---|---|
| Name | zkLTC Testnet |
| Symbol | $zkLTC |
| Decimals | 18 |
| Type | ERC20 |
| Faucet | 10 zkLTC per 24 hours |
| Initial Supply | 1,000,000 zkLTC |

### Faucet

Any address can claim `10 $zkLTC` from the built-in faucet once every 24 hours. This allows new users to immediately participate in the pool without needing external token sources.

---

## 5. Frontend Application

The LitCount web application provides a seamless user experience for interacting with the protocol.

### 5.1 Key Features

- **Connect Wallet** — RainbowKit integration supporting MetaMask, WalletConnect, and other EVM wallets
- **Real-time Pool Status** — Live countdown timer, participant count, estimated rewards
- **One-click Join** — Approve + stake in guided steps
- **Faucet Access** — Claim testnet tokens directly from the UI
- **Pool History** — On-chain round results with winner and reward data
- **Draw Phase UI** — Live 21-minute draw countdown with status updates

### 5.2 Tech Stack

| Component | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| UI Library | React 18 |
| Web3 | wagmi v2 + viem |
| Wallet Connect | RainbowKit v2 |
| Styling | Tailwind CSS |
| Deployment | Vercel |
| Version Control | GitHub |

---

## 6. Deployment

### 6.1 Network

LitCount is deployed on **LitVM Testnet**, an EVM-compatible test network.

### 6.2 Deployment Steps

1. Deploy `zkLTC.sol` → get token address
2. Deploy `LitCountPool.sol` with token address and treasury
3. Seed pool contract with reserve tokens via `adminMint()`
4. Update frontend config with deployed addresses
5. Deploy frontend to Vercel
6. Push all code to GitHub

### 6.3 Verification

All contracts are verified on the LitVM Testnet block explorer for full transparency.

---

## 7. Roadmap

### Phase 1 — Testnet (Current)
- [x] Smart contract development (Foundry)
- [x] Frontend application (Next.js)
- [x] Wallet integration (RainbowKit + wagmi)
- [x] LitVM Testnet deployment
- [x] GitHub repository
- [x] Vercel deployment

### Phase 2 — Mainnet
- [ ] Chainlink VRF integration
- [ ] Security audit
- [ ] Mainnet deployment
- [ ] Multiple pool tiers

### Phase 3 — Ecosystem
- [ ] Governance token
- [ ] Referral rewards
- [ ] Mobile application
- [ ] Cross-chain pools

---

## 8. Risk Disclaimer

LitCount is an experimental DeFi protocol deployed on testnet. The current implementation uses pseudo-random number generation which is not suitable for mainnet without Chainlink VRF. Users should:

- Only use testnet tokens with no real monetary value
- Understand that smart contracts may contain bugs
- Not invest more than they are willing to lose on any mainnet version

---

## 9. Conclusion

LitCount demonstrates that DeFi protocols can be simultaneously **fair**, **exciting**, and **simple**. The "Save & Win" mechanism ensures:

- ✅ Every participant receives a guaranteed reward (20% share)
- ✅ An exciting jackpot creates engagement (70% prize)
- ✅ The protocol is self-sustaining (10% fee)
- ✅ Clear rules prevent confusion
- ✅ No minimum holding periods
- ✅ Transparent on-chain execution

*Becoming a Truly Rich Person — one pool at a time.*

---

**Links:**
- GitHub: `https://github.com/33ai-wq/litcount`
- App: `https://litcount.vercel.app`
- Network: LitVM Testnet Explorer

---

*LitCount Whitepaper v1.0 — DeFi Pool Staking on LitVM Testnet*
