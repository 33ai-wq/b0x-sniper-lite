#!/usr/bin/env python3
"""Buy one call on each paid XH Agents endpoint using the throwaway test wallet.

This is the client side of the x402 flow — exactly what an agent with a funded wallet does:
request → receive 402 challenge → sign a payment authorization → retry with the payment
header → server verifies & settles (via the CDP facilitator, which pays the gas) → answer.

The payer needs USDC on Base only; no ETH is required, because the settlement is submitted
by the facilitator.

Usage:
    ./venv/bin/python x402_buy_test.py --check     # show wallet balance + challenges, spend nothing
    ./venv/bin/python x402_buy_test.py             # actually buy both endpoints
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

KEY_FILE = "/home/ubuntu/prpo_ai/keys/x402_test_payer.key"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC = "https://mainnet.base.org"

TARGETS = [
    ("https://xhagents.xyz/api/kb/ask", {"question": "How do I check which directory nginx really serves?"}, "0.03"),
    ("https://xhagents.xyz/api/chat", {"message": "One sentence on BTC right now, please."}, "0.10"),
]


RPC_LIST = ["https://base-rpc.publicnode.com", "https://base.llamarpc.com", "https://mainnet.base.org"]


def rpc(method, params):
    """Try each RPC in turn: the public endpoints rate-limit or 403 without warning."""
    last = None
    for url in RPC_LIST:
        try:
            req = urllib.request.Request(
                url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json",
                         # public RPC endpoints sit behind Cloudflare and 403 the default
                         # python-urllib agent, so identify ourselves
                         "User-Agent": "xh-agents-x402-test/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                out = json.loads(r.read())
            if "error" in out:
                raise RuntimeError(out["error"])
            return out.get("result")
        except Exception as e:  # try the next endpoint
            last = f"{url}: {e}"
            continue
    raise RuntimeError(f"all RPC endpoints failed (last: {last})")


def usdc_balance(address):
    data = "0x70a08231" + address.lower().replace("0x", "").rjust(64, "0")
    raw = rpc("eth_call", [{"to": USDC_BASE, "data": data}, "latest"])
    return int(raw, 16) / 1_000_000


def post(url, body, extra_headers=None):
    headers = {"Content-Type": "application/json", "User-Agent": "xh-agents-x402-test/1.0"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def challenge(headers):
    for key in ("PAYMENT-REQUIRED", "Payment-Required", "payment-required"):
        if headers.get(key):
            return headers[key]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="do not pay; only inspect")
    ap.add_argument("--only", help="only buy targets whose URL contains this string")
    args = ap.parse_args()

    from eth_account import Account
    from x402 import x402ClientSync
    from x402.http import (PAYMENT_RESPONSE_HEADER, X_PAYMENT_HEADER, PAYMENT_SIGNATURE_HEADER,
                           decode_payment_required_header, encode_payment_signature_header,
                           x402HTTPClientSync)
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    acct = Account.from_key(open(KEY_FILE).read().strip())
    print(f"payer wallet : {acct.address}")
    bal = usdc_balance(acct.address)
    print(f"USDC (Base)  : {bal:.6f}")

    client = x402ClientSync()
    register_exact_evm_client(client, EthAccountSigner(acct), ["eip155:8453"])
    http = x402HTTPClientSync(client)

    spend = sum(float(t[2]) for t in TARGETS)
    print(f"total price  : {spend:.2f} USDC for {len(TARGETS)} calls\n")
    if bal < spend:
        print(f"!! balance too low — send at least {spend - bal + 0.01:.2f} USDC to {acct.address} on Base")
        return 2

    failures = 0
    for url, body, price in TARGETS:
        if args.only and args.only not in url:
            continue
        print(f"── {url}  (${price})")
        status, headers, raw = post(url, body)
        ch = challenge(headers)
        print(f"   unpaid request -> HTTP {status}"
              f"{' with PAYMENT-REQUIRED challenge' if ch else ' (no challenge!)'}")
        if status != 402 or not ch:
            print(f"   body: {raw[:200]!r}")
            failures += 1
            continue
        required = decode_payment_required_header(ch)
        accepts = required.accepts or []
        a0 = accepts[0] if accepts else {}
        amount = getattr(a0, "amount", None) or getattr(a0, "max_amount_required", None)
        print(f"   challenge: v{required.x402_version} scheme={getattr(a0,'scheme',None)} "
              f"network={getattr(a0,'network',None)} amount={amount} payTo={getattr(a0,'pay_to',None)}")
        if args.check:
            continue

        payload = http.create_payment_payload(required)
        sig = encode_payment_signature_header(payload)
        hdrs = {X_PAYMENT_HEADER: sig, PAYMENT_SIGNATURE_HEADER: sig}
        status2, headers2, raw2 = post(url, body, hdrs)
        settled = headers2.get(PAYMENT_RESPONSE_HEADER) or headers2.get("payment-response")
        print(f"   paid request   -> HTTP {status2} | settlement header: {'yes' if settled else 'no'}")
        try:
            out = json.loads(raw2)
            preview = out.get("reply") or json.dumps(out.get("best_match") or out.get("matches") or out)[:160]
            print(f"   answer: {str(preview)[:170]}")
        except Exception:
            print(f"   body: {raw2[:180]!r}")
        if status2 != 200:
            failures += 1

    bal_after = usdc_balance(acct.address)
    print(f"\nUSDC after   : {bal_after:.6f}  (spent {bal - bal_after:.6f})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
