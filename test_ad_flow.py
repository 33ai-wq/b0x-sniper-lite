#!/usr/bin/env python3
"""End-to-end test of the XH Agents ad flow: order -> on-chain match -> activation.

Runs a private instance of the engine (own port, own temp DB/ads.json, stub RPC,
emails suppressed) so the live service and live data are untouched.

    /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/test_ad_flow.py
"""
import importlib
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="adtest_")
STUB_LOGS = []

# Stub Base RPC (must be set before importing the engine so its defaults pick it up)
class RpcStub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        m = req.get("method")
        if m == "eth_blockNumber":
            result = hex(1000)
        elif m == "eth_getLogs":
            result = STUB_LOGS
        else:
            result = None
        body = json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


rpc = ThreadingHTTPServer(("127.0.0.1", 0), RpcStub)
threading.Thread(target=rpc.serve_forever, daemon=True).start()
os.environ["XH_BASE_RPC"] = f"http://127.0.0.1:{rpc.server_address[1]}"
os.environ["XH_AD_NO_EMAIL"] = "1"
os.environ["XH_AD_ORDERS_PER_HOUR"] = "3"
os.environ["XH_ADMIN_TOKEN"] = "test-admin-token"
os.environ["XH_PROCESSED_DB"] = os.path.join(TMP, "processed.db")  # isolate idempotency state

sys.path.insert(0, "/home/ubuntu/prpo_ai")
sys.path.insert(0, "/home/ubuntu/prpo_ai/adengine")

import xh_verify as V  # noqa: E402
import ad_engine as A  # noqa: E402

# isolate state
A.DB = os.path.join(TMP, "ads.db")
A.ADS_JSON = os.path.join(TMP, "ads.json")
A.PORT = 0
A.NO_EMAIL = True
A.ADMIN_TOKEN = "test-admin-token"

PAYER = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
TREASURY = A.TREASURY["base"]
AMOUNT = A.RATES["728x90"]  # 40 USDC
TX_GOOD = "0x" + "aa" * 32
TX_OTHER = "0x" + "bb" * 32

fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        fails += 1


def pad(a):
    return "0x" + a[2:].lower().rjust(64, "0")


def log(frm, to, value, tx):
    return {"address": V.USDC_BASE, "topics": [V.TRANSFER_TOPIC, pad(frm), pad(to)],
            "data": hex(value), "transactionHash": tx, "blockNumber": hex(999)}


print("— input validation —")
errs, clean = A.validate_ad_payload({"size": "nope", "network": "base", "title": "t", "landing_url": "https://x.com"})
check("rejects an unknown size", "bad size" in errs, ",".join(errs))
errs, clean = A.validate_ad_payload({"size": "728x90", "network": "base", "title": "", "landing_url": "https://x.com"})
check("requires a title", "title required" in errs)
errs, clean = A.validate_ad_payload({"size": "728x90", "network": "base", "title": "t", "landing_url": "javascript:alert(1)"})
check("blocks a javascript: landing url", "landing_url must be an http(s) url" in errs, ",".join(errs))
errs, clean = A.validate_ad_payload({"size": "728x90", "network": "base", "title": "<img src=x onerror=alert(1)>Hi", "text": "<b>bold</b>", "landing_url": "https://ok.example"})
check("strips html from ad copy", "<img" not in clean["title"] and "Hi" in clean["title"], clean["title"])
check("strips html from body copy", clean["text"] == "bold", clean["text"])

print("— activation requires the admin token —")
srv = ThreadingHTTPServer(("127.0.0.1", 0), A.H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"


def post(path, payload, headers=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


st, body = post("/api/ads/activate", {"order_id": "XHTEST", "size": "728x90", "network": "base",
                                      "title": "Spam", "landing_url": "https://spam.example"})
check("activate without a token is refused", st == 403, f"{st} {body.get('error')}")
st, body = post("/api/ads/activate", {"order_id": "XHTEST", "size": "nope", "network": "base",
                                      "title": "x", "landing_url": "https://spam.example"},
                {"X-Admin-Token": "test-admin-token"})
check("activate with a token still validates the payload", st == 400, f"{st} {body.get('message')}")

print("— a real order —")
st, order = post("/api/ad-order", {"size": "728x90", "network": "base", "email": "advertiser@example.com",
                                   "advertiser_wallet": PAYER, "title": "Quiet Room",
                                   "text": "Breathe on Base", "landing_url": "https://ataraxia.xhagents.xyz"})
check("order created", st == 200 and order.get("order_id"), f"{st} {order.get('order_id')}")
check("invoice points at the confirmed treasury", order.get("treasury") == TREASURY, order.get("treasury"))
check("price comes from the published rate card", order.get("amount_usdc") == 40, str(order.get("amount_usdc")))
OID = order["order_id"]

codes = []
for _ in range(3):  # limit is 3/hour, one order already placed above
    st_extra, _b = post("/api/ad-order", {"size": "728x90", "network": "base", "advertiser_wallet": PAYER,
                                          "title": "x", "landing_url": "https://x.example"})
    codes.append(st_extra)
check("rate limit kicks in", 429 in codes, f"codes={codes}")

print("— payment detection —")
check("nothing active before payment", get("/api/ads")[1] == [])
STUB_LOGS[:] = [log(OTHER, TREASURY, AMOUNT * 1_000_000, TX_OTHER)]
A.detect_payments()
check("an unrelated payer does NOT activate the order (wallet-bound)", get("/api/ads")[1] == [],
      json.dumps(get("/api/ads")[1])[:80])

STUB_LOGS[:] = [log(PAYER, TREASURY, AMOUNT * 1_000_000, TX_GOOD)]
first = A.detect_payments()
check("the advertiser's own payment activates it", first == [OID], str(first))
ads = get("/api/ads")[1]
check("ad is published to ads.json", len(ads) == 1 and ads[0]["title"] == "Quiet Room", json.dumps(ads)[:120])
check("placement carries a 30-day expiry", ads and 25 <= (ads[0]["expire"] - time.time()) / 86400 <= 30)

print("— idempotency / replay —")
second = A.detect_payments()
check("re-running detection does not double-activate", second == [], str(second))
check("still exactly one ad", len(get("/api/ads")[1]) == 1)
check("the tx is recorded as used", V.processed.seen(TX_GOOD))
con = A.db()
row = con.execute("SELECT status, tx_hash FROM orders WHERE id=?", (OID,)).fetchone()
check("order row keeps the tx hash", row[0] == "paid" and row[1] == TX_GOOD, str(row))
con.close()

print("— expiry —")
ads = json.load(open(A.ADS_JSON))
ads.append({"order_id": "OLD", "size": "300x250", "title": "Expired", "text": "", "image_url": "",
            "landing_url": "https://old.example", "advertiser": "x@example.com", "expire": int(time.time()) - 10})
json.dump(ads, open(A.ADS_JSON, "w"))
live = A.load_ads()
check("expired placements are dropped on read", len(live) == 1 and live[0]["title"] == "Quiet Room", str(len(live)))
check("the file self-heals", len(json.load(open(A.ADS_JSON))) == 1)

srv.shutdown()
rpc.shutdown()
print("\n" + ("ALL AD-FLOW TESTS PASSED" if fails == 0 else f"{fails} TEST(S) FAILED"))
sys.exit(1 if fails else 0)
