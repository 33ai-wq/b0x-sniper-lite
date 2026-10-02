/**
 * src/handlers/defi-sentiment.js — DeFi macro sentiment
 */
export async function defiSentiment() {
  try {
    const [coins, yields] = await Promise.all([
      fetch("https://coins.llama.fi/chains").then(r => r.json()).catch(() => null),
      fetch("https://yields.llama.fi/pools").then(r => r.json()).catch(() => null),
    ]);
    const chainCount = coins ? Object.keys(coins).length : 0;
    const topPools = (yields?.data || []).slice(0, 5).map(p => ({
      pool: p.pool, project: p.project, chain: p.chain, apy: p.apy,
    }));
    return {
      chain_count: chainCount,
      top_pools: topPools,
      sentiment: chainCount > 30 ? "neutral" : "bearish",
      timestamp: new Date().toISOString(),
    };
  } catch (e) {
    return { error: e.message, sentiment: "unknown" };
  }
}
