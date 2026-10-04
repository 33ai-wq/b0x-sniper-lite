// Uji tokenSafety() pada mint Solana nyata.
import { tokenSafety, tokenSafetyMethod } from "./src/tokensafety.js";

const MINTS = {
  USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  BONK: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
  WIF: "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
};
const want = process.argv[2] || "BONK";
const mint = MINTS[want] || want;

const t0 = Date.now();
const r = await tokenSafety({ mint });
console.log(`=== ${want} ${r.symbol} — skor ${r.score} (${r.verdict}) dalam ${((Date.now() - t0) / 1000).toFixed(1)}s`);
console.log("   poin:", JSON.stringify(r.points));
console.log("   weights:", JSON.stringify(r.weights));
console.log("   liq:", r.market?.liquidity_usd, "| top10 wallet share:", r.checks.top10_wallet_share_pct,
            "| pools:", r.checks.pool_accounts, "| program:", (r.checks.mint?.program || "").slice(0, 12));
for (const f of r.findings.slice(0, 8)) console.log("   -", f);
console.log("   not_checked:", r.not_checked.length, "item");
console.log("\n=== method gratis ===");
const m = await tokenSafetyMethod();
console.log(JSON.stringify({ provider: m.provider, price: m.price_usdc_per_call, endpoint: m.endpoint, verdicts: m.verdicts }));
