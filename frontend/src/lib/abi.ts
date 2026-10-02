// ABI for LitCount contracts
// Contract: 0x7903e5B54913Fd67dA541F478b17c8B342C82b83 (LitCountPool)
// Token:    0xfbf1bD97e8511445Cc4FA180A5C3724d94642F8C (zkLTC)
// Network:  LitVM LitForge Testnet (chainId: 4441)

export const LITCOUNT_POOL_ABI = [
  // ── Read functions ───────────────────────────────────────────────
  {
    name: "getPoolStatus",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [
      { name: "poolId",              type: "uint256" },
      { name: "participantCount",    type: "uint256" },
      { name: "totalStaked",         type: "uint256" },
      { name: "timeLeft",            type: "uint256" },
      { name: "inDrawPhase",         type: "bool"    },
      { name: "jackpotEstimate",     type: "uint256" },
      { name: "stakerRewardEstimate",type: "uint256" },
    ],
  },
  {
    name: "getParticipantCount",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "getPoolHistory",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [
      {
        name: "",
        type: "tuple[]",
        components: [
          { name: "poolId",              type: "uint256" },
          { name: "winner",              type: "address" },
          { name: "jackpot",             type: "uint256" },
          { name: "stakerRewardPerUser", type: "uint256" },
          { name: "totalParticipants",   type: "uint256" },
          { name: "totalPool",           type: "uint256" },
          { name: "timestamp",           type: "uint256" },
          { name: "drawHeld",            type: "bool"    },
        ],
      },
    ],
  },
  {
    name: "hasJoined",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "isDrawPhase",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "drawExecuted",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "lastWinner",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "address" }],
  },
  {
    name: "lastJackpot",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "getDrawPhaseTimeLeft",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "poolStartTime",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "currentPoolId",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "getParticipants",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "address[]" }],
  },
  // ── Write functions ──────────────────────────────────────────────
  {
    name: "joinPool",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  {
    name: "triggerDrawPhase",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  {
    name: "executeDraw",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  {
    name: "forceReset",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  // ── Events ───────────────────────────────────────────────────────
  {
    name: "Joined",
    type: "event",
    inputs: [
      { name: "user",              type: "address", indexed: true  },
      { name: "poolId",            type: "uint256", indexed: false },
      { name: "totalParticipants", type: "uint256", indexed: false },
    ],
  },
  {
    name: "DrawPhaseStarted",
    type: "event",
    inputs: [
      { name: "poolId",         type: "uint256", indexed: false },
      { name: "participants",   type: "uint256", indexed: false },
      { name: "timestamp",       type: "uint256", indexed: false },
    ],
  },
  {
    name: "DrawExecuted",
    type: "event",
    inputs: [
      { name: "poolId",              type: "uint256", indexed: false },
      { name: "winner",              type: "address", indexed: false },
      { name: "jackpot",             type: "uint256", indexed: false },
      { name: "stakerRewardPerUser", type: "uint256", indexed: false },
    ],
  },
  {
    name: "DrawSkipped",
    type: "event",
    inputs: [
      { name: "poolId",    type: "uint256", indexed: false },
      { name: "participants", type: "uint256", indexed: false },
      { name: "reason",    type: "string",  indexed: false },
    ],
  },
  {
    name: "PoolReset",
    type: "event",
    inputs: [
      { name: "newPoolId", type: "uint256", indexed: false },
      { name: "timestamp", type: "uint256", indexed: false },
    ],
  },
] as const;

// NOTE: Removed getCurrentRoundInfo from ABI — it does NOT exist in the contract.
// The contract only has: getPoolStatus, triggerDrawPhase, executeDraw, forceReset

export const ZKLTC_ABI = [
  {
    name: "approve",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount",  type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "allowance",
    type: "function",
    stateMutability: "view",
    inputs: [
      { name: "owner",   type: "address" },
      { name: "spender", type: "address" },
    ],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "balanceOf",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "transfer",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to",     type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
  },
  {
    name: "faucet",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
  {
    name: "cooldownRemaining",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "user", type: "address" }],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "totalSupply",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
  {
    name: "decimals",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint8" }],
  },
] as const;