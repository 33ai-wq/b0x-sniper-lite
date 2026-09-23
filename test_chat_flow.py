#!/usr/bin/env python3
"""End-to-end test of the chat top-up path (Trading Assistant monetisation).

Private in-process instance: temp DB, stub Base RPC, own port. Proves that a
payment only credits when it really went to the treasury, that one transfer is
credited exactly once, and that paying more buys proportionally more messages.

    /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/test_chat_flow.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TMP = tempfile.mkdtemp(prefix="chattest_")
LOGS = []


class RpcStub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        m = req.get("method")
        result = hex(1000) if m == "eth_blockNumber" else (LOGS if m == "eth_getLogs" else None)
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
os.environ["XH_PROCESSED_DB"] = os.path.join(TMP, "processed.db")

sys.path.insert(0, "/home/ubuntu/prpo_ai")
sys.path.insert(0, "/home/ubuntu/prpo_ai/BossyFactory/trading-agent")

import xh_verify as V  # noqa: E402
import chat_engine as C  # noqa: E402

C.DB = os.path.join(TMP, "chat.db")
C.MSG_PRICE_USDC = 0.1
C.MSG_PRICE_ATOMIC = 100000
C.VERIFY_RATE_PER_HOUR = 50

WALLET = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
TREASURY = C.TREASURY["base"]
USER = "qa-user-1"
TX1 = "0x" + "a1" * 32
TX2 = "0x" + "b2" * 32
TX_BAD = "0x" + "c3" * 32

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


srv = ThreadingHTTPServer(("127.0.0.1", 0), C.H)
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


C.db()  # create tables

print("— no payment yet —")
st, body = post("/api/chat/verify-payment", {"user_id": USER, "wallet_address": WALLET, "network": "base"})
check("nothing is credited without a payment", st == 402 and body.get("credited") is False, f"{st} {body.get('message','')[:40]}")

print("— a payment to someone else must not count —")
LOGS[:] = [log(WALLET, OTHER, 100000, TX_BAD)]
st, body = post("/api/chat/verify-payment", {"user_id": USER, "wallet_address": WALLET, "network": "base"})
check("payment to a third party is ignored (recipient verified)", st == 402, f"{st}")

print("— the real top-up —")
LOGS[:] = [log(WALLET, TREASURY, C.MSG_PRICE_ATOMIC, TX1)]
st, body = post("/api/chat/verify-payment", {"user_id": USER, "wallet_address": WALLET, "network": "base"})
check("0.1 USDC to the treasury credits 1 message", st == 200 and body.get("credited") is True, f"{st} {body}")
check("balance is 1", body.get("balance") == 1, str(body.get("balance")))

print("— replay protection (the old bug) —")
st2, body2 = post("/api/chat/verify-payment", {"user_id": USER, "wallet_address": WALLET, "network": "base"})
check("the SAME transfer cannot be credited twice", st2 == 402 and body2.get("credited") is False, f"{st2} {body2.get('message','')[:45]}")
con = C.db()
bal = con.execute("SELECT balance FROM users WHERE user_id=?", (USER,)).fetchone()[0]
con.close()
check("balance stays 1 after the replay attempt", bal == 1, str(bal))

print("— paying more buys more —")
LOGS[:] = [log(WALLET, TREASURY, 300000, TX2)]
st, body = post("/api/chat/verify-payment", {"user_id": USER, "wallet_address": WALLET, "network": "base"})
check("0.3 USDC credits 3 messages", st == 200 and body.get("balance") == 4, f"{st} balance={body.get('balance')}")

print("— balance endpoint —")
st, body = post("/api/chat/balance", {"user_id": USER})
check("balance endpoint reports 4", st == 200 and body.get("balance") == 4, f"{st} {body}")

print("— a different wallet cannot spend this payment —")
st, body = post("/api/chat/verify-payment", {"user_id": "qa-user-2", "wallet_address": OTHER, "network": "base"})
check("another wallet gets nothing from someone else's payments", st == 402, f"{st}")

print("— topups are recorded with their tx hash —")
con = C.db()
rows = con.execute("SELECT amount, tx_hash, status FROM topups WHERE user_id=?", (USER,)).fetchall()
con.close()
check("two paid top-ups recorded", len(rows) == 2 and all(r[2] == "paid" for r in rows), str(rows))
check("each row keeps its on-chain tx hash", all(r[1] for r in rows), str([r[1][:10] for r in rows]))


# ── AI behaviour: retry transient overloads, never charge for a failure ──
print("— NIM retry —")
NIM_CALLS = []


class NimStub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        NIM_CALLS.append(1)
        # first two attempts: overloaded; third: a real answer
        body = (json.dumps({"error": {"message": "Service temporarily overloaded"}}).encode()
                if len(NIM_CALLS) < 3 else
                json.dumps({"choices": [{"message": {"content": "BTC is ranging; watch support."}}]}).encode())
        code = 503 if len(NIM_CALLS) < 3 else 200
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


nim = ThreadingHTTPServer(("127.0.0.1", 0), NimStub)
threading.Thread(target=nim.serve_forever, daemon=True).start()
C.NIM_URL = f"http://127.0.0.1:{nim.server_address[1]}/v1/chat/completions"
C.NVIDIA_API_KEY = "test-key"

con = C.db()
con.execute("UPDATE users SET balance=5 WHERE user_id=?", (USER,))
con.commit()
con.close()
st, body = post("/api/chat", {"user_id": USER, "message": "read on BTC?", "network": "Base"})
check("a transient 503 is retried and the reply still arrives",
      st == 200 and "ranging" in (body.get("reply") or ""), f"{st} calls={len(NIM_CALLS)}", )
check("three NIM attempts were made", len(NIM_CALLS) == 3, str(len(NIM_CALLS)))
check("the successful reply charged exactly one credit", body.get("charged") is True and body.get("balance") == 4,
      f"charged={body.get('charged')} balance={body.get('balance')}")

print("— the history sent to the model must use valid roles —")
SENT = []


class NimRecorder(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        SENT.append(json.loads(self.rfile.read(n) or b"{}"))
        body = json.dumps({"choices": [{"message": {"content": "ack"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


rec = ThreadingHTTPServer(("127.0.0.1", 0), NimRecorder)
threading.Thread(target=rec.serve_forever, daemon=True).start()
C.NIM_URL = f"http://127.0.0.1:{rec.server_address[1]}/v1/chat/completions"
con = C.db()
con.execute("UPDATE users SET balance=5 WHERE user_id=?", (USER,))
con.commit()
con.close()
# three messages in a row -> the 2nd/3rd carry history, which used to break the API
for i in range(3):
    st, body = post("/api/chat", {"user_id": USER, "message": f"message {i}", "network": "Base"})
roles = {m["role"] for msgs in SENT for m in msgs.get("messages", [])}
check("three consecutive messages all answered", st == 200 and len(SENT) == 3, f"calls={len(SENT)} last={st}")
check("only valid chat roles are sent to NIM", roles <= {"system", "user", "assistant", "tool", "function"}, str(roles))
check("our internal 'agent' role never reaches the API", "agent" not in roles, str(roles))
check("history is actually included after the first message", len(SENT[-1]["messages"]) > 2, str(len(SENT[-1]["messages"])))
rec.shutdown()

print("— AI failure must not cost the user —")
NIM_CALLS.clear()
con = C.db()
before = con.execute("SELECT balance FROM users WHERE user_id=?", (USER,)).fetchone()[0]
con.close()
C.NIM_URL = "http://127.0.0.1:1/v1/chat/completions"   # unreachable
st, body = post("/api/chat", {"user_id": USER, "message": "read on ETH?", "network": "Base"})
check("a failed AI call is reported honestly", st == 200 and "NOT charged" in (body.get("reply") or ""),
      (body.get("reply") or "")[:60])
check("the response reports the true balance", body.get("charged") is False and body.get("balance") == before,
      f"charged={body.get('charged')} balance={body.get('balance')} expected={before}")
con = C.db()
bal = con.execute("SELECT balance FROM users WHERE user_id=?", (USER,)).fetchone()[0]
con.close()
check("balance in the DB is unchanged after the failure", bal == before, f"{bal} vs {before}")

nim.shutdown()

srv.shutdown()
rpc.shutdown()
print("\n" + ("ALL CHAT-FLOW TESTS PASSED" if fails == 0 else f"{fails} TEST(S) FAILED"))
sys.exit(1 if fails else 0)
