#!/usr/bin/env python3
"""Register the daily-drop endpoints in the discovery documents (idempotent).

  /api/daily-drop          $0.03  dated daily brief (paid, x402)
  /api/daily-drop/preview   free  teaser: today's headline + counts

Writes openapi.json and .well-known/x402 in the live docroot and the Astro source copy,
with timestamped backups. Run:  python3 /home/ubuntu/prpo_ai/xh_api/add_daily_endpoints.py
"""
import datetime
import json
import os
import shutil

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
SITE = "https://xhagents.xyz"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

RESP_402 = {"description": "Payment required: x402 v2 challenge in the PAYMENT-REQUIRED header.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PaymentRequired"}}}}

NEW_PATHS = {
    "/api/daily-drop": {
        "post": {
            "summary": "XH Agents Daily Drop — dated demand brief",
            "description": "A dated brief rebuilt every day: what builders and agents are discussing and paying "
                           "for in the agent-payment economy over the last 30 days (Hacker News, GitHub, "
                           "Polymarket, marketplace listings) plus our own paid-endpoint call and settlement "
                           "numbers. Yesterday's copy is not today's product.",
            "operationId": "daily-drop",
            "security": [{"x402Payment": []}],
            "x-payment-info": {"protocols": ["x402"],
                               "price": {"mode": "fixed", "currency": "USD", "amount": "0.03"},
                               "network": "eip155:8453", "asset": "USDC"},
            "requestBody": {"required": False, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "Optional keyword filter."},
                               "window_days": {"type": "integer", "description": "Lookback window, default 30."}},
                "required": []}}}},
            "responses": {"402": RESP_402,
                          "200": {"description": "Today's brief: headline, signals, market snapshot, our stats.",
                                  "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
    },
    "/api/daily-drop/preview": {
        "get": {
            "summary": "XH Agents Daily Drop — free teaser",
            "description": "Free: today's headline, signal counts and the live price of the paid brief. "
                           "The brief itself is behind the x402 gate.",
            "operationId": "daily-drop-preview",
            "responses": {"200": {"description": "Headline, counts and how to buy.",
                                  "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
    },
}

changed = []
for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip:", oa)
        continue
    doc = json.load(open(oa))
    before = json.dumps(doc["paths"], sort_keys=True)
    for p, v in NEW_PATHS.items():
        doc["paths"][p] = v
    after = json.dumps(doc["paths"], sort_keys=True)
    if before != after:
        shutil.copy(oa, f"{oa}.bak.{STAMP}")
        json.dump(doc, open(oa, "w"), indent=2)
        changed.append(oa)
        print(f"openapi updated: {oa} ({len(doc['paths'])} paths)")
    else:
        print(f"openapi already has them: {oa}")

    wk = os.path.join(base, ".well-known", "x402")
    if not os.path.exists(wk):
        print("skip:", wk)
        continue
    man = json.load(open(wk))
    added = 0
    for p in NEW_PATHS:
        if "/preview" in p:      # the teaser is free: it does not belong in the paid manifest
            continue
        url = SITE + p
        if url not in man["resources"]:
            man["resources"].append(url)
            added += 1
    if added:
        shutil.copy(wk, f"{wk}.bak.{STAMP}")
        json.dump(man, open(wk, "w"), indent=4)
        changed.append(wk)
        print(f"well-known updated: {wk} (+{added}, total {len(man['resources'])})")
    else:
        print(f"well-known already has them: {wk}")

print("done. files changed:", len(changed))
