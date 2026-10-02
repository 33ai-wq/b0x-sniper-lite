import json, urllib.request

url = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=2000"
req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
d = json.load(urllib.request.urlopen(req, timeout=90))
items = d.get("items") or []
print("total items:", len(items), "pagination:", json.dumps(d.get("pagination")))
for it in items:
    s = json.dumps(it).lower()
    if any(k in s for k in ["pronomad", "mulberry-boar", "duckdns", "xhagent"]):
        print(json.dumps(it, indent=2)[:2500])
        print("=====")
