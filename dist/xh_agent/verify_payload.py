#!/usr/bin/env python3
"""verify_payload.py — buktikan payload x402 yang dibuat xh_pay.py benar-benar sah.

Alur: ambil challenge asli dari endpoint kita -> buat payload dengan xh_pay -> pulihkan penandatangan
dari tanda tangan EIP-712 (EIP-3009 TransferWithAuthorization, USDC Base) -> bandingkan dengan alamat
pembayar. Kalau cocok, jalur tanda tangan kita sah tanpa perlu facilitator atau dana.

Kunci yang dipakai hanya kunci acak sementara (tidak pernah ditulis ke disk).
"""
from __future__ import annotations

import json
import os
import secrets
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
URL = "https://xhagents.xyz/api/x402-trust"

os.environ["XH_PAYER_KEY"] = "0x" + secrets.token_hex(32)
import xh_pay  # noqa: E402

acct, signer = xh_pay._signer(os.environ["XH_PAYER_KEY"])
print("alamat pembayar (uji):", acct.address)

status, required, _hdr, _raw = xh_pay.challenge(URL, "GET")
assert status == 402 and required is not None, f"tidak dapat challenge (HTTP {status})"

from x402.client import x402ClientSync  # noqa: E402
from x402.http import x402HTTPClientSync  # noqa: E402
from x402.mechanisms.evm.exact import register_exact_evm_client  # noqa: E402

inner = x402ClientSync()
register_exact_evm_client(inner, signer, ["eip155:8453"])
payload = x402HTTPClientSync(inner).create_payment_payload(required)
d = payload.model_dump() if hasattr(payload, "model_dump") else payload
print("bentuk payload:", json.dumps(d, default=str)[:600])

pl = d.get("payload") or d
auth = pl.get("authorization") or pl
sig = pl.get("signature") or d.get("signature")
print("\nfield otorisasi:", sorted(auth.keys()) if isinstance(auth, dict) else auth)
print("signature ada:", bool(sig), "| panjang:", len(sig) if sig else 0)

from eth_account import Account  # noqa: E402
from eth_account.messages import encode_typed_data  # noqa: E402

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
domain = {"name": "USD Coin", "version": "2", "chainId": 8453, "verifyingContract": USDC}
types = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
    ]
}
msg = {
    "from": auth.get("from"), "to": auth.get("to"), "value": int(auth.get("value") or 0),
    "validAfter": int(auth.get("validAfter") or 0), "validBefore": int(auth.get("validBefore") or 0),
    "nonce": auth.get("nonce"),
}
try:
    enc = encode_typed_data(full_message={"types": {"EIP712Domain": [
        {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
        **types}, "primaryType": "TransferWithAuthorization", "domain": domain, "message": msg})
    rec = Account.recover_message(enc, signature=sig)
except Exception as e:  # noqa: BLE001
    rec = f"GAGAL pulihkan: {type(e).__name__}: {e}"

print("\nhasil pemulihan tanda tangan:", rec)
print("cocok dengan pembayar      :", str(rec).lower() == acct.address.lower())
print("nilai diotorisasi (USDC)   :", msg["value"] / 1e6, "| ke:", msg["to"])
