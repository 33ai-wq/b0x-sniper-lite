#!/usr/bin/env python3
"""Daftarkan /api/trust-leaderboard di dokumen discovery (idempotent)."""
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
RESP_200 = {"description": "The ranking with the evidence behind each score.",
            "content": {"application/json": {"schema": {"type": "object"}}}}

LB_DESC = (
    "The x402 seller trust leaderboard. We sweep the public x402 catalogue, take one representative endpoint "
    "per origin, and score it with the same trust layer sold as /api/x402-trust: unpaid 402 behaviour, challenge "
    "conformance, discovery documents, on-chain payTo reputation and price sanity. Returns the ranking (best or "
    "worst first), the verdict spread across the whole sweep, the most common reasons points were lost, and the "
    "timestamp each row was checked at. Point-in-time and outside-in: not an audit and not an endorsement.")

PAYINFO = {"protocols": ["x402"], "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
           "network": "eip155:8453", "asset": "USDC"}

BODY = {"type": "object",
        "properties": {"limit": {"type": "integer", "default": 50},
                       "verdict": {"type": "string", "description": "pay | pay_with_caution | avoid"},
                       "min_score": {"type": "number"}, "max_score": {"type": "number"},
                       "origin": {"type": "string"}, "order": {"type": "string", "default": "best"},
                       "include_findings": {"type": "boolean", "default": True}},
        "required": []}

NEW_PATHS = {
    "/api/trust-leaderboard/method": {"get": {
        "summary": "x402 trust leaderboard — free method index and top ten",
        "description": "Free: coverage, score statistics, the most common penalties and a preview of the top ten.",
        "operationId": "trustLeaderboardMethod",
        "responses": {"200": {"description": "Coverage, statistics, preview.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/trust-leaderboard": {
        "post": {
            "summary": "x402 seller trust leaderboard — ranked origins",
            "description": LB_DESC,
            "operationId": "trustLeaderboard",
            "tags": ["x402", "base", "trust", "leaderboard", "security"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": BODY}}},
            "responses": {"402": RESP_402, "200": RESP_200},
        },
        "get": {
            "summary": "x402 seller trust leaderboard — GET form",
            "description": LB_DESC,
            "operationId": "trustLeaderboardGet",
            "tags": ["x402", "base", "trust", "leaderboard", "security"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                           {"name": "verdict", "in": "query", "schema": {"type": "string"}},
                           {"name": "min_score", "in": "query", "schema": {"type": "number"}},
                           {"name": "max_score", "in": "query", "schema": {"type": "number"}},
                           {"name": "origin", "in": "query", "schema": {"type": "string"}},
                           {"name": "order", "in": "query", "schema": {"type": "string", "default": "best"}}],
            "responses": {"402": RESP_402, "200": RESP_200},
        },
    },
}

RESOURCES = [f"{SITE}/api/trust-leaderboard"]
changed = []
for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip:", oa)
        continue
    doc = json.load(open(oa))
    before = json.dumps(doc["paths"], sort_keys=True)
    doc["paths"].update(NEW_PATHS)
    if before != json.dumps(doc["paths"], sort_keys=True):
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
    for url in RESOURCES:
        if url not in man["resources"]:
            man["resources"].append(url)
            added += 1
    if added:
        shutil.copy(wk, f"{wk}.bak.{STAMP}")
        json.dump(man, open(wk, "w"), indent=4)
        changed.append(wk)
        print(f"well-known updated: {wk} (+{added}, total {len(man['resources'])})")
    else:
        print(f"well-known already has them: {wk} ({len(man['resources'])} resources)")

print("done. files changed:", len(changed))
