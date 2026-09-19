#!/usr/bin/env python3
"""
xh_mcp_server.py — XH Agents MCP Server
Membungkus endpoint XH Agents (xhagents.xyz) sebagai MCP tools sehingga AI agent lain
(bukan cuma manusia via browser) bisa berinteraksi/bertransaksi otomatis dengan XH Agents.

Ini yang membuat XH Agents bukan "sekedar web biasa" — ia menjadi layer API hidup untuk agent
(machine-to-machine): buat ad-order, cek ads, tanya trading assistant, invoice x402, status worker,
market data. Monetisasi tetap x402 USDC di sisi backend (lewat endpoint masing-masing).

Mode:
  # stdio (default) — untuk Hermes / Claude / MCP client lokal:
  /home/ubuntu/prpo_ai/venv/bin/python xh_mcp_server.py

  # SSE/HTTP (opsional, expose ke agent remote):
  /home/ubuntu/prpo_ai/venv/bin/python xh_mcp_server.py --transport sse --port 8989

Requirement: mcp<2 (FastMCP), httpx (terinstall di venv).
"""
import argparse
import os

import httpx
from mcp.server.fastmcp import FastMCP

# Scoped: server memanggil endpoint publik XH Agents (bukan secret).
BASE_URL = os.environ.get("XH_BASE_URL", "https://xhagents.xyz")
TIMEOUT = float(os.environ.get("XH_MCP_TIMEOUT", 40))

# Balанды endpoint yang diekspos sebagai tool.
END = {
    "ad_order": f"{BASE_URL}/api/ad-order",
    "ads": f"{BASE_URL}/api/ads",
    "chat": f"{BASE_URL}/api/chat",
    "chat_invoice": f"{BASE_URL}/api/chat/invoice",
    "chat_balance": f"{BASE_URL}/api/chat/balance",
    "status": f"{BASE_URL}/api/status.json",
    "markets": f"{BASE_URL}/api/markets",
}

mcp = FastMCP("xh-agents")


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


async def _post(path, payload):
    with _client() as c:
        r = c.post(path, json=payload)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}


async def _get(path):
    with _client() as c:
        r = c.get(path)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}


# ── Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
async def create_ad_order(size: str, network: str, email: str,
                          title: str = "", text: str = "",
                          landing_url: str = "", advertiser_wallet: str = "", image_url: str = ""):
    """Buat pesanan iklan (ad order) di XH Agents. size: 728x90/480x320/300x250;
    network: base/solana. Balik order_id, amount_usdc, treasury, memo, pay_url.
    Bayar via USDC (x402/transfer) utk aktivasi."""
    payload = {
        "size": size, "network": network, "email": email,
        "title": title, "text": text, "landing_url": landing_url,
        "advertiser_wallet": advertiser_wallet, "image_url": image_url,
    }
    code, data = await _post(END["ad_order"], payload)
    return {"status": code, "result": data}


@mcp.tool()
async def list_ads():
    """Daftar banner ad yang aktif di xhagents.xyz."""
    code, data = await _get(END["ads"])
    return {"status": code, "ads": data}


@mcp.tool()
async def chat_trading(message: str, user_id: str = "mcp",
                       pair: str = "SOL/USDT", network: str = "Solana",
                       strategy: str = "Momentum Scalp", sl: str = "3",
                       tp: str = "6", size: str = "50",
                       wallet_address: str = ""):
    """Kirim pesan ke AI trading assistant XH Agents (pay-per-message via balance/x402).
    Kalau balance user_id <1, server balas insufficient_balance + panduan top-up."""
    payload = {
        "user_id": user_id, "message": message, "pair": pair, "network": network,
        "strategy": strategy, "sl": sl, "tp": tp, "size": size,
        "wallet_address": wallet_address,
    }
    code, data = await _post(END["chat"], payload)
    return {"status": code, "result": data}


@mcp.tool()
async def chat_get_invoice():
    """Minta invoice x402 utk 1 pesan trading assistant ($0.10 USDC Base → treasury).
    Balik nonce, payout_address, amount; transfer USDC lalu panggil chat_trading dengan
    X-Payment header via raw_http."""
    code, data = await _post(END["chat_invoice"], {})
    return {"status": code, "result": data}


@mcp.tool()
async def chat_check_balance(user_id: str = "mcp", wallet_address: str = "", network: str = ""):
    """Cek saldo (jumlah pesan tersisa) user pada trading assistant."""
    code, data = await _post(END["chat_balance"], {
        "user_id": user_id, "wallet_address": wallet_address, "network": network,
    })
    return {"status": code, "result": data}


@mcp.tool()
async def get_status():
    """Status live worker XH Agents (Solana/Base/Cloudflare) + timestamp via /api/status.json."""
    code, data = await _get(END["status"])
    return {"status": code, "result": data}


@mcp.tool()
async def get_markets():
    """Data market crypto (dari trading assistant /api/markets)."""
    code, data = await _get(END["markets"])
    return {"status": code, "result": data}


@mcp.tool()
async def raw_http(method: str = "POST", path: str = "/api/chat", json_body: str = "{}",
                   headers_json: str = "{}"):
    """Langsung hit endpoint XH Agents dengan metode/body/header bebas (untuk X-Payment dll).
    path contoh: /api/chat, /api/ad-order, /api/onramp. body & header berupa JSON string."""
    import json as _json
    url = BASE_URL + path
    method = method.upper()
    try:
        body = _json.loads(json_body or "{}")
    except Exception:
        body = {}
    try:
        hdr = _json.loads(headers_json or "{}")
    except Exception:
        hdr = {}
    with _client() as c:
        if method == "GET":
            r = c.get(url, headers=hdr)
        else:
            r = c.request(method, url, json=body, headers=hdr)
        try:
            return {"status": r.status_code, "result": r.json()}
        except Exception:
            return {"status": r.status_code, "result": {"raw": r.text[:500]}}


# resources (read-only snapshot)
@mcp.resource("xh://status")
def resource_status() -> str:
    import json as _json
    try:
        with _client() as c:
            r = c.get(END["status"])
            return _json.dumps(r.json(), indent=2)
    except Exception as e:
        return f"error: {e}"


@mcp.resource("xh://ads")
def resource_ads() -> str:
    import json as _json
    try:
        with _client() as c:
            r = c.get(END["ads"])
            return _json.dumps(r.json(), indent=2)
    except Exception as e:
        return f"error: {e}"


def main():
    ap = argparse.ArgumentParser(description="XH Agents MCP Server")
    ap.add_argument("--transport", default="stdio", choices=["stdio", "sse"])
    ap.add_argument("--port", type=int, default=8989)
    args = ap.parse_args()

    if args.transport == "sse":
        import uvicorn
        uvicorn.run(mcp.sse_app(), host="127.0.0.1", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()