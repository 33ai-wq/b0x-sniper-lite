#!/usr/bin/env python3
"""Pay an x402 v2 endpoint with the official SDK, with a hard price/asset ceiling.

Usage:
  pay_x402_sdk.py --wallet x402_test_payer|base_treasury --url URL [--method POST]
                  [--body '{"json":...}'] [--max-usd 0.02] [--out FILE] [--dry]

Safety rules baked in (see skill x402-paid-api-development):
  * asset allowlist: only canonical Base USDC may be signed for
  * hard ceiling per payment (default $0.10), refuse anything above
  * the payTo address, amount and payer balance are printed BEFORE signing
  * the settlement proof (PAYMENT-RESPONSE) is saved next to the result
Never prints a private key. Reads it from a mode-600 file.
"""
import argparse, base64, json, os, sys, time
import urllib.request, urllib.error

from eth_account import Account
from x402.client import x402ClientSync
from x402.http import (x402HTTPClientSync, decode_payment_required_header,
                       encode_payment_signature_header, decode_payment_response_header)
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSigner

BASE = "eip155:8453"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
WALLETS = {
    "x402_test_payer": "/home/ubuntu/prpo_ai/keys/x402_test_payer.key",
    "base_treasury": "/home/ubuntu/prpo_ai/keys/base_treasury.key",
}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) xh-payer", "Accept": "application/json"}


def load_key(path):
    raw = open(path).read().strip()
    for tok in [raw] + [l.split("=", 1)[1] for l in raw.splitlines() if "=" in l]:
        tok = tok.strip().strip('"\'')
        if tok.startswith("0x") and len(tok) == 66:
            return tok
        if len(tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in tok):
            return "0x" + tok
    raise SystemExit(f"no 32-byte hex key in {path}")


def rpc(method, params, url="https://mainnet.base.org"):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            url, data=body, headers={"User-Agent": UA["User-Agent"], "Content-Type": "application/json"}), timeout=25) as r:
        return json.load(r).get("result")


def usdc_balance(addr):
    r = rpc("eth_call", [{"to": USDC_BASE, "data": "0x70a08231" + addr[2:].lower().rjust(64, "0")}, "latest"])
    return int(r, 16) / 1e6


def call(url, method, body, headers=None):
    h = dict(UA)
    h.update(headers or {})
    data = body
    if data is not None:
        h["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h, data=data, method=method), timeout=60) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", required=True, choices=list(WALLETS))
    ap.add_argument("--url", required=True)
    ap.add_argument("--method", default="GET")
    ap.add_argument("--body", default=None)
    ap.add_argument("--max-usd", type=float, default=0.10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    account = Account.from_key(load_key(WALLETS[a.wallet]))
    body = a.body.encode() if a.body else None
    code, hdrs, payload = call(a.url, a.method, body)
    print(f"[payer {a.wallet}] {a.method} {a.url} -> HTTP {code} ({len(payload)}B)  address={account.address}")
    pr_header = hdrs.get("payment-required")
    if code != 402 or not pr_header:
        print("not a 402 with PAYMENT-REQUIRED; nothing to pay. body head:", payload[:300])
        return 1 if code != 200 else 0

    required = decode_payment_required_header(pr_header)
    accepts = [a.model_dump() for a in (getattr(required, "accepts", []) or [])]
    print(f"challenge: x402Version={required.model_dump().get('x402Version')} accepts={len(accepts)}")
    for x in accepts:
        print(f"   {str(x.get('scheme')):5} {str(x.get('network')):12} amount={x.get('amount')} "
              f"asset={x.get('asset')} payTo={x.get('payTo')}")
    pick = None
    for x in accepts:
        if (x.get("network") == BASE and str(x.get("asset")).lower() == USDC_BASE.lower()
                and x.get("scheme") == "exact"):
            pick = x
            break
    if pick is None:
        raise SystemExit("REFUSED: no exact/eip155:8453/canonical-USDC accept — not signing anything")
    usd = int(pick["amount"]) / 1e6
    bal = usdc_balance(account.address)
    print(f"\nSELECTED: {usd:.6f} USDC on Base -> payTo {pick['payTo']}")
    print(f"REFUSAL CHECKS: amount<=${a.max_usd}: {usd <= a.max_usd} | asset is canonical Base USDC: True | payer USDC balance: {bal}")
    if usd > a.max_usd:
        raise SystemExit("REFUSED: price above --max-usd ceiling")
    if bal < usd:
        raise SystemExit(f"REFUSED: payer balance {bal} < price {usd}")
    if a.dry:
        print("dry run: not signing")
        return 0

    inner = x402ClientSync()
    register_exact_evm_client(inner, EthAccountSigner(account), [BASE])
    hc = x402HTTPClientSync(inner)
    sig = encode_payment_signature_header(hc.create_payment_payload(required))
    print("signed payload built (signature not printed)")

    code2, hdrs2, payload2 = call(a.url, a.method, body, {"X-PAYMENT": sig, "PAYMENT-SIGNATURE": sig})
    resp_hdr = hdrs2.get("payment-response") or hdrs2.get("x-payment-response")
    proof = None
    if resp_hdr:
        try:
            proof = decode_payment_response_header(resp_hdr)
        except Exception as e:
            proof = {"decode_error": str(e)[:120], "raw_len": len(resp_hdr)}
    paid = None
    try:
        j = json.loads(payload2)
        paid = j.get("paid") if isinstance(j, dict) else None
    except Exception:
        pass
    print(f"\nPAID CALL -> HTTP {code2} ({len(payload2)}B) settlement_proof={'yes' if proof else 'NO'}")
    if proof:
        print("  proof:", json.dumps(proof, default=str)[:400])
    print("  body head:", payload2[:400])
    if a.out:
        with open(a.out, "wb") as fh:
            fh.write(payload2)
        receipt = {"url": a.url, "method": a.method, "wallet": a.wallet, "payer": account.address,
                   "price_usd": usd, "payTo": pick["payTo"], "http_status": code2,
                   "settlement_proof": proof, "body_file": a.out, "at": int(time.time())}
        with open(a.out + ".receipt.json", "w") as fh:
            json.dump(receipt, fh, indent=1, default=str)
        print(f"  saved body -> {a.out}  (+ receipt {a.out}.receipt.json)")
    return 0 if code2 == 200 else 2


if __name__ == "__main__":
    sys.exit(main())
