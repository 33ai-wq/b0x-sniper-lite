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
console.log('Checking pool address:', poolAddress);
console.log('Checking token address:', tokenAddress);
console.log('Checking user address:', userAddress);
// First, check if the pool address has code
(async () => {
  try {
    const code = await client.getCode({ address: poolAddress });
    console.log('Pool contract code length:', code.length);
    if (code.length === 0) {
      console.log('Pool address has no code - not a contract');
    } else {
      console.log('Pool address has code');
    }
  } catch (e) {
    console.error('Error getting pool code:', e.message);
  }
  try {
    const code = await client.getCode({ address: tokenAddress });
    console.log('Token contract code length:', code.length);
    if (code.length === 0) {
      console.log('Token address has no code - not a contract');
    } else {
      console.log('Token address has code');
    }
  } catch (e) {
    console.error('Error getting token code:', e.message);
  }
})();
