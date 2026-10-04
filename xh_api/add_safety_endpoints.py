#!/usr/bin/env python3
"""Daftarkan /api/x402-trust dan /api/token-safety di dokumen discovery (idempotent).

Berbayar ($0.05, USDC di Base):
  POST/GET /api/x402-trust     skor kepercayaan sebuah endpoint x402 sebelum agent membayarnya
  POST/GET /api/token-safety   skor keamanan 0-100 sebuah token Base
Gratis:
  GET /api/x402-trust/method, GET /api/token-safety/method

Menulis openapi.json + .well-known/x402 di docroot live dan salinan sumber Astro, dengan backup.
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
RESP_200 = {"description": "The scored report with per-component evidence.",
            "content": {"application/json": {"schema": {"type": "object"}}}}

TRUST_DESC = (
    "Check an x402 endpoint before paying it. Give it any x402 URL: it makes the unpaid request, decodes the "
    "402 challenge, reads the origin's .well-known/x402 and openapi.json, inspects the payTo address on-chain "
    "(USDC inflows, distinct senders, EOA vs contract vs smart-wallet delegation), and returns a 0-100 trust "
    "score with pay/pay-with-caution/avoid plus the evidence and penalties behind every point. Built so an "
    "autonomous agent can refuse a seller it cannot verify.")
SAFETY_DESC = (
    "One 0-100 safety score for a Base token: liquidity on the deepest pair, top-10 holder concentration, owner "
    "powers found in the bytecode (mint/blacklist/pause/fee setters), upgradeability from the EIP-1967 slot, "
    "explorer/Sourcify verification, the creator's history, and the price impact of a small trade. Returns "
    "safe/caution/danger with every component printed. Checks that cannot be done honestly (buy/sell tax, "
    "honeypot simulation) are listed as not_checked.")

PAYINFO = {"protocols": ["x402"], "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
           "network": "eip155:8453", "asset": "USDC"}

NEW_PATHS = {
    "/api/x402-trust/method": {"get": {
        "summary": "x402 trust layer — free method index",
        "description": "Free: the weights, the verdict bands and what the check does not cover.",
        "operationId": "x402TrustMethod",
        "responses": {"200": {"description": "Weights, verdict bands and limits.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/x402-trust": {
        "post": {
            "summary": "x402 trust layer — score an endpoint before you pay it",
            "description": TRUST_DESC,
            "operationId": "x402Trust",
            "tags": ["x402", "base", "security", "trust"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The x402 endpoint an agent is about to pay"},
                    "method": {"type": "string", "description": "HTTP method the agent will use"},
                    "body": {"type": "object", "description": "JSON body the agent would send"},
                    "deep": {"type": "boolean", "description": "Also inspect payTo on-chain"}},
                "required": ["url"]}}}},
            "responses": {"402": RESP_402, "200": RESP_200, "400": {"description": "Refused (SSRF or bad URL)."}},
        },
        "get": {
            "summary": "x402 trust layer — GET form",
            "description": TRUST_DESC,
            "operationId": "x402TrustGet",
            "tags": ["x402", "base", "security", "trust"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "parameters": [{"name": "url", "in": "query", "required": True, "schema": {"type": "string"}},
                           {"name": "method", "in": "query", "required": False, "schema": {"type": "string", "default": "POST"}},
                           {"name": "deep", "in": "query", "required": False, "schema": {"type": "boolean", "default": True}}],
            "responses": {"402": RESP_402, "200": RESP_200},
        },
    },
    "/api/token-safety/method": {"get": {
        "summary": "Token safety score — free method index",
        "description": "Free: the weights, the verdict bands and what the score does not cover.",
        "operationId": "tokenSafetyMethod",
        "responses": {"200": {"description": "Weights, verdict bands and limits.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/token-safety": {
        "post": {
            "summary": "Token safety score (Base) — safe / caution / danger",
            "description": SAFETY_DESC,
            "operationId": "tokenSafety",
            "tags": ["x402", "base", "security", "token"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"token": {"type": "string", "description": "Base token contract address"}},
                "required": ["token"]}}}},
            "responses": {"402": RESP_402, "200": RESP_200, "400": {"description": "Not a Base address."}},
        },
        "get": {
            "summary": "Token safety score (Base) — GET form",
            "description": SAFETY_DESC,
            "operationId": "tokenSafetyGet",
            "tags": ["x402", "base", "security", "token"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "parameters": [{"name": "token", "in": "query", "required": True,
                            "schema": {"type": "string", "pattern": "^0x[a-fA-F0-9]{40}$"}}],
            "responses": {"402": RESP_402, "200": RESP_200},
        },
    },
}

RESOURCES = [f"{SITE}/api/x402-trust", f"{SITE}/api/token-safety"]
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
