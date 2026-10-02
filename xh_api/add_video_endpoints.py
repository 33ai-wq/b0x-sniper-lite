#!/usr/bin/env python3
"""Register the Ataraxia video-licence endpoint in the discovery documents (idempotent).

  /api/video-license        $0.10  one film master, signed stream URL (paid, x402)
  /api/video-stream/<token>  free  the stream itself; the signed token is the credential

Writes openapi.json and .well-known/x402 in the live docroot and the Astro source copy, with
timestamped backups. Run:  python3 /home/ubuntu/prpo_ai/xh_api/add_video_endpoints.py
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

DESCRIPTION = (
    "Licence one of the four XH Animations masters from Ataraxia: 109 seconds of 21x-extended looping "
    "ambient footage, delivered as a time-limited signed URL with HTTP Range support, so an agent can "
    "stream or download exactly the seconds it needs. Pick a video_id from GET /api/video-license (free); "
    "the paid response carries byte size and sha256 so the download can be verified. Priced at the same "
    "$0.10 a human viewer pays on the site, settled in USDC on Base, and 25% of what the room takes in is "
    "credited back to the wallets that paid."
)

NEW_PATHS = {
    "/api/video-license": {
        "get": {
            "summary": "XH Animations video licence — free menu",
            "description": "Free: the four films that can be licensed, their duration, byte size, sha256, "
                           "the price and the exact POST body to send. Use this to choose a video_id before paying.",
            "operationId": "video-license-menu",
            "responses": {"200": {"description": "Films, price and how to buy.",
                                  "content": {"application/json": {"schema": {"type": "object"}}}}},
        },
        "post": {
            "summary": "XH Animations video licence — one film master",
            "description": DESCRIPTION,
            "operationId": "video-license",
            "security": [{"x402Payment": []}],
            "x-payment-info": {"protocols": ["x402"],
                               "price": {"mode": "fixed", "currency": "USD", "amount": PRICE},
                               "network": "eip155:8453", "asset": "USDC"},
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"video_id": {"type": "string",
                                            "description": "One of the ids from GET /api/video-license."}},
                "required": ["video_id"]}}}},
            "responses": {"402": RESP_402,
                          "200": {"description": "The licence: signed stream_url, expiry, bytes and sha256.",
                                  "content": {"application/json": {"schema": {"type": "object"}}}},
                          "404": {"description": "Unknown video_id; the body lists the available ids."}},
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
    for p, v in NEW_PATHS.items():
        doc["paths"][p] = v
    after = json.dumps(doc["paths"], sort_keys=True)
    if before != after:
        shutil.copy(oa, f"{oa}.bak.{STAMP}")
        json.dump(doc, open(oa, "w"), indent=2)
        changed.append(oa)
        print(f"openapi updated: {oa} ({len(doc['paths'])} paths)")
    else:
        print(f"openapi already has it: {oa}")

    wk = os.path.join(base, ".well-known", "x402")
    if not os.path.exists(wk):
        print("skip:", wk)
        continue
    man = json.load(open(wk))
    url = SITE + "/api/video-license"
    if url in man["resources"]:
        print(f"well-known already has it: {wk}")
    else:
        shutil.copy(wk, f"{wk}.bak.{STAMP}")
        man["resources"].append(url)
        json.dump(man, open(wk, "w"), indent=4)
        changed.append(wk)
        print(f"well-known updated: {wk} (+1, total {len(man['resources'])})")

print("done. files changed:", len(changed))
