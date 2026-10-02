// Contract addresses on LitVM Testnet
export const CONTRACTS = {
  zkLTC: "0x40a7a0C8560492626D9bCA97C1eAf284b953098b",
  LitCountPool: "0x437F3401e3C45fe385873D3Cf5651D403ECADeE4",
} as const;

// LitVM LiteForge chain config
export const LITVM_TESTNET = {
  id: 4441,
  name: "LitVM LiteForge",
  nativeCurrency: { name: "zkLTC", symbol: "zkLTC", decimals: 18 },
  rpcUrls: {
    default: { http: ["https://liteforge.rpc.caldera.xyz/http"] },
  },
  blockExplorers: {
    default: { name: "LiteForge Explorer", url: "https://liteforge.explorer.caldera.xyz" },
  },
  testnet: true,
} as const;

// Pool constants (match contract)
export const POOL_CONFIG = {
  STAKE_AMOUNT:   BigInt("100000000000000000"), // 0.1 ether
  POOL_DURATION:  21 * 60 * 60,                 // 21 hours in seconds
  DRAW_WINDOW:    21 * 60,                       // 21 minutes in seconds
  MIN_USERS:      21,
  JACKPOT_PCT:    70,
  STAKER_PCT:     20,
  PROTOCOL_PCT:   10,
};
