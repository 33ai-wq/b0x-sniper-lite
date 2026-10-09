#!/usr/bin/env python3
"""test_extensions.py — uji apakah blok extensions (bazaar) yang membuat CDP menolak payload
pada route tertentu. Verify gratis.
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
BAD = sys.argv[1:] or ["https://xhagents.xyz/api/compute/xh-bundle",
                       "https://xhagents.xyz/api/howto/x402-register"]
GOOD = "https://xhagents.xyz/api/company-enrich"


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

    def build(url):
        _st, required, _h, _raw = xh_pay.challenge(url, "POST", {"a": 1})
        root = xh_pay._dict(required)
        inner = x402ClientSync()
        register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
        pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(
            by_alias=True, exclude_none=True)
        return root, pl

    _groot, gpl = build(GOOD)

    for url in BAD:
        root, pl = build(url)
        reqs = root["accepts"][0]
        print(f"\n== {url.split('/api/')[-1]} | amount={reqs.get('amount')} | "
              f"ext len={len(json.dumps(pl.get('extensions') or {}))}")

        def ok(payload, requirements=None):
            req = urllib.request.Request(VERIFY, data=json.dumps(
                {"x402Version": 2, "paymentPayload": payload,
                 "paymentRequirements": requirements or reqs}).encode(),
                headers={**hdrs, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp = r.read(200).decode()
            except urllib.error.HTTPError as e:
                resp = e.read(200).decode()
            except Exception:  # noqa: BLE001
                resp = ""
            return ("isValid" in resp and "true" in resp), resp[:90]

        v, r = ok(pl)
        print("   apa adanya                     :", "DITERIMA" if v else f"ditolak {r}")
        p = copy.deepcopy(pl); p.pop("extensions", None)
        v, r = ok(p)
        print("   tanpa extensions               :", "DITERIMA" if v else f"ditolak {r}")
        p = copy.deepcopy(pl); p["extensions"] = gpl.get("extensions")
        v, r = ok(p)
        print("   extensions dari route sehat    :", "DITERIMA" if v else f"ditolak {r}")
        p = copy.deepcopy(pl); p["accepted"] = gpl["accepted"]
        v, r = ok(p, gpl["accepted"] if False else None)
        print("   accepted diganti (harga lain)  :", "DITERIMA" if v else f"ditolak {r}")
        p = copy.deepcopy(pl)
        p["extensions"] = gpl.get("extensions")
        p["accepted"] = gpl["accepted"]
        v, r = ok(p, gpl["accepted"])
        print("   keduanya diganti ke route sehat:", "DITERIMA" if v else f"ditolak {r}")


if __name__ == "__main__":
    main()
