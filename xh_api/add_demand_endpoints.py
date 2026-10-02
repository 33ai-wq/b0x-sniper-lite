#!/usr/bin/env python3
"""Register the three demand-priced endpoints in the discovery documents.

Adds (idempotently) to openapi.json and .well-known/x402, for the live docroot and the
Astro source copy, with timestamped backups:

  /api/web-search      $0.25  Web search + page content retrieval
  /api/company-enrich  $0.05  People & company enrichment
  /api/social-data     $0.05  Social media data (X/Twitter + LinkedIn)

Run:  python3 /home/ubuntu/prpo_ai/xh_api/add_demand_endpoints.py
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
    "/api/web-search": {
        "post": {
            "summary": "Web search + page content retrieval",
            "description": "Runs a live web search and returns ranked results (title, URL, domain, snippet), "
                           "then fetches the top pages and returns their extracted readable text. Content "
                           "retrieval, not just links.",
            "operationId": "web-search",
            "security": [{"x402Payment": []}],
            "x-payment-info": {"protocols": ["x402"],
                               "price": {"mode": "fixed", "currency": "USD", "amount": "0.25"},
                               "network": "eip155:8453", "asset": "USDC"},
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"query": {"type": "string"},
                               "max_results": {"type": "integer", "description": "1-10, default 5."},
                               "fetch_pages": {"type": "integer", "description": "0-5, default 3."},
                               "extract_chars": {"type": "integer", "description": "200-6000 per page."}},
                "required": ["query"]}}}},
            "responses": {"402": RESP_402, "200": {"description": "Ranked results plus retrieved page text.",
                                                   "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
    },
    "/api/company-enrich": {
        "post": {
            "summary": "People & company enrichment",
            "description": "Enriches a company, domain or person from public structured sources (Wikidata, the "
                           "public LinkedIn company page, Clearbit autocomplete): industry, size, headquarters, "
                           "founding year, official website, stock listing and social handles.",
            "operationId": "company-enrich",
            "security": [{"x402Payment": []}],
            "x-payment-info": {"protocols": ["x402"],
                               "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
                               "network": "eip155:8453", "asset": "USDC"},
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"company": {"type": "string"}, "domain": {"type": "string"},
                               "person": {"type": "string"}},
                "required": []}}}},
            "responses": {"402": RESP_402, "200": {"description": "Resolved identity, company/person profile and sources.",
                                                   "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
    },
    "/api/social-data": {
        "post": {
            "summary": "Social media data (X/Twitter + LinkedIn)",
            "description": "Pulls one X/Twitter post by URL or id (text, author, metrics, language) and/or a public "
                           "LinkedIn company page (industry, size, headquarters, specialties, followers).",
            "operationId": "social-data",
            "security": [{"x402Payment": []}],
            "x-payment-info": {"protocols": ["x402"],
                               "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
                               "network": "eip155:8453", "asset": "USDC"},
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"x_tweet": {"type": "string"}, "x_username": {"type": "string"},
                               "linkedin": {"type": "string"}},
                "required": []}}}},
            "responses": {"402": RESP_402, "200": {"description": "Structured post/profile data with sources.",
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
