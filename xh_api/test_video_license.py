#!/usr/bin/env python3
"""Check the Ataraxia video-licence endpoint end to end, without spending anything.

The x402 gate itself is not bypassed here (an unpaid POST must answer 402 — that is asserted).
Everything downstream of the gate is exercised with a token minted from the same signing key the
service uses, so the stream, the Range handling, the expiry and the hash can all be verified for free.

  /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/xh_api/test_video_license.py
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time

import httpx

BASE = os.environ.get("XH_API_BASE", "https://xhagents.xyz")
KEY_FILE = os.environ.get("ATARAXIA_MEDIA_HMAC_FILE", "/home/ubuntu/prpo_ai/keys/ataraxia_media_hmac.key")

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def mint(video_id: str, exp: int) -> str:
    if not os.path.exists(KEY_FILE):
        # the service creates the key on first use — a junk request primes it
        httpx.get(f"{BASE}/api/video-stream/prime-the-key", timeout=20)
    key = open(KEY_FILE, "rb").read().strip()
    payload = base64.urlsafe_b64encode(
        json.dumps({"v": video_id, "e": exp}, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{payload}." + hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:43]


print(f"target {BASE}\n")

print("free menu")
menu = httpx.get(f"{BASE}/api/video-license", timeout=20)
check("GET /api/video-license -> 200", menu.status_code == 200, f"status={menu.status_code}")
m = menu.json()
films = m.get("films") or []
check("four films offered", len(films) == 4, f"got {len(films)}")
check("every film carries bytes + sha256", all(f.get("bytes") and f.get("sha256") for f in films), json.dumps(films[:1]))
check("price is 0.10 USDC", m.get("price_usdc") == 0.1 and m.get("price_atomic") == "100000",
      f"{m.get('price_usdc')} / {m.get('price_atomic')}")
check("tells the buyer how to pay", "POST this path" in str(m.get("how")), str(m.get("how"))[:60])
check("payTo is the treasury", str(m.get("pay_to", "")).lower() == "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0",
      str(m.get("pay_to")))

print("\npaid POST without payment")
r = httpx.post(f"{BASE}/api/video-license", json={"video_id": films[0]["id"]}, timeout=25)
check("unpaid POST -> 402", r.status_code == 402, f"status={r.status_code}")
hdr = r.headers.get("payment-required") or r.headers.get("PAYMENT-REQUIRED") or ""
check("challenge sent in PAYMENT-REQUIRED", bool(hdr), f"headers={list(r.headers)[:6]}")
try:
    ch = json.loads(base64.b64decode(hdr).decode()) if hdr and not hdr.strip().startswith("{") else json.loads(hdr or "{}")
except Exception:
    ch = {}
acc = (ch.get("accepts") or [{}])[0]
check("challenge quotes 0.10 USDC", json.dumps(acc).find("100000") >= 0, json.dumps(acc)[:160])
check("challenge quotes the public resource URL", "video-license" in str(ch.get("resource", "")), str(ch.get("resource"))[:80])

print("\nstream")
vid = films[0]["id"]
expected_bytes = films[0]["bytes"]
good = mint(vid, int(time.time()) + 600)
r = httpx.get(f"{BASE}/api/video-stream/{good}", timeout=60)
check("valid licence streams the master (200)", r.status_code == 200, f"status={r.status_code}")
check("content-type is video/mp4", r.headers.get("content-type") == "video/mp4", str(r.headers.get("content-type")))
check("Accept-Ranges advertised", r.headers.get("accept-ranges") == "bytes", str(r.headers.get("accept-ranges")))
check("byte count matches the catalogue", len(r.content) == expected_bytes, f"{len(r.content)} vs {expected_bytes}")
digest = hashlib.sha256(r.content).hexdigest()
check("sha256 matches the catalogue", digest == films[0]["sha256"], f"{digest[:16]} vs {str(films[0]['sha256'])[:16]}")

r = httpx.get(f"{BASE}/api/video-stream/{good}", headers={"Range": "bytes=0-1023"}, timeout=30)
check("Range 0-1023 -> 206", r.status_code == 206, f"status={r.status_code}")
check("206 carries Content-Range", r.headers.get("content-range") == f"bytes 0-1023/{expected_bytes}",
      str(r.headers.get("content-range")))
check("206 body is exactly 1024 bytes", len(r.content) == 1024, f"got {len(r.content)}")

r = httpx.get(f"{BASE}/api/video-stream/{good}", headers={"Range": f"bytes=-2048"}, timeout=30)
check("suffix range bytes=-2048 -> 206 with 2048 bytes",
      r.status_code == 206 and len(r.content) == 2048 and r.headers.get("content-range", "").endswith(str(expected_bytes)),
      f"status={r.status_code} len={len(r.content)}")
tail = hashlib.sha256(httpx.get(f"{BASE}/api/video-stream/{good}", timeout=60).content[-2048:]).hexdigest()
check("suffix range really is the tail of the file", hashlib.sha256(r.content).hexdigest() == tail, "")

r = httpx.get(f"{BASE}/api/video-stream/{good}", headers={"Range": f"bytes={expected_bytes + 10}-"}, timeout=20)
check("range past the end -> 416", r.status_code == 416, f"status={r.status_code}")

print("\nbad credentials")
r = httpx.get(f"{BASE}/api/video-stream/not-a-real-token", timeout=20)
check("garbage token -> 401", r.status_code == 401, f"status={r.status_code}")
r = httpx.get(f"{BASE}/api/video-stream/{good[:-1]}x", timeout=20)
check("tampered signature -> 401", r.status_code == 401, f"status={r.status_code}")
payload, sig = good.split(".")
forged = base64.urlsafe_b64encode(
    json.dumps({"v": vid, "e": int(time.time()) + 600}).encode()).decode().rstrip("=")
r = httpx.get(f"{BASE}/api/video-stream/{forged}.{sig}", timeout=20)
check("re-signed payload with a stale signature -> 401", r.status_code == 401, f"status={r.status_code}")
r = httpx.get(f"{BASE}/api/video-stream/{mint(vid, int(time.time()) - 5)}", timeout=20)
check("expired licence -> 401", r.status_code == 401, f"status={r.status_code}")
r = httpx.get(f"{BASE}/api/video-stream/{mint('no-such-film', int(time.time()) + 600)}", timeout=20)
check("licence for an unknown film -> 404", r.status_code == 404, f"status={r.status_code}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
