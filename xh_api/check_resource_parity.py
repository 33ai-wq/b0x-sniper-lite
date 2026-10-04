#!/usr/bin/env python3
"""Bandingkan resource berbayar di server.py dengan yang terbit di .well-known/x402."""
import json
import sys
import urllib.request

sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
import server  # noqa: E402

paid = [r[0] for r in server.PAID_ROUTES]
res_paths = set()
for route in paid:
    m, p = route.split(" ", 1)
    res_paths.add(server.RESOURCE_OVERRIDES.get(route, "/api" + p))
print("PAID_ROUTES:", len(paid), "| resource URL unik:", len(res_paths))

req = urllib.request.Request("https://xhagents.xyz/.well-known/x402", headers={"User-Agent": "Mozilla/5.0"})
wk = set(json.loads(urllib.request.urlopen(req, timeout=60).read().decode())["resources"])
site = {f"https://xhagents.xyz{p}" for p in res_paths}

only_wk = sorted(wk.difference(site))
only_site = sorted(site.difference(wk))
print("\nhanya di .well-known (bukan resource berbayar kita):")
for u in only_wk:
    print("   ", u)
print("\nresource berbayar kita yang TIDAK ada di .well-known:")
for u in only_site:
    print("   ", u)
print("\nsama (irisan):", len(wk.intersection(site)))
