#!/usr/bin/env python3
"""
scout_x402_cdp_scan.py — deep scan of the canonical x402 discovery index.

The Scout 15-minute monitor (scout_x402.py) only checks Boss's own manifests and
the x402bazaar.org marketplace. The canonical discovery index — the one agents
actually read — is Coinbase's CDP discovery endpoint, currently ~23k resources
with offset pagination and NO server-side filter. So checking whether Boss's
resources are indexed needs a full paginated sweep: too heavy for every cron run,
fine on demand (≈30 s with 16 threads).

Usage:  python3 scout_x402_cdp_scan.py
Exit:   0 always (monitor), prints a report to stdout.

Read-only. No auth, no writes outside /tmp.
"""
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

BASE = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
PAGE = 100
WORKERS = 16

# Domains / treasuries that mean "this listing is ours".
BOSS_DOMAINS = ["xhagents.xyz", "pronomad.duckdns.org", "mulberry-boar", "b0x402"]
BOSS_PAYTO = {
    "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0",  # xhagents.xyz (Base USDC)
    "0x57eec52d76a4a78d4562fc2564101a4bd2e3f357",  # legacy Base treasury
    "ghfbggnxern6pq7bosflfjupwxjuvj8tx7egoj9lv2aw",  # legacy Solana treasury
}

# Niche keywords -> direct competitors.
NICHE = ["meme-hunter", "memecoin", "honeypot", "defi-sentiment", "wallet-profile",
         "dinalibrium", "robinhood", "rh-season", "token-safety", "token-check",
         "whale-watch", "gas-tracker", "daily-drop", "web-search", "company-enrich",
         "social-data"]


def ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def fetch(offset):
    url = f"{BASE}?limit={PAGE}&offset={offset}"
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
            body = urllib.request.urlopen(req, timeout=40, context=ctx()).read().decode()
            return json.loads(body)
        except Exception:
            continue
    return None


def headline(d):
    pag = d.get("pagination") or {}
    total = pag.get("total") or 0
    offsets = list(range(0, total, PAGE))

    scanned = 0
    failed = 0
    boss_hits = []
    dom = Counter()
    dom_kw = defaultdict(set)

    def work(off):
        return off, fetch(off)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for off, d in ex.map(work, offsets):
            if not d:
                failed += 1
                continue
            items = d.get("items", [])
            scanned += len(items)
            for it in items:
                blob = json.dumps(it).lower()
                resource = it.get("resource") or it.get("url") or ""
                paytos = [str(a.get("payTo", "")).lower() for a in (it.get("accepts") or [])]

                if any(b in blob for b in BOSS_DOMAINS) or any(p in BOSS_PAYTO for p in paytos):
                    boss_hits.append({
                        "resource": resource,
                        "payTo": paytos[0] if paytos else None,
                        "network": (it.get("accepts") or [{}])[0].get("network"),
                    })

                if any(k in blob for k in NICHE):
                    m = re.match(r"https?://([^/]+)", resource)
                    if m:
                        dom[m.group(1)] += 1
                        for k in NICHE:
                            if k in blob:
                                dom_kw[m.group(1)].add(k)

    return {
        "total": total,
        "scanned": scanned,
        "failed_pages": failed,
        "boss_hits": boss_hits,
        "competitor_domains": dom,
        "competitor_kw": dom_kw,
    }


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== SCOUT CDP DISCOVERY DEEP SCAN — {now} ===")

    first = fetch(0)
    if not first:
        print("⚠️  CDP discovery endpoint unreachable.")
        return 1

    r = headline(first)
    print(f"Index: {BASE}")
    print(f"Resources: total={r['total']} scanned={r['scanned']} failed_pages={r['failed_pages']}")

    print(f"\n🎯 BOSS / XH LISTINGS INDEXED: {len(r['boss_hits'])}")
    for h in r["boss_hits"]:
        print(f"  • {h['resource']}  [{h['network']}] payTo={h['payTo']}")

    print(f"\n📊 Niche competitors mineable ({len(r['competitor_domains'])} domains):")
    for name, n in r["competitor_domains"].most_common(15):
        print(f"  {name}  ({n} endpoints)  {sorted(r['competitor_kw'][name])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
