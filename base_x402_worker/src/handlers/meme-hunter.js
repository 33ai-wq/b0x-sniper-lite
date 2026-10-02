/**
 * src/handlers/meme-hunter.js — DexScreener top meme signals (Base)
 */
import { CFG } from "../config.js";

export async function memeHunter(limit = 10) {
  try {
    const r = await fetch("https://api.dexscreener.com/latest/dex/search?q=base&limit=100", {
      cf: { cacheTtl: 60, cacheEverything: true },
    }).catch(() => fetch("https://api.dexscreener.com/latest/dex/search?q=base&limit=100"));
    const data = await r.json();
    const pairs = (data.pairs || [])
      .filter(p => p?.chainId === "base" && p?.liquidity?.usd >= 1000)
      .sort((a, b) => (b.volume?.h24 || 0) - (a.volume?.h24 || 0))
      .slice(0, Math.min(limit, 30));
    return { count: pairs.length, pairs, timestamp: new Date().toISOString() };
  } catch (e) {
    return { error: e.message, count: 0, pairs: [] };
  }
}
