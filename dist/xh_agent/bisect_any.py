#!/usr/bin/env python3
"""bisect_any.py — generalisasi: cari panjang deskripsi maksimum yang diterima CDP untuk URL mana pun,
dan uji apakah masalahnya di panjang atau di isi teks. Verify gratis.

Pakai: python3 bisect_any.py <url> [<url> ...]
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

    urls = sys.argv[1:] or ["https://xhagents.xyz/api/compute/xh-bundle"]
    c = creds()
    hdrs = get_auth_headers(GetAuthHeadersOptions(
        api_key_id=c["CDP_API_KEY_ID"], api_key_secret=c["CDP_API_KEY_PRIVATE_KEY"],
        request_method="POST", request_host="api.cdp.coinbase.com",
        request_path="/platform/v2/x402/verify")) or {}
    acct = Account.from_key(xh_pay._key())

    for url in urls:
        print(f"\n===== {url}")
        _st, required, _h, _raw = xh_pay.challenge(url, "POST", {"a": 1})
        root = xh_pay._dict(required)
        reqs = root["accepts"][0]
        inner = x402ClientSync()
        register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
        pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(
            by_alias=True, exclude_none=True)
        res = pl.get("resource") or {}
        desc = res.get("description") or ""
        print("  resource:", json.dumps({k: (str(v)[:60]) for k, v in res.items()}))

        def ok(d, drop_resource=False):
            p = copy.deepcopy(pl)
            if drop_resource:
                p.pop("resource", None)
            else:
                p["resource"] = dict(p["resource"], description=d)
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

        print("  tanpa resource        :", "DITERIMA" if ok("", True) else "ditolak")
        print(f"  deskripsi asli ({len(desc)}):", "DITERIMA" if ok(desc) else "ditolak")
        print("  deskripsi 'short'     :", "DITERIMA" if ok("short") else "ditolak")
        lo, hi = 0, len(desc)
        if ok(desc):
            print("  -> deskripsi asli sudah diterima, tidak perlu bisect")
            continue
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if ok(desc[:mid]):
                lo = mid
            else:
                hi = mid
        print(f"  batas: prefiks {lo} DITERIMA, {hi} ditolak | potongan: {desc[max(0,lo-30):hi+40]!r}")


if __name__ == "__main__":
    main()
