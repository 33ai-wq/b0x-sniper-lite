const { createPublicClient, http } = require('viem');
// Define the chain manually
const chain = {
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
};
const client = createPublicClient({
  chain: chain,
  transport: http('https://liteforge.rpc.caldera.xyz/http')
});
const poolAddress = "0x437F3401e3C45fe385873D3Cf5651D403ECADeE4";
const tokenAddress = "0x40a7a0C8560492626D9bCA97C1eAf284b953098b";
const userAddress = "0xF34900299e6f526c4e1b5967b87A880fB880d2B7";
const ZKLTC_ABI = [
  {
    name: "balanceOf",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "account", type: "address" }],
    outputs: [{ name: "", type: "uint256" }]
  },
  {
    name: "allowance",
    type: "function",
    stateMutability: "view",
    inputs: [
      { name: "owner", type: "address" },
      { name: "spender", type: "address" }
    ],
    outputs: [{ name: "", type: "uint256" }]
  }
];
const LITCOUNT_POOL_ABI = [
  {
    name: "hasJoined",
    type: "function",
    stateMutability: "view",
    inputs: [{ name: "", type: "address" }],
    outputs: [{ name: "", type: "bool" }]
  },
  {
    name: "getPoolStatus",
    type: "function",
    stateMutability: "view",
    inputs: [],
    outputs: [
      { name: "poolId", type: "uint256" },
      { name: "participantCount", type: "uint256" },
      { name: "totalStaked", type: "uint256" },
      { name: "timeLeft", type: "uint256" },
      { name: "inDrawPhase", type: "bool" },
      { name: "jackpotEstimate", type: "uint256" },
      { name: "stakerRewardEstimate", type: "uint256" }
    ]
  }
];
(async () => {
  try {
    const balance = await client.readContract({
      address: tokenAddress,
      abi: ZKLTC_ABI,
      functionName: "balanceOf",
      args: [userAddress]
    });
    console.log('User zkLTC balance (wei):', balance.toString());
    console.log('User zkLTC balance (zkLTC):', Number(balance) / 1e18);
  } catch (e) {
    console.error('Balance error:', e.message);
  }
  try {
    const allowance = await client.readContract({
      address: tokenAddress,
      abi: ZKLTC_ABI,
      functionName: "allowance",
      args: [userAddress, poolAddress]
    });
    console.log('User allowance for pool (wei):', allowance.toString());
    console.log('User allowance for pool (zkLTC):', Number(allowance) / 1e18);
  } catch (e) {
    console.error('Allowance error:', e.message);
  }
  try {
    const hasJoined = await client.readContract({
      address: poolAddress,
      abi: LITCOUNT_POOL_ABI,
      functionName: "hasJoined",
      args: [userAddress]
    });
    console.log('User hasJoined:', hasJoined);
  } catch (e) {
    console.error('hasJoined error:', e.message);
  }
  try {
    const poolStatus = await client.readContract({
      address: poolAddress,
      abi: LITCOUNT_POOL_ABI,
      functionName: "getPoolStatus"
    });
    console.log('Pool status:', {
      participantCount: Number(poolStatus[1]),
      timeLeft: Number(poolStatus[3]),
      inDrawPhase: Boolean(poolStatus[4])
    });
  } catch (e) {
    console.error('Pool status error:', e.message);
  }
})();
