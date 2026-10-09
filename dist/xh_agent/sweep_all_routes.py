#!/usr/bin/env python3
"""sweep_all_routes.py — uji (gratis, via CDP /verify) apakah SEMUA route berbayar kita sekarang
menghasilkan payload yang sah, dan bedakan tiga penyebab penolakan:
  - schema/payload  : masalah kita
  - saldo kurang    : masalah isi dompet pembeli
  - lain-lain       : dicetak apa adanya
Dana tidak berpindah.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

VERIFY = "https://api.cdp.coinbase.com/platform/v2/x402/verify"
BASE = "https://xhagents.xyz"


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
    bal = xh_pay.usdc_balance(acct.address) or 0
    print(f"saldo pembeli: ${bal:.4f}\n")

    routes = []
    for r in xh_pay.catalogue():
        routes.append((r["method"], r["path"]))
    ok = schema_bad = funds = other = 0
    problems = []
    for method, path in sorted(set(routes)):
        url = BASE + path
        _st, required, _h, _raw = xh_pay.challenge(url, method, {"a": 1})
        if required is None:
            problems.append((method, path, "tidak ada challenge 402"))
            other += 1
            continue
        root = xh_pay._dict(required)
        reqs = root["accepts"][0]
        amount = int(reqs.get("amount") or 0) / 1e6
        inner = x402ClientSync()
        register_exact_evm_client(inner, EthAccountSigner(acct), ["eip155:8453"])
        pl = x402HTTPClientSync(inner).create_payment_payload(required).model_dump(
            by_alias=True, exclude_none=True)
        desc_len = len(((root.get("resource") or {}).get("description")) or "")
        req = urllib.request.Request(VERIFY, data=json.dumps(
            {"x402Version": 2, "paymentPayload": pl, "paymentRequirements": reqs}).encode(),
            headers={**hdrs, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = r.read(300).decode()
        except urllib.error.HTTPError as e:
            resp = e.read(300).decode()
        except Exception as e:  # noqa: BLE001
            resp = str(e)[:80]
        if "isValid" in resp and "true" in resp:
            ok += 1
        elif "execution reverted" in resp or "insufficient" in resp.lower():
            funds += 1
            problems.append((method, path, f"saldo kurang (butuh ${amount:.2f}, saldo ${bal:.2f})"))
        elif "paymentPayload" in resp or "invalid_request" in resp:
            schema_bad += 1
            problems.append((method, path, f"SCHEMA (desc {desc_len}) {resp[:110]}"))
        else:
            other += 1
            problems.append((method, path, resp[:110]))

    print(f"total route diuji : {len(set(routes))}")
    print(f"  payload SAH     : {ok}")
    print(f"  saldo kurang    : {funds}")
    print(f"  SCHEMA RUSAK    : {schema_bad}   <- ini yang harus nol")
    print(f"  lain-lain       : {other}")
    if problems:
        print("\ncatatan per route:")
        for m, p, why in problems[:20]:
            print(f"  {m:4} {p:<38} {why}")


if __name__ == "__main__":
    main()
