"""Regenerate the how-to entries in both discovery documents from xh_api/howto/*.json.

Run after adding or editing an SOP:
    python3 /home/ubuntu/prpo_ai/xh_api/sync_discovery.py
Idempotent: rewrites the /api/howto/<slug> paths in openapi.json and adds each URL to
.well-known/x402, for the live docroot and the Astro source copy, with timestamped backups.
"""
import json, os, shutil, datetime

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
HOWTO_DIR = "/home/ubuntu/prpo_ai/xh_api/howto"

sops = {}
for name in sorted(os.listdir(HOWTO_DIR)):
    if not name.endswith(".json"):
        continue
    with open(os.path.join(HOWTO_DIR, name)) as fh:
        doc = json.load(fh)
    if doc.get("slug"):
        sops[doc["slug"]] = doc

example_slug = next(iter(sops), "youtube-auto-ai")
req_schema = {"type": "object",
              "properties": {"sop": {"type": "string", "example": example_slug}},
              "required": []}
step_schema = {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "do": {"type": "string"}, "cmd": {"type": "string"}}}}
sop_schema = {"type": "object", "properties": {
    "slug": {"type": "string", "example": example_slug},
    "title": {"type": "string"},
    "summary": {"type": "string"},
    "prerequisites": {"type": "array", "items": {"type": "string"}},
    "steps": step_schema,
    "pitfalls": {"type": "array", "items": {"type": "string"}},
    "verify": {"type": "array", "items": {"type": "string"}},
    "files": {"type": "array", "items": {"type": "string"}}}}
resp_402 = {"description": "Payment required: x402 v2 challenge in the PAYMENT-REQUIRED header.",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PaymentRequired"}}}}
index_schema = {"type": "object", "properties": {
    "sops_total": {"type": "integer", "example": len(sops)},
    "sops": {"type": "array", "items": {"type": "object", "properties": {
        "slug": {"type": "string"}, "title": {"type": "string"},
        "price_usdc": {"type": "number"}}}}}}

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
changed = []

for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip:", oa)
        continue
    with open(oa) as fh:
        doc = json.load(fh)
    before = json.dumps({k: v for k, v in doc["paths"].items() if k.startswith("/api/howto")}, sort_keys=True)

    for slug, s in sops.items():
        info = {"protocols": ["x402"],
                "price": {"mode": "fixed", "currency": "USD", "amount": f"{float(s.get('price_usdc', 0.1)):.2f}"},
                "network": "eip155:8453", "asset": "USDC"}
        doc["paths"][f"/api/howto/{slug}"] = {
            "get": {
                "summary": f"GET — {s['title']}",
                "description": s.get("summary", ""),
                "operationId": f"howto-{slug}-get",
                "security": [{"x402Payment": []}],
                "x-payment-info": info,
                "parameters": [{"name": "sop", "in": "query", "required": False,
                                "schema": {"type": "string", "example": slug}}],
                "responses": {"402": resp_402,
                              "200": {"description": "The SOP.",
                                      "content": {"application/json": {"schema": sop_schema}}}},
            },
            "post": {
                "summary": f"POST — {s['title']}",
                "description": s.get("summary", ""),
                "operationId": f"howto-{slug}-post",
                "security": [{"x402Payment": []}],
                "x-payment-info": info,
                "requestBody": {"required": False, "content": {"application/json": {"schema": req_schema}}},
                "responses": {"402": resp_402,
                              "200": {"description": "The SOP.",
                                      "content": {"application/json": {"schema": sop_schema}}}},
            },
        }
    doc["paths"]["/api/howto"] = {
        "get": {"summary": "How-To index (free)",
                "description": "Lists every SOP with its slug, title and price. No payment required.",
                "operationId": "howto-index",
                "responses": {"200": {"description": "SOP index.",
                                      "content": {"application/json": {"schema": index_schema}}}}}
    }

    after = json.dumps({k: v for k, v in doc["paths"].items() if k.startswith("/api/howto")}, sort_keys=True)
    if before != after:
        shutil.copy(oa, f"{oa}.bak.{stamp}")
        with open(oa, "w") as fh:
            json.dump(doc, fh, indent=2)
        changed.append(oa)
        print(f"openapi diperbarui: {oa} ({len(sops)} SOP, total path {len(doc['paths'])})")
    else:
        print(f"openapi sudah sinkron: {oa}")

    wk = os.path.join(base, ".well-known", "x402")
    if not os.path.exists(wk):
        print("skip:", wk)
        continue
    with open(wk) as fh:
        man = json.load(fh)
    added = 0
    for slug in sops:
        url = f"https://xhagents.xyz/api/howto/{slug}"
        if url not in man["resources"]:
            man["resources"].append(url)
            added += 1
    if added:
        shutil.copy(wk, f"{wk}.bak.{stamp}")
        with open(wk, "w") as fh:
            json.dump(man, fh, indent=4)
        changed.append(wk)
        print(f"well-known diperbarui: {wk} (+{added}, total {len(man['resources'])})")
    else:
        print(f"well-known sudah sinkron: {wk}")

print("selesai. berkas berubah:", len(changed))
