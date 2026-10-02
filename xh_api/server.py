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
import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sqlite3
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, "/home/ubuntu/prpo_ai")
from xh_verify import verify_tx_usdc  # noqa: E402

# ── config ────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("XH_API_PORT", "8991"))
PRICE_USDC = float(os.environ.get("XH_API_PRICE", "0.1"))
# the bundle is a knowledge product, not a data call: priced per route ($2 vs $0.10)
BUNDLE_PRICE_USDC = float(os.environ.get("XH_BUNDLE_PRICE_USDC", "0.91"))
PRICE_OVERRIDES: dict[str, float] = {"POST /xh-bundle": BUNDLE_PRICE_USDC}
# Demand-priced routes (2026-09-30). Search + retrieval is the high-effort call (one search plus
# N page fetches and text extraction), so it carries the higher price; enrichment and social are
# single-lookup calls and are priced cheap to win volume.
DEMAND_PRICES = {"POST /web-search": 0.25, "POST /company-enrich": 0.05, "POST /social-data": 0.05}
PRICE_OVERRIDES.update(DEMAND_PRICES)
# a route can be served under a longer public path (nginx prefix) — the challenge must quote the
# URL a buyer can actually reach, not the internal one
RESOURCE_OVERRIDES: dict[str, str] = {"POST /xh-bundle": "/api/compute/xh-bundle"}
# ── daily drop (2026-10-02): a dated product that agents must re-buy every day ──
DAILY_DIR = os.environ.get("XH_DAILY_DIR", "/home/ubuntu/prpo_ai/xh_api/daily")
DAILY_FILE = os.path.join(DAILY_DIR, "daily_drop.json")
DAILY_PRICE = float(os.environ.get("XH_DAILY_PRICE_USDC", "0.03"))
PRICE_OVERRIDES["POST /daily-drop"] = DAILY_PRICE
# ── video licences (2026-10-02): the four Ataraxia masters, licensed to agents per film ──
# Priced like a single viewer pays on the site ($0.10), so the human and machine doors charge the
# same. The buyer gets a time-limited signed URL instead of a cookie session.
VIDEO_PRICE = float(os.environ.get("XH_VIDEO_PRICE_USDC", "0.1"))
PRICE_OVERRIDES["POST /video-license"] = VIDEO_PRICE
RESOURCE_OVERRIDES["POST /video-license"] = "/api/video-license"
MEDIA_DIR = os.environ.get("ATARAXIA_MEDIA_DIR", "/home/ubuntu/ataraxia-media")
ATARAXIA_CATALOG_URL = os.environ.get("ATARAXIA_CATALOG_URL", "http://127.0.0.1:3110/api/agent-catalog")
LICENSE_KEY_FILE = os.environ.get("ATARAXIA_MEDIA_HMAC_FILE", "/home/ubuntu/prpo_ai/keys/ataraxia_media_hmac.key")
LICENSE_TTL_S = int(os.environ.get("XH_VIDEO_LICENSE_TTL_S", "3600"))
# ── request log: every 402/200 is recorded so revenue per endpoint is measurable ──
LOG_DB = os.environ.get("XH_API_LOG_DB", "/home/ubuntu/prpo_ai/xh_api/logs/xh_api.db")
BUNDLE_FILE = os.environ.get("XH_BUNDLE_FILE", "/home/ubuntu/prpo_ai/xh_api/bundles/xh_bundle.json")
# how-to SOPs: one JSON file per SOP, each becomes its own paid route (GET and POST)
HOWTO_DIR = os.environ.get("XH_HOWTO_DIR", "/home/ubuntu/prpo_ai/xh_api/howto")
TREASURY_BASE = os.environ.get("XH_TREASURY_BASE", "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0")
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_NETWORK = "eip155:8453"
SITE = "https://xhagents.xyz"
FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
CDP_HOST, CDP_BASE_PATH = "api.cdp.coinbase.com", "/platform/v2/x402"
CDP_ENV_FILE = "/home/ubuntu/prpo_ai/cdp/.env.cdp"

# A dedicated RPC (e.g. Alchemy) goes first for cheap calls when XH_BASE_RPC is set; the public
# endpoints stay as fallbacks. Dropped after measuring them on 2026-09-26: base.llamarpc.com
# (Cloudflare 525, returns non-JSON), base.blockpi.network (same), base.meowrpc.com (no
# eth_getLogs), base.drpc.org (>10k block cap), 1rpc.io/base (eth_getLogs capped at 50 blocks).
#
# eth_getLogs is ordered the other way round on purpose: Alchemy's Free tier answers
# "Under the Free tier plan, you can make eth_getLogs requests with up to a 10 block range"
# (measured 2026-09-27), while whale-watch scans 200 blocks and a settlement scan 800. So wide
# log queries go to the public endpoints first and the dedicated RPC is the last resort.
_PUBLIC_RPC = ["https://base-rpc.publicnode.com", "https://mainnet.base.org"]
_DEDICATED_RPC = os.environ.get("XH_BASE_RPC", "").strip()
RPC_LIST = ([_DEDICATED_RPC] if _DEDICATED_RPC else []) + _PUBLIC_RPC
LOG_RPC_LIST = _PUBLIC_RPC + ([_DEDICATED_RPC] if _DEDICATED_RPC else [])
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

# ── arkham-intel (2026-10-02): the five Arkham use-case endpoints, computed on public Base data ──
# Handlers live in arkham_intel.py; the RPC helpers are injected so the module stays import-safe.
import arkham_intel  # noqa: E402

arkham_intel.register(app, arkham_intel.Ctx(
    rpc=_rpc, erc20=erc20_call, is_address=_is_address, hex_to_int=_hex_to_int))

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
    # ── demand-priced trio (2026-09-30): search/retrieval, enrichment, social ──
    ("POST /web-search", "webSearch", "Web search + page retrieval",
     "Runs a live web search and returns ranked results with title, URL, domain and snippet, then fetches the top pages and returns their extracted readable text — content retrieval, not just links.",
     {"query": "x402 paid API on Base", "max_results": 5, "fetch_pages": 3},
     {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"},
                                       "fetch_pages": {"type": "integer"}, "extract_chars": {"type": "integer"}},
      "required": ["query"]},
     {"query": "x402 paid API on Base", "results_returned": 5, "pages_retrieved": 3,
      "results": [{"rank": 1, "title": "Quickstart for Sellers - x402",
                   "url": "https://docs.x402.org/getting-started/quickstart-for-seller",
                   "domain": "docs.x402.org", "snippet": "...",
                   "retrieval": {"status": 200, "chars_total": 8123, "content": "..."}}]}),
    ("POST /company-enrich", "companyEnrich", "People & company enrichment",
     "Enriches a company, domain or person from public structured sources (Wikidata, the public LinkedIn company page, Clearbit autocomplete): industry, size, headquarters, founding year, official website, stock listing and social handles.",
     {"company": "Coinbase"},
     {"type": "object", "properties": {"company": {"type": "string"}, "domain": {"type": "string"},
                                       "person": {"type": "string"}}, "required": []},
     {"query": "Coinbase", "resolved": {"wikidata_id": "Q16972754",
                                        "description": "American company that operates a cryptocurrency exchange platform"},
      "company": {"website": "https://www.coinbase.com", "industry": "Financial Services",
                  "company_size": "1,001-5,000 employees", "headquarters": "Remote First",
                  "type": "Public Company", "linkedin_followers": 1489428, "stock_exchange": "NASDAQ"},
      "sources": ["wikidata", "linkedin-public", "clearbit-autocomplete"]}),
    ("POST /social-data", "socialData", "Social media data (X/Twitter + LinkedIn)",
     "Pulls one X/Twitter post by URL or id (text, author, metrics, language) and/or a public LinkedIn company page (industry, size, headquarters, specialties, followers) as structured JSON.",
     {"x_tweet": "https://x.com/jack/status/20"},
     {"type": "object", "properties": {"x_tweet": {"type": "string"}, "x_username": {"type": "string"},
                                       "linkedin": {"type": "string"}}, "required": []},
     {"x_tweet": {"id": "20", "text": "just setting up my twttr", "lang": "en",
                  "author": {"screen_name": "jack", "name": "jack"}, "metrics": {"likes": 308968},
                  "created_at": "2006-03-21T20:50:14.000Z"},
      "linkedin": {"name": "Coinbase", "followers": 1489428, "industry": "Financial Services",
                   "company_size": "1,001-5,000 employees", "headquarters": "Remote First"}}),
]

# ── daily drop (2026-10-02): the date is the product, so agents re-buy every day ──
PAID_ROUTES.append((
    "POST /daily-drop", "dailyDrop", "XH Agents Daily Drop",
    "A dated, freshly rebuilt brief on where demand is in the agent-payment economy: what builders and agents are discussing and paying for in the last 30 days (Hacker News, GitHub, Polymarket, marketplace listings), plus our own paid-endpoint call and settlement performance. Rebuilt every day at 06:00 WIB; yesterday's copy is not the product.",
    {"topic": "x402", "window_days": 30},
    {"type": "object", "properties": {"topic": {"type": "string"}, "window_days": {"type": "integer"}},
     "required": []},
    {"date": "2026-10-02", "headline": "x402 pricing talk is up, agent-payment listings keep growing",
     "counts": {"signals": 12, "sources_ok": 4, "our_paid_calls_24h": 3},
     "signals": [{"kind": "hackernews", "title": "...", "score": 42, "url": "https://..."}],
     "market": {"payapi_apis": 239, "verified": 215},
     "our_endpoints": {"paid_routes": 19, "calls_24h": 3, "revenue_usd_24h": 0.09},
     "methodology": {"sources": ["hackernews", "github", "polymarket", "payapi-market"],
                     "not_checked": ["paid buyer traffic you cannot see from the provider side"]}}),
)

# GET is served too: directory crawlers probe GET/HEAD before POST, and a 405 reads as "broken"
# to a validator. Same product, same price, one resource URL.
_dd = PAID_ROUTES[-1]
PAID_ROUTES.append((_dd[0].replace("POST /", "GET /", 1), _dd[1] + "Get", _dd[2] + " (GET)",
                    _dd[3], _dd[4], _dd[5], _dd[6]))
PRICE_OVERRIDES["GET /daily-drop"] = DAILY_PRICE

# ── video licence (2026-10-02): the Ataraxia masters licensed to machine buyers ──
PAID_ROUTES.append((
    "POST /video-license", "videoLicense", "XH Animations video licence (Ataraxia)",
    "Licence one of the four XH Animations masters: 109 seconds of 21x-extended looping ambient footage, "
    "delivered as a time-limited signed URL with HTTP Range support so an agent can stream or fetch exactly "
    "the bytes it needs. Pick a video_id from the free menu at GET /api/video-license; the response carries "
    "bytes and sha256 so the download can be verified. Same price a human viewer pays on the site ($0.10), "
    "settled in USDC on Base, and 25% of what the room takes in is credited back to the wallets that paid.",
    {"video_id": "helixhdna"},
    {"type": "object", "properties": {
        "video_id": {"type": "string", "description": "One of the ids from GET /api/video-license."}},
     "required": ["video_id"]},
    {"video_id": "helixhdna", "title": "HeliXHDNA", "duration_sec": 109.3, "bytes": 5760999,
     "sha256": "…", "expires_at": "2026-10-02T20:31:00Z",
     "stream_url": "https://xhagents.xyz/api/video-stream/<token>",
     "licence": {"scope": "stream or download", "ttl_seconds": 3600, "range_requests": True}},
))
# ── arkham-intel (2026-10-02): five intel products answering Arkham's published API use cases ──
# Same honesty rules as the rest of the catalogue: we are not Arkham and hold no Arkham key; every
# response states its sources and what was NOT checked. Entity names come only from a curated label
# file; otherwise addresses are reported with an on-chain verified interface class.
_ARKHAM_PRICE = float(os.environ.get("XH_ARKHAM_PRICE_USDC", "0.1"))
_ARKHAM = [
    ("use-cases", "arkhamIntelUseCases", "Arkham-style intel — use-case router",
     "Given a role (traders, builders, brokers, investigators) or a task in plain words, returns the ordered "
     "call plan across the XH Arkham-intel endpoints, mapped to the use cases Arkham published (inflow/outflow "
     "monitoring, portfolio monitoring, counterparty due diligence, know-your-users, competitor analysis, AML, "
     "ransomware, darknet). Says explicitly what we cannot answer.",
     {"role": "traders", "task": "are coins piling into an exchange or draining out?"},
     {"type": "object", "properties": {"role": {"type": "string"},
                                       "task": {"type": "string"}}, "required": []},
     {"playbooks": [{"goal": "Are coins piling into an exchange or draining out?",
                     "arkham_use_case": "Inflow & Outflow Monitoring",
                     "plan": ["POST /api/arkham-intel/exchange-flow", "POST /api/arkham-intel/counterparties"]}],
      "not_checked": ["we do not call Arkham's API", "no Arkham entity graph"]}),
    ("exchange-flow", "arkhamIntelExchangeFlow", "Arkham-style intel — pool inflow/outflow",
     "Inflow/outflow for an ERC-20 token on Base over a window, measured where it is actually verifiable: "
     "each of the token's deepest pools has its own balance of that token read at two blocks, so the change, "
     "direction (into pool = sell side, out of pool = bought) and USD value are real numbers, plus the pool's "
     "price move from slot0 where the pool exposes it. Pools that cannot be read are listed with the reason.",
     {"token": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "hours": 6},
     {"type": "object", "properties": {"token": {"type": "string"},
                                       "hours": {"type": "integer", "minimum": 1, "maximum": 24}},
      "required": ["token"]},
     {"token": "0x8335…2913", "pool_totals": {"into_pools": 1200.5, "out_of_pools": 800.25, "net": 400.25},
      "pools": [{"pair": "0x…", "dex": "aerodrome", "reserve_then": 91000.0, "reserve_now": 89800.0,
                 "token_change": -1200.0, "direction": "out_of_pool (bought)", "usd_change": 1200.0}],
      "price": {"price_usd": 1.0, "method": "derived_from_quote_side"}}),
    ("portfolio", "arkhamIntelPortfolio", "Arkham-style intel — wallet portfolio snapshot",
     "Holdings of a Base wallet with USD values at request time (native + the ERC-20s you name), each token's "
     "verified class, and the totals. A snapshot, not a historical curve — that limit is stated in the response.",
     {"address": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0",
      "tokens": ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"], "hours": 6},
     {"type": "object", "properties": {"address": {"type": "string"},
                                       "tokens": {"type": "array", "items": {"type": "string"}},
                                       "hours": {"type": "integer"}}, "required": ["address"]},
     {"address": "0x6cb5…3ed0", "native": {"eth": 0.0, "value_usd": 0.0},
      "holdings": [{"token": "0x8335…2913", "amount": 12.5, "price_usd": 1.0, "value_usd": 12.5}],
      "total_value_usd": 12.5, "not_checked": ["other chains", "staked positions", "historical curve"]}),
    ("counterparties", "arkhamIntelCounterparties", "Arkham-style intel — counterparty due diligence",
     "Who an address transacts with inside a window: counterparties ranked by USD volume and transfer count, each "
     "with an on-chain verified class, first/last seen, and a flag only if the operator's curated label file marks "
     "it. An empty flag list means 'nothing curated', never 'clean'.",
     {"address": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0", "hours": 24, "limit": 15},
     {"type": "object", "properties": {"address": {"type": "string"}, "hours": {"type": "integer"},
                                       "limit": {"type": "integer"}}, "required": ["address"]},
     {"counterparties": [{"address": "0x…", "class": "eoa", "in": 40.0, "out": 0.0, "usd_volume": 40.0,
                          "flag": False, "first_seen": "2026-10-02T10:00:00Z"}],
      "labels_configured": 3}),
    ("trace", "arkhamIntelTrace", "Arkham-style intel — fund trace for investigations",
     "Hop-by-hop follow of USDC outflows from an address (up to 3 hops), with each destination's verified class, "
     "curated labels and any flagged venues on the path. Answers 'where did the money go' with evidence and an "
     "explicit boundary: it is not an attribution or sanctions product.",
     {"address": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0", "hops": 2, "hours": 24},
     {"type": "object", "properties": {"address": {"type": "string"}, "hops": {"type": "integer", "minimum": 1, "maximum": 3},
                                       "hours": {"type": "integer"}}, "required": ["address"]},
     {"origin": "0x6cb5…3ed0", "hops": [{"hop": 1, "transfers": [{"to": "0x…", "class": "dex_router", "usd": 40.0}]}],
      "flags": [], "not_checked": ["tokens other than USDC", "off-chain identity"]}),
]
for _slug, _op, _name, _desc, _ex_in, _schema, _ex_out in _ARKHAM:
    _route = f"POST /arkham-intel/{_slug}"
    PRICE_OVERRIDES[_route] = _ARKHAM_PRICE
    RESOURCE_OVERRIDES[_route] = f"/api/arkham-intel/{_slug}"
    PAID_ROUTES.append((_route, _op, _name, _desc, _ex_in, _schema, _ex_out))
    # GET twin: directory crawlers probe GET first, and a 405 reads as "broken" to a validator
    _groute = f"GET /arkham-intel/{_slug}"
    PRICE_OVERRIDES[_groute] = _ARKHAM_PRICE
    RESOURCE_OVERRIDES[_groute] = f"/api/arkham-intel/{_slug}"
    PAID_ROUTES.append((_groute, _op + "Get", _name + " (GET)", _desc, _ex_in, _schema, _ex_out))

STANDARD_X402 = os.environ.get("X402_STANDARD", "1") != "0"

# ── how-to SOPs: one file per SOP becomes its own paid route on both GET and POST ─────────────
def _load_sops() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        for name in sorted(os.listdir(HOWTO_DIR)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(HOWTO_DIR, name), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            if doc.get("slug"):
                out[doc["slug"]] = doc
    except OSError as e:
        print(f"[xh-api] WARNING: cannot read the how-to directory ({e})", flush=True)
    return out


SOPS = _load_sops()

for _slug, _sop in SOPS.items():
    _price = float(_sop.get("price_usdc", PRICE_USDC))
    _search = f"{_sop.get('title', '')}. {_sop.get('summary', '')}"[:900]
    for _method in ("GET", "POST"):
        _route = f"{_method} /howto/{_slug}"
        PRICE_OVERRIDES[_route] = _price
        RESOURCE_OVERRIDES[_route] = f"/api/howto/{_slug}"
        PAID_ROUTES.append((
            _route, f"howto:{_slug}", f"How-To: {_sop.get('title', _slug)}",
            _search,
            {"sop": _slug},
            {"type": "object", "properties": {"sop": {"type": "string"}}, "required": []},
            {"sop": _slug, "title": _sop.get("title"), "steps": len(_sop.get("steps") or []),
             "summary": (_sop.get("summary") or "")[:200]},
        ))
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


# ── request log middleware (2026-10-02) ──────────────────────────────────────
# Without this we cannot answer "which endpoint actually earns". One row per request:
# timestamp, route, status, whether it was paid, price, latency and a thin client fingerprint.
def _log_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(LOG_DB), exist_ok=True)
    con = sqlite3.connect(LOG_DB, timeout=5)
    con.execute(
        "CREATE TABLE IF NOT EXISTS requests ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, day TEXT NOT NULL,"
        " method TEXT, path TEXT, status INTEGER, paid INTEGER, price_usdc REAL,"
        " route TEXT, latency_ms REAL, ua TEXT, referer TEXT, ip TEXT, country TEXT)"
    )
    con.execute("CREATE INDEX IF NOT EXISTS requests_day ON requests(day)")
    con.execute("CREATE INDEX IF NOT EXISTS requests_route ON requests(route, status)")
    return con


@app.middleware("http")
async def xh_request_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    try:
        path = request.url.path
        route = None
        price = None
        for r, cfg in X402_ROUTES.items():
            _m, _p = r.split(" ", 1)
            if _p == path:
                route = r
                try:
                    price = float(str(cfg["accepts"]["price"]).lstrip("$"))
                except Exception:
                    price = None
                break
        now = datetime.now(timezone.utc)
        con = _log_conn()
        with con:
            con.execute(
                "INSERT INTO requests (ts, day, method, path, status, paid, price_usdc, route,"
                " latency_ms, ua, referer, ip, country) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now.isoformat(timespec="seconds"), now.strftime("%Y-%m-%d"),
                 request.method, path, response.status_code,
                 1 if (response.status_code == 200 and route) else 0,
                 price, route, round((time.perf_counter() - start) * 1000, 1),
                 (request.headers.get("user-agent") or "")[:300],
                 (request.headers.get("referer") or "")[:300],
                 (request.headers.get("cf-connecting-ip")
                  or (request.client.host if request.client else "") or "")[:64],
                 (request.headers.get("cf-ipcountry") or "")[:8]),
            )
        con.close()
    except Exception as e:  # logging must never break an answer
        print(f"[xh-api] log middleware warning: {e}", flush=True)
    return response


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


# ── daily drop (2026-10-02) ──────────────────────────────────────────────────
class DailyReq(BaseModel):
    topic: str | None = None
    window_days: int | None = 30


def _load_daily() -> dict | None:
    try:
        with open(DAILY_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


@app.get("/daily-drop/preview")
def daily_drop_preview():
    """Free: today's headline and counts. The brief itself is behind the gate."""
    doc = _load_daily() or {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "product": "XH Agents Daily Drop", "free": True, "price_usdc": DAILY_PRICE,
        "date": doc.get("date") or today,
        "fresh": bool(doc.get("date") == today),
        "headline": doc.get("headline"),
        "counts": doc.get("counts") or {},
        "sources_ok": doc.get("sources_ok") or [],
        "how_to_buy": (f"POST {SITE}/api/daily-drop with an x402 payment header "
                       f"(unpaid requests receive a standard 402 challenge quoting ${DAILY_PRICE})"),
        "why_daily": "Dated and rebuilt every day: yesterday's copy is not today's product.",
    }


@app.post("/daily-drop")
def daily_drop(req: DailyReq):
    """Paid: today's demand brief plus our own endpoint performance."""
    doc = _load_daily()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not doc:
        return {"date": today, "published": False, "requested_topic": req.topic,
                "note": "no brief published yet (the generator runs at 06:00 WIB / 23:00Z)",
                "price_usdc": DAILY_PRICE}
    out: dict[str, Any] = dict(doc)
    out["requested_topic"] = req.topic
    if req.topic:
        want = req.topic.strip().lower()
        hits = [s for s in (doc.get("signals") or []) if want in json.dumps(s).lower()]
        if hits:
            out["signals"] = hits
            out["filtered_by"] = req.topic
        else:
            out["filtered_by"] = None
            out["filter_note"] = f"no signal matched '{req.topic}'; the full brief is returned"
    return out


# ── free ──────────────────────────────────────────────────────────────────────
@app.get("/daily-drop")
def daily_drop_get(topic: str | None = None):
    """Paid (same product as the POST route; GET exists because crawlers probe GET first)."""
    return daily_drop(DailyReq(topic=topic))


# ── video licence + signed stream (2026-10-02) ────────────────────────────────
# The menu is free so an agent can pick a film before paying; the licence itself is behind the x402
# gate on POST. A licence is a signed token, not a cookie: the buyer streams with it until it expires.
_video_cache: dict[str, Any] = {"at": 0.0, "data": None}


def _video_catalog() -> dict | None:
    """The Ataraxia catalogue, read from the local service and cached for 60 s."""
    now = time.time()
    cached = _video_cache["data"]
    if cached is not None and now - float(_video_cache["at"]) < 60:
        return cached
    try:
        r = httpx.get(ATARAXIA_CATALOG_URL, timeout=8.0)
        r.raise_for_status()
        data = r.json()
        _video_cache.update({"at": now, "data": data})
        return data
    except Exception as e:  # a catalogue outage must not take the licence route down
        print(f"[xh-api] video catalogue unavailable: {e}", flush=True)
        return cached


def _video_item(video_id: str) -> dict | None:
    data = _video_catalog() or {}
    want = str(video_id or "").strip().lower()
    for item in data.get("items") or []:
        if str(item.get("id", "")).lower() == want:
            return item
    return None


def _license_key() -> bytes:
    """HMAC key for stream tokens — created on first use, mode 600, never printed."""
    try:
        with open(LICENSE_KEY_FILE, "rb") as fh:
            key = fh.read().strip()
        if key:
            return key
    except FileNotFoundError:
        pass
    key = os.urandom(32).hex().encode()
    os.makedirs(os.path.dirname(LICENSE_KEY_FILE), exist_ok=True)
    with open(LICENSE_KEY_FILE, "wb") as fh:
        fh.write(key)
    os.chmod(LICENSE_KEY_FILE, 0o600)
    print(f"[xh-api] created licence signing key at {LICENSE_KEY_FILE}", flush=True)
    return key


def _mint_license(video_id: str, ttl_s: int) -> tuple[str, int]:
    exp = int(time.time()) + ttl_s
    payload = base64.urlsafe_b64encode(
        json.dumps({"v": video_id, "e": exp}, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_license_key(), payload.encode(), hashlib.sha256).hexdigest()[:43]
    return f"{payload}.{sig}", exp


def _read_license(token: str) -> dict | None:
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expect = hmac.new(_license_key(), payload.encode(), hashlib.sha256).hexdigest()[:43]
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return None
    if int(claims.get("e", 0)) <= int(time.time()):
        return None
    return claims


@app.get("/video-license")
def video_license_menu():
    """Free: what can be licensed, at what price, and how the gate works."""
    data = _video_catalog() or {}
    films = [{k: it.get(k) for k in ("id", "title", "subtitle", "durationSec", "bytes", "sha256")}
             for it in data.get("items") or []]
    if not films:
        return JSONResponse({"error": "catalogue_unavailable",
                             "message": "the Ataraxia catalogue could not be read; try again shortly"},
                            status_code=503)
    return {
        "provider": data.get("provider", "XH Agents — Ataraxia"),
        "site": data.get("site", "https://ataraxia.xhagents.xyz"),
        "films": films,
        "price_usdc": VIDEO_PRICE,
        "price_atomic": str(int(round(VIDEO_PRICE * 1_000_000))),
        "pay_to": TREASURY_BASE,
        "network": X402_NETWORK,
        "asset": USDC_BASE,
        "how": (f'POST this path with {{"video_id":"<id>"}}. x402 settles the price in USDC on Base, then the '
                f'200 body carries a signed stream_url valid for {LICENSE_TTL_S // 60} minutes. HTTP Range is '
                f'supported, so an agent can pull only the seconds it needs.'),
        "license_note": ("A licence covers streaming and download for its lifetime. The films are looping ambient "
                         "footage — usable as background in your own video, ads or products. Resale of the master "
                         "as-is is not licensed."),
    }


class VideoLicenseReq(BaseModel):
    video_id: str = Field(..., description="One of the ids from GET /api/video-license")


@app.post("/video-license")
def video_license(req: VideoLicenseReq):
    item = _video_item(req.video_id)
    if not item:
        data = _video_catalog() or {}
        return JSONResponse({
            "error": "unknown_video", "video_id": req.video_id,
            "available": [it.get("id") for it in data.get("items") or []],
            "menu": "https://xhagents.xyz/api/video-license",
        }, status_code=404)
    token, exp = _mint_license(str(item["id"]), LICENSE_TTL_S)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    print(f"[xh-api] video licence {item['id']} exp={expires_at}", flush=True)
    return {
        "video_id": item.get("id"),
        "title": item.get("title"),
        "subtitle": item.get("subtitle"),
        "duration_sec": item.get("durationSec"),
        "bytes": item.get("bytes"),
        "sha256": item.get("sha256"),
        "expires_at": expires_at,
        "ttl_seconds": LICENSE_TTL_S,
        "stream_url": f"{SITE}/api/video-stream/{token}",
        "range_requests": True,
        "license": {
            "scope": "stream or download until expires_at",
            "proof": "this URL is signed; keep it until it expires",
            "not_licensed": "reselling the master file as-is",
        },
        "methodology": {
            "source": "Ataraxia catalogue served by the XH Agents media service",
            "not_checked": ["that the buyer's use respects their own local law or platform terms"],
        },
    }


@app.get("/video-stream/{token}")
def video_stream(token: str, request: Request):
    """Serve a licensed master. The signed token is the only credential, and it expires."""
    claims = _read_license(token)
    if not claims:
        return JSONResponse({"error": "invalid_or_expired_license",
                             "message": "mint a fresh licence at POST /api/video-license"}, status_code=401)
    item = _video_item(str(claims.get("v")))
    if not item:
        return JSONResponse({"error": "unknown_video", "video_id": claims.get("v")}, status_code=404)
    path = os.path.join(MEDIA_DIR, str(item.get("file", "")))
    if not os.path.isfile(path):
        return JSONResponse({"error": "media_missing", "video_id": item.get("id")}, status_code=500)

    size = os.path.getsize(path)
    start, end, status = 0, size - 1, 200
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300",
        "Content-Disposition": f'inline; filename="{item.get("id")}.mp4"',
        "X-License-Expires": str(claims.get("e")),
    }
    rng = request.headers.get("range")
    if rng and rng.startswith("bytes="):
        spec = rng.split("=", 1)[1].split(",")[0].strip()
        first, _, last = spec.partition("-")
        try:
            if first:
                start = int(first)
                end = int(last) if last else size - 1
            else:                      # suffix form: bytes=-N
                start = max(0, size - int(last))
                end = size - 1
        except ValueError:
            return JSONResponse({"error": "bad_range", "range": rng}, status_code=416,
                                headers={"Content-Range": f"bytes */{size}"})
        if start >= size or start > end:
            return JSONResponse({"error": "range_not_satisfiable", "size": size}, status_code=416,
                                headers={"Content-Range": f"bytes */{size}"})
        end = min(end, size - 1)
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)

    def body(chunk: int = 65536):
        remaining = end - start + 1
        with open(path, "rb") as fh:
            fh.seek(start)
            while remaining > 0:
                data = fh.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(body(), status_code=status, headers=headers)


# the signing key must exist from boot, so a restart never looks like a broken licence
_license_key()


@app.get("/health")
async def health():
    return {"ok": True, "service": "xh-api", "paid_routes": len(X402_ROUTES), "standard_x402": STANDARD_X402,
            "price_usdc": PRICE_USDC, "bundle_price_usdc": BUNDLE_PRICE_USDC,
            "bundle_items": len(_load_bundle()["items"]) if os.path.exists(BUNDLE_FILE) else 0,
            "howto_sops": len(SOPS), "howto": {s: d.get("price_usdc") for s, d in SOPS.items()}}


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


# ── 10. how-to SOPs (content in HOWTO_DIR, one JSON file per SOP) ──────────────
@app.get("/howto")
def howto_index():
    """Free: every SOP on offer with its price. The SOP content itself is behind the gate."""
    return {
        "service": "XH Agents How-To",
        "summary": "Production SOPs from a company that runs its own paid APIs, automation and infrastructure. "
                   "Each one lists the exact commands, the pitfalls that cost us real time or real money, and how "
                   "to verify the result — written from the incidents, not from theory.",
        "free": True,
        "sops_total": len(SOPS),
        "sops": [{"slug": s, "title": d.get("title"), "price_usdc": d.get("price_usdc"),
                  "summary": d.get("summary"), "steps": len(d.get("steps") or []),
                  "pitfalls": len(d.get("pitfalls") or []), "tags": d.get("tags") or [],
                  "last_verified": d.get("last_verified")} for s, d in sorted(SOPS.items())],
        "how_to_buy": f"GET or POST {SITE}/api/howto/<slug> with an x402 payment header; an unpaid request "
                      f"receives a standard 402 challenge quoting that SOP's price",
        "all_in_option": {"bundle": "POST " + SITE + "/api/compute/xh-bundle",
                          "note": "the bundle contains 13 playbooks (including x402 registration and endpoint "
                                  "building) for a single call — check both prices before buying"},
    }


def _howto_payload(slug: str) -> dict:
    sop = SOPS.get(slug)
    if not sop:
        # never a 4xx after the payment was verified: answer 200 with the index instead
        return {"error": "unknown_sop", "requested": slug, "available": sorted(SOPS.keys()),
                "note": "the requested slug does not exist; the list of valid slugs is in 'available'"}
    out = dict(sop)
    out["licence"] = "Single-caller licence: use this SOP in your own project; do not resell the document."
    out["delivery"] = {
        "methods": ["GET", "POST"], "url": f"{SITE}/api/howto/{slug}",
        "price_usdc": sop.get("price_usdc"),
        "field_guide": "steps[] carries the commands; pitfalls[] are documented failures; verify[] is how to "
                       "prove the result; files[] lists what the SOP touches",
    }
    out["methodology"] = {
        "written_from": "the incidents that actually happened while running this in production",
        "not_included": ["credentials, tokens or private keys", "guarantees about third-party APIs or quotas"],
        "freshness": sop.get("last_verified"),
    }
    return out


@app.get("/howto/{slug}")
def howto_get(slug: str):
    return _howto_payload(slug)


@app.post("/howto/{slug}")
def howto_post(slug: str):
    return _howto_payload(slug)


# ══ demand endpoints (2026-09-30) ═════════════════════════════════════════════
# Three routes Boss prioritised by real demand: web search + content retrieval ($0.25),
# people/company enrichment ($0.05) and social data on X + LinkedIn ($0.05). Every source is
# public and key-less; every handler states what it could NOT verify instead of guessing.
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DDG_HTML = "https://html.duckduckgo.com/html/"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
CLEARBIT_SUGGEST = "https://autocomplete.clearbit.com/v1/companies/suggest"


class WebSearchReq(BaseModel):
    query: str
    max_results: int | None = 5
    fetch_pages: int | None = 3
    extract_chars: int | None = 1500


class EnrichReq(BaseModel):
    company: str | None = None
    domain: str | None = None
    person: str | None = None


class SocialReq(BaseModel):
    x_tweet: str | None = None
    x_username: str | None = None
    linkedin: str | None = None


def _strip_tags(x: str) -> str:
    import html as _html
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", _html.unescape(x or ""))).strip()


def _meta(html_text: str, name: str) -> str | None:
    m = re.search(r'<meta[^>]+(?:property|name)="' + re.escape(name) + r'"[^>]*content="([^"]*)"',
                  html_text, re.I)
    return _strip_tags(m.group(1)) if m else None


# ── web search + retrieval ────────────────────────────────────────────────────
def _ddg_real_url(href: str) -> str:
    import html as _html
    href = _html.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
        if real:
            return real[0]
    return href


def _ddg_search(query: str, limit: int) -> list[dict]:
    with httpx.Client(follow_redirects=True, timeout=20) as c:
        r = c.get(DDG_HTML, params={"q": query},
                  headers={"User-Agent": UA_BROWSER, "Accept": "text/html,application/xhtml+xml"})
        r.raise_for_status()
    page = r.text
    titles = re.findall(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
    out = []
    for i, (href, title) in enumerate(titles[:limit]):
        url = _ddg_real_url(href)
        out.append({"rank": i + 1, "title": _strip_tags(title), "url": url,
                    "domain": urllib.parse.urlparse(url).hostname,
                    "snippet": _strip_tags(snips[i]) if i < len(snips) else None})
    return out


def _fetch_readable(url: str, limit: int) -> dict:
    bad = _check_ssrf(url)
    if bad:
        return {"url": url, "error": f"refused: {bad}"}
    try:
        with httpx.Client(follow_redirects=True, max_redirects=4, timeout=20) as c:
            r = c.get(url, headers={"User-Agent": UA_BROWSER,
                                    "Accept": "text/html,application/xhtml+xml,application/json,*/*"})
        ct = (r.headers.get("content-type") or "").lower()
        if not any(k in ct for k in ("html", "text", "json", "xml")):
            return {"url": url, "status": r.status_code, "error": f"unsupported content-type: {ct[:60]}"}
        body = r.text
        title = None
        if "html" in ct or "xml" in ct:
            m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
            title = _strip_tags(m.group(1)) if m else None
            body = re.sub(r"(?is)<(script|style|noscript|svg|head|nav|footer|form)[^>]*>.*?</\1>", " ", body)
            body = re.sub(r"(?is)<!--.*?-->", " ", body)
            body = _strip_tags(body)
        else:
            body = re.sub(r"\s+", " ", body).strip()
        return {"url": url, "status": r.status_code, "content_type": ct.split(";")[0], "title": title,
                "chars_total": len(body), "content": body[:limit]}
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {str(e)[:150]}"}


@app.post("/web-search")
def web_search(req: WebSearchReq):
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query required")
    limit = max(1, min(int(req.max_results or 5), 10))
    n_fetch = max(0, min(int(req.fetch_pages or 0), limit, 5))
    chars = max(200, min(int(req.extract_chars or 1500), 6000))
    try:
        results = _ddg_search(q, limit)
    except Exception as e:
        return {"query": q, "results": [], "results_returned": 0, "pages_retrieved": 0,
                "error": f"search_backend_failed: {type(e).__name__} {str(e)[:150]}",
                "not_checked": ["page retrieval (the search itself failed)"]}
    retrieved = 0
    for r in results[:n_fetch]:
        pg = _fetch_readable(r["url"], chars)
        r["retrieval"] = pg
        if pg.get("content"):
            retrieved += 1
    return {
        "query": q, "results_returned": len(results), "pages_retrieved": retrieved, "results": results,
        "methodology": {
            "search": "DuckDuckGo HTML endpoint (no API key); results are the engine's own order",
            "retrieval": f"top {n_fetch} result(s) fetched over http/https and stripped of markup, "
                         f"scripts and styles; up to {chars} chars of readable text each",
            "ssrf_guard": "private/loopback/link-local targets are refused",
            "note_on_content": "extracted text omits JavaScript-rendered bodies and anything behind a paywall or login",
        },
        "not_checked": ["JavaScript-rendered pages", "paywalled or authenticated pages",
                        "facts inside the pages (the text is delivered, not adjudicated)",
                        "ad/spam filtering beyond what the engine returns"],
    }


# ── company / person enrichment ───────────────────────────────────────────────
def _wd_call(params: dict) -> dict:
    p = {"format": "json"}
    p.update(params)
    hdr = {"User-Agent": "xh-agents-api/1.0 (https://xhagents.xyz; paid x402 data API)",
           "Accept": "application/json"}
    last: Exception | None = None
    for attempt in range(3):  # Wikidata 403s "Too Many Reqs" on anonymous bursts
        try:
            r = httpx.get(WIKIDATA_API, params=p, headers=hdr, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.0 + attempt)
    raise last  # type: ignore[misc]


def _wd_search(term: str, limit: int = 5) -> list[dict]:
    d = _wd_call({"action": "wbsearchentities", "search": term, "language": "en",
                  "limit": limit, "type": "item"})
    return [{"id": s.get("id"), "label": s.get("label") or "", "description": s.get("description")}
            for s in (d.get("search") or [])]


def _wd_entity(qid: str) -> dict:
    r = httpx.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
                  headers={"User-Agent": "xh-agents-api/1.0 (https://xhagents.xyz)"}, timeout=25)
    r.raise_for_status()
    return r.json()["entities"][qid]


def _wd_ids(ent: dict, prop: str) -> list[str]:
    out = []
    for c in (ent.get("claims") or {}).get(prop, []):
        try:
            v = c["mainsnak"]["datavalue"]["value"]
        except Exception:
            continue
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def _wd_str(ent: dict, prop: str) -> str | None:
    for c in (ent.get("claims") or {}).get(prop, []):
        try:
            v = c["mainsnak"]["datavalue"]["value"]
        except Exception:
            continue
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return v.get("text") or v.get("id")
    return None


def _wd_time(ent: dict, prop: str) -> str | None:
    for c in (ent.get("claims") or {}).get(prop, []):
        try:
            t = c["mainsnak"]["datavalue"]["value"]["time"]
        except Exception:
            continue
        m = re.match(r"[+-](\d{4})", t)
        if m:
            return m.group(1)
    return None


def _wd_labels(qids: list[str]) -> dict[str, str | None]:
    qids = [q for q in qids if q][:40]
    if not qids:
        return {}
    d = _wd_call({"action": "wbgetentities", "ids": "|".join(qids), "props": "labels", "languages": "en"})
    return {q: (((e.get("labels") or {}).get("en") or {}).get("value"))
            for q, e in (d.get("entities") or {}).items()}


def _clearbit_suggest(term: str, limit: int = 3) -> dict | None:
    try:
        r = httpx.get(CLEARBIT_SUGGEST, params={"query": term},
                      headers={"User-Agent": "xh-agents-api/1.0"}, timeout=15)
        if r.status_code != 200:
            return None
        rows = r.json() or []
        return rows[0] if rows else None
    except Exception:
        return None


def _linkedin_company(slug: str) -> dict:
    slug = (slug or "").strip()
    if slug.startswith("http"):
        m = re.search(r"linkedin\.com/company/([^/?#]+)", slug)
        slug = m.group(1) if m else slug
    slug = slug.strip("/")
    if not slug or not re.fullmatch(r"[A-Za-z0-9\-_.%]+", slug):
        return {"error": "not a usable LinkedIn company slug"}

    url = f"https://www.linkedin.com/company/{slug}/"
    try:
        r = httpx.get(url, headers={"User-Agent": UA_BROWSER, "Accept-Language": "en-US,en;q=0.9"},
                      timeout=25, follow_redirects=True)
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {str(e)[:150]}"}
    if r.status_code != 200:
        return {"url": url, "status": r.status_code,
                "error": "LinkedIn did not serve the public page (guest access is rate-limited)"}
    h = r.text
    fields: dict[str, str] = {}
    for k, v in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", h, re.S):
        key = _strip_tags(k).lower()
        val = re.sub(r"\s*(External link for .*|Show all .*|\d+ associated members?.*)$", "", _strip_tags(v)).strip()
        if key and val:
            fields[key] = val
    desc = _meta(h, "og:description") or _meta(h, "description")
    out = {"url": url, "name": (_meta(h, "og:title") or "").replace(" | LinkedIn", "").strip() or None,
           "website": fields.get("website"), "industry": fields.get("industry"),
           "company_size": fields.get("company size"), "headquarters": fields.get("headquarters"),
           "type": fields.get("type"), "specialties": fields.get("specialties"),
           "description": desc}
    if desc:
        m = re.search(r"([\d,]+) followers", desc)
        if m:
            out["followers"] = int(m.group(1).replace(",", ""))
    return {k: v for k, v in out.items() if v}


@app.post("/company-enrich")
def company_enrich(req: EnrichReq):
    company, domain, person = (req.company or "").strip(), (req.domain or "").strip(), (req.person or "").strip()
    term = person or company or domain
    if not term:
        raise HTTPException(status_code=400, detail="give one of: company, domain, person")
    out: dict[str, Any] = {"query": term, "kind": "person" if person else "company",
                           "sources": [], "not_checked": []}

    # 1. Clearbit autocomplete — resolves a domain to a name and vice versa (key-less endpoint)
    if not person:
        cb = _clearbit_suggest(domain or company)
        if cb:
            out["web_identity"] = {"name": cb.get("name"), "domain": cb.get("domain"), "logo": cb.get("logo")}
            out["sources"].append("clearbit-autocomplete")
            if not company and cb.get("name"):
                term = cb["name"]
        else:
            out["not_checked"].append("clearbit autocomplete (no match or endpoint unavailable)")

    # 2. Wikidata — company or person facts
    ent = None
    try:
        cands = _wd_search(term, 5)
        out["wikidata_candidates"] = cands
        if cands:
            ent = _wd_entity(cands[0]["id"])
            out["sources"].append("wikidata")
    except Exception as e:
        out["wikidata_error"] = f"{type(e).__name__}: {str(e)[:150]}"
        out["not_checked"].append("wikidata lookup failed")

    if ent:
        qid = ent.get("id")
        labels = _wd_labels(_wd_ids(ent, "P452") + _wd_ids(ent, "P17") + _wd_ids(ent, "P159")
                            + _wd_ids(ent, "P414") + _wd_ids(ent, "P112"))
        profile = {
            "wikidata_id": qid,
            "label": ((ent.get("labels") or {}).get("en") or {}).get("value"),
            "description": ((ent.get("descriptions") or {}).get("en") or {}).get("value"),
            "website": _wd_str(ent, "P856"),
            "country": labels.get((_wd_ids(ent, "P17") or [""])[0]),
            "headquarters": labels.get((_wd_ids(ent, "P159") or [""])[0]),
            "industry": [(labels.get(q) or q) for q in _wd_ids(ent, "P452")],
            "employees": _wd_str(ent, "P1128"),
            "inception": _wd_time(ent, "P571"),
            "stock_exchange": [(labels.get(q) or q) for q in _wd_ids(ent, "P414")],
            "founders": [(labels.get(q) or q) for q in _wd_ids(ent, "P112")],
            "x_username": _wd_str(ent, "P2002"),
            "linkedin_company_id": _wd_str(ent, "P4264"),
            "linkedin_person_id": _wd_str(ent, "P6634"),
            "occupation": [(labels.get(q) or q) for q in _wd_ids(ent, "P106")],
            "employer": [(labels.get(q) or q) for q in _wd_ids(ent, "P108")],
        }
        out["resolved"] = {k: v for k, v in profile.items() if v not in (None, [], "")}
        li_slug = profile.get("linkedin_company_id")
        if li_slug and not person:
            li = _linkedin_company(li_slug)
            if li.get("error"):
                out["not_checked"].append(f"linkedin public page ({li['error'][:80]})")
            else:
                out["linkedin"] = li
                out["sources"].append("linkedin-public")

    out["methodology"] = {
        "wikidata": "wbsearchentities + Special:EntityData (CC0 structured data)",
        "linkedin": "the public (guest) company page only — no login, no scraping behind auth",
        "clearbit": "the public autocomplete endpoint (name/domain/logo only)",
        "not_claimed": "we do not invent emails, phone numbers or headcounts not present in the sources",
    }
    out["not_checked"] += ["personal emails / phone numbers", "LinkedIn member profiles (login-walled)",
                           "private-company financials not in Wikidata"]
    return out


# ── social data: X/Twitter + LinkedIn ─────────────────────────────────────────
def _x_token(tweet_id: str) -> str:
    import math
    return format(int((int(tweet_id) / 1e15) * math.pi), "x")


def _x_tweet(ref: str) -> dict:
    m = re.search(r"/status(?:es)?/(\d{1,25})", ref or "") or re.match(r"^\s*(\d{1,25})\s*$", ref or "")
    if not m:
        return {"error": "could not parse a tweet id from x_tweet (pass a status URL or a numeric id)"}
    tid = m.group(1)
    url = f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&token={_x_token(tid)}&lang=en"
    try:
        r = httpx.get(url, headers={"User-Agent": UA_BROWSER}, timeout=20)
    except Exception as e:
        return {"id": tid, "error": f"{type(e).__name__}: {str(e)[:150]}"}
    if r.status_code != 200:
        return {"id": tid, "status": r.status_code,
                "error": "X did not return the embedded post (deleted, protected, or rate-limited)"}
    try:
        d = r.json()
    except Exception:
        return {"id": tid, "error": "X returned a non-JSON body"}
    u = d.get("user") or {}
    media = d.get("mediaDetails") or []
    return {"id": d.get("id_str") or tid, "text": d.get("text"), "lang": d.get("lang"),
            "created_at": d.get("created_at"),
            "author": {"name": u.get("name"), "screen_name": u.get("screen_name"),
                       "verified": u.get("verified"), "id": u.get("id_str"),
                       "avatar": u.get("profile_image_url_https")},
            "metrics": {"likes": d.get("favorite_count"), "replies": d.get("conversation_count"),
                        "quotes": d.get("quote_count")},
            "has_media": bool(media), "media": [{"type": m.get("type"), "url": m.get("media_url_https")}
                                                for m in media][:4],
            "source": "cdn.syndication.twimg.com (X's own public embed endpoint)"}


def _x_profile(username: str) -> dict:
    u = (username or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", u):
        return {"error": "not a valid X username"}
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{u}"
    try:
        r = httpx.get(url, params={"showReplies": "false"}, headers={"User-Agent": UA_BROWSER}, timeout=25)
    except Exception as e:
        return {"username": u, "error": f"{type(e).__name__}: {str(e)[:150]}"}
    if r.status_code != 200:
        return {"username": u, "status": r.status_code,
                "error": "X rate-limited the public timeline embed (try again later or use x_tweet)"}
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.S)
    if not m:
        return {"username": u, "error": "public timeline had no embedded payload"}
    try:
        d = json.loads(m.group(1))
        props = (d.get("props") or {}).get("pageProps") or {}
        header = props.get("header") or {}
        entries = ((props.get("timeline") or {}).get("entries") or [])
    except Exception as e:
        return {"username": u, "error": f"payload parse failed: {str(e)[:120]}"}
    tweets = []
    for e in entries[:8]:
        c = e.get("content") or {}
        t = c.get("tweet") or {}
        if t:
            tweets.append({"id": t.get("id_str"), "text": t.get("full_text") or t.get("text"),
                           "created_at": t.get("created_at"),
                           "likes": (t.get("favorite_count") if t.get("favorite_count") is not None else None)})
    return {"username": u, "profile": {"name": header.get("name"), "description": header.get("description"),
                                       "followers": header.get("followers_count"),
                                       "following": header.get("following_count"),
                                       "tweets": header.get("statuses_count"),
                                       "verified": header.get("verified"),
                                       "location": header.get("location")},
            "recent_posts": tweets, "source": "syndication.twitter.com public timeline embed"}


@app.post("/social-data")
def social_data(req: SocialReq):
    if not (req.x_tweet or req.x_username or req.linkedin):
        raise HTTPException(status_code=400, detail="give one of: x_tweet, x_username, linkedin")
    out: dict[str, Any] = {"sources": [], "not_checked": []}
    if req.x_tweet:
        out["x_tweet"] = _x_tweet(req.x_tweet)
        out["sources"].append("x-syndication")
    if req.x_username:
        out["x_profile"] = _x_profile(req.x_username)
        out["sources"].append("x-syndication")
    if req.linkedin:
        out["linkedin"] = _linkedin_company(req.linkedin)
        out["sources"].append("linkedin-public")
    out["methodology"] = {
        "x": "X's own public embed endpoints (cdn.syndication.twimg.com / syndication.twitter.com) — "
             "no API key, read-only, post-level",
        "linkedin": "the public guest company page only; member profiles are login-walled and are not touched",
        "not_claimed": "no follower lists, no private accounts, no data behind authentication",
    }
    out["not_checked"] += ["LinkedIn member/personal profiles (login-walled)",
                           "X timelines beyond the public embed (may be rate-limited)",
                           "historical analytics or follower demographics"]
    return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
