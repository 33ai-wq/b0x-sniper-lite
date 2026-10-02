import json, urllib.request, time, collections, sys

BASE = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
BOSS_PAYTO = {
    "0x57eec52d76a4a78d4562fc2564101a4bd2e3f357",   # evm_main
    "ghfbggnxern6pq7bosflfjupwxjuvj8tx7egoj9lv2aw",  # solana_main
}
BOSS_HOSTS = ["pronomad.duckdns.org", "mulberry-boar.workers.dev", "nomad-7.duckdns.org"]
WL = ["robinhood", "rh chain", "memecoin", "meme-hunter", "defi-sentiment",
      "dinalibrium", "wallet-profile", "honeypot", "b0x402"]

all_items = []
offset, total = 0, None
while True:
    url = "%s?limit=1000&offset=%d" % (BASE, offset)
    req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=90))
    except Exception as e:
        print("ERROR at offset %d: %r" % (offset, e)); break
    items = d.get("items") or []
    pg = d.get("pagination") or {}
    total = pg.get("total", total)
    all_items.extend(items)
    print("offset %d -> +%d (have %d / total %s)" % (offset, len(items), len(all_items), total))
    if not items or len(all_items) >= (total or 0):
        break
    offset += 1000
    time.sleep(0.4)

print("SCANNED:", len(all_items))

boss_hits, wl_cnt = [], collections.Counter()
for it in all_items:
    s = json.dumps(it).lower()
    paytos = [str(a.get("payTo", "")).lower() for a in (it.get("accepts") or [])]
    res = str(it.get("resource") or it.get("url") or "")
    if any(p in BOSS_PAYTO for p in paytos) or any(h in res.lower() for h in BOSS_HOSTS):
        boss_hits.append((res, paytos, it.get("lastUpdated")))
    for w in WL:
        if w in s:
            wl_cnt[w] += 1

print("BOSS ENDPOINTS IN DISCOVERY INDEX:", len(boss_hits))
for r, p, lu in boss_hits:
    print("  ", r, "| payTo:", p, "| updated:", lu)
print("watchlist (full index):", dict(wl_cnt))

out = "/home/ubuntu/prpo_ai/sniper/rh/data/scout_cdp_scan_latest.json"
with open(out, "w") as f:
    json.dump({"scanned": len(all_items), "total": total,
               "boss_hits": boss_hits, "watchlist": dict(wl_cnt),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
print("saved:", out)
