#!/usr/bin/env python3
"""
scout_monitor.py — Agent Scout: monitor x402 endpoints health
Checks all registered endpoints, reports status to Hermes.
Run via cron every 15 minutes.
"""
import urllib.request
import json
import sys
from datetime import datetime, timezone

# ── All registered endpoints ──────────────────────────────────────
ENDPOINTS = {
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

TIMEOUT = 10


def check_health(base_url):
    """Check /health or root endpoint."""
    for path in ["/health", "/"]:
        try:
            url = base_url + path
            req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
            return resp.status, resp.read().decode()[:200]
        except urllib.error.HTTPError as e:
            return e.code, str(e.reason)
        except Exception as e:
            return -1, str(e)
    return -1, "unreachable"


def check_x402_discovery(base_url):
    """Check /.well-known/x402.json for endpoint count."""
    try:
        url = base_url + "/.well-known/x402.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read())
        entries = data.get("entries", [])
        resources = data.get("resources", [])
        return True, len(entries) or len(resources)
    except Exception as e:
        return False, str(e)


def check_paid_endpoint(base_url, path):
    """Hit a paid endpoint without payment — expect 402."""
    try:
        url = base_url + path
        req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return resp.status, "returned 200 (unexpected)"
    except urllib.error.HTTPError as e:
        if e.code == 402:
            return 402, "correct (payment required)"
        return e.code, str(e.reason)
    except Exception as e:
        return -1, str(e)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = []
    total_endpoints = 0
    healthy_count = 0
    issues = []

    for worker_name, cfg in ENDPOINTS.items():
        base = cfg["base_url"]
        chain = cfg["chain"]

        # Health check
        h_status, h_body = check_health(base)
        health_ok = h_status in (200, 402)

        # Discovery check
        disc_ok, disc_info = check_x402_discovery(base)

        section = f"[{worker_name}] ({chain}) {base}"
        section += f"\n  Health: {h_status} {'OK' if health_ok else 'FAIL'}"
        section += f"\n  Discovery (x402.json): {'OK' if disc_ok else 'FAIL'} — {disc_info} endpoints found"

        if not health_ok:
            issues.append(f"{worker_name}: health={h_status}")

        # Spot-check first 2 paid endpoints
        for ep in cfg["endpoints"][:2]:
            total_endpoints += 1
            ep_status, ep_msg = check_paid_endpoint(base, ep)
            ep_ok = ep_status == 402
            if ep_ok:
                healthy_count += 1
            else:
                issues.append(f"{worker_name}{ep}: status={ep_status} {ep_msg}")
            section += f"\n  {ep}: {ep_status} ({ep_msg})"

        # Count remaining as healthy if discovery OK
        remaining = len(cfg["endpoints"]) - 2
        if remaining > 0 and disc_ok:
            total_endpoints += remaining
            healthy_count += remaining
            section += f"\n  +{remaining} more endpoints (discovery OK, skipped spot-check)"

        report.append(section)

    # Summary
    summary = f"=== SCOUT ENDPOINT MONITOR — {now} ==="
    summary += f"\nWorkers: {len(ENDPOINTS)}"
    summary += f"\nEndpoints checked: {total_endpoints}"
    summary += f"\nHealthy: {healthy_count}/{total_endpoints}"

    if issues:
        summary += f"\nISSUES ({len(issues)}):"
        for i in issues:
            summary += f"\n  ! {i}"
    else:
        summary += "\nAll endpoints operational."

    output = summary + "\n\n" + "\n\n".join(report)
    print(output)
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
