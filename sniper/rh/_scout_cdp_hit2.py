import json, urllib.request

url = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Scout/1.0"})
d = json.load(urllib.request.urlopen(req, timeout=90))
items = d.get("items") or []
KEYS = ["pronomad", "mulberry-boar", "duckdns", "xhagent"]
for it in items:
    s = json.dumps(it).lower()
    m = [k for k in KEYS if k in s]
    if m:
        print("matched:", m)
        print("resource:", it.get("resource") or it.get("url"))
        print("type:", it.get("type"), "| lastUpdated:", it.get("lastUpdated"))
        print("payTo:", [a.get("payTo") for a in it.get("accepts", [])])
        print("name/desc:", str(it.get("description"))[:120])
        print("=====")
print("done. total:", len(items))
