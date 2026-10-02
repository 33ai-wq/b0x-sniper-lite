import json, urllib.request, collections

url = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
d = json.load(urllib.request.urlopen(req, timeout=60))
items = d.get("items") or d.get("resources") or []
print("total items:", len(items))
print("top-level keys:", list(d.keys())[:10])

hits = []
for it in items:
    s = json.dumps(it).lower()
    if any(k in s for k in ["pronomad", "mulberry-boar", "duckdns", "xhagent"]):
        hits.append(it)
print("BOSS HITS:", len(hits))
for h in hits[:10]:
    print(json.dumps(h)[:500])
    print("--")

wl = ["robinhood", "rh chain", "memecoin", "meme-hunter", "defi-sentiment",
      "dinalibrium", "wallet-profile", "honeypot", "b0x402"]
cnt = collections.Counter()
for it in items:
    s = json.dumps(it).lower()
    for w in wl:
        if w in s:
            cnt[w] += 1
print("watchlist counts:", dict(cnt))
