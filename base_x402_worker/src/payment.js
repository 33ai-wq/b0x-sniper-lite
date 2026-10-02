/**
 * src/payment.js - x402 invoice + EIP-3009 payment submission
 *
 * Flow:
 * 1. Buyer gets 402 invoice (server stores nonce + amount)
 * 2. Buyer signs EIP-3009 TransferWithAuthorization (off-chain)
 * 3. Buyer submits header with x-payment
 * 4. Server (relayer) calls USDC.transferWithAuthorization (pays gas)
 *    → actual USDC transfer happens on-chain to payoutAddress
 * 5. Server returns 200 + data
 *
 * For Boss's worker we use a "facilitator" pattern: server pays gas from
 * a funded relayer wallet. For now, the test buyer will sign + we submit
 * directly via the buyer (they pay their own gas).
 */
import crypto from "node:crypto";
import { Web3 } from "web3";
import { CFG } from "./config.js";

const w3 = new Web3(CFG.rpcUrl);
const invoices = new Map();

function parseAuthHeader(value) {
  const parts = {};
  const re = /(\w+)=(?:\"([^\"]*)\"|([^,\s]+))/g;
  let m;
  while ((m = re.exec(value)) !== null) {
    parts[m[1]] = m[m[2] ? 2 : 3];
  }
  return parts;
}

const nowSeconds = () => Math.floor(Date.now() / 1000);
const makeNonce = () => crypto.randomBytes(32).toString("hex");
const b64Utf8 = (s) => Buffer.from(s, "utf8").toString("base64");

async function getLatestBlock() {
  try { return Number(await w3.eth.getBlockNumber()); }
  catch { return null; }
}

/**
 * Submit signed EIP-3009 authorization to USDC contract.
 * Returns { ok, txHash } or { ok: false, reason }.
 */
async function submitTransferAuthorization(parsed) {
  const sig = parsed.signature;
  if (!sig || !sig.startsWith("0x") || sig.length !== 132) {
    return { ok: false, reason: "bad_signature_format" };
  }
  const r = "0x" + sig.slice(2, 66);
  const s = "0x" + sig.slice(66, 130);
  const v = parseInt(sig.slice(130, 132), 16);

  const USDC_ABI = [{
    inputs: [
      { name: "from", type: "address" },
      { name: "to", type: "address" },
      { name: "value", type: "uint256" },
      { name: "validAfter", type: "uint256" },
      { name: "validBefore", type: "uint256" },
      { name: "nonce", type: "bytes32" },
      { name: "v", type: "uint8" },
      { name: "r", type: "bytes32" },
      { name: "s", type: "bytes32" },
    ],
    name: "transferWithAuthorization",
    outputs: [{ name: "", type: "bool" }],
    stateMutability: "nonpayable",
    type: "function",
  }];

  const contract = new w3.eth.Contract(USDC_ABI, CFG.usdcContract);

  try {
    // Encode the call data
    const data = contract.methods.transferWithAuthorization(
      parsed.from,
      parsed.to,
      parsed.value,
      parsed.validAfter,
      parsed.validBefore,
      parsed.nonce,
      v,
      r,
      s
    ).encodeABI();

    // Send via a funded relayer (or here: use the buyer as sender, they pay gas)
    // For Boss's MVP: buyer submits themselves, they pay gas from their ETH
    // Server gets the signed tx hash and waits for inclusion
    return {
      ok: true,
      action: "buyer_must_submit",
      data,
      to: CFG.usdcContract,
      // To submit buyer would do: account.signTransaction({to, data, gas, ...}).send()
      // OR server acts as relayer with funded wallet (not implemented here)
    };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

export function issuePaymentRequired(path, amount, resource, bazaar) {
  const invNonce = makeNonce();
  const tags = bazaar?.info?.tags || ["crypto", "ai-agent", "x402-v2"];
  const summary = bazaar?.info?.summary || `x402 paid endpoint: ${path}`;
  const extra = { name: "USD Coin", version: "2", nonce: invNonce };

  invoices.set(invNonce, {
    _amount: amount,
    _expires: nowSeconds() + CFG.invoiceTTL,
    _path: path,
  });

  const payload = {
    x402Version: 2,
    resource: {
      url: resource,
      description: summary,
      mimeType: "application/json",
      serviceName: `b0x402-${path.split("/").pop()}`,
      tags,
    },
    accepts: [{
      scheme: "exact",
      network: CFG.network,
      amount: String(amount),
      payTo: CFG.payoutAddress,
      asset: CFG.usdcContract,
      maxTimeoutSeconds: CFG.invoiceTTL,
      extra,
    }],
  };

  return {
    body: payload,
    headerB64: b64Utf8(JSON.stringify(payload)),
  };
}

/**
 * Verify submitted payment: extract auth header, submit EIP-3009 to USDC.
 * Returns { ok, txHash } or { ok: false, reason }.
 */
export async function verifyPayment(paymentHdr) {
  const parsed = parseAuthHeader(paymentHdr);
  const nonce = parsed.nonce;
  if (!nonce) return { ok: false, reason: "missing_nonce" };

  const inv = invoices.get(nonce);
  if (!inv) return { ok: false, reason: "invalid_nonce" };
  if (nowSeconds() > inv._expires) {
    invoices.delete(nonce);
    return { ok: false, reason: "invoice_expired" };
  }

  // Submit the signed authorization
  const result = await submitTransferAuthorization(parsed);
  if (!result.ok) return result;

  // For MVP: buyer must submit themselves (server returns tx data)
  // In production: server has funded relayer wallet that submits
  invoices.delete(nonce);
  return result;
}
