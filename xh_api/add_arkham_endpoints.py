#!/usr/bin/env python3
"""Register the five arkham-intel endpoints in the discovery documents (idempotent).

Paid ($0.10 each, USDC on Base, x402 standard envelope):
  /api/arkham-intel/use-cases     role or task -> ordered call plan
  /api/arkham-intel/exchange-flow token -> pool-level inflow/outflow
  /api/arkham-intel/portfolio     address -> holdings with USD values
  /api/arkham-intel/counterparties address -> counterparties + flags
  /api/arkham-intel/trace         address -> hop-by-hop flow
Free:
  /api/arkham-intel               index of the five

Writes openapi.json and .well-known/x402 in the live docroot and the Astro source copy, with
timestamped backups. Run: python3 /home/ubuntu/prpo_ai/xh_api/add_arkham_endpoints.py
"""
import datetime
import json
import os
import shutil

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
SITE = "https://xhagents.xyz"
PRICE = "0.10"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

RESP_402 = {"description": "Payment required: x402 v2 challenge in the PAYMENT-REQUIRED header.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PaymentRequired"}}}}

SCOPE = ("Computed from public Base chain data. This is not Arkham and holds no Arkham API key: the response "
         "states its sources and an explicit not_checked list, and entity names appear only from a curated label "
         "file — otherwise addresses carry an on-chain verified interface class.")

FIVE = {
    "use-cases": {
        "summary": "Arkham-style intel — use-case router",
        "description": "Given a role (traders, builders, brokers, investigators) or a task in plain words, returns "
                       "the ordered call plan across the XH Arkham-intel endpoints, mapped to the use cases Arkham "
                       "published (inflow/outflow monitoring, portfolio monitoring, counterparty due diligence, "
                       "know-your-users, competitor analysis, AML, ransomware, darknet). " + SCOPE,
        "props": {"role": {"type": "string", "description": "traders | builders | brokers | investigators"},
                  "task": {"type": "string", "description": "Free-text description of the question."}},
        "required": [],
    },
    "exchange-flow": {
        "summary": "Arkham-style intel — pool inflow/outflow",
        "description": "Inflow/outflow for an ERC-20 token on Base, measured where it is verifiable: each of the "
                       "token's deepest pools has its own balance of the token read at two blocks, so the change, "
                       "direction (into pool = sell side, out = bought) and USD value are real numbers, with the "
                       "pool's price move from slot0 where the pool exposes it. Pools that cannot be read are "
                       "listed with the reason. " + SCOPE,
        "props": {"token": {"type": "string", "description": "ERC-20 address on Base."},
                  "hours": {"type": "integer", "minimum": 1, "maximum": 24, "description": "Lookback window."}},
        "required": ["token"],
    },
    "portfolio": {
        "summary": "Arkham-style intel — wallet portfolio snapshot",
        "description": "Holdings of a Base wallet with USD values at request time (native + the ERC-20s you name), "
                       "each token's verified class, and the totals. A snapshot, not a historical curve. " + SCOPE,
        "props": {"address": {"type": "string"}, "tokens": {"type": "array", "items": {"type": "string"}},
                  "hours": {"type": "integer"}},
        "required": ["address"],
    },
    "counterparties": {
        "summary": "Arkham-style intel — counterparty due diligence",
        "description": "Who an address transacts with in a window: counterparties ranked by USD volume and transfer "
                       "count, each with an on-chain verified class, first/last seen, and a flag only when the "
                       "curated label file marks it. An empty flag list means nothing is curated, never 'clean'. " + SCOPE,
        "props": {"address": {"type": "string"}, "hours": {"type": "integer"}, "limit": {"type": "integer"}},
        "required": ["address"],
    },
    "trace": {
        "summary": "Arkham-style intel — fund trace for investigations",
        "description": "Hop-by-hop follow of USDC outflows from an address (up to 3 hops) with each destination's "
                       "verified class, curated labels and flagged venues on the path. Evidence with an explicit "
                       "boundary: not an attribution or sanctions product. " + SCOPE,
        "props": {"address": {"type": "string"}, "hops": {"type": "integer", "minimum": 1, "maximum": 3},
                  "hours": {"type": "integer"}},
        "required": ["address"],
    },
}

NEW_PATHS = {"/api/arkham-intel": {"get": {
    "summary": "Arkham-style intel — free index",
    "description": "Free: the five arkham-intel endpoints, their prices, the sources they use and what they do not check.",
    "operationId": "arkham-intel-index",
    "responses": {"200": {"description": "Endpoint list, price, methodology and limits.",
                          "content": {"application/json": {"schema": {"type": "object"}}}}}}}}

for slug, spec in FIVE.items():
    NEW_PATHS[f"/api/arkham-intel/{slug}"] = {"post": {
        "summary": spec["summary"],
        "description": spec["description"],
        "operationId": "arkham-intel-" + slug,
        "security": [{"x402Payment": []}],
        "x-payment-info": {"protocols": ["x402"],
                           "price": {"mode": "fixed", "currency": "USD", "amount": PRICE},
                           "network": "eip155:8453", "asset": "USDC"},
        "requestBody": {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "properties": spec["props"], "required": spec["required"]}}}},
        "responses": {"402": RESP_402,
                      "200": {"description": "The intel payload, with methodology and not_checked.",
                              "content": {"application/json": {"schema": {"type": "object"}}}},
                      "400": {"description": "Invalid address/token."}},
    }}

changed = []
for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip:", oa)
        continue
    doc = json.load(open(oa))
    before = json.dumps(doc["paths"], sort_keys=True)
    doc["paths"].update(NEW_PATHS)
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
    for slug in FIVE:
        url = f"{SITE}/api/arkham-intel/{slug}"
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
