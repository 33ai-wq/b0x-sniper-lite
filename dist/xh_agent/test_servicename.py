#!/usr/bin/env python3
"""test_servicename.py — uji apakah panjang resource.serviceName (atau gabungan) yang ditolak CDP.
Verify gratis.
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
URLS = sys.argv[1:] or ["https://xhagents.xyz/api/compute/xh-bundle",
                        "https://xhagents.xyz/api/howto/x402-register"]


def creds():
    out = {}
    with open("/home/ubuntu/prpo_ai/cdp/.env.cdp") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    from eth_account import Account
    from x402.client import x402ClientSync
    from x402.http import x402HTTPClientSync
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    c = creds()
    hdrs = get_auth_headers(GetAuthHeadersOptions(
        api_key_id=c["CDP_API_KEY_ID"], api_key_secret=c["CDP_API_KEY_PRIVATE_KEY"],
        request_method="POST", request_host="api.cdp.coinbase.com",
        request_path="/platform/v2/x402/verify")) or {}
    acct = Account.from_key(xh_pay._key())

    for url in URLS:
        _st, required, _h, _raw = xh_pay.challenge(url, "POST", {"a": 1})
        root = xh_pay._dict(required)
        reqs = root["accepts"][0]
        inner = x402ClientSync()
        register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
        pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(
            by_alias=True, exclude_none=True)
        res = pl.get("resource") or {}
        print(f"\n== {url.split('/api/')[-1]}")
        print(f"   desc={len(res.get('description') or '')} serviceName={len(res.get('serviceName') or '')} "
              f"mimeType={res.get('mimeType')!r} tags={res.get('tags')}")

        def ok(**over):
            p = copy.deepcopy(pl)
            p["resource"] = dict(p["resource"], **over)
            req = urllib.request.Request(VERIFY, data=json.dumps(
                {"x402Version": 2, "paymentPayload": p, "paymentRequirements": reqs}).encode(),
                headers={**hdrs, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp = r.read(200).decode()
            except urllib.error.HTTPError as e:
                resp = e.read(200).decode()
            except Exception:  # noqa: BLE001
                resp = ""
            return "isValid" in resp and "true" in resp

        print("   apa adanya                          :", "DITERIMA" if ok() else "ditolak")
        print("   serviceName dipendekkan             :", "DITERIMA" if ok(serviceName="XH Agents") else "ditolak")
        print("   desc pendek + serviceName pendek    :",
              "DITERIMA" if ok(description="short", serviceName="XH Agents") else "ditolak")
        print("   desc pendek + serviceName panjang   :",
              "DITERIMA" if ok(description="short") else "ditolak")
        print("   desc pendek + serviceName kosong    :",
              "DITERIMA" if ok(description="short", serviceName="") else "ditolak")
        for n in (60, 80, 100, 120, 150):
            sn = (res.get("serviceName") or "")[:n]
            print(f"   serviceName {n:>3} karakter (+desc pendek) :",
                  "DITERIMA" if ok(description="short", serviceName=sn) else "ditolak")


if __name__ == "__main__":
    main()
