#!/usr/bin/env python3
"""cdp_verify_repro.py — panggil CDP /verify langsung dengan payload yang sama seperti klien kita,
lalu coba beberapa variasi bentuk supaya ketemu mana yang diterima. Verify TIDAK memindahkan dana.

Kredensial CDP dibaca dari cdp/.env.cdp; tidak pernah dicetak (hanya jenis header yang dilaporkan).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

CDP_ENV = "/home/ubuntu/prpo_ai/cdp/.env.cdp"
VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"
URL = sys.argv[4] if len(sys.argv) > 4 else "https://xhagents.xyz/api/x402-trust"
METHOD = "POST"
BODY = {"url": "https://xhagents.xyz/api/x402-trust"}


def creds() -> dict:
    out = {}
    with open(CDP_ENV) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def auth_headers(kid: str, ksec: str) -> dict:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    return get_auth_headers(GetAuthHeadersOptions(
        api_key_id=kid, api_key_secret=ksec, request_method="POST",
        request_host="api.cdp.coinbase.com", request_path="/platform/v2/x402/verify")) or {}


def post(body: dict, hdrs: dict) -> tuple[int, str]:
    req = urllib.request.Request(VERIFY, data=json.dumps(body).encode(),
                                 headers={**hdrs, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(700).decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read(700).decode()
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def main() -> None:
    c = creds()
    kid, ksec = c.get("CDP_API_KEY_ID", ""), c.get("CDP_API_KEY_PRIVATE_KEY", "")
    print("kredensial CDP:", "ADA" if kid and ksec else "TIDAK ADA", "| kid prefix:", kid[:8] + "…" if kid else "-")
    hdrs = auth_headers(kid, ksec)
    print("header auth dibuat:", sorted(hdrs.keys()))

    _st, required, _h, _raw = xh_pay.challenge(URL, METHOD, BODY)
    root = xh_pay._dict(required)
    reqs = (root.get("accepts") or [{}])[0]
    print("\nrequirements:", json.dumps(reqs)[:300])

    from eth_account import Account
    from x402.client import x402ClientSync
    from x402.http import x402HTTPClientSync, encode_payment_signature_header
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    acct = Account.from_key(xh_pay._key())
    inner = x402ClientSync()
    register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
    payload = x402HTTPClientSync(inner).create_payment_payload(required)
    pv2 = payload.model_dump(by_alias=True, exclude_none=True)
    pv2_nulls = payload.model_dump(by_alias=True)
    print("\npayload (exclude_none=True):", json.dumps(pv2)[:400])
    print("payload (dengan null)      :", json.dumps(pv2_nulls)[:400])

    variants = [
        ("v2 apa adanya (exclude_none)", {"x402Version": 2, "paymentPayload": pv2, "paymentRequirements": reqs}),
        ("v2 dengan null eksplisit", {"x402Version": 2, "paymentPayload": pv2_nulls, "paymentRequirements": reqs}),
        ("v2 di-nest di field payload", {"x402Version": 2, "paymentPayload": pv2, "paymentRequirements": reqs, "scheme": reqs.get("scheme")}),
        ("v1-style (scheme top-level)", {"x402Version": 1, "scheme": reqs.get("scheme"), "network": reqs.get("network"),
                                         "payload": pv2.get("payload"), "paymentRequirements": reqs}),
    ]
    for label, body in variants:
        code, resp = post(body, hdrs)
        print(f"\n--- {label} -> HTTP {code}")
        print("   ", resp[:400].replace("\n", " "))


if __name__ == "__main__":
    main()
