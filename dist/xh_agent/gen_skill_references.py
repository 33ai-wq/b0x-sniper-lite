#!/usr/bin/env python3
"""gen_skill_references.py — bangun references/routes.md untuk folder skill dari HARGA LIVE.

Kenapa tidak ditulis tangan: tabel harga di dokumen selalu basi. Skrip ini menanyakan challenge 402
setiap route berbayar (GET dan POST) di openapi.json, lalu menulis tabel yang bisa diregenerasi.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xh_pay  # noqa: E402

OUT = "/home/ubuntu/prpo_ai/dist/clawhub/xh-agents-x402/references/routes.md"
BASE = "https://xhagents.xyz"


def paid_paths() -> list[tuple[str, str, str]]:
    req = urllib.request.Request(f"{BASE}/openapi.json", headers={"User-Agent": xh_pay.UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        doc = json.loads(r.read().decode())
    rows = []
    for path, methods in (doc.get("paths") or {}).items():
        for m, spec in methods.items():
            if m.lower() not in ("get", "post") or not isinstance(spec, dict) or not spec.get("security"):
                continue
            rows.append((m.upper(), path, (spec.get("summary") or "")[:90]))
    return sorted(rows, key=lambda r: (r[1], r[0]))


def quote(row: tuple[str, str, str]):
    method, path, summary = row
    _st, required, _h, _raw = xh_pay.challenge(BASE + path, method)
    info = xh_pay.describe(required) if required is not None else {}
    return method, path, summary, info.get("price_usdc")


def main() -> None:
    rows = paid_paths()
    with ThreadPoolExecutor(max_workers=6) as ex:
        quoted = list(ex.map(quote, rows))
    quoted.sort(key=lambda r: (r[3] if r[3] is not None else 9e9, r[1]))
    lines = ["# XH Agents paid routes (generated from live 402 challenges)", "",
             f"Source: `{BASE}/openapi.json` + each route's own 402 challenge. "
             "Regenerate with `gen_skill_references.py`; do not hand-edit prices.", "",
             f"{len(quoted)} paid routes.", "",
             "| price | method | path | summary |", "|---|---|---|---|"]
    for method, path, summary, price in quoted:
        p = f"${price:.2f}" if price is not None else "?"
        lines.append(f"| {p} | {method} | `{path}` | {summary} |")
    lines += ["", "Free, no key: `python3 scripts/xh_pay.py quote <url>` prints the live price, the",
              "network, the asset and the `payTo` address before anything is signed.", ""]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines))
    priced = [q[3] for q in quoted if q[3] is not None]
    print(f"ditulis: {OUT} ({len(quoted)} route, {len(priced)} berharga)")
    if priced:
        print(f"  rentang harga: ${min(priced):.2f} – ${max(priced):.2f}")


if __name__ == "__main__":
    main()
