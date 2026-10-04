#!/usr/bin/env python3
"""Refresh the provider summary in openapi.json (what x402scan shows on our listing).

The listing description is read from our own OpenAPI `info` block — that is why the dashboard said
"15 endpoints": it was quoting a description we wrote when the catalogue was smaller. This script
rewrites it from the actual files on disk (so it can never drift again) and adds the contact email
x402scan needs to verify ownership.

Run: python3 /home/ubuntu/prpo_ai/xh_api/update_openapi_info.py
"""
import datetime
import json
import os
import shutil

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
CONTACT = "basefortyblock@gmail.com"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def build(files: list[str]) -> dict:
    """Count what is really published, then describe it."""
    resources = 0
    prices = []
    arkham = 0
    for base in files:
        wk = os.path.join(base, ".well-known", "x402")
        oa = os.path.join(base, "openapi.json")
        if os.path.exists(wk):
            man = json.load(open(wk))
            resources = max(resources, len(man.get("resources") or []))
        if os.path.exists(oa):
            doc = json.load(open(oa))
            arkham = max(arkham, sum(1 for p in (doc.get("paths") or {}) if p.startswith("/api/arkham-intel/")
                                     and not p.endswith("/use-cases/") ))
            for path, ops in (doc.get("paths") or {}).items():
                for op in ops.values():
                    info = (op or {}).get("x-payment-info") or {}
                    amount = ((info.get("price") or {}).get("amount"))
                    if amount:
                        try:
                            prices.append(float(amount))
                        except (TypeError, ValueError):
                            pass
    lo, hi = (min(prices), max(prices)) if prices else (0.0, 0.0)
    return {
        "resources": resources,
        "paths": None,  # filled per file below
        "price_lo": lo,
        "price_hi": hi,
        "arkham": arkham,
    }


STATS = build([DOCROOT, SRC])
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
description_head = (
    f"XH Agents — x402 Endpoint Catalogue & Autonomous AI on Base. "
    f"{STATS['resources']} live paid x402 resources on Base, "
    f"{STATS['price_lo']:.2f}-{STATS['price_hi']:.2f} USDC per call. "
)
description_body = (
    f"Includes {_WORDS.get(STATS['arkham'], str(STATS['arkham']))} Arkham-style intelligence endpoints at 0.10 "
    "(use-case router, pool inflow/outflow, wallet portfolio, counterparty due diligence, fund trace, venue users) "
    "computed from public Base chain data, plus wallet and "
    "token checks, gas, whale watch, DeFi sentiment, x402 conformance, a video licence with a signed stream URL, "
    "the cycle-wallet hunt (the seven-step method for finding the next 100x: a coin from a previous cycle, its "
    "earliest buyers, the ones still trading, the machines removed, what they bought since, scored — on Base here "
    "and for Solana at pronomad.duckdns.org), a trust layer that scores any x402 endpoint before an agent pays it, "
    "a 0-100 token safety score on both chains, document-to-text with OCR, a domain and email deliverability "
    "audit, a trust leaderboard of x402 sellers, "
    "a dated daily demand brief, a 13-playbook knowledge bundle and how-to SOPs. "
    "Every response states its sources and what was NOT checked. Listed on x402scan (the Coinbase Bazaar "
    "crawler picks up a subset — indexing there is selective, so we claim only what is verifiable), "
    "no API key required. Operated by a fleet of autonomous AI agents."
)

changed = []
for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip:", oa)
        continue
    doc = json.load(open(oa))
    head = description_head.replace(f"{STATS['resources']} live", f"{STATS['resources']} live")
    new_desc = head + description_body
    info = doc.setdefault("info", {})
    before = json.dumps({"d": info.get("description"), "c": info.get("contact")}, sort_keys=True)
    info["description"] = new_desc
    info["contact"] = {"email": CONTACT, "name": "XH Agents"}
    after = json.dumps({"d": info.get("description"), "c": info.get("contact")}, sort_keys=True)
    if before != after:
        shutil.copy(oa, f"{oa}.bak.{STAMP}")
        json.dump(doc, open(oa, "w"), indent=2)
        changed.append(oa)
        print(f"updated {oa}: {len(doc.get('paths') or {})} paths, resources={STATS['resources']}, "
              f"price range ${STATS['price_lo']:.2f}-${STATS['price_hi']:.2f}")
    else:
        print(f"already current: {oa}")

print("files changed:", len(changed))
if changed:
    print("\ndescription now:\n" + description_head + description_body[:200] + "…")
