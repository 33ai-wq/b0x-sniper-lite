#!/usr/bin/env python3
"""test_ascii_theory.py — uji apakah karakter non-ASCII di resource.description yang membuat CDP
menolak payload. Verify gratis.
"""
from __future__ import annotations

import copy
import json
import sys
import unicodedata
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"


def creds() -> dict:
    out = {}
    with open("/home/ubuntu/prpo_ai/cdp/.env.cdp") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def post(body, hdrs):
    req = urllib.request.Request(VERIFY, data=json.dumps(body).encode(),
                                 headers={**hdrs, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(200).decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode()
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:80]


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

    _st, required, _h, _raw = xh_pay.challenge("https://xhagents.xyz/api/x402-trust", "POST", {"a": 1})
    root = xh_pay._dict(required)
    reqs = root["accepts"][0]
    acct = Account.from_key(xh_pay._key())
    inner = x402ClientSync()
    register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
    pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(by_alias=True, exclude_none=True)
    orig = (pl.get("resource") or {}).get("description") or ""
    nonascii = sorted({ch for ch in orig if ord(ch) > 127})
    print(f"deskripsi asli: {len(orig)} karakter | non-ASCII ditemukan: {nonascii}")

    def check(label, desc):
        p = copy.deepcopy(pl)
        p["resource"] = dict(p["resource"], description=desc)
        code, resp = post({"x402Version": 2, "paymentPayload": p, "paymentRequirements": reqs}, hdrs)
        ok = "isValid" in resp and "true" in resp
        print(f"  {'DITERIMA' if ok else 'ditolak ':9} {label:52} HTTP {code}")
        return ok

    check("asli apa adanya", orig)
    check("em dash diganti '-'", orig.replace("\u2014", "-").replace("\u2013", "-"))
    check("semua non-ASCII dibuang", "".join(ch for ch in orig if ord(ch) < 128))
    check("ASCII + normalisasi NFKD lalu buang non-ASCII",
          unicodedata.normalize("NFKD", orig).encode("ascii", "ignore").decode())
    check("hanya em dash yang diuji (potongan)", "a \u2014 b")


if __name__ == "__main__":
    main()
