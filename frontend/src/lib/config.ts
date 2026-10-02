// Contract addresses on LitVM Testnet
export const CONTRACTS = {
  zkLTC: "0xfbf1bD97e8511445Cc4FA180A5C3724d94642F8C",
  LitCountPool: "0x7903e5B54913Fd67dA541F478b17c8B342C82b83",
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

export const POOL_CONFIG = {
  STAKE_AMOUNT:   BigInt("1000000000000000000"),  // 1 zkLTC (was 0.1 — adjusted to match 10zkLTC faucet)
  POOL_DURATION:  21 * 60 * 60,
  DRAW_WINDOW:    21 * 60,
  MIN_USERS:      21,
  JACKPOT_PCT:    70,
  STAKER_PCT:     20,
  PROTOCOL_PCT:   10,
};
