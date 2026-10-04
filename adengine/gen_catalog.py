#!/usr/bin/env python3
"""Build the XH Agents endpoint catalogue for the public site.

Two renderings from one dataset:
  homepage (#status)  — compact: live stats + one button per category, each opening a modal
                        that lists that category's endpoints as links. No prices on the page.
  endpoints.html      — the same catalogue fully visible (better for search engines), one
                        anchored section per endpoint. No prices either.

Prices deliberately stay OUT of the human pages: an agent reads the exact price from the 402
challenge and from /openapi.json, which is where a machine needs it.

Inputs:
  /var/www/xhagents-www/openapi.json                  paid operations, summaries
  /home/ubuntu/prpo_ai/xh_api/howto/*.json            how-to SOPs (title, summary, counts, tags)
  /home/ubuntu/prpo_ai/xh_api/bundles/xh_bundle.json  playbook bundle
Outputs: index.html block, endpoints.html, sitemap.xml (+ copies beside the Astro source)

Run: python3 /home/ubuntu/prpo_ai/adengine/gen_catalog.py
"""
import html
import json
import os
import re
import shutil
from datetime import datetime, timezone

DOCROOT = "/var/www/xhagents-www"
SRC_MIRROR = "/home/ubuntu/xhagents-web/public"
OPENAPI = os.path.join(DOCROOT, "openapi.json")
HOWTO_DIR = "/home/ubuntu/prpo_ai/xh_api/howto"
BUNDLE = "/home/ubuntu/prpo_ai/xh_api/bundles/xh_bundle.json"
SITE = "https://xhagents.xyz"
STAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d")

SAMPLES = {
    "/api/wallet-profile": '{"address":"0x6cb53f00…","chain_id":8453,"is_contract":true,\n "balance_usdc":"2.000000","nonce":1,"recent_usdc_transfers":6}',
    "/api/gas-tracker": '{"chain":"base","block_number":51880546,"base_fee_gwei":0.005,\n "priority_fee_gwei":{"low":0.001,"medium":0.002,"high":0.005},\n "usd_estimate":{"transfer_21000":"0.0001","erc20_transfer_65000":"0.0003"}}',
    "/api/token-check": '{"token":"0x833589fcd…","is_contract":true,"name":"USD Coin","symbol":"USDC",\n "decimals":6,"is_proxy":false,"dex":{"liquidity_usd":296000000.0},\n "not_checked":["honeypot simulation","holder concentration"]}',
    "/api/x402-check": '{"url":"https://xhagents.xyz/api/kb/ask","reachable":true,"status":402,\n "conformant":true,"x402Version":2,"failed_checks":[]}',
    "/api/payment-verify": '{"tx_hash":"0x3ddcb67f…","verified":true,"reason":"ok",\n "transfer":{"from":"0x85fc53d6…","to":"0x6cb53f00…","value_atomic":2000000,"block":51825798}}',
    "/api/defi-sentiment": '{"asset":"BTC","sentiment":"neutral","score":0.08,\n "funding_rate_8h_pct":"0.0089","open_interest_usd":412000000,\n "protocol_tvl":{"slug":"aerodrome","tvl_usd":380000000,"change_24h_pct":1.1}}',
    "/api/whale-watch": '{"token":"USDC","blocks_scanned":200,"threshold_usd":50000.0,"events_found":1240,\n "largest":[{"amount":1250000.0,"from":"0x…","to":"0x…","tx_hash":"0x…"}]}',
    "/api/x402-directory": '{"query":"gas","sources":{"coinbase-bazaar":"ok","x402-list":"ok"},"results":5,\n "endpoints":[{"url":"https://xhagents.xyz/api/gas-tracker","sources":["coinbase-bazaar","x402-list"]}]}',
    "/api/kb/ask": '{"best_match":{"id":"nginx-docroot","title":"Which docroot does nginx really serve?"},\n "matches":3}',
    "/api/chat": '{"reply":"BTC is trading near …","engine":"xh-chatengine","credits_left":1}',
    "/api/compute/xh-bundle": '{"bundle":"XH Agents — Build & Ship an x402 Paid API","version":"1.0.0",\n "items_total":13,"items_returned":13,\n "items":[{"id":"ship-x402-endpoint","title":"Ship a new x402 paid endpoint end to end"}]}',
    "/api/web-search": '{"query":"x402 paid API on Base","results_returned":5,"pages_retrieved":3,\n "results":[{"rank":1,"title":"Quickstart for Sellers - x402","domain":"docs.x402.org",\n "url":"https://docs.x402.org/getting-started/quickstart-for-seller",\n "retrieval":{"status":200,"chars_total":8123,"content":"…"}}]}',
    "/api/company-enrich": '{"query":"Coinbase","sources":["wikidata","linkedin-public","clearbit-autocomplete"],\n "resolved":{"wikidata_id":"Q16972754","industry":["cryptocurrency exchange","fintech"],\n "headquarters":"San Francisco","inception":"2012","stock_exchange":["Nasdaq"]},\n "linkedin":{"company_size":"1,001-5,000 employees","followers":1489647}}',
    "/api/social-data": '{"sources":["x-syndication","linkedin-public"],\n "x_tweet":{"id":"20","text":"just setting up my twttr","author":{"screen_name":"jack"},\n "metrics":{"likes":310997}},\n "linkedin":{"name":"Coinbase","industry":"Financial Services","headquarters":"Remote First"}}',
}

BACKUP = [
    {"slug": "backup-cf-worker", "name": "b0x402 — Cloudflare Worker",
     "base": "https://x402-cf-worker.mulberry-boar.workers.dev",
     "what": "The original x402 seller experiment at the edge: meme signals, DeFi sentiment, market "
             "equilibrium and wallet profiling.",
     "paths": ["/v1/meme-hunter", "/v1/defi-sentiment", "/v1/dinalibrium", "/v1/wallet-profile", "/health"],
     "note": "Kept online as a secondary endpoint set. The registered catalogue is the VPS-hosted API."},
    {"slug": "backup-solana-pronomad", "name": "b0x402 — Solana (pronomad)",
     "base": "https://pronomad.duckdns.org",
     "what": "The same idea on Solana mainnet: token radar and honeypot checks, settled in USDC on Solana.",
     "paths": ["/v1/meme-hunter", "/v1/defi-sentiment", "/v1/dinalibrium", "/v1/wallet-profile", "/v1/honeypot-check"],
     "note": "Secondary chain, listed so an agent knows a Solana rail exists; Base is the primary catalogue."},
]

GROUPS = {
    "data": ("Data & intelligence", "Live market, wallet, token and chain checks served from our own "
                                    "workers on Base."),
    "knowledge": ("Knowledge products", "Everything we learned shipping this, delivered in one call."),
    "playbooks": ("How-to playbooks", "Step-by-step SOPs with the commands and the failures behind them."),
    "backup": ("Secondary hosts", "Older endpoint sets we keep online: Cloudflare edge and Solana."),
}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def collect() -> dict:
    oa = load_json(OPENAPI)
    sops = {}
    for name in sorted(os.listdir(HOWTO_DIR)):
        if name.endswith(".json"):
            doc = load_json(os.path.join(HOWTO_DIR, name))
            sops[doc["slug"]] = doc
    bundle = load_json(BUNDLE)

    data, playbooks, knowledge = [], [], []
    for path, ops in oa["paths"].items():
        post, get = ops.get("post") or {}, ops.get("get") or {}
        paid = post.get("x-payment-info") or get.get("x-payment-info")
        if not paid:
            continue
        methods = [m.upper() for m in ("get", "post") if (ops.get(m) or {}).get("x-payment-info")]
        entry = {
            "path": path,
            "slug": path.strip("/").replace("/", "-"),
            "url": SITE + path,
            "methods": methods,
            "network": paid.get("network", "eip155:8453"),
            "summary": (post.get("description") or get.get("description") or "").strip(),
            "name": (post.get("summary") or get.get("summary") or path).strip(),
            "tags": [],
        }
        if path.startswith("/api/howto/"):
            sop = sops.get(path.rsplit("/", 1)[1], {})
            entry.update({"title": sop.get("title", entry["name"]),
                          "steps": len(sop.get("steps") or []),
                          "pitfalls": len(sop.get("pitfalls") or []),
                          "tags": sop.get("tags") or []})
            playbooks.append(entry)
        elif path == "/api/compute/xh-bundle":
            entry.update({"title": bundle["bundle"], "items": len(bundle["items"])})
            knowledge.append(entry)
        else:
            data.append(entry)

    order = lambda e: e["path"]
    return {"data": sorted(data, key=order), "playbooks": sorted(playbooks, key=order),
            "knowledge": sorted(knowledge, key=order),
            "total_resources": len(data) + len(playbooks) + len(knowledge)}


def entry_link(e: dict) -> str:
    """One line inside a modal list — the name is the link, the address is visible as text."""
    detail = ""
    if e.get("steps"):
        detail = f"{e['steps']} steps · {e.get('pitfalls', 0)} pitfalls"
    elif e.get("items"):
        detail = f"{e['items']} playbooks in one call"
    detail_html = f' <span class="ep-meta">{esc(detail)}</span>' if detail else ""
    return (f'          <li><a href="/endpoints.html#{esc(e["slug"])}">{esc(e.get("title") or e["name"])}</a> '
            f'<span class="ep-method">{esc(" · ".join(e["methods"]))}</span>'
            f'<code class="ep-addr">{esc(e["path"])}</code>{detail_html}</li>')


def modal(key: str, title: str, blurb: str, entries: list[dict], extra: str = "") -> str:
    items = "\n".join(entry_link(e) for e in entries)
    return f"""    <div class="ep-modal" id="ep-modal-{key}" hidden>
      <div class="ep-modal-panel" role="dialog" aria-modal="true" aria-label="{esc(title)}">
        <button class="ep-modal-close" type="button" data-close-ep aria-label="Close">✕</button>
        <p class="eyebrow">{esc(title)} · {len(entries)} endpoints</p>
        <p class="ep-meta">{esc(blurb)}</p>
        <ul class="ep-list">
{items}{extra}
        </ul>
        <p class="ep-meta">Each endpoint answers <code>402 Payment Required</code> with its own payment
          challenge and settles in USDC on Base per call — the exact price is quoted in that challenge
          (and listed in <a href="/openapi.json">openapi.json</a>). No API key, no account.</p>
      </div>
    </div>
"""


def backup_lines() -> str:
    out = ""
    for b in BACKUP:
        paths = " ".join(f'<code class="ep-addr">{esc(p)}</code>' for p in b["paths"][:4])
        out += (f'          <li><a href="/endpoints.html#{esc(b["slug"])}">{esc(b["name"])}</a> '
                f'<span class="ep-method">x402</span> {paths}</li>\n')
    return out


def jsonld(cat: dict) -> str:
    """Structured data for search engines — description and location only, no prices."""
    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "XH Agents x402 endpoint catalogue",
        "description": f"{cat['total_resources']} x402 endpoints on Base, paid per call in USDC via the "
                       f"x402 protocol, listed on x402scan (a growing subset is also picked up by the "
                       f"Coinbase Bazaar crawler — that indexing is selective and lags, so we claim only "
                       f"what is verifiable there).",
        "numberOfItems": cat["total_resources"],
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": {
                "@type": "WebAPI",
                "name": (e.get("title") or e["name"])[:110],
                "description": e["summary"][:300],
                "url": f"{SITE}/endpoints.html#{e['slug']}",
                "documentation": f"{SITE}/openapi.json",
                "provider": {"@type": "Organization", "name": "XH Agents", "url": SITE},
                "termsOfService": f"{SITE}/terms.html",
            }}
            for i, e in enumerate(cat["data"] + cat["knowledge"] + cat["playbooks"])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


CSS = """<style>
  .ep-wrap{margin-top:8px}
  .ep-lede{color:var(--text-muted);font-size:.95rem;max-width:78ch;margin:0 0 18px}
  .ep-lede a{color:var(--accent-live)}
  .ep-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:0 0 22px}
  .ep-stat{border:1px solid var(--border);background:var(--surface);border-radius:var(--radius);padding:12px 14px}
  .ep-stat .v{font-family:var(--font-mono);font-size:1.3rem;color:var(--accent-live);display:block}
  .ep-stat .l{font-size:.78rem;color:var(--text-faint);text-transform:uppercase;letter-spacing:.04em}
  .ep-stat .d{font-size:.8rem;color:var(--text-muted);display:block;margin-top:4px}
  .ep-cats{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:0 0 16px}
  .ep-cat{border:1px solid var(--border);background:var(--surface-raised);border-radius:var(--radius);padding:14px 16px;text-align:left;cursor:pointer;color:var(--text);font-family:inherit}
  .ep-cat:hover{border-color:var(--accent-live)}
  .ep-cat .n{font-family:var(--font-mono);font-size:.75rem;color:var(--accent-pay);display:block}
  .ep-cat strong{display:block;margin:4px 0 6px;font-size:.98rem}
  .ep-cat span.b{font-size:.84rem;color:var(--text-muted)}
  .ep-cat .go{font-family:var(--font-mono);font-size:.78rem;color:var(--accent-live);display:block;margin-top:8px}
  .ep-modal{position:fixed;inset:0;background:#02040ae0;display:flex;align-items:center;justify-content:center;z-index:40;padding:20px}
  .ep-modal[hidden]{display:none}
  .ep-modal-panel{background:var(--surface);border:1px solid var(--border-strong);border-radius:var(--radius);max-width:720px;width:100%;max-height:82vh;overflow-y:auto;padding:22px 24px;position:relative}
  .ep-modal-close{position:absolute;top:10px;right:12px;background:none;border:0;color:var(--text-muted);font-size:1rem;cursor:pointer}
  .ep-list{list-style:none;padding:0;margin:14px 0 0}
  .ep-list li{border-top:1px solid var(--border);padding:10px 0;font-size:.9rem}
  .ep-list li:first-child{border-top:0}
  .ep-list a{color:var(--accent-live);text-decoration:none;font-weight:500}
  .ep-list a:hover{text-decoration:underline}
  .ep-method{font-family:var(--font-mono);font-size:.7rem;color:var(--accent-pay);border:1px solid var(--border-strong);border-radius:4px;padding:1px 6px;margin-left:6px}
  .ep-addr{font-family:var(--font-mono);font-size:.74rem;color:var(--text-faint);display:inline-block;margin:4px 6px 0 0}
  .ep-meta{font-size:.8rem;color:var(--text-faint);margin:8px 0 0}
  .ep-meta a{color:var(--accent-live)}
  .ep-group-title{font-family:var(--font-mono);font-size:.82rem;color:var(--text-faint);margin:28px 0 10px;text-transform:uppercase;letter-spacing:.06em}
  .ep-card{border:1px solid var(--border);background:var(--surface);border-radius:var(--radius);padding:14px 16px;margin-bottom:12px}
  .ep-card h3{margin:8px 0 6px;font-size:1rem}
  .ep-card p{font-size:.88rem;color:var(--text-muted);margin:0 0 6px}
  .ep-card details{margin-top:8px;border-top:1px dashed var(--border);padding-top:8px}
  .ep-card summary{cursor:pointer;font-family:var(--font-mono);font-size:.78rem;color:var(--accent-live)}
  .ep-pre{font-family:var(--font-mono);font-size:.72rem;background:#070c16;border:1px solid var(--border);border-radius:4px;padding:8px 10px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;color:var(--text-muted)}
  .ep-flow{margin:6px 0 0;padding-left:20px;color:var(--text-muted);font-size:.88rem}
  .ep-flow li{margin-bottom:6px}
</style>"""

HOMEPAGE_SCRIPT = """<script>
(function () {
  var modals = document.querySelectorAll('.ep-modal');
  function closeAll() { modals.forEach(function (m) { m.hidden = true; }); }
  document.querySelectorAll('[data-open-ep]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var key = btn.getAttribute('data-open-ep');
      closeAll();
      var target = document.getElementById('ep-modal-' + key);
      if (target) target.hidden = false;
    });
  });
  document.querySelectorAll('[data-close-ep]').forEach(function (btn) {
    btn.addEventListener('click', function () { closeAll(); });
  });
  modals.forEach(function (m) {
    m.addEventListener('click', function (ev) { if (ev.target === m) closeAll(); });
  });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeAll(); });
})();
</script>"""


def homepage_block(cat: dict) -> str:
    n = cat["total_resources"]
    cats = ""
    for key in ("data", "knowledge", "playbooks", "backup"):
        title, blurb = GROUPS[key]
        count = {"data": len(cat["data"]), "knowledge": len(cat["knowledge"]),
                 "playbooks": len(cat["playbooks"]), "backup": len(BACKUP)}[key]
        cats += (f'        <button class="ep-cat" type="button" data-open-ep="{key}">'
                 f'<span class="n">{count} endpoint{"s" if count != 1 else ""}</span>'
                 f'<strong>{esc(title)}</strong><span class="b">{esc(blurb)}</span>'
                 f'<span class="go">Open list →</span></button>\n')
    modals = (modal("data", "Data & intelligence", GROUPS["data"][1], cat["data"]) +
              modal("knowledge", "Knowledge products", GROUPS["knowledge"][1], cat["knowledge"]) +
              modal("playbooks", "How-to playbooks", GROUPS["playbooks"][1], cat["playbooks"]) +
              modal("backup", "Secondary hosts", GROUPS["backup"][1], [], backup_lines()))
    return f"""<!-- CATALOG:START — generated by prpo_ai/adengine/gen_catalog.py on {STAMP}; edit the sources, not this block -->
{CSS}
<div class="ep-wrap">
  <p class="ep-lede">
    These are the <strong>{n} x402 endpoints</strong> XH Agents runs in production: our own workers answer
    with a payment challenge and settle in <strong>USDC on Base</strong> per call — no API key, no account,
    no invoice. Every resource is <strong>registered on x402scan</strong> and <strong>indexed by Coinbase
    Bazaar</strong>, so an autonomous agent can find and pay for one on its own. Browse the categories
    below (free, no sign-up) or open the <a href="/endpoints.html">full catalogue page</a>.
  </p>
  <div class="ep-stats" id="metrics-grid">
    <div class="ep-stat" data-label="Registered endpoints"><span class="v mono" id="m-endpoints">{n}</span><span class="l">Registered endpoints</span><span class="d">x402scan verified · Bazaar crawler picks up a subset</span></div>
    <div class="ep-stat" data-label="Payment rail"><span class="v mono" id="m-rail">x402 · USDC</span><span class="l">Payment rail</span><span class="d">per call on Base · quoted in the 402 challenge</span></div>
    <div class="ep-stat" data-label="Base mainnet block"><span class="v mono" id="m-block">—</span><span class="l">Base mainnet block</span><span class="d" id="m-block-note">read live, nothing cached</span></div>
    <div class="ep-stat" data-label="Secondary hosts"><span class="v mono" id="m-backup">{len(BACKUP)}</span><span class="l">Secondary hosts</span><span class="d">Cloudflare edge + Solana mainnet</span></div>
  </div>
  <p class="ep-meta" id="updated-note">Live figures refresh every few minutes from this host.</p>
  <div class="ep-cats">
{cats}  </div>
{modals}
  <p class="ep-meta">Machine-readable: <a href="/openapi.json">openapi.json</a> ·
    <a href="/.well-known/x402">.well-known/x402</a> ·
    all playbooks in one call: <a href="/endpoints.html#api-compute-xh-bundle">the bundle</a>.</p>
</div>
{HOMEPAGE_SCRIPT}
<script type="application/ld+json">{jsonld(cat)}</script>
<!-- CATALOG:END -->
"""


def endpoints_page(cat: dict) -> str:
    n = cat["total_resources"]
    sections = ""
    for key in ("data", "knowledge", "playbooks"):
        title, blurb = GROUPS[key]
        sections += f'<h2 class="ep-group-title">{esc(title)} · {len(cat[key])}</h2>\n<p class="ep-meta">{esc(blurb)}</p>\n'
        for e in cat[key]:
            method = " · ".join(e["methods"])
            sample = SAMPLES.get(e["path"], "")
            curl = (f'curl -X {e["methods"][0]} {e["url"]}' if e["methods"] == ["GET"]
                    else f'curl -X POST {e["url"]} -H \'Content-Type: application/json\' -d \'{{}}\'')
            detail = ""
            if e.get("steps"):
                detail = f"{e['steps']} steps · {e.get('pitfalls', 0)} documented pitfalls"
            elif e.get("items"):
                detail = f"{e['items']} playbooks in one call"
            sections += f"""<article class="ep-card" id="{esc(e['slug'])}">
  <span class="ep-method">{esc(method)}</span> <code class="ep-addr">{esc(e['path'])}</code>
  <h3>{esc(e.get('title') or e['name'])}</h3>
  <p>{esc(e['summary'][:280])}</p>
  {f'<p class="ep-meta">{esc(detail)}</p>' if detail else ''}
  <details><summary>Sample call and response</summary>
    <pre class="ep-pre">{esc(curl)}</pre>
    <pre class="ep-pre">{esc(sample)}</pre>
    <p class="ep-meta">An unpaid call answers <code>402</code> with the payment challenge; the price is
      quoted there and in <a href="/openapi.json">openapi.json</a>.</p>
  </details>
</article>
"""
    backup_section = f'<h2 class="ep-group-title">{esc(GROUPS["backup"][0])} · {len(BACKUP)}</h2>\n<p class="ep-meta">{esc(GROUPS["backup"][1])}</p>\n'
    for b in BACKUP:
        paths = "".join(f"<li><code>{esc(p)}</code></li>" for p in b["paths"])
        backup_section += f"""<article class="ep-card" id="{esc(b['slug'])}">
  <span class="ep-method">x402</span> <code class="ep-addr">{esc(b['base'].replace('https://', ''))}</code>
  <h3>{esc(b['name'])}</h3><p>{esc(b['what'])}</p>
  <details><summary>Endpoints on this host</summary><ul class="ep-flow">{paths}</ul>
    <p class="ep-meta">{esc(b['note'])}</p></details>
</article>
"""

    return f"""<!DOCTYPE html><html lang="en"> <head>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7552930808768657"
     crossorigin="anonymous"></script>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<title>x402 Endpoint Catalogue — {n} pay-per-call APIs on Base | XH Agents</title>
<meta name="description" content="Catalogue of {n} live x402 endpoints on Base: wallet and token checks, gas, whale watch, DeFi sentiment, x402 conformance, Arkham-style intel, the seven-step cycle-wallet hunt, a 13-playbook knowledge bundle and how-to SOPs. Paid per call in USDC, no API key. Listed on x402scan.">
<link rel="canonical" href="https://xhagents.xyz/endpoints.html">
<meta property="og:type" content="website"><meta property="og:title" content="x402 Endpoint Catalogue — XH Agents">
<meta property="og:description" content="{n} x402 endpoints on Base, paid per call in USDC, listed on x402scan.">
<meta property="og:url" content="https://xhagents.xyz/endpoints.html">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#050810;--surface:#0b1220;--surface-raised:#101a2e;--border:#1b2436;--border-strong:#2a3654;--text:#e7ebf3;--text-muted:#8a94a6;--text-faint:#5a6478;--accent-live:#4fd1c5;--accent-live-dim:rgba(79,209,197,.12);--accent-pay:#7c8cff;--font-mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace;--font-sans:"Inter",-apple-system,"Segoe UI",sans-serif;--radius:6px;--max-width:1080px}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-sans);line-height:1.55}}
a{{color:inherit}}.container{{max-width:var(--max-width);margin:0 auto;padding:0 24px}}
.mono{{font-family:var(--font-mono)}}.eyebrow{{font-family:var(--font-mono);font-size:.8rem;color:var(--text-faint)}}
header.site{{border-bottom:1px solid var(--border);padding:16px 0}}
header.site a.brand{{text-decoration:none;font-weight:600;font-family:var(--font-mono)}}
main{{padding:40px 0 64px}}h1{{font-size:clamp(1.6rem,3vw,2.3rem);margin:6px 0 18px;max-width:46ch}}
footer.site{{border-top:1px solid var(--border);padding:28px 0 48px;font-size:.8rem;color:var(--text-faint)}}
footer.site a{{color:var(--text-muted);text-decoration:none}}
</style>
{CSS}
</head><body>
<header class="site"><div class="container"><a class="brand" href="/">XHAGENTS&gt; <span style="color:var(--text-faint);font-weight:400">Endpoint Catalogue</span></a></div></header>
<main><div class="container">
<p class="eyebrow">x402 · USDC on Base · pay-per-call</p>
<h1>{n} x402 endpoints any agent can discover and pay for</h1>
<p class="ep-lede">Every endpoint below is live in production and answers <code>402 Payment Required</code>
with its own payment challenge, settling in USDC on Base per call — no API key, no account. Each one is
registered on x402scan (the Coinbase Bazaar crawler picks up a subset of them — indexing there is selective,
so we claim only what is verifiable). The exact price is quoted in the challenge itself
and listed in <a href="/openapi.json">openapi.json</a>.</p>
{sections}{backup_section}
<h2 class="ep-group-title">How an agent pays</h2>
<ol class="ep-flow">
  <li>Call an endpoint with no credentials; it answers <code>402</code> with the price, the network
    (<code>eip155:8453</code>), the asset (USDC) and the receiving address.</li>
  <li>Sign an EIP-3009 transfer authorisation for that amount — the payer needs USDC only, the
    facilitator pays the gas.</li>
  <li>Repeat the request with the signed authorisation in the <code>X-PAYMENT</code> header.</li>
  <li>The endpoint returns <code>200</code> with the answer plus a <code>PAYMENT-RESPONSE</code>
    settlement header you can verify on-chain. A call that fails is never charged.</li>
</ol>
<p class="ep-meta">Back to the <a href="/">main site</a> · free SOP index <a href="/api/howto">/api/howto</a>
· discovery <a href="/openapi.json">openapi.json</a> and <a href="/.well-known/x402">/.well-known/x402</a>.</p>
<script type="application/ld+json">{jsonld(cat)}</script>
</div></main>
<footer class="site"><div class="container">
<p>XH Agents · <a href="/">home</a> · <a href="/about.html">about</a> · <a href="/privacy.html">privacy</a>
· <a href="/terms.html">terms</a> · <a href="/disclaimer.html">disclaimer</a></p>
<p>Prices are settled in USDC on Base, per call. Nothing here is financial advice; data comes from public
sources and every response states the checks it could not perform.</p>
</div></footer>
</body></html>
"""


def _price_range() -> tuple[float, float]:
    """Read the price range straight from the published openapi so the page cannot drift from it."""
    try:
        doc = json.load(open(os.path.join(DOCROOT, "openapi.json")))
        prices = [float(((op.get("x-payment-info") or {}).get("price") or {}).get("amount"))
                  for ops in (doc.get("paths") or {}).values() for op in ops.values()
                  if ((op.get("x-payment-info") or {}).get("price") or {}).get("amount")]
        return (min(prices), max(prices)) if prices else (0.0, 0.0)
    except Exception:
        return (0.0, 0.0)


def patch_index(block: str, cat: dict) -> None:
    path = os.path.join(DOCROOT, "index.html")
    src = open(path).read()
    if "<!-- CATALOG:START" not in src:
        raise SystemExit("marker CATALOG:START tidak ada di index.html")
    new = re.sub(r"<!-- CATALOG:START.*?<!-- CATALOG:END -->", block.strip(), src, flags=re.S)
    # Directories (x402scan) read our listing title/description from THIS page's metadata, so the text
    # is generated from the catalogue instead of being a sentence someone has to remember to edit.
    n = int(cat.get("total_resources") or 0)
    lo, hi = _price_range()
    meta = (f"{n} live x402 endpoints on Base priced ${lo:.2f}–${hi:.2f} in USDC per call: wallet and token checks, "
            f"gas, whale watch, DeFi sentiment, x402 conformance, six Arkham-style intel endpoints, the seven-step "
            f"cycle-wallet hunt (Base here, Solana at pronomad.duckdns.org), a video licence "
            f"with a signed stream URL, a dated daily brief, a 13-playbook knowledge bundle and how-to SOPs. "
            f"Listed on x402scan (the Coinbase Bazaar crawler picks up a subset), no API key required. "
            f"Operated by a fleet of autonomous AI agents.")
    og = (f"{n} x402 endpoints on Base, ${lo:.2f}–${hi:.2f} in USDC per call, listed on x402scan. "
          f"Humans browse free; agents pay per call.")
    new = re.sub(r'<meta name="description" content="[^"]*"',
                 f'<meta name="description" content="{html.escape(meta, quote=True)}"', new, count=1)
    new = re.sub(r'<meta property="og:description" content="[^"]*"',
                 f'<meta property="og:description" content="{html.escape(og, quote=True)}"', new, count=1)
    if new == src:
        print("index.html: blok katalog identik")
        return
    shutil.copy(path, path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S"))
    open(path, "w").write(new)
    print(f"index.html diperbarui ({len(new)} byte), meta deskripsi disetel ke {n} endpoint")


def write_endpoints_page(page: str) -> None:
    path = os.path.join(DOCROOT, "endpoints.html")
    if os.path.exists(path):
        shutil.copy(path, path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S"))
    open(path, "w").write(page)
    print(f"endpoints.html ditulis ({len(page)} byte)")


def write_sitemap() -> None:
    path = os.path.join(DOCROOT, "sitemap.xml")
    pages = [("/", "daily", "1.0"), ("/endpoints.html", "daily", "0.9"), ("/trading/", "daily", "0.8"),
             ("/ad-order.html", "weekly", "0.5"), ("/about.html", "monthly", "0.4"),
             ("/kb/", "monthly", "0.4"), ("/privacy.html", "yearly", "0.3"),
             ("/terms.html", "yearly", "0.3"), ("/disclaimer.html", "yearly", "0.3")]
    entries = "\n".join(
        f"  <url>\n    <loc>{SITE}{p}</loc>\n    <lastmod>{STAMP}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>"
        for p, freq, prio in pages)
    if os.path.exists(path):
        shutil.copy(path, path + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S"))
    open(path, "w").write('<?xml version="1.0" encoding="UTF-8"?>\n'
                          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                          f"{entries}\n</urlset>\n")
    print(f"sitemap.xml ditulis ({len(pages)} URL)")


def mirror(block: str) -> None:
    if not os.path.isdir(SRC_MIRROR):
        return
    open(os.path.join(SRC_MIRROR, "catalog-block.html"), "w").write(block)
    for name in ("endpoints.html", "sitemap.xml"):
        src = os.path.join(DOCROOT, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(SRC_MIRROR, name))
    print(f"salinan disimpan di {SRC_MIRROR}")


def main() -> None:
    cat = collect()
    block = homepage_block(cat)
    patch_index(block, cat)
    write_endpoints_page(endpoints_page(cat))
    write_sitemap()
    mirror(block)
    print(f"katalog: {cat['total_resources']} resource "
          f"({len(cat['data'])} data, {len(cat['knowledge'])} knowledge, {len(cat['playbooks'])} playbook)")


if __name__ == "__main__":
    main()
