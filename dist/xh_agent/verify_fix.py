#!/usr/bin/env python3
"""verify_fix.py — setelah restart: ukur panjang deskripsi & uji CDP menerima payload tiap route
yang tadinya >500 karakter. Verify gratis (tanpa dana).
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"
ROUTES = ["https://xhagents.xyz/api/x402-trust", "https://xhagents.xyz/api/token-safety",
          "https://xhagents.xyz/api/hundred-x-hunter", "https://xhagents.xyz/api/video-license",
          "https://xhagents.xyz/api/compute/xh-bundle", "https://xhagents.xyz/api/howto/x402-register"]


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

    print(f"{'route':<44} {'desc':>5}  verify CDP")
    for url in ROUTES:
        _st, required, _h, _raw = xh_pay.challenge(url, "POST", {"a": 1})
        if required is None:
            print(f"{url.split('/api/')[-1]:<44} {'?':>5}  (tidak ada challenge)")
            continue
        root = xh_pay._dict(required)
        reqs = root["accepts"][0]
        desc = ((root.get("resource") or {}).get("description")) or ""
        inner = x402ClientSync()
        register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
        pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(
            by_alias=True, exclude_none=True)
        req = urllib.request.Request(VERIFY, data=json.dumps(
            {"x402Version": 2, "paymentPayload": pl, "paymentRequirements": reqs}).encode(),
            headers={**hdrs, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                code, resp = r.status, r.read(200).decode()
        except urllib.error.HTTPError as e:
            code, resp = e.code, e.read(200).decode()
        except Exception as e:  # noqa: BLE001
            code, resp = 0, str(e)[:60]
        verdict = "DITERIMA" if ("isValid" in resp and "true" in resp) else "DITOLAK"
        print(f"{url.split('/api/')[-1]:<44} {len(desc):>5}  {verdict} (HTTP {code})")


if __name__ == "__main__":
    main()
