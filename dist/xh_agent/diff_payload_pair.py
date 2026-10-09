#!/usr/bin/env python3
"""diff_payload_pair.py — bandingkan payload + requirements untuk route yang GAGAL vs BERHASIL,
field per field, supaya bedanya terbaca (bukan ditebak).
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

PAIR = [("https://xhagents.xyz/api/x402-trust", "GAGAL"),
        ("https://xhagents.xyz/api/kb/ask", "BERHASIL")]


def build(url: str):
    _st, required, _h, _raw = xh_pay.challenge(url, "POST", {"a": 1})
    root = xh_pay._dict(required)
    from eth_account import Account
    from x402.client import x402ClientSync
    from x402.http import x402HTTPClientSync
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner
    acct = Account.from_key(xh_pay._key())
    inner = x402ClientSync()
    register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
    payload = x402HTTPClientSync(inner).create_payment_payload(required)
    return root, payload.model_dump(by_alias=True, exclude_none=True)


outs = {}
for url, tag in PAIR:
    root, pl = build(url)
    outs[tag] = (root, pl)
    print(f"\n===== {tag}: {url}")
    print("challenge:", json.dumps(root, indent=1)[:900])
    print("payload  :", json.dumps(pl, indent=1)[:900])

a_root, a_pl = outs["GAGAL"]
b_root, b_pl = outs["BERHASIL"]
print("\n===== PERBANDINGAN =====")
ka, kb = set(a_root.keys()), set(b_root.keys())
print("challenge: hanya-GAGAL:", ka - kb, "| hanya-BERHASIL:", kb - ka)
print("resource GAGAL:", json.dumps(a_root.get("resource")))
print("resource OK   :", json.dumps(b_root.get("resource")))
ac_a, ac_b = (a_root.get("accepts") or [{}])[0], (b_root.get("accepts") or [{}])[0]
print("accepts beda kunci:", {k for k in set(ac_a) | set(ac_b) if ac_a.get(k) != ac_b.get(k)})
for k in sorted(set(ac_a) | set(ac_b)):
    if ac_a.get(k) != ac_b.get(k):
        print(f"   {k}: GAGAL={ac_a.get(k)!r}  BERHASIL={ac_b.get(k)!r}")
print("payload beda kunci:", {k for k in set(a_pl) | set(b_pl) if a_pl.get(k) != b_pl.get(k)})
print("accepted(requirements) dalam payload, kunci beda:",
      {k for k in set(a_pl.get("accepted") or {}) | set(b_pl.get("accepted") or {})
       if (a_pl.get("accepted") or {}).get(k) != (b_pl.get("accepted") or {}).get(k)})
print("accepted GAGAL:", json.dumps(a_pl.get("accepted"))[:400])
print("accepted OK   :", json.dumps(b_pl.get("accepted"))[:400])
print("extensions GAGAL:", json.dumps(a_root.get("extensions"))[:200])
print("extensions OK   :", json.dumps(b_root.get("extensions"))[:200])
