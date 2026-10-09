#!/usr/bin/env python3
"""find_desc_limit.py — cari batas panjang resource.description yang diterima CDP, dan ukur deskripsi
semua route kita. Verify gratis (tidak memindahkan dana).
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"
BASE = "https://xhagents.xyz"


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
            return r.status, r.read(200).decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode()
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:80]


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
    pl = x402HTTPClientSync(inner).create_payment_payload(required)
    return root, pl.model_dump(by_alias=True, exclude_none=True)


def main() -> None:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    c = creds()
    hdrs = get_auth_headers(GetAuthHeadersOptions(
        api_key_id=c["CDP_API_KEY_ID"], api_key_secret=c["CDP_API_KEY_PRIVATE_KEY"],
        request_method="POST", request_host="api.cdp.coinbase.com",
        request_path="/platform/v2/x402/verify")) or {}

    root, pl = build(f"{BASE}/api/x402-trust")
    reqs = root["accepts"][0]
    d = (pl.get("resource") or {}).get("description") or ""
    print(f"panjang deskripsi x402-trust saat ini: {len(d)} karakter")

    print("\ncari batas (verify gratis):")
    for n in (120, 200, 240, 250, 255, 256, 260, 300, 400, 500):
        p = copy.deepcopy(pl)
        p["resource"] = dict(p["resource"], description=("x" * n))
        code, resp = post({"x402Version": 2, "paymentPayload": p, "paymentRequirements": reqs}, hdrs)
        ok = "isValid" in resp and "true" in resp
        print(f"  panjang {n:4} -> HTTP {code} " + ("DITERIMA" if ok else "ditolak"))

    print("\npanjang deskripsi resource di route kita (dari challenge):")
    oa = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/openapi.json", headers={"User-Agent": "xh/1.0"}), timeout=45).read().decode())
    rows = []
    for path, methods in (oa.get("paths") or {}).items():
        for m, spec in methods.items():
            if m.lower() not in ("get", "post") or not isinstance(spec, dict) or not spec.get("security"):
                continue
            desc = spec.get("summary") or spec.get("description") or ""
            rows.append((len(desc), m.upper(), path))
    rows.sort(reverse=True)
    for n, m, p in rows[:12]:
        print(f"  {n:4}  {m:4} {p}")


if __name__ == "__main__":
    main()
