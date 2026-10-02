/**
 * src/payment.js - x402 payment flow: invoice generation + Solana USDC verification
 *
 * Invoice flow:
 *   1. Client calls paid endpoint WITHOUT x-payment header
 *   2. Server returns HTTP 402 with Payment-Required header (base64 JSON)
 *   3. Client pays USDC to treasury address on Solana
 *   4. Client retries WITH x-payment header containing invoice nonce
 *   5. Server verifies transfer on-chain via Solana RPC
 *   6. If verified, returns 200 + data
 */
import { Connection, PublicKey } from "@solana/web3.js";
import config, { OPENAPI_PARAMS } from "./config.js";

const rpc = new Connection(config.rpc.mainnet, "confirmed");

// In-memory invoice store (per worker process)
// In production, this should be Redis or DB-backed for multi-instance
const invoices = new Map();

/**
 * Generate a random 32-byte hex nonce for invoice ID
 */
function makeNonce() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * UTF-8-safe base64 (replaces btoa() which fails on non-Latin-1)
 */
function b64Utf8(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return Buffer.from(bytes).toString("base64");
}

/**
 * Parse x-payment auth header (k=v, k="v", format)
 */
function parseAuthHeader(value) {
  const parts = {};
  const re = /(\w+)=(?:\"([^\"]*)\"|([^,\s]+))/g;
  let m;
  while ((m = re.exec(value)) !== null) parts[m[1]] = m[m[2] ? 2 : 3];
  return parts;
}

/**
 * Build V2 x402 payment-required envelope (per PaymentRequiredV2Schema)
 */
function buildPaymentRequired(path) {
  const amount = config.prices[path];
  if (!amount) return null;

  const nonce = makeNonce();
  const resource = config.baseUrl + path;
  const now = Math.floor(Date.now() / 1000);

  // Store invoice for later verification
  invoices.set(nonce, {
    _amount: amount,
    _expires: now + config.invoiceTtl,
    _path: path,
    _created: now,
  });

  // Cleanup expired invoices periodically
  if (invoices.size > 1000) {
    for (const [k, v] of invoices) {
      if (v._expires < now) invoices.delete(k);
    }
  }

  return {
    x402Version: 2,
    resource: {
      url: resource,
      description: `Solana x402 paid endpoint: ${path}`,
      mimeType: "application/json",
    },
    accepts: [{
      scheme: "exact",
      network: config.network,
      amount: String(amount),
      payTo: config.treasury,
      asset: config.usdcMint,
      maxTimeoutSeconds: config.invoiceTtl,
      extra: { name: "USD Coin", version: "2", nonce },
    }],
  };
}

/**
 * Issue 402 response (when client has no payment header)
 */
export function issuePaymentRequired(path) {
  const payment = buildPaymentRequired(path);
  if (!payment) return null;

  return new Response(JSON.stringify(payment), {
    status: 402,
    headers: {
      "Content-Type": "application/json",
      "Payment-Required": b64Utf8(JSON.stringify(payment)),
      "X-Payment-Version": "2",
      "Cache-Control": "no-store",
      "Access-Control-Expose-Headers": "Payment-Required, X-Payment-Version",
    },
  });
}

/**
 * Verify submitted payment: check Solana RPC for USDC transfer to treasury
 *
 * Strategy:
 *   1. Get recent signatures for treasury address
 *   2. Parse each transaction's token balance changes
 *   3. Look for USDC transfer with amount >= invoice amount
 *   4. Verify sender is NOT treasury (avoid self-transfer cheat)
 */
export async function verifyPayment(paymentHdr, path) {
  const parsed = parseAuthHeader(paymentHdr);
  const nonce = parsed.nonce;

  if (!nonce) return { ok: false, reason: "missing_nonce" };
  const inv = invoices.get(nonce);
  if (!inv) return { ok: false, reason: "invalid_nonce" };

  const now = Math.floor(Date.now() / 1000);
  if (now > inv._expires) {
    invoices.delete(nonce);
    return { ok: false, reason: "invoice_expired" };
  }

  // Query Solana RPC for recent transactions to treasury
  const treasuryPubkey = new PublicKey(config.treasury);
  const signatures = await rpc.getSignaturesForAddress(treasuryPubkey, {
    limit: 50,
  });

  const minAmount = inv._amount; // in USDC base units (6 decimals)

  for (const sigInfo of signatures) {
    if (sigInfo.err) continue; // skip failed tx
    const tx = await rpc.getParsedTransaction(sigInfo.signature, {
      maxSupportedTransactionVersion: 0,
    });
    if (!tx || !tx.meta) continue;

    // Look for USDC token transfer
    const preBalances = tx.meta.preTokenBalances || [];
    const postBalances = tx.meta.postTokenBalances || [];

    for (const post of postBalances) {
      if (post.mint !== config.usdcMint) continue;
      if (post.owner !== config.treasury) continue;
      if (post.uiTokenAmount.uiAmount == null) continue;

      const pre = preBalances.find(
        (p) => p.accountIndex === post.accountIndex
      );
      const preAmount = pre?.uiTokenAmount?.uiAmount || 0;
      const postAmount = post.uiTokenAmount.uiAmount;
      const diff = postAmount - preAmount;

      // Verify: positive delta (received) >= minAmount
      if (diff * Math.pow(10, config.usdcDecimals) >= minAmount) {
        invoices.delete(nonce);
        return { ok: true, txHash: sigInfo.signature };
      }
    }
  }

  return { ok: false, reason: "payment_not_verified" };
}

export { makeNonce, b64Utf8, parseAuthHeader };
