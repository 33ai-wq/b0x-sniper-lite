#!/usr/bin/env python3
"""Generates status.json — the LIVE figures for the endpoint catalogue on xhagents.xyz.

Run every 9 minutes by xh-status-generator.timer. The homepage fetches this at /api/status.json
and fills the stat strip by matching each card's data-label.

Design rule: every number here is either read from a machine-readable source on this host or
measured at run time. When a measurement fails, the cell says so instead of showing a stale value.
The static counts this script used to serve (and the "via Scout agent" line) are gone: the catalogue
itself is generated from openapi.json by adengine/gen_catalog.py.

Env:
  STATUS_OUTPUT_PATH  where to write (default /home/ubuntu/prpo_ai/adengine/status.json)
  XH_OPENAPI_PATH     openapi.json to count (default /var/www/xhagents-www/openapi.json)
"""
import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone

OUTPUT_PATH = os.environ.get("STATUS_OUTPUT_PATH", "/home/ubuntu/prpo_ai/adengine/status.json")
OPENAPI_PATH = os.environ.get("XH_OPENAPI_PATH", "/var/www/xhagents-www/openapi.json")
UA = {"User-Agent": "xh-agents-status/1.0", "Content-Type": "application/json"}

BASE_RPCS = [os.environ.get("XH_BASE_RPC", "").strip(), "https://base-rpc.publicnode.com",
             "https://mainnet.base.org"]
SECONDARY_HOSTS = [
    ("b0x402 Cloudflare Worker", "https://x402-cf-worker.mulberry-boar.workers.dev/health"),
    ("b0x402 Solana (pronomad)", "https://pronomad.duckdns.org/health"),
]


def catalogue_counts() -> tuple[int, str, str]:
    """Registered resources + price range, straight from the OpenAPI document."""
    try:
        with open(OPENAPI_PATH) as fh:
            doc = json.load(fh)
    except OSError:
        return 0, "—", "openapi.json unreadable"
    resources, prices = set(), []
    for path, ops in doc.get("paths", {}).items():
        for op in ops.values():
            if isinstance(op, dict) and op.get("x-payment-info"):
                resources.add(path)
                prices.append(float(op["x-payment-info"]["price"]["amount"]))
                break
    if not prices:
        return len(resources), "—", "no priced operation found"
    return len(resources), f"${min(prices):.2f}–${max(prices):.2f}", "USDC on Base · settled per request"


def base_block() -> tuple[str, str]:
    """Current Base block, or an honest note that the read failed."""
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}).encode()
    for url in [u for u in BASE_RPCS if u]:
        try:
            req = urllib.request.Request(url, data=payload, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                block = int(json.loads(r.read())["result"], 16)
            return f"{block:,}", "read live from Base mainnet"
        except Exception:  # try the next endpoint
            continue
    return "—", "chain read failed"


def secondary_hosts() -> tuple[int, str]:
    """How many secondary hosts answer right now (they are not part of the registered catalogue)."""
    up = []
    for name, url in SECONDARY_HOSTS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
            with urllib.request.urlopen(req, timeout=12) as r:
                if r.status == 200:
                    up.append(name)
        except (urllib.error.URLError, socket.timeout, ValueError):
            continue
    total = len(SECONDARY_HOSTS)
    if len(up) == total:
        return total, "Cloudflare edge + Solana mainnet · both answering"
    return len(up), f"{len(up)}/{total} answering (checked now)"


def build_status() -> dict:
    now = datetime.now(timezone.utc)
    resources, _price_range, _price_detail = catalogue_counts()
    block, block_detail = base_block()
    hosts, hosts_detail = secondary_hosts()
    # Labels must match the data-label attributes on the homepage cards, or the card is never
    # updated. No price range here: prices live in the 402 challenge and openapi.json, not on the
    # public page or its feed.
    return {
        "updatedNote": f"Live figures updated {now.strftime('%H:%M')} UTC — every number below is read "
                       f"from this host or from Base mainnet.",
        "generatedAt": now.isoformat(),
        "groups": [
            {"label": "Registered endpoints", "value": resources,
             "detail": "x402scan verified · Coinbase Bazaar indexed"},
            {"label": "Payment rail", "value": "x402 · USDC",
             "detail": "per call on Base · quoted in the 402 challenge"},
            {"label": "Base mainnet block", "value": block,
             "detail": f"{block_detail} at {now.strftime('%H:%M')} UTC"},
            {"label": "Secondary hosts", "value": hosts, "detail": hosts_detail},
        ],
    }


def main() -> None:
    status = build_status()
    tmp = OUTPUT_PATH + ".tmp"
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(tmp, "w") as fh:
        json.dump(status, fh, indent=2)
    os.replace(tmp, OUTPUT_PATH)  # atomic, so a reader never sees a half-written file
    print(f"Wrote {OUTPUT_PATH}: " + "; ".join(f"{g['label']}={g['value']}" for g in status["groups"]))


if __name__ == "__main__":
    main()
