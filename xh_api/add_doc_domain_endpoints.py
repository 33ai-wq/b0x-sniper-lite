#!/usr/bin/env python3
"""Daftarkan /api/document-extract dan /api/domain-audit di dokumen discovery (idempotent).

Berbayar ($0.05, USDC di Base):
  POST/GET /api/document-extract  PDF/gambar/DOCX/HTML -> teks (native + OCR)
  POST/GET /api/domain-audit      audit SPF/DMARC/DKIM/MX/TLS/header, skor 0-100
Gratis:
  GET /api/document-extract/method, GET /api/domain-audit/method
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
RESP_200 = {"description": "The result with per-item evidence.",
            "content": {"application/json": {"schema": {"type": "object"}}}}

DOC_DESC = (
    "Document to text. Send a public URL or the file's base64: PDF (native text, with an OCR fallback for "
    "scanned pages), an image (PNG/JPEG/WEBP via OCR), DOCX, HTML or plain text. Returns the text, the method "
    "used per page, page and word counts, the sha256 of the exact bytes read, and an honest list of what was not "
    "extracted (tables are flattened, charts are ignored, OCR is English). Runs on the seller's own machine with "
    "pymupdf and tesseract, so there is no per-page third-party fee and the document is not stored.")
DOMAIN_DESC = (
    "Domain and email deliverability audit, scored 0-100. Measures live: SPF (mechanisms parsed against the "
    "RFC 7208 lookup limit), DMARC (policy, pct, rua, alignment), DKIM on the common selectors (with wildcard "
    "detection so an empty-p= blanket answer is not counted as a key), MX (including null MX per RFC 7505), the "
    "TLS certificate from a real handshake, and web hygiene (HTTP-to-HTTPS redirect, HSTS, security headers). "
    "Returns the score, every component with its evidence, and what was not checked (blocklists, inbox placement).")

PAYINFO = {"protocols": ["x402"], "price": {"mode": "fixed", "currency": "USD", "amount": "0.05"},
           "network": "eip155:8453", "asset": "USDC"}

DOC_BODY = {"type": "object",
            "properties": {"url": {"type": "string", "description": "Public URL of the document"},
                           "base64": {"type": "string", "description": "The document bytes, base64"},
                           "filename": {"type": "string", "description": "Optional name hint (.pdf, .docx…)"},
                           "ocr": {"type": "boolean", "default": True},
                           "max_chars": {"type": "integer", "default": 60000}},
            "required": []}
DOMAIN_BODY = {"type": "object",
               "properties": {"domain": {"type": "string", "description": "Domain to audit, e.g. example.com"}},
               "required": ["domain"]}

NEW_PATHS = {
    "/api/document-extract/method": {"get": {
        "summary": "Document to text — free method index",
        "description": "Free: supported formats, limits and what is not extracted.",
        "operationId": "documentExtractMethod",
        "responses": {"200": {"description": "Formats, limits, methodology.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/document-extract": {
        "post": {
            "summary": "Document to text (PDF, scans, images, DOCX, HTML)",
            "description": DOC_DESC,
            "operationId": "documentExtract",
            "tags": ["x402", "base", "documents", "ocr"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": DOC_BODY}}},
            "responses": {"402": RESP_402, "200": RESP_200,
                          "400": {"description": "No url/base64, or the fetch was refused."}},
        },
        "get": {
            "summary": "Document to text — GET form",
            "description": DOC_DESC,
            "operationId": "documentExtractGet",
            "tags": ["x402", "base", "documents", "ocr"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "parameters": [{"name": "url", "in": "query", "required": True, "schema": {"type": "string"}},
                           {"name": "ocr", "in": "query", "required": False,
                            "schema": {"type": "boolean", "default": True}},
                           {"name": "max_chars", "in": "query", "required": False,
                            "schema": {"type": "integer", "default": 60000}}],
            "responses": {"402": RESP_402, "200": RESP_200},
        },
    },
    "/api/domain-audit/method": {"get": {
        "summary": "Domain & email audit — free method index",
        "description": "Free: the weights, the verdict bands and what the audit does not cover.",
        "operationId": "domainAuditMethod",
        "responses": {"200": {"description": "Weights, verdict bands, limits.",
                              "content": {"application/json": {"schema": {"type": "object"}}}}}}},
    "/api/domain-audit": {
        "post": {
            "summary": "Domain & email audit — SPF, DMARC, DKIM, MX, TLS, headers",
            "description": DOMAIN_DESC,
            "operationId": "domainAudit",
            "tags": ["x402", "base", "email", "dns", "security"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "requestBody": {"required": True, "content": {"application/json": {"schema": DOMAIN_BODY}}},
            "responses": {"402": RESP_402, "200": RESP_200,
                          "400": {"description": "Not a valid domain name."}},
        },
        "get": {
            "summary": "Domain & email audit — GET form",
            "description": DOMAIN_DESC,
            "operationId": "domainAuditGet",
            "tags": ["x402", "base", "email", "dns", "security"],
            "security": [{"x402Payment": []}],
            "x-payment-info": PAYINFO,
            "parameters": [{"name": "domain", "in": "query", "required": True, "schema": {"type": "string"}}],
            "responses": {"402": RESP_402, "200": RESP_200},
        },
    },
}

RESOURCES = [f"{SITE}/api/document-extract", f"{SITE}/api/domain-audit"]
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
