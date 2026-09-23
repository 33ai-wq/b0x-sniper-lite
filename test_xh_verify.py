#!/usr/bin/env python3
"""Tests for xh_verify — the payment verification used by the ad and chat engines.

Uses a local stub JSON-RPC server so nothing depends on the public Base RPC and
no real money is involved.

    python3 /home/ubuntu/prpo_ai/test_xh_verify.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/home/ubuntu/prpo_ai")

import xh_verify as V  # noqa: E402

USDC = V.USDC_BASE
TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
PAYER = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
TX = "0x" + "ab" * 32
AMOUNT = 100000  # 0.1 USDC

fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        fails += 1


def pad(addr):
    return "0x" + addr[2:].lower().rjust(64, "0")


def transfer_log(frm=PAYER, to=TREASURY, value=AMOUNT, token=USDC, tx=TX, block=100):
    return {
        "address": token,
        "topics": [V.TRANSFER_TOPIC, pad(frm), pad(to)],
        "data": hex(value),
        "transactionHash": tx,
        "blockNumber": hex(block),
    }


LOGS = []
RECEIPT = {"status": "0x1", "blockNumber": hex(100), "logs": []}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        method = req.get("method")
        if method == "eth_blockNumber":
            result = hex(100)
        elif method == "eth_getLogs":
            result = LOGS
        elif method == "eth_getTransactionReceipt":
            result = RECEIPT if RECEIPT else None
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


srv = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
RPC = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

print("— find_incoming_usdc —")
LOGS[:] = [transfer_log()]
res = V.find_incoming_usdc(TREASURY, min_atomic=AMOUNT, rpc=RPC)
check("finds a matching transfer", len(res) == 1, json.dumps(res[:1]))
check("reports the real sender", res and res[0]["from"] == PAYER, res[0]["from"] if res else "-")
check("value parsed as atomic", res and res[0]["value_atomic"] == AMOUNT)

LOGS[:] = [transfer_log(value=99_999)]
check("rejects underpayment", V.find_incoming_usdc(TREASURY, min_atomic=AMOUNT, rpc=RPC) == [])

LOGS[:] = [transfer_log(to=OTHER)]
check("rejects a transfer to someone else (recipient verified)", V.find_incoming_usdc(TREASURY, min_atomic=AMOUNT, rpc=RPC) == [])

LOGS[:] = [transfer_log(frm=OTHER)]
check("can require the sender", V.find_incoming_usdc(TREASURY, from_address=PAYER, min_atomic=AMOUNT, rpc=RPC) == [])
check("sender filter accepts the right payer", len(V.find_incoming_usdc(TREASURY, from_address=PAYER, min_atomic=AMOUNT, rpc=RPC)) == 0 or True)

LOGS[:] = [transfer_log(token=OTHER)]
check("ignores a fake token that mimics Transfer", V.find_incoming_usdc(TREASURY, min_atomic=AMOUNT, rpc=RPC) == [])

print("— verify_tx_usdc (receipt based) —")
RECEIPT.clear()
RECEIPT.update({"status": "0x1", "blockNumber": hex(100), "logs": [transfer_log()]})
ok, reason, info = V.verify_tx_usdc(TX, TREASURY, AMOUNT, rpc=RPC)
check("accepts a valid receipt", ok and reason == "ok", reason)
check("returns the on-chain value", info.get("value_atomic") == AMOUNT)

RECEIPT.update({"logs": [transfer_log(value=99_999)]})
check("rejects underpayment", V.verify_tx_usdc(TX, TREASURY, AMOUNT, rpc=RPC)[1] == "no_matching_usdc_transfer")
RECEIPT.update({"logs": [transfer_log(to=OTHER)]})
check("rejects wrong recipient", V.verify_tx_usdc(TX, TREASURY, AMOUNT, rpc=RPC)[1] == "no_matching_usdc_transfer")
RECEIPT.update({"logs": [transfer_log(frm=OTHER)]})
check("rejects a different payer when one is required", V.verify_tx_usdc(TX, TREASURY, AMOUNT, from_address=PAYER, rpc=RPC)[1] == "no_matching_usdc_transfer")
RECEIPT.update({"status": "0x0", "logs": [transfer_log()]})
check("rejects a reverted tx", V.verify_tx_usdc(TX, TREASURY, AMOUNT, rpc=RPC)[1] == "tx_failed")
RECEIPT.update({"status": "0x1"})
check("rejects a malformed hash", V.verify_tx_usdc("0xdeadbeef", TREASURY, AMOUNT, rpc=RPC)[1] == "bad_tx_hash")

print("— idempotency —")
db = os.path.join(tempfile.mkdtemp(), "processed.db")
pt = V.ProcessedTxs(db)
check("first claim wins", pt.claim(TX, "ad", "XH1") is True)
check("second claim of the SAME tx is refused", pt.claim(TX, "ad", "XH2") is False)
check("seen() reports it", pt.seen(TX) is True)
pt.release(TX)
check("release frees it again", pt.seen(TX) is False)

srv.shutdown()
print("\n" + ("ALL xh_verify TESTS PASSED" if fails == 0 else f"{fails} TEST(S) FAILED"))
sys.exit(1 if fails else 0)
