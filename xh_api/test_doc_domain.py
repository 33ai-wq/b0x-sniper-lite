#!/usr/bin/env python3
"""Uji nyata document_intel + domain_audit."""
import json
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
import document_intel  # noqa: E402
import domain_audit  # noqa: E402
import server  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else "doc"

if which == "doc":
    dctx = document_intel.Ctx(check_ssrf=server._check_ssrf)
    tests = [
        ("PDF arxiv", {"url": "https://arxiv.org/pdf/1706.03762"}),
        ("PDF kecil", {"url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"}),
        ("teks", {"url": "https://www.gutenberg.org/files/11/11-0.txt"}),
    ]
    for label, kw in tests:
        r = document_intel.extract(dctx, **kw)
        print(f"\n=== {label} ({kw.get('url','')[:60]})")
        if r.get("error"):
            print("    error:", r["error"][:140]); continue
        print(f"    kind={r['kind']} bytes={r['bytes']} pages={r.get('page_count')} "
              f"chars={r['text_chars']} words={r['words']} ocr_pages={r.get('ocr_pages')} "
              f"sha={r['sha256'][:12]}… {r['elapsed_ms']}ms")
        print("    cuplikan:", repr(r["text"][:160]))
else:
    actx = domain_audit.Ctx()
    for dom in ["xhagents.xyz", "google.com", "example.com"]:
        r = domain_audit.assess(actx, dom)
        print(f"\n=== {dom}: skor {r['score']} ({r['verdict']}) {r['elapsed_ms']}ms")
        print("    poin:", json.dumps(r["points"]))
        print(f"    SPF: {'ada' if r['spf'].get('record') else 'TIDAK'} (lookup={r['spf'].get('lookups')}, "
              f"all={r['spf'].get('all_qualifier')}) | DMARC: {r['dmarc'].get('policy')} | "
              f"DKIM: {[f['selector'] for f in r['dkim']['found']]}")
        print(f"    MX: {len(r['mx']['hosts'])} | TLS: {r['tls'].get('tls_version')} "
              f"exp={r['tls'].get('days_until_expiry')}d | HSTS: {bool(r['http'].get('hsts'))}")
        for f in r["findings"][:4]:
            print("    -", f[:120])
