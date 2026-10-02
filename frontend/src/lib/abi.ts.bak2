export const LITCOUNT_POOL_ABI = [
  // Read functions
  {
    name: "getPoolStatus",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [
      { name: "poolId",                type: "uint256" },
      { name: "participantCount",      type: "uint256" },
      { name: "totalStaked",           type: "uint256" },
      { name: "timeLeft",              type: "uint256" },
      { name: "inDrawPhase",           type: "bool"    },
      { name: "jackpotEstimate",       type: "uint256" },
      { name: "stakerRewardEstimate",  type: "uint256" },
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
  // Write functions
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
  // Events
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
    name: "DrawExecuted",
    type: "event",
    inputs: [
      { name: "poolId",               type: "uint256", indexed: false },
      { name: "winner",               type: "address", indexed: false },
      { name: "jackpot",              type: "uint256", indexed: false },
      { name: "stakerRewardPerUser",  type: "uint256", indexed: false },
    ],
  },
] as const;

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
] as const;

// Append to LITCOUNT_POOL_ABI — add forceReset
export const POOL_EXTRA_ABI = [
  {
    name: "forceReset",
    type: "function",
    stateMutability: "nonpayable",
    inputs: [],
    outputs: [],
  },
] as const;
