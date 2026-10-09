#!/usr/bin/env python3
"""cdp_verify_variants.py — uji bentuk paymentPayload yang lebih lengkap ke CDP /verify (gratis).

Yang dicoba: V1 dengan field yang benar, V2 dengan scheme/network di top-level, V2 dengan resource,
V2 dengan accepted disertakan, dan V2 tanpa wrapper.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"
URL = "https://xhagents.xyz/api/x402-trust"


def creds() -> dict:
    out = {}
    with open("/home/ubuntu/prpo_ai/cdp/.env.cdp") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def post(body: dict, hdrs: dict):
    req = urllib.request.Request(VERIFY, data=json.dumps(body).encode(),
                                 headers={**hdrs, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(500).decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read(500).decode()
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def main() -> None:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    c = creds()
    hdrs = get_auth_headers(GetAuthHeadersOptions(
        api_key_id=c["CDP_API_KEY_ID"], api_key_secret=c["CDP_API_KEY_PRIVATE_KEY"],
        request_method="POST", request_host="api.cdp.coinbase.com",
        request_path="/platform/v2/x402/verify")) or {}

    _st, required, _h, _raw = xh_pay.challenge(URL, "POST", {"url": URL})
    root = xh_pay._dict(required)
    reqs = (root.get("accepts") or [{}])[0]
    res_info = root.get("resource")

    from eth_account import Account
    from x402.client import x402ClientSync
    from x402.http import x402HTTPClientSync
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    acct = Account.from_key(xh_pay._key())
    inner = x402ClientSync()
    register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
    pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(by_alias=True, exclude_none=True)
    core = pl["payload"]

    def body_v1(inner_payload):
        return {"x402Version": 1, "paymentPayload": inner_payload, "paymentRequirements": reqs}

    v1_ok = {"scheme": reqs["scheme"], "network": reqs["network"], "payload": core}
    v2_flat = {"x402Version": 2, "scheme": reqs["scheme"], "network": reqs["network"], "payload": core}
    v2_res = dict(pl)
    if res_info:
        v2_res["resource"] = res_info
    variants = [
        ("V1 bentuk benar (scheme/network/payload)", body_v1(v1_ok)),
        ("V2 scheme+network top-level", {"x402Version": 2, "paymentPayload": v2_flat, "paymentRequirements": reqs}),
        ("V2 + resource", {"x402Version": 2, "paymentPayload": v2_res, "paymentRequirements": reqs}),
        ("V2 apa adanya dari SDK", {"x402Version": 2, "paymentPayload": pl, "paymentRequirements": reqs}),
        ("V2 tanpa x402Version di dalam payload", {"x402Version": 2,
                                                   "paymentPayload": {k: v for k, v in pl.items() if k != "x402Version"},
                                                   "paymentRequirements": reqs}),
    ]
    for label, body in variants:
        code, resp = post(body, hdrs)
        print(f"\n--- {label} -> HTTP {code}")
        print("   ", resp[:330].replace("\n", " "))


if __name__ == "__main__":
    main()
