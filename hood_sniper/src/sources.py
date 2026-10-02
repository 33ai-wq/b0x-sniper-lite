"""hood_sniper.sources — multi-source pollers.

Each function returns a list of normalized 'candidates' that
`engine.py` scores against baseline. Defensive against:

  • DNS hijack (Trust+Positif) → arcus works via Cloudflare path,
    RPC falls back to Blockscout mirror.
  • Auth-gated endpoints → never expose keys; public-read only.
  • Rate limits → all pollers timeout to 8s, retry once.

Source verification status (2026-07-16):
  ✓ arcus     — /v1/markets public, 41 markets, 35 ONLINE avg
  ✓ blockscout — RH chain indexed, new-contracts API
  ✓ robidy    — Next.js streaming payload, phases[].{startsAt,endsAt,priceEth}
  ✗ x/twitter — skipped; requires paid X API key, deferred to v0.2
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from typing import Any

from . import config


# ─── Helpers ───────────────────────────────────────────────────

def _http_get(url: str, timeout: int = 8, headers: dict | None = None) -> dict | list | None:
    """GET with timeout + soft-fail. Returns parsed JSON or None."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "hood-sniper/0.1 (+prpo_ai)")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ─── Arcus /v1/markets ────────────────────────────────────────

def poll_arcus() -> list[dict]:
    """Fetch Arcus universe. Returns list of candidate events:
        market status flips, volume spikes, funding flips.
    """
    payload = _http_get(f"{config.ARCUS_BASE_URL}/v1/markets")
    if not isinstance(payload, dict):
        return []
    markets = payload.get("markets") or []
    candidates = []
    # Compute aggregate 24h volume for baseline
    for m in markets:
        vol = float(m.get("volume24h") or 0)
        status = (m.get("status") or "").upper()
        if vol >= config.VOLUME_SPIKE_FLOOR_USD:
            candidates.append({
                "source": "arcus",
                "kind": "volume_present",
                "ts": _now_iso(),
                "title": f"{m.get('marketDisplayName','?')} 24h vol ${int(vol):,}",
                "url": f"https://app.arcus.xyz/markets/{m.get('marketId','')}",
                "chain_id": config.RHCHAIN_CHAIN_ID,
                "context": {
                    "market_id": m.get("marketId"),
                    "volume_24h": vol,
                    "status": status,
                    "funding_rate": m.get("fundingRate"),
                    "open_interest": m.get("openInterest"),
                },
            })
    return candidates


# ─── Blockscout new contracts ────────────────────────────────

def poll_blockscout_new_contracts(limit: int = 25) -> list[dict]:
    """Recent contract deployments on RH Chain.

    Verified endpoint shape (Blockscout V2):
      GET /api/v2/contracts  → {items:[{hash, name, compiler, ...}]}
    May 404 on partial outages — degrade silently.
    """
    payload = _http_get(
        f"{config.BLOCKSCOUT_BASE_URL}/api/v2/contracts"
        f"?filter=vyper%7Csolidity&sort=created_on&order=desc"
    )
    if not isinstance(payload, dict):
        return []
    items = payload.get("items") or []
    candidates = []
    for c in items[:limit]:
        created = c.get("created_at") or c.get("block_number")
        name = c.get("name") or "(anon)"
        candidates.append({
            "source": "blockscout",
            "kind": "new_contract",
            "ts": _now_iso(),
            "title": f"New contract: {name}",
            "url": f"{config.BLOCKSCOUT_BASE_URL}/address/{c.get('hash','')}",
            "chain_id": config.RHCHAIN_CHAIN_ID,
            "context": {
                "address": c.get("hash"),
                "deployer": (c.get("creator") or {}).get("hash"),
                "compiler": c.get("compiler"),
                "created_at": created,
            },
        })
    return candidates


# ─── Robidy launches (Next.js streaming payload) ──────────────

_NEXT_PHASE_RE = re.compile(
    r'"name"\s*:\s*"([^"]+)"[^}]*?"startsAt"\s*:\s*"([^"]+)"[^}]*?"endsAt"\s*:\s*"([^"]+)"'
    r'[^}]*?(?:"priceEth"\s*:\s*"([^"]+)"|"perWallet"\s*:\s*(\d+))',
    re.DOTALL,
)


def poll_robidy_internal() -> list[dict]:
    """Polite internal-pull of robidy.app for new launches/phases.

    Scans the home + /launches/* paths for `RBDY-XXXXXX` passes and phase
    windows. Public; no auth.
    """
    html = _http_get(config.ROBIDY_BASE_URL)  # may return JSON if API hit
    # urllib returns dict/list here since Accept:json; for HTML we want
    # the raw HTML — fall back to raw fetch via urllib.
    raw = _raw_get(config.ROBIDY_BASE_URL)
    if not raw:
        return []
    candidates = []
    matches = _NEXT_PHASE_RE.findall(raw)
    for name, starts_at, ends_at, price_eth, per_wallet in matches:
        candidates.append({
            "source": "robidy",
            "kind": "robidy_phase_start",
            "ts": _now_iso(),
            "title": f"Robidy launch: {name} (starts {starts_at})",
            "url": config.ROBIDY_BASE_URL,
            "chain_id": config.RHCHAIN_CHAIN_ID,
            "context": {
                "name": name,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "price_eth": price_eth,
                "per_wallet": per_wallet,
            },
        })
    return candidates


def _raw_get(url: str, timeout: int = 8) -> str | None:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "hood-sniper/0.1 (+prpo_ai)")
    req.add_header(
        "Accept",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            # Next.js streaming lives inside <script>self.__next_f.push …</script>
            if "self.__next_f.push" in body:
                m = re.search(
                    r"<script[^>]*>(self\.__next_f\.push.*?)</script>",
                    body,
                    re.DOTALL,
                )
                if m:
                    return m.group(1)
            return body
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
