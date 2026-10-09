#!/usr/bin/env python3
"""probe_third_party_pay.py — pisahkan salah-klien dari salah-server.

Logika: kalau klien kita berhasil membayar endpoint MILIK ORANG LAIN, maka klien kita benar dan
masalahnya ada di sisi server kita (proxy yang me-remarshal payload saat meneruskan ke facilitator CDP).
Kalau gagal dengan error yang sama persis, masalahnya di klien/SDK.

Ambil kandidat murah (<= $0.005) dari indeks discovery Coinbase, lalu coba bayar satu.
"""
from __future__ import annotations

import json
import sys
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

INDEX = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
UA = {"User-Agent": "xh-probe/1.0", "Accept": "application/json"}


def cheap_candidates(max_price: float = 0.005, pages: int = 4):
    out = []
    for off in range(0, pages * 100, 100):
        try:
            req = urllib.request.Request(f"{INDEX}?limit=100&offset={off}", headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            print(f"  halaman {off} gagal: {type(e).__name__}")
            continue
        for it in (d.get("items") or []):
            url = it.get("resource") or ""
            if "xhagents.xyz" in url:
                continue
            for a in (it.get("accepts") or []):
                if a.get("network") != "eip155:8453":
                    continue
                amt = a.get("amount") or a.get("maxAmountRequired")
                try:
                    price = int(amt) / 1e6
                except Exception:  # noqa: BLE001
                    continue
                if 0 < price <= max_price:
                    out.append({"url": url, "price": price, "host": url.split("/")[2],
                                "desc": (it.get("description") or "")[:60]})
    uniq = {}
    for c in out:
        uniq.setdefault(c["url"], c)
    return sorted(uniq.values(), key=lambda c: c["price"])[:12]


def main() -> None:
    cands = cheap_candidates()
    print(f"kandidat murah (<=$0.005) dari indeks: {len(cands)}")
    for c in cands[:8]:
        print(f"  ${c['price']:.4f}  {c['url'][:78]}  {c['desc']}")
    if not cands:
        return
    target = cands[0]
    print(f"\n--- mencoba membayar {target['url']} (${target['price']:.4f}) ---")
    _st, required, _h, _raw = xh_pay.challenge(target["url"], "GET")
    if required is None:
        print("tidak ada challenge 402 di URL itu; coba kandidat lain secara manual")
        return
    print("quote:", json.dumps(xh_pay.describe(required)))
    out = xh_pay.pay(target["url"], "GET", None, max_price=0.01, show=400)
    print(json.dumps(out, indent=1)[:2500])


if __name__ == "__main__":
    main()
