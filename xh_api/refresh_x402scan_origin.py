#!/usr/bin/env python3
"""Segarkan catatan origin di x402scan (judul/deskripsi) dari metadata situs kita.

x402scan membangun judul + deskripsi listing dari <meta name="description"> / og:description di beranda,
dan menyimpannya di catatan origin. Karena itu angkanya hanya ikut berubah kalau ada resource yang
di-register ulang — dipakai oleh cron harian supaya "N endpoints" tidak pernah basi lagi.

Contoh:
    python3 refresh_x402scan_origin.py                       # origin kita sendiri
    python3 refresh_x402scan_origin.py --origin https://pronomad.duckdns.org
    python3 refresh_x402scan_origin.py --check               # hanya baca, tidak mengubah
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
T = "https://www.x402scan.com/api/trpc/"
OUR_ORIGIN = "https://xhagents.xyz"
OUR_ORIGIN_ID = "c38382fc-0d5f-4e48-b368-c088f24581ac"


def call(proc: str, payload: dict) -> dict:
    req = urllib.request.Request(T + proc, data=json.dumps(payload).encode(), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:300]}


def inner(d: dict) -> dict:
    return ((d.get("result") or {}).get("data") or {}).get("json") or {}


def origin_record(origin_id: str) -> dict:
    return inner(call("public.origins.get", {"json": origin_id}))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", default=OUR_ORIGIN)
    ap.add_argument("--origin-id", default=OUR_ORIGIN_ID)
    ap.add_argument("--check", action="store_true", help="hanya laporkan, jangan register")
    args = ap.parse_args()

    disco = inner(call("public.resources.checkDiscovery", {"json": {"origin": args.origin, "bustCache": True}}))
    urls = [u if isinstance(u, str) else u.get("url") for u in (disco.get("resources") or [])]
    # x402scan merges our .well-known with every path in openapi.json, so it also lists endpoints that are
    # not x402-paid (the ad engine, for instance). Use OUR discovery document as the authoritative paid set:
    # it is what we publish as paid, and registering something that does not answer 402 fails.
    try:
        req = urllib.request.Request(f"{args.origin.rstrip('/')}/.well-known/x402",
                                     headers={"User-Agent": "xh-agents-origin-refresh/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            ours = json.loads(r.read().decode()).get("resources") or []
    except Exception as e:
        print(f"  gagal membaca .well-known sendiri: {type(e).__name__} — memakai daftar discovery x402scan")
        ours = []
    pool = [u for u in (ours or urls) if u and not u.rstrip("/").endswith("/method")]
    # utamakan yang paling baru kita bangun: kalau satu gagal, coba berikutnya
    pref = [u for u in pool if any(k in u for k in ("domain-audit", "document-extract", "trust-leaderboard",
                                                    "token-safety", "x402-trust", "hundred-x-hunter"))]
    paid = sorted(set(pref)) + sorted(set(pool).difference(pref))
    print(f"{args.origin}: discovery {disco.get('resourceCount')} entri, {len(set(pool))} resource berbayar "
          f"(dari .well-known sendiri)")

    before = origin_record(args.origin_id)
    print(f"  tercatat sekarang: {str(before.get('description'))[:110]}…")
    print(f"  diperbarui pada : {before.get('updatedAt')}")

    if args.check:
        return

    if not paid:
        print("  tidak ada resource untuk di-register ulang — dibatalkan")
        return
    # satu register yang berhasil sudah menulis ulang catatan origin; coba beberapa kandidat teratas
    ok = None
    for url in paid[:6]:
        d = call("public.resources.register", {"json": {"url": url}})
        j = inner(d)
        print(f"  register ulang: {url} -> success={j.get('success')}")
        if j.get("success"):
            ok = url
            break
    if not ok:
        print("  semua percobaan register gagal — catatan origin tidak tersentuh")
        return

    after = origin_record(args.origin_id)
    desc = str(after.get("description") or "")
    print(f"  sesudah        : {desc[:150]}…")
    print(f"  diperbarui pada: {after.get('updatedAt')}")
    same = desc == str(before.get("description") or "")
    print("  status: " + ("TIDAK BERUBAH (situs sudah sinkron)" if same else "DESKRIPSI DIPERBARUI"))
    if desc != str(before.get("description") or "") and "live x402" in desc:
        print("  angka yang diklaim deskripsi:", desc.split("live x402")[0].strip().split()[-1])


if __name__ == "__main__":
    sys.exit(main())
