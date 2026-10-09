#!/usr/bin/env python3
"""strip_future_annotations.py — buang baris `from __future__ import annotations` dari modul rute berbayar.

Sebab: dengan future-annotations, anotasi jadi string; FastAPI tidak bisa meresolusi model request yang
didefinisikan DI DALAM fungsi register(), sehingga parameter `req: TrustReq` diperlakukan sebagai QUERY
param -> setiap pembeli yang sah mendapat 422 "query req is missing" setelah pembayarannya diverifikasi.

Python 3.12 mendukung `X | Y` dan `list[str]` saat runtime, jadi import itu tidak dibutuhkan di sini.
Setiap berkas dicadangkan sebelum diubah; skrip melaporkan jumlah baris yang dibuang.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import time

FILES = ["x402_trust.py", "token_safety.py", "document_intel.py", "domain_audit.py", "trust_leaderboard.py"]
ROOT = pathlib.Path("/home/ubuntu/prpo_ai/xh_api")
STAMP = time.strftime("%Y%m%d_%H%M%S")

for name in FILES:
    p = ROOT / name
    if not p.exists():
        print(f"{name}: TIDAK ADA")
        continue
    lines = p.read_text().splitlines(True)
    kept = [ln for ln in lines if ln.strip() != "from __future__ import annotations"]
    removed = len(lines) - len(kept)
    if removed:
        shutil.copy(p, p.with_suffix(f".py.bak.{STAMP}"))
        p.write_text("".join(kept))
    print(f"{name}: dibuang {removed} baris (cadangan .bak.{STAMP})")

import py_compile  # noqa: E402

bad = []
for name in FILES:
    try:
        py_compile.compile(str(ROOT / name), doraise=True)
    except Exception as e:  # noqa: BLE001
        bad.append(f"{name}: {type(e).__name__}: {e}")
print("kompilasi:", "SEMUA OK" if not bad else "GAGAL -> " + "; ".join(bad))
sys.exit(1 if bad else 0)
