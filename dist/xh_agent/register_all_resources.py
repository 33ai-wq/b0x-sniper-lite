#!/usr/bin/env python3
"""register_all_resources.py — daftarkan ulang SEMUA resource berbayar kita ke tabel registri x402scan,
lalu baca-balik hasilnya. Ini yang mengisi daftar resource di halaman server kita
(deskripsi origin saja tidak cukup — itu hanya metadata).

Read-only terhadap sistem kita; menulis ke registri x402scan milik kita sendiri.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

T = "https://www.x402scan.com/api/trpc/"
OID = "c38382fc-0d5f-4e48-b368-c088f24581ac"
UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def call(proc: str, payload, timeout: int = 90):
    req = urllib.request.Request(T + proc, data=json.dumps(payload).encode(), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return ((d.get("result") or {}).get("data") or {}).get("json")
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode()[:150]}
    except Exception as e:  # noqa: BLE001
        return {"_err": f"{type(e).__name__}: {str(e)[:80]}"}


def main() -> None:
    urls = sorted({r["path"] for r in xh_pay.catalogue()})
    urls = ["https://xhagents.xyz" + p for p in urls]
    print(f"resource berbayar untuk didaftarkan ulang: {len(urls)}")
    ok = fail = 0
    for u in urls:
        res = call("public.resources.register", {"json": {"url": u, "method": "POST"}}, timeout=60)
        good = isinstance(res, dict) and (res.get("success") is True or res.get("id") or res.get("resource"))
        ok += 1 if good else 0
        fail += 0 if good else 1
        if not good:
            print(f"  GAGAL {u} -> {json.dumps(res)[:120]}")
        time.sleep(0.4)
    print(f"register: sukses {ok} | gagal {fail}")

    chk = call("public.resources.checkRegistered",
               {"json": {"resources": [{"url": u} for u in urls]}})
    if isinstance(chk, dict):
        print(f"checkRegistered: registered={len(chk.get('registered') or [])} "
              f"unregistered={len(chk.get('unregistered') or [])}")
    org = call("public.origins.get", {"json": OID})
    if isinstance(org, dict):
        print(f"origins.get: resources={len(org.get('resources') or [])} "
              f"updatedAt={org.get('updatedAt')}")
    else:
        print("origins.get:", json.dumps(org)[:150])


if __name__ == "__main__":
    main()
