#!/usr/bin/env python3
"""List Nvidia NIM catalog and filter for target keywords."""
import os, json, urllib.request, ssl

KEY = os.environ["NVIDIA_NIM_API_KEY"]
req = urllib.request.Request(
    "https://integrate.api.nvidia.com/v1/models",
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
)
with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
    body = json.loads(r.read())

data = body.get("data", [])
print(f"TOTAL models in catalog: {len(data)}\n")

KEYWORDS = ["nemotron", "opus", "fable", "anthropic", "claude", "minimax", "mistral", "nemoguard"]
for m in sorted(data, key=lambda x: x.get("id", "")):
    mid = m.get("id", "").lower()
    if any(k in mid for k in KEYWORDS):
        print(f"  {m['id']}")

print("\n--- Full catalog ---")
for m in sorted(data, key=lambda x: x.get("id", "")):
    print(f"  {m['id']}")
