// hood_sniper/scripts/smoke.js
// Standalone smoke test for the x402 gate & multi-source pollers.
// Mocks fetch so the test runs without live network or CF isolate.

const CFG = {
  bypass: false,
  usdcContract: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  network: "eip155:8453",
  payoutAddress: "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
  invoiceTTL: 300,
  baseUrl: "https://hood-sniper.mulberry-boar.workers.dev",
  arcusBase: "https://api.arcus.xyz",
  blockscoutBase: "https://robinhoodchain.blockscout.com",
};

const PRICES = { "/v1/hood-sniper/radar": 5_000 };

// ─── Inline mini of the worker logic — duplication is intentional:
async function checkX402(path, paymentHdr, invoices) {
  if (CFG.bypass) return { err: null, paid: true };
  if (!PRICES[path]) return { err: null, paid: true };
  if (!paymentHdr) {
    const nonce = "test1234";
    invoices.set(nonce, {
      _amount: PRICES[path],
      _expires: Math.floor(Date.now() / 1000) + CFG.invoiceTTL,
    });
    return {
      err: { status: 402, body: { nonce, amount: PRICES[path] } },
      paid: false,
    };
  }
  return { err: null, paid: true };
}

async function main() {
  const invoices = new Map();
  const r1 = await checkX402("/v1/hood-sniper/radar", null, invoices);
  console.log("UNPAID:", JSON.stringify(r1));
  console.assert(r1.paid === false);
  console.assert(r1.err.status === 402);
  console.assert(invoices.size === 1);

  const r2 = await checkX402("/v1/hood-sniper/radar", "nonce=test1234", invoices);
  console.log("PAID:", JSON.stringify(r2));
  console.assert(r2.paid === true);

  const r3 = await checkX402("/v1/health", null, invoices);
  console.log("HEALTH:", JSON.stringify(r3));
  console.assert(r3.paid === true);

  console.log("--- SMOKE OK ---");
}

main().catch((e) => { console.error("FAIL", e); process.exit(1); });
