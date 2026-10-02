const { createPublicClient, http } = require('viem');
const { LITVM_TESTNET } = require('./src/lib/config');
const { LITCOUNT_POOL_ABI, ZKLTC_ABI } = require('./src/lib/abi');
const client = createPublicClient({
  chain: LITVM_TESTNET,
  transport: http('https://liteforge.rpc.caldera.xyz/http')
});
const poolAddress = '0x437F3401e3C45fe385873D3Cf5651D403ECADeE4';
const tokenAddress = '0x40a7a0C8560492626D9bCA97C1eAf284b953098b';
const userAddress = '0xF34900299e6f526c4e1b5967b87A880fB880d2B7';
(async () => {
  try {
    const balance = await client.readContract({
      address: tokenAddress,
      abi: ZKLTC_ABI,
      functionName: 'balanceOf',
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
      functionName: 'allowance',
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
      functionName: 'hasJoined',
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
      functionName: 'getPoolStatus'
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
