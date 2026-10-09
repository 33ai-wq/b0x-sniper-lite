#!/usr/bin/env python3
"""isolate_field.py — cari field mana yang membuat CDP menolak payload route x402-trust.

Mulai dari payload apa adanya (ditolak), lalu hapus/ganti satu field per langkah sampai CDP bilang
isValid:true. Verify gratis, tidak memindahkan dana.
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
FAIL_URL = "https://xhagents.xyz/api/x402-trust"
OK_URL = "https://xhagents.xyz/api/kb/ask"


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
            return r.status, r.read(300).decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode()
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


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
    payload = x402HTTPClientSync(inner).create_payment_payload(required)
    return root, payload.model_dump(by_alias=True, exclude_none=True)


def main() -> None:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    c = creds()
    hdrs = get_auth_headers(GetAuthHeadersOptions(
        api_key_id=c["CDP_API_KEY_ID"], api_key_secret=c["CDP_API_KEY_PRIVATE_KEY"],
        request_method="POST", request_host="api.cdp.coinbase.com",
        request_path="/platform/v2/x402/verify")) or {}

    root_f, pl_f = build(FAIL_URL)          # ditolak
    root_o, pl_o = build(OK_URL)            # diterima
    reqs_f = root_f["accepts"][0]

    def send(label, payload, reqs=None):
        body = {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": reqs or reqs_f}
        code, resp = post(body, hdrs)
        ok = '"isValid":true' in resp
        print(f"  {'OK ' if ok else '   '} {label:52} -> HTTP {code} {resp[:110]}")
        return ok

    print("acuan:")
    send("x402-trust apa adanya (harus GAGAL)", pl_f)
    send("kb/ask apa adanya (harus OK)", pl_o, root_o["accepts"][0])

    print("\nbedah field (payload x402-trust):")
    p = copy.deepcopy(pl_f)
    p1 = copy.deepcopy(p); p1.pop("extensions", None)
    send("tanpa extensions", p1)
    p2 = copy.deepcopy(p); p2.pop("resource", None)
    send("tanpa resource", p2)
    p3 = copy.deepcopy(p); p3["resource"] = pl_o.get("resource")
    send("resource diganti milik kb/ask", p3)
    p4 = copy.deepcopy(p); p4["accepted"] = dict(p4["accepted"], amount="30000")
    send("amount diubah ke 30000", p4)
    p5 = copy.deepcopy(p); p5["resource"] = dict((p5.get("resource") or {}),
                                                 description="short")
    send("resource.description dipendekkan", p5)
    p6 = copy.deepcopy(p); p6["resource"] = dict((p6.get("resource") or {}), mimeType="")
    send("resource.mimeType dikosongkan", p6)
    p7 = copy.deepcopy(p); p7["resource"] = dict((p7.get("resource") or {}),
                                                 serviceName="XH Agents test")
    send("resource.serviceName disederhanakan", p7)
    p8 = copy.deepcopy(p); p8["resource"] = dict((p8.get("resource") or {}), tags=["x402"])
    send("tags disederhanakan", p8)


if __name__ == "__main__":
    main()
