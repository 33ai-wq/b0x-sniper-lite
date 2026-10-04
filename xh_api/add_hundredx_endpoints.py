#!/usr/bin/env python3
"""Register the cycle-wallet hunt endpoint (Base side) in the discovery documents (idempotent).

Paid ($0.15, USDC on Base, x402 standard envelope):
  POST /api/hundred-x-hunter        the seven-step hunt for one token from a previous cycle
  GET  /api/hundred-x-hunter        same product, query-string form (crawlers probe GET first)
Free:
  GET  /api/hundred-x-hunter/method the method itself, the threshold and the limits

Sibling on Solana (same method, settled in USDC on Solana): POST /v1/hundred-x-hunter at
https://pronomad.duckdns.org — registered in that worker's own discovery document.

Writes openapi.json and .well-known/x402 in the live docroot and the Astro source copy, with timestamped
backups. Run: python3 /home/ubuntu/prpo_ai/xh_api/add_hundredx_endpoints.py
"""
import datetime
import json
import os
import shutil

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
SITE = "https://xhagents.xyz"
PRICE = "0.15"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

RESP_402 = {"description": "Payment required: x402 v2 challenge in the PAYMENT-REQUIRED header.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PaymentRequired"}}}}

DESC = (
    "The seven-step cycle-wallet hunt on Base. Give it a coin from a previous cycle and it does the work the "
    "method describes: reads that token's earliest transfers and lists its first buyers, keeps only the wallets "
    "that traded in the last N days, drops the machines (any wallet whose own transfers of the token are under "
    "a minute apart), reads what the survivors bought since and whether they still hold it, finds the tokens "
    "that appear in several of those wallets, then scores every candidate on a published rubric and returns "
    "buy/watch/reject. Below the threshold the answer is no, however profitable the wallets were. Every number "
    "is computed from Base chain data (Alchemy indexer + public RPC + DexScreener); steps that could not be "
    "completed are listed in not_checked instead of being invented."
)

PROPS = {
    "token": {"type": "string", "description": "Base contract address of a coin from a previous cycle."},
    "window_days": {"type": "integer", "minimum": 1, "maximum": 180, "description": "Activity window in days."},
    "min_wallets": {"type": "integer", "minimum": 2, "maximum": 10,
                    "description": "How many surviving wallets must hold a token for it to be a signal."},
    "limit": {"type": "integer", "minimum": 1, "maximum": 60},
}

RESP_200 = {"description": "The seven steps with their evidence, the scored candidates and the decision.",
            "content": {"application/json": {"schema": {"type": "object"}}}}

PAYMENT_INFO = {"protocols": ["x402"],
                "price": {"mode": "fixed", "currency": "USD", "amount": PRICE},
                "network": "eip155:8453", "asset": "USDC"}

PARAM_LIST = [
    {"name": "token", "in": "query", "required": True,
     "schema": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"}},
    {"name": "window_days", "in": "query", "required": False, "schema": {"type": "integer", "default": 30}},
    {"name": "min_wallets", "in": "query", "required": False, "schema": {"type": "integer", "default": 3}},
    {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 25}},
]

NEW_PATHS = {
    "/api/hundred-x-hunter/method": {"get": {
        "summary": "Cycle-wallet hunt — free method index",
        "description": ("Free: the seven steps, the scoring rubric, the threshold (9 of 10), the chains this "
                        "method is served on and what it does not check."),
        "operationId": "hundredXHunterMethod",
        "responses": {"200": {"description": "Method, rubric, threshold and limits.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/hundred-x-hunter": {
        "post": {
            "summary": "XH cycle-wallet hunt (seven-step 'next 100x' method)",
            "description": DESC,
            "operationId": "hundredXHunter",
            "tags": ["x402", "base", "data", "meme-coins"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYMENT_INFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "properties": PROPS, "required": ["token"]}}}},
            "responses": {"402": RESP_402, "200": RESP_200,
                          "400": {"description": "token is not a Base contract address."}},
        },
        "get": {
            "summary": "XH cycle-wallet hunt — GET form",
            "description": DESC,
            "operationId": "hundredXHunterGet",
            "tags": ["x402", "base", "data", "meme-coins"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYMENT_INFO,
            "parameters": PARAM_LIST,
            "responses": {"402": RESP_402, "200": RESP_200,
                          "400": {"description": "token is not a Base contract address."}},
        },
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
    url = f"{SITE}/api/hundred-x-hunter"
    if url not in man["resources"]:
        shutil.copy(wk, f"{wk}.bak.{STAMP}")
        man["resources"].append(url)
        json.dump(man, open(wk, "w"), indent=4)
        changed.append(wk)
        print(f"well-known updated: {wk} (+1, total {len(man['resources'])})")
    else:
        print(f"well-known already has it: {wk} ({len(man['resources'])} resources)")

print("done. files changed:", len(changed))
