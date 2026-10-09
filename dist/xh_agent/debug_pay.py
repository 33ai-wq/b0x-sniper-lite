#!/usr/bin/env python3
"""debug_pay.py — kirim pembayaran berbayar yang sebenarnya, lalu cetak SEMUA bukti mentah:
status, seluruh header respons, challenge terdekode (termasuk field `error`), dan body.
Tidak menyembunyikan apa pun supaya penyebab penolakan terbaca, bukan ditebak.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://xhagents.xyz/api/x402-trust"
METHOD = sys.argv[2] if len(sys.argv) > 2 else "POST"
BODY = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {"url": "https://xhagents.xyz/api/x402-trust"}

key = xh_pay._key()
if not key:
    print("tidak ada kunci pembayar"); sys.exit(1)
from eth_account import Account  # noqa: E402
from x402.client import x402ClientSync  # noqa: E402
from x402.http import (x402HTTPClientSync, decode_payment_required_header,  # noqa: E402
                       encode_payment_signature_header)
from x402.mechanisms.evm.exact import register_exact_evm_client  # noqa: E402
from x402.mechanisms.evm.signers import EthAccountSigner  # noqa: E402

acct = Account.from_key(key)
print("pembayar:", acct.address, "| saldo USDC:", xh_pay.usdc_balance(acct.address))

status, required, _hdr, raw = xh_pay.challenge(URL, METHOD, BODY)
print(f"\n1) challenge: HTTP {status}")
info = xh_pay.describe(required) if required is not None else {}
print("   quote:", json.dumps(info))
root = xh_pay._dict(required)
if "error" in root:
    print("   error dari server:", json.dumps(root["error"])[:400])

inner = x402ClientSync()
register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
sig = encode_payment_signature_header(x402HTTPClientSync(inner).create_payment_payload(required))
print("\n2) header pembayaran dibuat, panjang:", len(sig))

req = urllib.request.Request(URL, data=json.dumps(BODY).encode(), method=METHOD,
                             headers={"X-PAYMENT": sig, "PAYMENT-SIGNATURE": sig,
                                      "User-Agent": xh_pay.UA, "Content-Type": "application/json"})
print("\n3) respons setelah membayar:")
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        print("   HTTP", r.status)
        for k, v in r.headers.items():
            print(f"   header {k}: {str(v)[:200]}")
        print("   body:", r.read(400).decode("utf-8", "replace"))
except urllib.error.HTTPError as e:
    print("   HTTP", e.code)
    for k, v in e.headers.items():
        print(f"   header {k}: {str(v)[:200]}")
    body = e.read(600).decode("utf-8", "replace")
    print("   body:", body[:600])
    hdr = e.headers.get("PAYMENT-REQUIRED") or e.headers.get("payment-required")
    if hdr:
        try:
            ch = decode_payment_required_header(hdr)
            d = ch.model_dump() if hasattr(ch, "model_dump") else ch
            print("\n4) challenge balik (cari alasan):")
            print("   error:", json.dumps(d.get("error"))[:500])
        except Exception as ex:  # noqa: BLE001
            print("   (gagal decode challenge balik:", ex, ")")
            try:
                print("   mentah:", base64.b64decode(hdr + "=" * (-len(hdr) % 4)).decode()[:500])
            except Exception:  # noqa: BLE001
                print("   mentah:", hdr[:300])
