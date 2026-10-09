#!/usr/bin/env python3
"""diff_challenges.py — bandingkan challenge GET vs POST pada route kembar.

Tujuan: cari beda antara route yang BISA dibayar (mis. /howto/youtube-auto-ai) dan yang TIDAK
(mis. /x402-trust), supaya penyebabnya terbaca, bukan ditebak.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

PAIRS = [
    ("https://xhagents.xyz/api/x402-trust", "GAGAL dibayar"),
    ("https://xhagents.xyz/api/token-safety", "GAGAL dibayar"),
    ("https://xhagents.xyz/api/howto/youtube-auto-ai", "BERHASIL dibayar"),
    ("https://xhagents.xyz/api/daily-drop", "BERHASIL dibayar"),
    ("https://xhagents.xyz/api/wallet-profile", "BERHASIL dibayar"),
]

for url, note in PAIRS:
    print(f"\n=== {url.split('/api/')[-1]}  ({note}) ===")
    rows = {}
    for m in ("GET", "POST"):
        st, required, _h, _raw = xh_pay.challenge(url, m)
        info = xh_pay.describe(required) if required is not None else {"http": st}
        rows[m] = info
        print(f"  {m}: HTTP {st} | " + json.dumps(info))
    if rows["GET"].get("price_usdc") is not None and rows["POST"].get("price_usdc") is not None:
        same = all(rows["GET"].get(k) == rows["POST"].get(k)
                   for k in ("price_usdc", "payTo", "network", "asset", "resource"))
        print(f"  → challenge GET == POST ? {same}")
        for k in ("price_usdc", "payTo", "resource"):
            if rows["GET"].get(k) != rows["POST"].get(k):
                print(f"     BEDA di {k}: GET={rows['GET'].get(k)} POST={rows['POST'].get(k)}")
