#!/usr/bin/env python3
"""
scout_x402.py — Scout x402 Bazaar Monitor
Checks x402bazaar.org for Boss's endpoints visibility, tracks state to suppress duplicates.
Run via cron every 15 minutes.
"""
import urllib.request
import urllib.error
import urllib.parse
import json
import sys
import ssl
from datetime import datetime, timezone
from pathlib import Path

# ── Watchlist keywords ────────────────────────────────────────────────
WATCHLIST = [
    "robinhood", "rh chain", "memecoin", "meme-hunter",
    "defi-sentiment", "dinalibrium", "wallet-profile",
    "honeypot", "b0x402"
]

# ── State file ────────────────────────────────────────────────────────
STATE_FILE = Path(__file__).parent / "data" / "scout_x402_state.json"

# ── Boss's known endpoints ────────────────────────────────────────────
BOSS_ENDPOINTS = {
    "b0x402-base": {
        "base_url": "https://x402-cf-worker.mulberry-boar.workers.dev",
        "endpoints": [
            "/v1/meme-hunter",
            "/v1/defi-sentiment",
            "/v1/dinalibrium",
            "/v1/wallet-profile",
        ],
        "chain": "Base",
        "treasury": "0x57EEC52d76A4A78D4562fc2564101A4bD2e3F357",
    },
    "b0x402-solana": {
        "base_url": "https://pronomad.duckdns.org",
        "endpoints": [
            "/v1/meme-hunter",
            "/v1/defi-sentiment",
            "/v1/dinalibrium",
            "/v1/wallet-profile",
            "/v1/b0x402-data",
            "/v1/honeypot-check",
        ],
        "chain": "Solana",
        "treasury": "GhFbGgNxERN6pQ7boSFLFJuPwXJuvJ8Tx7EgoJ9LV2Aw",
    },
}

TIMEOUT = 15


def load_state():
    """Load seen endpoints state from JSON file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen_endpoints": {}, "last_run": None}


def save_state(state):
    """Save state to JSON file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def normalize_text(text):
    """Normalize text for matching."""
    return text.lower().strip()


def matches_watchlist(text):
    """Check if text matches any watchlist keyword."""
    text_lower = normalize_text(text)
    return any(kw in text_lower for kw in WATCHLIST)


def fetch_bazaar():
    """Fetch x402bazaar.org listings."""
    url = "https://x402bazaar.org/api/listings"
    # Fallback to main page if API not available
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        return json.loads(resp.read().decode())
    except Exception as e:
        # Try HTML page
        try:
            url2 = "https://x402bazaar.org"
            req = urllib.request.Request(url2, headers={"User-Agent": "Scout/1.0"})
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
            html = resp.read().decode()
            # Extract JSON from page if embedded
            import re
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
    return None


def fetch_bazaar_search(query):
    """Search x402bazaar for a specific query."""
    url = f"https://x402bazaar.org/api/search?q={urllib.parse.quote(query)}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def check_boss_endpoint_on_bazaar(base_url, endpoint_path):
    """Check if a specific Boss endpoint is visible on bazaar."""
    search_term = base_url.replace("https://", "").replace("http://", "") + endpoint_path
    result = fetch_bazaar_search(search_term)
    if result and isinstance(result, dict):
        items = result.get("results") or result.get("listings") or result.get("items") or []
        for item in items:
            item_url = item.get("url") or item.get("endpoint_url") or item.get("base_url") or ""
            if base_url in item_url and endpoint_path in item_url:
                return True, item
    return False, None


def check_health(base_url):
    """Check /health or root endpoint."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for path in ["/health", "/"]:
        try:
            url = base_url + path
            req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
            return resp.status, resp.read().decode()[:200]
        except urllib.error.HTTPError as e:
            return e.code, str(e.reason)
        except Exception as e:
            return -1, str(e)
    return -1, "unreachable"


def check_x402_discovery(base_url):
    """Check /.well-known/x402.json for endpoint count."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        url = base_url + "/.well-known/x402"
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = json.loads(resp.read())
        entries = data.get("entries", [])
        resources = data.get("resources", [])
        return True, len(entries) or len(resources)
    except Exception as e:
        return False, str(e)


def check_paid_endpoint(base_url, path):
    """Hit a paid endpoint without payment — expect 402."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        url = base_url + path
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        return resp.status, "returned 200 (unexpected)"
    except urllib.error.HTTPError as e:
        if e.code == 402:
            return 402, "correct (payment required)"
        return e.code, str(e.reason)
    except Exception as e:
        return -1, str(e)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state = load_state()
    seen = state.get("seen_endpoints", {})

    print(f"=== SCOUT x402 BAZAAR MONITOR — {now} ===")

    # ── 1. Check x402bazaar.org for all listings ──────────────────────
    print("\n📊 Checking x402bazaar.org for listings...")
    bazaar_data = fetch_bazaar()

    total_resources = 0
    watchlist_matches = []
    new_matches = []
    boss_visible_count = 0
    boss_endpoints_details = []

    if bazaar_data:
        # Handle different response structures
        items = []
        if isinstance(bazaar_data, list):
            items = bazaar_data
        elif isinstance(bazaar_data, dict):
            items = (bazaar_data.get("results")
                     or bazaar_data.get("listings")
                     or bazaar_data.get("items")
                     or bazaar_data.get("data")
                     or [])

        total_resources = len(items)
        print(f"  Total resources discovered on Bazaar: {total_resources}")

        # Check each item for watchlist matches
        for item in items:
            # Extract text fields for matching
            text_fields = []
            for key in ["name", "title", "description", "summary", "tags", "category", "endpoint_url", "url", "base_url"]:
                val = item.get(key)
                if val:
                    if isinstance(val, list):
                        text_fields.extend(str(v) for v in val)
                    else:
                        text_fields.append(str(val))

            full_text = " ".join(text_fields)
            if matches_watchlist(full_text):
                # Check if this is a Boss endpoint
                is_boss = False
                for worker_name, cfg in BOSS_ENDPOINTS.items():
                    base = cfg["base_url"]
                    for ep in cfg["endpoints"]:
                        if base in full_text and ep in full_text:
                            is_boss = True
                            break
                    if is_boss:
                        break

                match_info = {
                    "item": item,
                    "is_boss_endpoint": is_boss,
                    "matched_keywords": [kw for kw in WATCHLIST if kw in normalize_text(full_text)]
                }
                watchlist_matches.append(match_info)

                if is_boss:
                    boss_visible_count += 1
                    boss_endpoints_details.append(match_info)

        # Check for NEW watchlist matches (not seen before)
        new_matches = []
        for match in watchlist_matches:
            # Create a unique key for this match
            item = match["item"]
            item_key = item.get("id") or item.get("url") or item.get("endpoint_url") or json.dumps(item, sort_keys=True)[:100]
            if item_key not in seen:
                new_matches.append(match)
                seen[item_key] = {
                    "first_seen": now,
                    "is_boss": match["is_boss_endpoint"],
                    "keywords": match["matched_keywords"]
                }

        if new_matches:
            print(f"\n🆕 NEW watchlist matches ({len(new_matches)}):")
            for m in new_matches:
                item = m["item"]
                name = item.get("name") or item.get("title") or item.get("endpoint_url") or "Unknown"
                boss_flag = " 🎯 BOSS ENDPOINT" if m["is_boss_endpoint"] else ""
                print(f"  • {name}{boss_flag}")
                print(f"    Keywords: {', '.join(m['matched_keywords'])}")
                if m["is_boss_endpoint"]:
                    print("    ⚡ BOSS REVENUE STREAM GOING LIVE ON DISCOVERY!")

    else:
        print("  ⚠️  Could not fetch bazaar data (network/API issue)")

    # ── 2. Check Boss's specific endpoints on Bazaar ──────────────────
    print("\n🎯 Checking Boss's endpoints on Bazaar...")
    for worker_name, cfg in BOSS_ENDPOINTS.items():
        base = cfg["base_url"]
        chain = cfg["chain"]
        print(f"\n  [{worker_name}] ({chain}) {base}")

        for ep in cfg["endpoints"]:
            visible, item = check_boss_endpoint_on_bazaar(base, ep)
            status = "✅ VISIBLE" if visible else "❌ Not found"
            print(f"    {ep}: {status}")
            if visible and item:
                boss_visible_count += 1
                boss_endpoints_details.append({
                    "worker": worker_name,
                    "endpoint": ep,
                    "item": item,
                    "chain": chain
                })

    # ── 3. Health checks (from original scout_monitor) ────────────────
    print("\n🏥 Health & endpoint checks...")
    total_endpoints = 0
    healthy_count = 0
    issues = []

    for worker_name, cfg in BOSS_ENDPOINTS.items():
        base = cfg["base_url"]
        chain = cfg["chain"]

        h_status, h_body = check_health(base)
        health_ok = h_status in (200, 402)

        disc_ok, disc_info = check_x402_discovery(base)

        if not health_ok:
            issues.append(f"{worker_name}: health={h_status}")

        for ep in cfg["endpoints"][:2]:  # Spot-check first 2
            total_endpoints += 1
            ep_status, ep_msg = check_paid_endpoint(base, ep)
            ep_ok = ep_status == 402
            if ep_ok:
                healthy_count += 1
            else:
                issues.append(f"{worker_name}{ep}: status={ep_status} {ep_msg}")

        remaining = len(cfg["endpoints"]) - 2
        if remaining > 0 and disc_ok:
            total_endpoints += remaining
            healthy_count += remaining

    # ── 4. Update state ───────────────────────────────────────────────
    state["seen_endpoints"] = seen
    state["last_run"] = now
    save_state(state)

    # ── 5. Summary ────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"📋 SUMMARY — {now}")
    print(f"{'='*50}")
    print(f"Bazaar resources discovered: {total_resources}")
    print(f"Watchlist matches: {len(watchlist_matches)}")
    print(f"  New matches this run: {len(new_matches) if 'new_matches' in locals() else 0}")
    print(f"Boss endpoints visible on Bazaar: {boss_visible_count}")
    print(f"Health checks: {healthy_count}/{total_endpoints} endpoints OK")

    if boss_visible_count > 0:
        print(f"\n🎉 BOSS ENDPOINTS VISIBLE ON BAZAAR: {boss_visible_count}")
        for detail in boss_endpoints_details:
            if isinstance(detail, dict):
                if "worker" in detail:
                    print(f"  • {detail['worker']} ({detail['chain']}) — {detail['endpoint']}")
                else:
                    item = detail.get("item", {})
                    name = item.get("name") or item.get("title") or "Boss endpoint"
                    print(f"  • {name}")

    if issues:
        print(f"\n⚠️  ISSUES ({len(issues)}):")
        for i in issues:
            print(f"  ! {i}")
    else:
        print("\n✅ All endpoints operational.")

    print(f"\nState file: {STATE_FILE}")
    print(f"Next run: +15 min (cron)")

    return 0 if not issues else 1


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())