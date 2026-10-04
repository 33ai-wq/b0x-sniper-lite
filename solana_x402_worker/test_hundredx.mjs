// Uji hundredXHunter pada mint Solana asli (tanpa lewat HTTP/paid gate).
import { hundredXHunter, hundredXMethod } from "./src/hundredx.js";

const found = [];
const seen = new Set();
for (const q of ["solana", "bonk", "wif", "pump"]) {
  try {
    const r = await fetch(`https://api.dexscreener.com/latest/dex/search?q=${q}`);
    const j = await r.json();
    for (const p of j.pairs || []) {
      if (p.chainId !== "solana") continue;
      const mint = p.baseToken?.address;
      const liq = parseFloat(p.liquidity?.usd || 0);
      const vol = parseFloat(p.volume?.h24 || 0);
      const ageDays = p.pairCreatedAt ? (Date.now() - p.pairCreatedAt) / 86400000 : 999;
      if (!mint || seen.has(mint)) continue;
      if (liq < 60_000 || liq > 5_000_000 || vol < 15_000 || vol > 2_000_000) continue;
      if (ageDays < 20 || ageDays > 400) continue;
      seen.add(mint);
      found.push({ mint, symbol: p.baseToken?.symbol, liq, vol, ageDays: +ageDays.toFixed(0), dex: p.dexId });
    }
  } catch (e) {
    console.log("search gagal", q, String(e).slice(0, 80));
  }
}
found.sort((a, b) => a.vol - b.vol);
console.log("kandidat:", found.slice(0, 6).map((f) => `${f.symbol}(${f.ageDays}h,liq$${Math.round(f.liq / 1000)}k,vol$${Math.round(f.vol / 1000)}k)`).join(", "));

const target = process.argv[2] || found[0]?.mint;
if (!target) {
  console.log("tidak ada kandidat; pakai BONK sebagai uji paksa");
}
const mint = target || "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263";
console.log("\n== uji mint:", mint);
const t0 = Date.now();
const out = await hundredXHunter({ mint, window_days: 30, min_wallets: 3, limit: 6 });
console.log(`selesai dalam ${((Date.now() - t0) / 1000).toFixed(1)}s`);
console.log("token:", out.input_mint, "| dex liq:", out.input_mint_dex?.liquidity_usd);
console.log("step2 pembeli awal:", out.step_2_first_buyers.count,
  "| sig dilihat:", out.step_2_first_buyers.signatures_seen,
  "| tx diperiksa:", out.step_2_first_buyers.transactions_examined);
console.log("step3 aktif:", out.step_3_active_in_window.kept, "| gugur:", out.step_3_active_in_window.dropped);
console.log("step4 bot dibuang:", out.step_4_bots_excluded.excluded);
console.log("step6 berulang:", JSON.stringify(out.step_6_recurring_tokens.slice(0, 5)));
console.log("step7 skor:", JSON.stringify(out.step_7_scored.slice(0, 4).map((s) => ({ t: s.token.slice(0, 8), s: s.score, v: s.verdict, w: s.wallets }))));
console.log("truncated:", out.truncated, "| notes:", out.notes);
console.log("keputusan — buy:", out.decision.buy.length, "watch:", out.decision.watch.length, "reject:", out.decision.reject.length);
console.log("\n== method (gratis) ==");
const m = await hundredXMethod();
console.log(JSON.stringify({ provider: m.provider, price: m.price_usdc_per_call, endpoint: m.endpoint, threshold: m.threshold }));
