#!/usr/bin/env python3
"""mcp_server.py — server MCP XH Agents: endpoint berbayar kita dipasang sebagai tool untuk agent lain.

Jalankan (stdio, standar MCP):
    /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/dist/xh_agent/mcp_server.py

Tool gratis (tanpa kunci, tanpa biaya):
    xh_catalogue      daftar route berbayar + ringkasannya
    xh_quote          harga/jaringan/payTo sebuah resource sebelum membayar
    xh_provenance     angka kami sendiri (panggilan cair, USDC on-chain, saldo treasury)
Tool berbayar (butuh XH_PAYER_KEY / XH_PAYER_KEY_FILE; ada plafon harga per panggilan):
    xh_trust_score    skor kepercayaan 0-100 sebuah endpoint x402
    xh_token_safety   skor keamanan 0-100 sebuah token di Base
    xh_call           panggil route apa pun di katalog dengan plafon harga

Keselamatan: setiap tool berbayar memeriksa harga dari challenge 402 dan MENOLAK kalau melebihi
plafon (default $0.10). Kunci tidak pernah dicetak; yang dilaporkan hanya alamat pembayar.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xh_pay  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

BASE = "https://xhagents.xyz"
MAX_PRICE = float(os.environ.get("XH_MAX_PRICE_USDC", "0.10"))
mcp = FastMCP("xh-agents")


@mcp.tool()
def xh_catalogue() -> str:
    """List the paid x402 routes XH Agents sells, with a one-line summary for each."""
    rows = xh_pay.catalogue()
    lines = [f'{r["method"]:<4} {BASE}{r["path"]:<36} {r["summary"]}' for r in rows]
    return f"{len(rows)} paid routes:\n" + "\n".join(lines)


@mcp.tool()
def xh_quote(url: str, method: str = "GET") -> str:
    """Read the x402 price challenge for a resource before paying it (free, no key needed)."""
    status, required, _hdr, raw = xh_pay.challenge(url, method)
    if required is None:
        return json.dumps({"http": status, "note": "no PAYMENT-REQUIRED challenge", "body": raw[:200]})
    return json.dumps({"http": status, "quote": xh_pay.describe(required)}, indent=1)


@mcp.tool()
def xh_provenance() -> str:
    """Our own published numbers: settled calls, USDC into the treasury, treasury balance."""
    import urllib.request
    req = urllib.request.Request(f"{BASE}/data/provenance.json", headers={"User-Agent": xh_pay.UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()
    except Exception:  # noqa: BLE001
        path = "/home/ubuntu/prpo_ai/adengine/data/provenance.json"
        return open(path).read() if os.path.exists(path) else "{}"


@mcp.tool()
def xh_trust_score(url: str, max_price: float = MAX_PRICE) -> str:
    """Score an x402 endpoint 0-100 before paying it: gate behaviour, challenge conformance,
    discovery documents, payTo reputation, price sanity. Paid ($0.05); refuses above max_price."""
    out = xh_pay.pay(f"{BASE}/api/x402-trust", "POST", {"url": url}, max_price=max_price, show=4000)
    return json.dumps(out, indent=1)[:6000]


@mcp.tool()
def xh_token_safety(token: str, max_price: float = MAX_PRICE) -> str:
    """Score a Base token 0-100 for safety (liquidity, holder concentration, contract powers,
    upgradeability, creator history). Paid ($0.05); refuses above max_price."""
    out = xh_pay.pay(f"{BASE}/api/token-safety", "POST", {"token": token},
                     max_price=max_price, show=4000)
    return json.dumps(out, indent=1)[:6000]


@mcp.tool()
def xh_call(path: str, method: str = "POST", body_json: str = "{}",
            max_price: float = MAX_PRICE) -> str:
    """Call any route from xh_catalogue and pay for it. `path` is like /api/x402-trust.
    `body_json` is the JSON request body. Refuses if the quoted price exceeds max_price."""
    try:
        body = json.loads(body_json) if body_json else None
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"body_json bukan JSON: {e}"})
    url = path if path.startswith("http") else BASE + path
    out = xh_pay.pay(url, method, body, max_price=max_price, show=4000)
    return json.dumps(out, indent=1)[:6000]


if __name__ == "__main__":
    mcp.run()
