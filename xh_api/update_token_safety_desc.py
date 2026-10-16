"""Samakan deskripsi /api/token-safety di openapi.json + .well-known/x402 (docroot + salinan sumber).

Aman: setiap entri LAIN harus byte-identik sebelum & sesudah; backup ditulis DI LUAR docroot.
"""
import datetime
import json
import os
import shutil

DOCROOT = "/var/www/xhagents-www"
SRC = "/home/ubuntu/xhagents-web/public"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BK = f"/home/ubuntu/backups/xh-token-safety-desc-{STAMP}"
URL = "https://xhagents.xyz/api/token-safety"

NEW_DESC = (
    "One 0-100 safety score for a Base token before an agent buys: liquidity, top-10 holder concentration, "
    "owner powers in the bytecode, upgradeability (EIP-1967), explorer/Sourcify verification, creator "
    "history, small-trade price impact. Verdicts: safe/caution/danger per component, unknown when a check "
    "could not run, and not_a_token with no score when the address deploys no code.")
NEW_SUMMARY_POST = "Token safety score (Base) — safe / caution / danger, or not_a_token with no score"
NEW_SUMMARY_GET = "Token safety score (Base) — GET form"

os.makedirs(BK, exist_ok=True)
changed = []

for base in (DOCROOT, SRC):
    oa = os.path.join(base, "openapi.json")
    if not os.path.exists(oa):
        print("skip (tidak ada):", oa)
        continue
    doc = json.load(open(oa))
    before = json.dumps(doc, sort_keys=True)
    path = doc["paths"].get("/api/token-safety")
    if not path:
        print("skip (path tidak ada):", oa)
        continue
    old = path["post"]["description"]
    if old == NEW_DESC and path["post"].get("summary") == NEW_SUMMARY_POST:
        print("sudah sinkron:", oa)
        continue
    path["post"]["description"] = NEW_DESC
    path["post"]["summary"] = NEW_SUMMARY_POST
    if "get" in path:
        path["get"]["description"] = NEW_DESC
        path["get"]["summary"] = NEW_SUMMARY_GET
    after = json.dumps(doc, sort_keys=True)
    # assert: HANYA deskripsi/summary token-safety yang berubah
    doc2 = json.loads(after)
    doc_before = json.loads(before)
    doc2["paths"]["/api/token-safety"] = doc_before["paths"]["/api/token-safety"]
    assert json.dumps(doc2, sort_keys=True) == before, "ada perubahan lain di luar token-safety!"
    shutil.copy(oa, os.path.join(BK, os.path.basename(base) + "-openapi.json"))
    with open(oa, "w") as fh:
        json.dump(doc, fh, indent=2)
    json.load(open(oa))  # re-parse sebelum dianggap selesai
    print(f"openapi diperbarui: {oa} (desc {len(old)} -> {len(NEW_DESC)} char)")
    changed.append(oa)

    wk = os.path.join(base, ".well-known", "x402")
    if not os.path.exists(wk):
        print("skip:", wk)
        continue
    man = json.load(open(wk))
    before_wk = json.dumps(man, sort_keys=True)
    hit = 0
    for e in man.get("entries", []):
        if (e.get("resource") or {}).get("url") == URL:
            old_d = e["resource"]["description"]
            e["resource"]["description"] = NEW_DESC[:195] + "..."
            print(f"  entri manifest: {len(old_d)} -> {len(e['resource']['description'])} char")
            hit += 1
    if not hit:
        print("  (tidak ada entri manifest untuk", URL, ")")
        continue
    # assert: hanya entri itu yang berubah
    man2 = json.loads(json.dumps(man, sort_keys=True))
    man_before = json.loads(before_wk)
    for a, b in zip(man2.get("entries", []), man_before.get("entries", [])):
        if (a.get("resource") or {}).get("url") == URL:
            b["resource"]["description"] = a["resource"]["description"]
    assert json.dumps(man2, sort_keys=True) == json.dumps(man_before, sort_keys=True), \
        "ada perubahan lain di luar entri token-safety!"
    shutil.copy(wk, os.path.join(BK, os.path.basename(base) + "-well-known-x402"))
    with open(wk, "w") as fh:
        json.dump(man, fh, indent=4)
    json.load(open(wk))
    print(f"well-known diperbarui: {wk} ({len(man['resources'])} resources)")
    changed.append(wk)

print("\nbackup:", BK)
print("berkas berubah:", len(changed))
