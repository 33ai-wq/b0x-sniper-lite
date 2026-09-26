#!/usr/bin/env python3
"""xh_api — paid x402 data endpoints on xhagents.xyz.

Five POST endpoints, 0.10 USDC each, settled in USDC on Base through the CDP facilitator:

  /wallet-profile   EVM address forensics on Base (balances, contract?, recent USDC activity, labels)
  /gas-tracker      Base gas: base fee, suggested priority fees, USD cost estimates
  /token-check      ERC-20 metadata + proxy detection + free DEX liquidity/volume data
  /x402-check       Probe ANY x402 endpoint and return a conformance report
  /payment-verify   Verify a USDC settlement by transaction hash

Design rules that matter here:
* Every endpoint returns its methodology and an explicit `not_checked` list where a claim could not
  be verified from the data we actually have. Never report a safety check we did not perform.
* /x402-check fetches an arbitrary URL, so it is guarded against SSRF (http/https only, no private
  or loopback targets, bounded redirects, small body cap, short timeout).
* The paid gate is the same standard x402 envelope as the KB endpoint: unpaid requests are answered
  before any request validation.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, "/home/ubuntu/prpo_ai")
from xh_verify import verify_tx_usdc  # noqa: E402

# ── config ────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("XH_API_PORT", "8991"))
PRICE_USDC = float(os.environ.get("XH_API_PRICE", "0.1"))
# the bundle is a knowledge product, not a data call: priced per route ($2 vs $0.10)
BUNDLE_PRICE_USDC = float(os.environ.get("XH_BUNDLE_PRICE_USDC", "2"))
PRICE_OVERRIDES: dict[str, float] = {"POST /xh-bundle": BUNDLE_PRICE_USDC}
# a route can be served under a longer public path (nginx prefix) — the challenge must quote the
# URL a buyer can actually reach, not the internal one
RESOURCE_OVERRIDES: dict[str, str] = {"POST /xh-bundle": "/api/compute/xh-bundle"}
BUNDLE_FILE = os.environ.get("XH_BUNDLE_FILE", "/home/ubuntu/prpo_ai/xh_api/bundles/xh_bundle.json")
TREASURY_BASE = os.environ.get("XH_TREASURY_BASE", "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0")
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_NETWORK = "eip155:8453"
SITE = "https://xhagents.xyz"
FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
CDP_HOST, CDP_BASE_PATH = "api.cdp.coinbase.com", "/platform/v2/x402"
CDP_ENV_FILE = "/home/ubuntu/prpo_ai/cdp/.env.cdp"

# A dedicated RPC (e.g. Alchemy) goes first when XH_BASE_RPC is set; the public endpoints stay
# as fallbacks. Dropped after measuring them on 2026-09-26: base.llamarpc.com (Cloudflare 525,
# returns non-JSON), base.blockpi.network (same), base.meowrpc.com (no eth_getLogs),
# base.drpc.org (>10k block cap), 1rpc.io/base (eth_getLogs capped at 50 blocks).
_DEDICATED_RPC = os.environ.get("XH_BASE_RPC", "").strip()
RPC_LIST = ([_DEDICATED_RPC] if _DEDICATED_RPC else []) + \
           ["https://base-rpc.publicnode.com", "https://mainnet.base.org"]
LOG_RPC_LIST = RPC_LIST
ERC20_MIN_ABI = [
    {"name": "name", "type": "function", "inputs": [], "outputs": [{"type": "string"}], "stateMutability": "view"},
    {"name": "symbol", "type": "function", "inputs": [], "outputs": [{"type": "string"}], "stateMutability": "view"},
    {"name": "decimals", "type": "function", "inputs": [], "outputs": [{"type": "uint8"}], "stateMutability": "view"},
    {"name": "totalSupply", "type": "function", "inputs": [], "outputs": [{"type": "uint256"}], "stateMutability": "view"},
    {"name": "owner", "type": "function", "inputs": [], "outputs": [{"type": "address"}], "stateMutability": "view"},
    {"name": "balanceOf", "type": "function", "inputs": [{"type": "address"}],
     "outputs": [{"type": "uint256"}], "stateMutability": "view"},
]

# EIP-1967 implementation slot — presence means the contract is a proxy
EIP1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"

# A few Base addresses worth labelling when they show up as USDC counterparties.
LABELS = {
    "0x4200000000000000000000000000000000000006": "WETH (Base predeploy)",
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "USDC (Base)",
    "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": "Aerodrome Router",
    "0x2626664c2603336e57b271c5c0b26f421741e481": "Uniswap V3 SwapRouter02",
    "0x3154cf16ccdb4c6d922629664174b904d80f2c35": "Base Bridge",
    "0x49048044d57e1c92a77f79988d21fa8faf74e97e": "Base L1 Standard Bridge",
}


# ── RPC helpers (fallback across public endpoints) ────────────────────────────
def _rpc(method: str, params: list, timeout: float = 20.0) -> Any:
    """Try every endpoint, twice: the public RPCs rate-limit bursts and time out at random."""
    last: Any = None
    for attempt in range(2):
        for url in (LOG_RPC_LIST if method == "eth_getLogs" else RPC_LIST):
            try:
                r = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                               headers={"User-Agent": "xh-agents-api/1.0"},
                               timeout=timeout if method != "eth_getLogs" else max(timeout, 45.0))
                r.raise_for_status()
                j = r.json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                return j.get("result")
            except Exception as e:  # try the next endpoint
                last = f"{url}: {type(e).__name__} {e}"[:200]
        if attempt == 0:
            time.sleep(1.5)
    raise HTTPException(status_code=503, detail=f"rpc_unavailable: {last}")


def _hex_to_int(v: Any) -> int:
    if v is None:
        return 0
    return int(v, 16) if isinstance(v, str) else int(v)


def _is_address(a: str) -> bool:
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", a or ""))


def erc20_call(to: str, fn: str, args: list | None = None) -> Any:
    """Call a view function from the minimal ABI using web3 (with an RPC fallback)."""
    from web3 import Web3
    last: Any = None
    for url in RPC_LIST:
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 20}))
            c = w3.eth.contract(address=Web3.to_checksum_address(to), abi=ERC20_MIN_ABI)
            return getattr(c.functions, fn)(*(args or [])).call()
        except Exception as e:
            last = f"{url}: {type(e).__name__} {e}"[:200]
    raise RuntimeError(f"erc20_call {fn} failed ({last})")


# ── x402 paid gate (same pattern as the KB service) ───────────────────────────
def _cdp_credentials() -> dict:
    creds: dict[str, str] = {}
    try:
        with open(CDP_ENV_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as e:
        print(f"[xh-api] WARNING: cannot read CDP credentials ({e})", flush=True)
    return creds


def _cdp_create_headers() -> dict:
    from cdp.auth import GetAuthHeadersOptions, get_auth_headers
    creds = _cdp_credentials()
    kid = creds.get("CDP_API_KEY_ID") or os.environ.get("CDP_API_KEY_ID", "")
    ksec = creds.get("CDP_API_KEY_PRIVATE_KEY") or os.environ.get("CDP_API_KEY_PRIVATE_KEY", "")

    def one(method: str, path: str) -> dict:
        return get_auth_headers(GetAuthHeadersOptions(
            api_key_id=kid, api_key_secret=ksec,
            request_method=method, request_host=CDP_HOST, request_path=path)) or {}

    return {"supported": one("GET", CDP_BASE_PATH + "/supported"),
            "verify": one("POST", CDP_BASE_PATH + "/verify"),
            "settle": one("POST", CDP_BASE_PATH + "/settle"),
            "bazaar": one("GET", CDP_BASE_PATH + "/discovery/resources")}


app = FastAPI(title="XH Agents paid data API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["*"])

PAID_ROUTES = [
    ("POST /wallet-profile", "walletProfile", "EVM address profile on Base",
     "Balances, contract status, nonce, recent USDC activity and known-address labels for any Base address.",
     {"address": "0x4200000000000000000000000000000000000006"},
     {"type": "object", "properties": {"address": {"type": "string"}, "chain_id": {"type": "integer"}},
      "required": ["address"]},
     {"address": "0x4200000000000000000000000000000000000006", "is_contract": True,
      "balance_eth": "0.0", "balance_usdc": "0.0", "nonce": 0, "recent_usdc_transfers": 3, "labels": ["WETH (Base predeploy)"]}),
    ("POST /gas-tracker", "gasTracker", "Base gas tracker",
     "Current Base base fee, suggested priority fees and USD cost estimates for a transfer or an ERC-20 transfer.",
     {"chain_id": 8453},
     {"type": "object", "properties": {"chain_id": {"type": "integer"}}},
     {"chain_id": 8453, "base_fee_gwei": "0.012", "priority_fee_gwei": {"low": "0.001", "medium": "0.005", "high": "0.02"},
      "usd_estimate": {"transfer_21000": "0.0001", "erc20_transfer_65000": "0.0003"}}),
    ("POST /token-check", "tokenCheck", "Base ERC-20 check",
     "ERC-20 metadata, proxy detection and free DEX liquidity data for a token on Base, with the checks that could not be performed stated explicitly.",
     {"token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
     {"type": "object", "properties": {"token": {"type": "string"}, "chain_id": {"type": "integer"}},
      "required": ["token"]},
     {"token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6,
      "is_proxy": False, "dex": {"liquidity_usd": 296000000.0}, "not_checked": ["honeypot simulation", "holder concentration"]}),
    ("POST /x402-check", "x402Check", "x402 endpoint conformance report",
     "Fetches any x402 endpoint, decodes its 402 challenge and reports conformance: version, accepts fields, PAYMENT-REQUIRED header, bazaar metadata and price.",
     {"url": "https://xhagents.xyz/api/kb/ask", "method": "POST"},
     {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"},
                                       "body": {"type": "object"}}, "required": ["url"]},
     {"url": "https://xhagents.xyz/api/kb/ask", "status": 402, "conformant": True, "x402Version": 2,
      "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "30000",
                   "payTo": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"}], "has_bazaar_extension": True}),
    ("POST /defi-sentiment", "defiSentiment", "DeFi / asset sentiment",
     "Funding rate, open interest and price trend for a perpetual pair (Binance public data) plus protocol TVL change from DefiLlama, combined into a labelled sentiment with its weights shown.",
     {"asset": "BTC", "protocol": "aerodrome"},
     {"type": "object", "properties": {"asset": {"type": "string"}, "protocol": {"type": "string"}}},
     {"asset": "BTC", "sentiment": "mildly bullish", "score": 0.42,
      "funding_rate_8h_pct": "0.0089", "open_interest_usd": 412000000, "price_change": {"24h_pct": 1.9, "7d_pct": -2.4},
      "protocol_tvl": {"slug": "aerodrome", "tvl_usd": 380000000, "change_24h_pct": 1.1, "change_7d_pct": -3.2}}),
    ("POST /whale-watch", "whaleWatch", "Large recent transfers on Base",
     "Scans the last blocks for USDC and WETH transfers above a USD threshold and returns the largest movements with direction and counterparties. Pending-mempool visibility needs a node with txpool access, which this reports instead of faking.",
     {"min_usd": 100000, "blocks": 300, "token": "USDC"},
     {"type": "object", "properties": {"min_usd": {"type": "number"}, "blocks": {"type": "integer"},
                                       "token": {"type": "string"}}},
     {"blocks_scanned": 300, "threshold_usd": 100000, "events_found": 4,
      "largest": [{"token": "USDC", "amount": "1250000.0", "from": "0x...", "to": "0x...", "tx_hash": "0x..."}]}),
    ("POST /x402-directory", "x402Directory", "Search the x402 ecosystem",
     "Searches Coinbase Bazaar and the x402-list directory at once and returns de-duplicated endpoints with price, network, payTo and description, so an agent can find a service to pay without knowing it in advance.",
     {"query": "gas", "max_price_usd": 0.5, "limit": 10},
     {"type": "object", "properties": {"query": {"type": "string"}, "network": {"type": "string"},
                                       "max_price_usd": {"type": "number"}, "limit": {"type": "integer"}}},
     {"query": "gas", "sources": ["coinbase-bazaar", "x402-list"], "results": 3,
      "endpoints": [{"url": "https://xhagents.xyz/api/gas-tracker", "price_usd": 0.1, "network": "eip155:8453",
                     "payTo": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0", "sources": ["bazaar", "x402-list"]}]}),
    ("POST /payment-verify", "paymentVerify", "USDC settlement verification",
     "Verifies that a transaction hash settled a USDC payment to a given recipient, returning the parsed transfer and confirmation count.",
     {"tx_hash": "0x" + "0" * 64, "to": TREASURY_BASE, "min_amount": 0.1},
     {"type": "object", "properties": {"tx_hash": {"type": "string"}, "to": {"type": "string"},
                                       "from": {"type": "string"}, "min_amount": {"type": "number"}},
      "required": ["tx_hash"]},
     {"verified": True, "from": "0x85fc53d6a89bf64e563588efc37b12ee89c4e421", "to": TREASURY_BASE,
      "amount_usdc": "0.1", "confirmations": 3}),
    ("POST /xh-bundle", "xhBundle", "XH Agents playbook bundle",
     "Thirteen production playbooks from running an x402 paid API on Base: shipping the endpoint, the payment-verifier rules, the real-money buyer test, the Base RPC capability audit, CDP authentication, directory registration, consolidating Cloudflare/Solana data, an rclone Google Drive bridge, AdSense, multi-size ad slots, nginx route recovery and secure Telegram alerts. Each item carries the mechanism, the commands, the pitfalls that cost us real money and how to verify the result.",
     {"topic": "fix-bug-base-rpc", "format": "json"},
     {"type": "object", "properties": {"topic": {"type": "string"}, "format": {"type": "string"}},
      "required": []},
     {"bundle": "XH Agents — Build & Ship an x402 Paid API", "version": "1.0.0",
      "items_returned": 13, "requested_topic": None,
      "items": [{"id": "fix-bug-base-rpc", "title": "Pick Base RPC endpoints that actually work",
                 "steps": [{"n": 1, "do": "probe each candidate with a real ~200-block eth_getLogs"}],
                 "pitfalls": ["base.llamarpc.com answers a Cloudflare 525 / non-JSON"]}]}),
]

STANDARD_X402 = os.environ.get("X402_STANDARD", "1") != "0"
X402_ROUTES: dict[str, Any] = {}
if STANDARD_X402:
    try:
        from x402 import x402ResourceServer
        from x402.extensions.bazaar import OutputConfig, declare_discovery_extension
        from x402.http import CreateHeadersAuthProvider, FacilitatorConfig, HTTPFacilitatorClient
        from x402.http.middleware.fastapi import payment_middleware
        from x402.mechanisms.evm.exact import register_exact_evm_server

        _fac = HTTPFacilitatorClient(FacilitatorConfig(
            url=FACILITATOR_URL, auth_provider=CreateHeadersAuthProvider(_cdp_create_headers)))
        _srv = x402ResourceServer(_fac)
        register_exact_evm_server(_srv, [X402_NETWORK])

        for route, op_id, name, desc, example_in, schema_in, example_out in PAID_ROUTES:
            path = route.split(" ", 1)[1]
            X402_ROUTES[route] = {
                "accepts": {"scheme": "exact", "payTo": TREASURY_BASE,
                            "price": f"${PRICE_OVERRIDES.get(route, PRICE_USDC)}", "network": X402_NETWORK},
                "resource": f"{SITE}{RESOURCE_OVERRIDES.get(route, '/api' + path)}",
                "service_name": f"XH Agents — {name}",
                "description": desc,
                "mime_type": "application/json",
                "tags": ["x402", "base", "data", op_id],
                "extensions": declare_discovery_extension(
                    input=example_in, input_schema=schema_in, body_type="json",
                    output=OutputConfig(example=example_out)),
            }

        @app.middleware("http")
        async def x402_payment_gate(request: Request, call_next):
            return await payment_middleware(X402_ROUTES, _srv)(request, call_next)

        print(f"[xh-api] standard x402 ON | facilitator={FACILITATOR_URL} | {len(X402_ROUTES)} paid routes "
              f"@ ${PRICE_USDC} -> {TREASURY_BASE}", flush=True)
    except Exception as e:  # a payment-gate problem must never take the API down
        X402_ROUTES = {}
        STANDARD_X402 = False
        print(f"[xh-api] WARNING: standard x402 setup failed ({e}); serving without the gate", flush=True)


# ── models ────────────────────────────────────────────────────────────────────
class AddressReq(BaseModel):
    address: str
    chain_id: int | None = 8453


class GasReq(BaseModel):
    chain_id: int | None = 8453


class TokenReq(BaseModel):
    token: str
    chain_id: int | None = 8453


class CheckReq(BaseModel):
    url: str
    method: str | None = "POST"
    body: dict | None = None


class SentimentReq(BaseModel):
    asset: str | None = None
    protocol: str | None = None


class WhaleReq(BaseModel):
    min_usd: float | None = 100000.0
    blocks: int | None = 300
    token: str | None = "USDC"


class DirectoryReq(BaseModel):
    query: str | None = None
    network: str | None = None
    max_price_usd: float | None = None
    limit: int | None = 10


class VerifyReq(BaseModel):
    model_config = {"populate_by_name": True}

    tx_hash: str
    to: str | None = None
    from_addr: str | None = Field(default=None, alias="from")
    min_amount: float | None = 0.0


class BundleReq(BaseModel):
    topic: str | None = None
    format: str | None = "json"


# ── free ──────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"ok": True, "service": "xh-api", "paid_routes": len(X402_ROUTES), "standard_x402": STANDARD_X402,
            "price_usdc": PRICE_USDC, "bundle_price_usdc": BUNDLE_PRICE_USDC,
            "bundle_items": len(_load_bundle()["items"]) if os.path.exists(BUNDLE_FILE) else 0}


# ── 1. wallet profile ─────────────────────────────────────────────────────────
@app.post("/wallet-profile")
def wallet_profile(req: AddressReq):
    if not _is_address(req.address):
        raise HTTPException(status_code=400, detail="invalid address")
    addr = req.address.lower()
    code = _rpc("eth_getCode", [addr, "latest"])
    is_contract = bool(code and code != "0x")
    balance_wei = _hex_to_int(_rpc("eth_getBalance", [addr, "latest"]))
    nonce = _hex_to_int(_rpc("eth_getTransactionCount", [addr, "latest"]))
    usdc = 0
    try:
        usdc = int(erc20_call(USDC_BASE, "balanceOf", [addr]))
    except Exception:
        pass
    latest = _hex_to_int(_rpc("eth_blockNumber", []))
    # recent USDC activity: logs where this address appears as sender or recipient
    recent: list[dict] = []
    try:
        from_block = hex(max(0, latest - 1200))
        padded = "0x" + addr[2:].rjust(64, "0")
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        for topics in ([transfer_topic, padded], [transfer_topic, None, padded]):
            logs = _rpc("eth_getLogs", [{"fromBlock": from_block, "toBlock": "latest",
                                         "address": USDC_BASE, "topics": topics}]) or []
            for lg in logs[-50:]:
                recent.append({"tx_hash": lg["transactionHash"], "block": _hex_to_int(lg["blockNumber"]),
                               "direction": "out" if topics[1] else "in",
                               "counterparty": "0x" + lg["topics"][2 if topics[1] else 1][-40:],
                               "amount_usdc": round(_hex_to_int(lg.get("data")) / 1e6, 6)})
    except Exception:
        pass
    recent.sort(key=lambda x: x["block"], reverse=True)
    counterparties = {r["counterparty"].lower() for r in recent}
    labels = [LABELS[c] for c in counterparties if c in LABELS]
    return {
        "address": addr,
        "chain_id": req.chain_id or 8453,
        "is_contract": is_contract,
        "code_size_bytes": (len(code) - 2) // 2 if is_contract else 0,
        "nonce": nonce,
        "balance_eth": round(balance_wei / 1e18, 8),
        "balance_usdc": round(usdc / 1e6, 6),
        "latest_block": latest,
        "recent_usdc_activity": {"window_blocks": 1200, "transfers_found": len(recent), "sample": recent[:10]},
        "labels": labels,
        "methodology": {
            "balances": "RPC eth_getBalance + USDC balanceOf",
            "activity": "USDC Transfer logs in the last 1200 Base blocks (~40 minutes), matched as sender or recipient",
            "not_checked": ["historical activity older than the window", "off-chain identity", "portfolio valuation",
                            "known-entity attribution beyond the small built-in label table"],
        },
    }


# ── 2. gas tracker ────────────────────────────────────────────────────────────
@app.post("/gas-tracker")
def gas_tracker(req: GasReq):
    block = _rpc("eth_getBlockByNumber", ["latest", False]) or {}
    base_fee = _hex_to_int(block.get("baseFeePerGas"))
    gas_price = _hex_to_int(_rpc("eth_gasPrice", []))
    try:
        priority = _hex_to_int(_rpc("eth_maxPriorityFeePerGas", []))
    except Exception:
        priority = max(gas_price - base_fee, 0)
    eth_usd = None
    try:
        r = httpx.get("https://api.coingecko.com/api/v3/simple/price",
                      params={"ids": "ethereum", "vs_currencies": "usd"}, timeout=12)
        eth_usd = float(r.json()["ethereum"]["usd"])
    except Exception:
        pass

    def usd(gas_units: int, gwei: float) -> float | None:
        if not eth_usd:
            return None
        return round(gas_units * gwei * 1e-9 * eth_usd, 8)

    tiers = {"low": max(priority * 0.5, 1e6), "medium": max(priority, 1e6), "high": max(priority * 2, 1e6)}
    return {
        "chain": "base",
        "chain_id": 8453,
        "block_number": _hex_to_int(block.get("number")),
        "base_fee_gwei": round(base_fee / 1e9, 9),
        "gas_price_gwei": round(gas_price / 1e9, 9),
        "priority_fee_gwei": {k: round(v / 1e9, 9) for k, v in tiers.items()},
        "max_fee_gwei": {k: round((base_fee * 1.25 + v) / 1e9, 9) for k, v in tiers.items()},
        "eth_price_usd": eth_usd,
        "usd_estimate": {f"transfer_21000_{k}": usd(21000, (base_fee + v) / 1e9) for k, v in tiers.items()}
                        | {f"erc20_transfer_65000_{k}": usd(65000, (base_fee + v) / 1e9) for k, v in tiers.items()},
        "methodology": {"source": "Base RPC baseFeePerGas / eth_gasPrice / eth_maxPriorityFeePerGas",
                        "usd": "converted with the live CoinGecko ETH price; null when that lookup fails",
                        "note": "estimates use 21,000 gas for a plain transfer and 65,000 for an ERC-20 transfer"},
    }


# ── 3. token check ────────────────────────────────────────────────────────────
@app.post("/token-check")
def token_check(req: TokenReq):
    if not _is_address(req.token):
        raise HTTPException(status_code=400, detail="invalid token address")
    token = req.token.lower()
    code = _rpc("eth_getCode", [token, "latest"])
    if not code or code == "0x":
        return {"token": token, "is_contract": False,
                "error": "no contract code at this address on Base",
                "not_checked": ["everything: the address is not a contract"]}
    out: dict[str, Any] = {"token": token, "chain_id": 8453, "is_contract": True,
                           "code_size_bytes": (len(code) - 2) // 2}
    for fn in ("name", "symbol", "decimals", "totalSupply", "owner"):
        try:
            v = erc20_call(token, fn)
            out[fn] = str(v) if fn in ("name", "symbol") else (int(v) if fn != "owner" else str(v))
        except Exception:
            out[fn] = None
    # proxy detection: EIP-1967 implementation slot
    try:
        impl = _rpc("eth_getStorageAt", [token, EIP1967_IMPL_SLOT, "latest"])
        impl_addr = "0x" + (impl or "")[-40:]
        out["is_proxy"] = bool(impl_addr and impl_addr != "0x" + "0" * 40)
        out["implementation"] = impl_addr if out["is_proxy"] else None
    except Exception:
        out["is_proxy"] = None
        out["implementation"] = None
    # free DEX data
    dex = {"pairs": 0, "liquidity_usd": None, "volume_24h_usd": None, "price_usd": None, "oldest_pair_created": None}
    try:
        r = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=15)
        pairs = (r.json() or {}).get("pairs") or []
        base_pairs = [p for p in pairs if str(p.get("chainId")) == "base"]
        if base_pairs:
            best = max(base_pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            dex = {"pairs": len(base_pairs),
                   "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0),
                   "volume_24h_usd": float((best.get("volume") or {}).get("h24") or 0),
                   "price_usd": best.get("priceUsd"),
                   "oldest_pair_created": min((p.get("pairCreatedAt") for p in base_pairs if p.get("pairCreatedAt")),
                                              default=None)}
    except Exception as e:
        dex["error"] = str(e)[:120]
    out["dex"] = dex
    out["not_checked"] = ["honeypot simulation (needs a fork/simulator, not available here)",
                          "holder concentration (needs a token indexer we do not run)",
                          "mint/freeze authority (a Solana concept; not applicable on Base)",
                          "contract source verification (needs an explorer API key)"]
    out["methodology"] = {
        "metadata": "on-chain ERC-20 view calls (name/symbol/decimals/totalSupply/owner)",
        "proxy": "reads the EIP-1967 implementation storage slot",
        "dex": "public DexScreener API, Base pairs only, best pair by liquidity",
        "confidence": "high for metadata and proxy detection; medium for DEX figures (third-party, may lag)",
    }
    return out


# ── 4. x402 conformance checker ───────────────────────────────────────────────
def _check_ssrf(url: str) -> str | None:
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return "unparsable url"
    if p.scheme not in ("http", "https"):
        return "scheme must be http or https"
    host = p.hostname or ""
    if not host:
        return "missing host"
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return f"cannot resolve {host}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return "target resolves to a private/loopback address"
    return None


def _decode_challenge(header_value: str | None, body_text: str) -> tuple[dict | None, str | None]:
    import base64
    if header_value:
        try:
            raw = header_value.strip()
            return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4))), "header"
        except Exception:
            pass
    try:
        d = json.loads(body_text)
        if isinstance(d, dict) and ("accepts" in d or "x402Version" in d):
            return d, "body"
    except Exception:
        pass
    return None, None


@app.post("/x402-check")
def x402_check(req: CheckReq):
    bad = _check_ssrf(req.url)
    if bad:
        raise HTTPException(status_code=400, detail=f"refused: {bad}")
    method = (req.method or "POST").upper()
    started = time.time()
    status, headers, text = None, {}, ""
    try:
        with httpx.Client(follow_redirects=True, max_redirects=3, timeout=20) as c:
            send = {"body": json.dumps(req.body)} if req.body is not None and method in ("POST", "PUT", "PATCH") else None
            r = c.request(method, req.url, content=send["body"] if send else None,
                          headers={"Content-Type": "application/json", "Accept": "*/*"})
            status, headers, text = r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.text[:200000]
    except Exception as e:
        return {"url": req.url, "method": method, "reachable": False, "error": str(e)[:200]}
    challenge, source = _decode_challenge(headers.get("payment-required"), text)
    checks: dict[str, Any] = {}
    acc = (challenge or {}).get("accepts") or []
    a0 = acc[0] if acc else {}
    checks["returns_402"] = status == 402
    checks["challenge_present"] = challenge is not None
    checks["challenge_transport"] = source
    checks["x402_version"] = (challenge or {}).get("x402Version")
    checks["has_accepts"] = bool(acc)
    for f in ("scheme", "network", "asset", "payTo", "maxTimeoutSeconds"):
        checks[f"accepts_has_{f}"] = a0.get(f) is not None
    amount = a0.get("amount") or a0.get("maxAmountRequired")
    checks["amount_is_atomic_units"] = isinstance(amount, str) and amount.isdigit()
    checks["has_resource"] = (challenge or {}).get("resource") is not None
    ext = ((challenge or {}).get("extensions") or {}).get("bazaar") or {}
    checks["has_bazaar_extension"] = bool(ext)
    checks["bazaar_input_method"] = ((ext.get("info") or {}).get("input") or {}).get("method")
    checks["bazaar_output_example"] = bool(((ext.get("info") or {}).get("output") or {}).get("example"))
    required = ["returns_402", "challenge_present", "has_accepts", "accepts_has_scheme", "accepts_has_network",
                "accepts_has_asset", "accepts_has_payTo", "amount_is_atomic_units"]
    failed = [k for k in required if not checks.get(k)]
    return {
        "url": req.url,
        "method": method,
        "reachable": True,
        "status": status,
        "latency_ms": round((time.time() - started) * 1000),
        "conformant": not failed,
        "failed_checks": failed,
        "checks": checks,
        "accepts": [{"scheme": a.get("scheme"), "network": a.get("network"), "asset": a.get("asset"),
                     "amount": a.get("amount") or a.get("maxAmountRequired"), "payTo": a.get("payTo"),
                     "maxTimeoutSeconds": a.get("maxTimeoutSeconds")} for a in acc[:3]],
        "price_usd": (round(int(amount) / 1e6, 6) if isinstance(amount, str) and amount.isdigit() else None),
        "resource": (challenge or {}).get("resource"),
        "methodology": {
            "probe": f"one {method} request with an empty JSON body; the challenge is read from the "
                     "PAYMENT-REQUIRED header (x402 v2) or the JSON body (legacy)",
            "checks": "the same checklist CDP's validator applies, minus the bazaar schema deep-dive",
            "not_checked": ["settlement actually succeeding (this makes no payment)", "uptime over time",
                            "whether the payTo address is honest"],
        },
    }


# ── 5. payment verification ───────────────────────────────────────────────────
@app.post("/payment-verify")
def payment_verify(req: VerifyReq):
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", req.tx_hash or ""):
        raise HTTPException(status_code=400, detail="invalid tx hash")
    to = req.to or TREASURY_BASE
    if not _is_address(to):
        raise HTTPException(status_code=400, detail="invalid recipient")
    min_atomic = int(round(float(req.min_amount or 0) * 1_000_000))
    ok, reason, detail = verify_tx_usdc(tx_hash=req.tx_hash, to_address=to, min_atomic=min_atomic,
                                        from_address=req.from_addr if _is_address(req.from_addr or "") else None,
                                        rpc=RPC_LIST[0])
    return {
        "tx_hash": req.tx_hash,
        "verified": bool(ok),
        "reason": reason,
        "expected": {"to": to.lower(), "min_amount_usdc": req.min_amount or 0,
                     "from": (req.from_addr or "").lower() or None, "token": USDC_BASE},
        "transfer": detail if isinstance(detail, dict) else None,
        "methodology": {
            "how": "reads the transaction receipt and matches the USDC Transfer log (token contract as emitter, "
                   "recipient as the third topic, sender as the second), re-checked locally",
            "not_checked": ["off-chain promises", "payments in other tokens (USDC on Base only)"],
        },
    }


# ── 6. DeFi / asset sentiment ─────────────────────────────────────────────────
@app.post("/defi-sentiment")
def defi_sentiment(req: SentimentReq):
    if not req.asset and not req.protocol:
        raise HTTPException(status_code=400, detail="provide 'asset' (e.g. BTC) and/or 'protocol' (e.g. aerodrome)")
    out: dict[str, Any] = {"methodology": {
        "price": "Binance public klines (spot)",
        "funding": "Binance public premium index for the USDT perpetual",
        "protocol_tvl": "DefiLlama public API",
        "derivation": "score = 0.5*funding_percentile + 0.3*24h price change (normalised) + 0.2*open-interest change; "
                      "labelled only as a summary of those inputs, never as advice",
        "not_checked": ["on-chain flows", "liquidity depth", "news or social sentiment"],
    }}
    score_parts: list[float] = []
    if req.asset:
        sym = req.asset.upper()
        try:
            kl = httpx.get("https://api.binance.com/api/v3/klines",
                           params={"symbol": f"{sym}USDT", "interval": "1h", "limit": 200}, timeout=15).json()
            closes = [float(k[4]) for k in kl]
            last = closes[-1]
            out["asset"] = sym
            out["price_usd"] = last
            out["price_change"] = {"1h_pct": round((last / closes[-2] - 1) * 100, 4),
                                    "24h_pct": round((last / closes[-25] - 1) * 100, 4) if len(closes) > 25 else None,
                                    "7d_pct": round((last / closes[-169] - 1) * 100, 4) if len(closes) > 169 else None}
            ch24 = (last / closes[-25] - 1) if len(closes) > 25 else 0
            score_parts.append(max(-1.0, min(1.0, ch24 * 8)))
        except Exception as e:
            out["asset_error"] = str(e)[:120]
        try:
            prem = httpx.get("https://fapi.binance.com/fapi/v1/premiumIndex",
                             params={"symbol": f"{sym}USDT"}, timeout=15).json()
            fr = float(prem.get("lastFundingRate") or 0)
            out["funding_rate_8h_pct"] = round(fr * 100, 6)
            out["mark_price_usd"] = float(prem.get("markPrice") or 0)
            score_parts.append(max(-1.0, min(1.0, fr * 2000)))
        except Exception as e:
            out["funding_error"] = str(e)[:120]
        try:
            oi = httpx.get("https://fapi.binance.com/fapi/v1/openInterest",
                           params={"symbol": f"{sym}USDT"}, timeout=15).json()
            out["open_interest_contracts"] = float(oi.get("openInterest") or 0)
        except Exception:
            pass
    if req.protocol:
        slug = req.protocol.lower()
        try:
            hist = httpx.get(f"https://api.llama.fi/protocol/{slug}", timeout=25).json()
            tvl = hist.get("tvl") or []
            if tvl:
                cur = float(tvl[-1].get("totalLiquidityUSD") or 0)
                def at(days):
                    return float(tvl[-1 - days].get("totalLiquidityUSD") or 0) if len(tvl) > days else None
                d1, d7 = at(1), at(7)
                out["protocol_tvl"] = {"slug": slug, "tvl_usd": cur,
                                        "change_24h_pct": round((cur / d1 - 1) * 100, 3) if d1 else None,
                                        "change_7d_pct": round((cur / d7 - 1) * 100, 3) if d7 else None,
                                        "chain_breakdown": (hist.get("currentChainTvls") or {})}
                if d1:
                    score_parts.append(max(-1.0, min(1.0, (cur / d1 - 1) * 10)))
            else:
                out["protocol_error"] = "no tvl series returned"
        except Exception as e:
            out["protocol_error"] = str(e)[:120]
    if score_parts:
        score = round(sum(score_parts) / len(score_parts), 4)
        label = ("bullish" if score > 0.5 else "mildly bullish" if score > 0.1 else
                 "bearish" if score < -0.5 else "mildly bearish" if score < -0.1 else "neutral")
        out["score"] = score
        out["sentiment"] = label
        out["score_inputs_used"] = len(score_parts)
    return out


# ── 7. whale watch (large recent transfers) ───────────────────────────────────
TOKEN_MAP = {"usdc": (USDC_BASE, 6, 1.0), "weth": ("0x4200000000000000000000000000000000000006", 18, None)}

@app.post("/whale-watch")
def whale_watch(req: WhaleReq):
    key = (req.token or "USDC").lower()
    if key not in TOKEN_MAP:
        raise HTTPException(status_code=400, detail="token must be USDC or WETH")
    token, decimals, _ = TOKEN_MAP[key]
    blocks = max(20, min(int(req.blocks or 300), 2000))
    threshold = float(req.min_usd or 0)
    eth_usd = None
    if key == "weth":
        try:
            eth_usd = float(httpx.get("https://api.coingecko.com/api/v3/simple/price",
                                      params={"ids": "ethereum", "vs_currencies": "usd"}, timeout=12)
                            .json()["ethereum"]["usd"])
        except Exception:
            eth_usd = None
    latest = _hex_to_int(_rpc("eth_blockNumber", []))
    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    logs = _rpc("eth_getLogs", [{"fromBlock": hex(max(0, latest - blocks)), "toBlock": "latest",
                                 "address": token, "topics": [transfer_topic]}]) or []
    events = []
    for lg in logs:
        amt = _hex_to_int(lg.get("data")) / (10 ** decimals)
        usd = amt if key == "usdc" else (amt * eth_usd if eth_usd else None)
        if usd is None or usd < threshold:
            continue
        events.append({"token": key.upper(), "amount": round(amt, 6), "usd": round(usd, 2),
                       "from": "0x" + lg["topics"][1][-40:], "to": "0x" + lg["topics"][2][-40:],
                       "tx_hash": lg["transactionHash"], "block": _hex_to_int(lg["blockNumber"])})
    events.sort(key=lambda e: e["usd"], reverse=True)
    counterparties = {e["to"] for e in events} | {e["from"] for e in events}
    return {
        "token": key.upper(),
        "blocks_scanned": blocks,
        "block_range": [latest - blocks, latest],
        "threshold_usd": threshold,
        "events_found": len(events),
        "largest": events[:25],
        "labels_seen": [LABELS[c.lower()] for c in counterparties if c.lower() in LABELS],
        "methodology": {
            "how": f"eth_getLogs on the {key.upper()} contract for the Transfer topic across the last {blocks} blocks, "
                   "decoded and filtered by USD threshold",
            "not_checked": ["pending (unconfirmed) transactions — that needs a node with txpool access, which the "
                            "public endpoints do not expose", "cex-internal transfers", "off-chain order flow"],
            "usd_rate": "USDC is treated as 1:1 USD; WETH uses the live CoinGecko ETH price",
        },
    }


# ── 8. x402 directory search ─────────────────────────────────────────────────
@app.post("/x402-directory")
def x402_directory(req: DirectoryReq):
    limit = max(1, min(int(req.limit or 10), 50))
    query = (req.query or "").strip().lower()
    results: dict[str, dict] = {}

    # Coinbase Bazaar (CDP) — authenticated discovery search
    try:
        from cdp.auth import GetAuthHeadersOptions, get_auth_headers
        env = _cdp_credentials()
        path = "/platform/v2/x402/discovery/search"
        h = get_auth_headers(GetAuthHeadersOptions(
            api_key_id=env.get("CDP_API_KEY_ID", ""), api_key_secret=env.get("CDP_API_KEY_PRIVATE_KEY", ""),
            request_method="GET", request_host=CDP_HOST, request_path=path))
        params = {"limit": "50"}
        if query:
            params["query"] = req.query
        if req.network:
            params["network"] = req.network
        r = httpx.get(f"https://{CDP_HOST}{path}", params=params, headers=h, timeout=25)
        for it in (r.json().get("items") or []):
            url = it.get("resource") or it.get("url")
            if not url:
                continue
            acc = (it.get("accepts") or [{}])[0]
            amt = acc.get("amount") or acc.get("maxAmountRequired")
            results[url] = {"url": url, "description": it.get("description"),
                            "price_usd": (int(amt) / 1e6 if str(amt).isdigit() else None),
                            "network": acc.get("network"), "payTo": acc.get("payTo"),
                            "sources": ["coinbase-bazaar"]}
    except Exception as e:
        bazaar_error = str(e)[:150]
    else:
        bazaar_error = None

    # x402-list directory — {"data": [ {slug,name,base_url,min_price_usd,networks,...}, ... ]}
    try:
        r = httpx.get("https://x402-list.com/api/v1/services",
                      params={"q": req.query or "", "limit": 50}, timeout=25)
        payload = r.json()
        data: Any = payload.get("data") if isinstance(payload, dict) else payload
        services = data if isinstance(data, list) else ((data or {}).get("services") or [])
        for svc in services:
            if not isinstance(svc, dict):
                continue
            price = svc.get("min_price_usd")
            if price is None:
                price = (svc.get("assessment") or {}).get("price_usd")
            net = (svc.get("networks") or [None])[0]
            eps = [e for e in (svc.get("endpoints") or []) if isinstance(e, dict)]
            if not eps:
                eps = [{"url": svc.get("base_url")}] if svc.get("base_url") else []
            for ep in eps:
                url = ep.get("url")
                if not url:
                    continue
                existing = results.get(url)
                if existing:
                    if "x402-list" not in existing["sources"]:
                        existing["sources"].append("x402-list")
                    continue
                results[url] = {"url": url,
                                "description": svc.get("description") or svc.get("name"),
                                "price_usd": ep.get("price_usd") if ep.get("price_usd") is not None else price,
                                "network": ep.get("network") or net,
                                "payTo": ep.get("payTo") or ep.get("pay_to"),
                                "sources": ["x402-list"]}
    except Exception as e:
        list_error = str(e)[:150]
    else:
        list_error = None

    items = list(results.values())
    if req.max_price_usd is not None:
        items = [i for i in items if i.get("price_usd") is not None and i["price_usd"] <= req.max_price_usd]
    if query:
        scored = []
        for i in items:
            hay = f"{i['url']} {i.get('description') or ''}".lower()
            hits = sum(1 for w in query.split() if w in hay)
            scored.append((hits, i))
        items = [i for h, i in sorted(scored, key=lambda t: -t[0]) if h > 0] or items
    items.sort(key=lambda i: (i.get("price_usd") is None, i.get("price_usd") or 0))
    return {
        "query": req.query, "network_filter": req.network, "limit": limit,
        "sources": {"coinbase-bazaar": ("ok" if not bazaar_error else f"error: {bazaar_error}"),
                    "x402-list": ("ok" if not list_error else f"error: {list_error}")},
        "results": len(items[:limit]),
        "endpoints": items[:limit],
        "methodology": {
            "how": "queries Coinbase's Bazaar discovery search (authenticated) and the public x402-list API, "
                   "merges by URL, keeps the cheapest first and marks which directory each result came from",
            "not_checked": ["whether a listed endpoint is honest or always up", "settlement history per endpoint"],
        },
    }


# ── 9. playbook bundle (the content lives in a JSON file, not in this code) ───
_bundle_cache: dict[str, Any] = {"mtime": None, "data": None}


def _load_bundle() -> dict:
    """Read the bundle content, reloading only when the file changes on disk."""
    mtime = os.path.getmtime(BUNDLE_FILE)
    if _bundle_cache["data"] is None or _bundle_cache["mtime"] != mtime:
        with open(BUNDLE_FILE, "r", encoding="utf-8") as fh:
            _bundle_cache["data"] = json.load(fh)
        _bundle_cache["mtime"] = mtime
    return _bundle_cache["data"]


def _bundle_markdown(items: list[dict], meta: dict) -> str:
    """Render the selected items as one markdown document (for a caller that wants a file)."""
    out = [f"# {meta['bundle']}",
           f"_{meta['version']} — {meta['vendor']}_", "", meta["summary"], ""]
    for it in items:
        out += [f"## {it['title']}", f"`{it['id']}`", "", f"**Solves:** {it['solves']}", ""]
        if it.get("prerequisites"):
            out += ["**Prerequisites:**"] + [f"- {p}" for p in it["prerequisites"]] + [""]
        out.append("**Steps:**")
        for s in it.get("steps", []):
            out.append(f"{s['n']}. {s['do']}")
            if s.get("cmd"):
                out.append(f"   ```\n   {s['cmd']}\n   ```")
        out.append("")
        if it.get("pitfalls"):
            out += ["**Pitfalls:**"] + [f"- {p}" for p in it["pitfalls"]] + [""]
        if it.get("verify"):
            out += ["**Verify:**"] + [f"- {v}" for v in it["verify"]] + [""]
        if it.get("files"):
            out += ["**Files:** " + ", ".join(it["files"]), ""]
        out += ["---", ""]
    return "\n".join(out)


@app.get("/xh-bundle")
def xh_bundle_preview():
    """Free: what is in the bundle and what it costs. The content itself is behind the gate."""
    b = _load_bundle()
    return {
        "bundle": b["bundle"], "bundle_id": b["bundle_id"], "version": b["version"], "vendor": b["vendor"],
        "summary": b["summary"], "free": True,
        "price_usdc": BUNDLE_PRICE_USDC,
        "how_to_buy": f"POST {SITE}/api/compute/xh-bundle with an x402 payment header "
                      f"(unpaid requests receive a standard 402 challenge quoting ${BUNDLE_PRICE_USDC})",
        "items_total": len(b["items"]),
        "items": [{"id": i["id"], "title": i["title"],
                   "requested_by_owner": i.get("requested_by_owner", False)} for i in b["items"]],
    }


@app.post("/xh-bundle")
def xh_bundle(req: BundleReq):
    """Paid: the playbooks. topic=<id> narrows it; format=markdown adds a single document."""
    b = _load_bundle()
    all_items = b["items"]
    topic = (req.topic or "").strip()
    items = all_items
    topic_found: bool | None = None
    note: str | None = None
    if topic:
        topic_found = any(i["id"] == topic for i in all_items)
        if topic_found:
            items = [i for i in all_items if i["id"] == topic]
        else:
            # never return an error after the buyer paid: send everything and say so
            note = (f"topic '{topic}' is not in this bundle, so the full set was returned. "
                    f"Valid ids are in items[].id.")
            topic_found = False
    out: dict[str, Any] = {
        "bundle": b["bundle"], "bundle_id": b["bundle_id"], "version": b["version"], "vendor": b["vendor"],
        "summary": b["summary"], "generated": b.get("generated"),
        "items_total": len(all_items), "items_returned": len(items),
        "requested_topic": topic or None, "topic_found": topic_found, "note": note,
        "licence": "Single-caller licence: use these playbooks in your own project; do not resell this document set.",
        "delivery": b.get("delivery"),
        "items": items,
        "methodology": {
            "what_this_is": "a curated set of production playbooks from running paid x402 endpoints in USDC on Base, "
                            "written from the incidents that actually happened",
            "how_to_use": "each item lists the mechanism, the commands, the pitfalls and how to verify the result; "
                          "pitfalls are documented failures, not opinions",
            "not_included": ["credentials, tokens or private keys", "guarantees about third-party APIs",
                             "any promise of revenue"],
            "freshness": "dated where a finding can rot (RPC capabilities, directory payload shapes) — re-probe before trusting",
        },
    }
    if (req.format or "json").lower() == "markdown":
        out["markdown"] = _bundle_markdown(items, b)
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
