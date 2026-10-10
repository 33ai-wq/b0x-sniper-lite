#!/usr/bin/env python3
"""test_payment_verify_evidence.py — the payer-vs-broadcaster upgrade of POST /payment-verify.

Two mistakes this suite locks out:

1. Reading `tx.from` as "the payer". An x402 facilitator settles an EIP-3009
   `transferWithAuthorization` (selector 0xe3ee160e) and pays the gas, so `tx.from` is the relayer
   while only the USDC `Transfer` log (topics[1]) carries the payer. Our own two $0.004 payments to
   PulseFeed (0x8496d711…, 0x5e466bdf…) went through two *different* relayers — the case that
   started this.
2. Reporting "no payment" when the RPC refused the block range. Wide eth_getLogs ranges are refused
   by every public Base endpoint (1rpc caps at 50 blocks, 10k answers 403), and a `None` result that
   is treated as an empty list reads as a false zero. Windows are counted and `unreadable` is set
   instead.

No network and no charge: `_rpc_any` and `verify_tx_usdc` are stubbed with real-shaped payloads.
Run:  /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/xh_api/test_payment_verify_evidence.py
"""
import os
import sys
from datetime import datetime, timezone

os.environ["X402_STANDARD"] = "0"          # must be set BEFORE importing the app
sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
sys.path.insert(0, "/home/ubuntu/prpo_ai")

import server as srv  # noqa: E402
from fastapi import HTTPException  # noqa: E402

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
XFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
PAYER = "0x99Cc2cA01841ca704C834415b5909bE591f36d27"
RELAYER_A = "0x97acce27d5069544480bde0f04d9f47d7422a016"
RELAYER_B = "0x772003a2e9c2ccc8af956870a37a66f64f8cec38"
TX = "0x8496d711d84e49d7bc775db02f465bea4f82721e3932a3649b552ab295679e48"
BLOCK = 52397554
TS = 1791584455          # 2026-10-09 22:20:55Z, the real block time of TX (block 52397554)
VALUE = 4000             # 0.004 USDC

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def topic(addr):
    return "0x" + addr[2:].lower().rjust(64, "0")


def tlog(tx, frm, to, value, block):
    """A USDC Transfer log exactly as eth_getLogs / a receipt returns it."""
    return {"address": USDC, "topics": [XFER, topic(frm), topic(to)], "data": hex(value),
            "blockNumber": hex(block), "transactionHash": tx, "logIndex": "0x1"}


def receipt(tx_from, logs, status=1, gas=51342):
    return {"status": hex(status), "blockNumber": hex(BLOCK), "gasUsed": hex(gas), "from": tx_from,
            "logs": logs, "transactionHash": TX}


def txpayload(broadcaster, selector="0xe3ee160e"):
    return {"from": broadcaster, "to": USDC, "input": selector + "0" * 120, "hash": TX}


class RPC:
    """Stub for server._rpc_any: returns (result, error) with refusal modelled explicitly."""

    def __init__(self, receipt_=None, tx_=None, block_=TS, windows=None):
        self.receipt_, self.tx_, self.block_, self.windows = receipt_, tx_, block_, windows or []
        self.calls = []
        self.ifs = 0

    def __call__(self, method, params, endpoints, timeout=20.0):
        self.calls.append(method)
        if method == "eth_blockNumber":
            return hex(BLOCK + 10), None
        if method == "eth_getTransactionReceipt":
            return (self.receipt_, None) if self.receipt_ else (None, "publicnode: HTTPError 403; 1rpc: limit")
        if method == "eth_getTransactionByHash":
            return (self.tx_, None) if self.tx_ else (None, "drpc: HTTPError 403")
        if method == "eth_getBlockByNumber":
            return ({"timestamp": hex(self.block_), "number": hex(BLOCK)}, None)
        if method == "eth_getLogs":
            i = min(self.ifs, len(self.windows) - 1)
            self.ifs += 1
            w = self.windows[i] if self.windows else None
            if w is None or w == "refused":
                return None, "all endpoints refused the range"
            return w, None
        raise AssertionError(f"unexpected method {method}")


def call(rpc, verdict, **body):
    """Run the real handler with the RPC boundary and the shared verifier stubbed."""
    srv._rpc_any = rpc
    srv.verify_tx_usdc = lambda **kw: verdict
    body.setdefault("tx_hash", TX)
    return srv.payment_verify(srv.VerifyReq(**body))


OK = (True, "ok", {"from": PAYER.lower(), "to": TREASURY.lower(), "value_atomic": VALUE, "block": BLOCK})
RELAYED_CASE = (receipt(RELAYER_A, [tlog(TX, PAYER, TREASURY, VALUE, BLOCK)]), txpayload(RELAYER_A))

print("1. relayed EIP-3009 settlement: tx.from is the relayer, the log carries the payer")
rpc = RPC(*RELAYED_CASE)
out = call(rpc, OK)
check("verified", out["verified"] is True, out["reason"])
check("payer == Transfer.from (topics[1])", out["payer"] == PAYER.lower(), out["payer"])
check("broadcaster == tx.from (facilitator)", out["broadcaster"] == RELAYER_A, out["broadcaster"])
check("relayed flag", out["relayed"] is True)
check("EIP-3009 selector detected", out["eip3009"] == {"is_transfer_with_authorization": True,
                                                       "selector": "0xe3ee160e"}, out["eip3009"])
check("block_number", out["block_number"] == BLOCK)
check("block_time is UTC ISO-Z",
      out["block_time"] == datetime.fromtimestamp(TS, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      out["block_time"])
check("status / gas_used from the receipt", out["status"] == 1 and out["gas_used"] == 51342)
check("amount_usdc of the buyer's own transfer", out["amount_usdc"] == 0.004)
check("nothing marked unreadable", out["unreadable"] is False and out["read"]["log_search"]["attempted"] is False,
      str(out["unreadable_parts"]))
check("no money figure beyond the payer's own transfer in the payload",
      not any(k in out for k in ("balance", "__removed_amount_field__", "portfolio")))

print("\n2. the payer broadcast it themselves (plain transfer)")
rpc = RPC(receipt(PAYER, [tlog(TX, PAYER, TREASURY, VALUE, BLOCK)]), txpayload(PAYER, "0xa9059cbb"))
out = call(rpc, OK)
check("relayed is false", out["relayed"] is False)
check("selectors that are not EIP-3009 are not flagged", out["eip3009"]["is_transfer_with_authorization"] is False
      and out["eip3009"]["selector"] == "0xa9059cbb", out["eip3009"])

print("\n3. expect_relayer=true rejects a self-broadcast payment")
out = call(rpc, OK, expect_relayer=True)
check("verified false", out["verified"] is False, out["reason"])
check("reason names the relayer expectation", out["reason"] == "relayer_mismatch", out["reason"])
check("checks expose the mismatch", out["checks"]["relayer_as_expected"] is False)

print("\n4. expect_relayer=false rejects a relayed payment")
rpc2 = RPC(*RELAYED_CASE)
out = call(rpc2, OK, expect_relayer=False)
check("verified false / relayer_mismatch", out["verified"] is False and out["reason"] == "relayer_mismatch",
      out["reason"])
out = call(rpc2, OK, expect_relayer=True)
check("expect_relayer=true passes on the relayed payment", out["verified"] is True, out["reason"])

print("\n5. expected_broadcaster pins the account allowed to relay")
rpc3 = RPC(*RELAYED_CASE)
out = call(rpc3, OK, expected_broadcaster=RELAYER_A)
check("matching broadcaster passes", out["verified"] is True, out["reason"])
out = call(rpc3, OK, expected_broadcaster=RELAYER_B)
check("a different facilitator is refused", out["verified"] is False and out["reason"] == "broadcaster_mismatch",
      out["reason"])
try:
    call(rpc3, OK, expected_broadcaster="not-an-address")
    check("invalid expected_broadcaster is a 400", False)
except HTTPException as e:
    check("invalid expected_broadcaster is a 400", e.status_code == 400, str(e.detail))

print("\n6. from / min_amount constraints")
out = call(RPC(*RELAYED_CASE), OK, **{"from": PAYER})
check("requested from == payer passes", out["verified"] is True, out["reason"])
out = call(RPC(*RELAYED_CASE), OK, **{"from": RELAYER_A})
check("requested from == broadcaster is refused (payer_mismatch)",
      out["verified"] is False and out["reason"] == "payer_mismatch", out["reason"])
out = call(RPC(*RELAYED_CASE), (False, "no_matching_usdc_transfer", {}), min_amount=0.10)
check("amount below min_amount is refused", out["verified"] is False and out["reason"] == "amount_below_minimum",
      out["reason"])

print("\n7. receipt refused but short windows read the chain -> proved via logs, labelled as such")
rpc4 = RPC(receipt_=None, tx_=txpayload(RELAYER_A), windows=["refused", [tlog(TX, PAYER, TREASURY, VALUE, BLOCK)]])
out = call(rpc4, (False, "rpc_error:rpc_unavailable (publicnode: 403)", {}))
check("verified via the log windows", out["verified"] is True, out["reason"])
check("reason says which route proved it", out["reason"] == "ok_logs_only", out["reason"])
check("payer still recovered from the log", out["payer"] == PAYER.lower(), out["payer"])
check("windows counted (1 refused, 1 read)", out["windows_read"] == 1 and out["windows_refused"] == 1,
      f"{out['windows_read']}/{out['windows_refused']}")
check("unreadable names the receipt", out["unreadable"] is True and "receipt" in out["unreadable_parts"],
      str(out["unreadable_parts"]))

print("\n8. every window refused -> unreadable, never a false zero")
rpc5 = RPC(receipt_=None, tx_=None, windows=["refused"])
out = call(rpc5, (False, "rpc_error:rpc_unavailable (all endpoints)", {}))
check("verified false", out["verified"] is False)
check("reason is unreadable, not no_matching_usdc_transfer", out["reason"] == "unreadable", out["reason"])
check("unreadable flag + parts", out["unreadable"] is True and out["unreadable_parts"] == ["receipt", "transaction", "logs"],
      str(out["unreadable_parts"]))
check("windows_refused counted, windows_read zero", out["windows_read"] == 0 and out["windows_refused"] == srv.LOGS_MAX_WINDOWS,
      f"{out['windows_read']}/{out['windows_refused']}")
check("no transfer claimed", out["transfer"] is None and out["checks"]["transfer_found"] is False)

print("\n9. an expectation that cannot be evaluated is never a pass")
out = call(RPC(receipt_=receipt(RELAYER_A, [tlog(TX, PAYER, TREASURY, VALUE, BLOCK)]), tx_=None),
           OK, expect_relayer=True)
check("verified false", out["verified"] is False, out["reason"])
check("reason broadcaster/relayer unreadable", out["reason"] in ("broadcaster_unreadable", "relayer_unreadable"),
      out["reason"])
check("unreadable lists the transaction", "transaction" in out["unreadable_parts"], str(out["unreadable_parts"]))

print("\n10. receipt readable and no matching USDC transfer -> a real 'no', not 'unknown'")
rpc6 = RPC(receipt(RELAYER_A, [tlog(TX, PAYER, "0x000000000000000000000000000000000000dead", VALUE, BLOCK)]),
           txpayload(RELAYER_A))
out = call(rpc6, (False, "no_matching_usdc_transfer", {}))
check("verified false", out["verified"] is False)
check("reason is a definite no", out["reason"] == "no_matching_usdc_transfer", out["reason"])
check("not flagged unreadable", out["unreadable"] is False, str(out["unreadable_parts"]))
check("recipient_matches is False, not None", out["checks"]["recipient_matches"] is False)

print("\n11. a failed transaction cannot be recovered by the log route")
rpc7 = RPC(receipt(RELAYER_A, [tlog(TX, PAYER, TREASURY, VALUE, BLOCK)], status=0), txpayload(RELAYER_A))
out = call(rpc7, (False, "tx_failed", {}))
check("verified false", out["verified"] is False, out["reason"])
check("reason is the verifier's tx_failed", out["reason"] == "tx_failed", out["reason"])
check("receipt_status_ok is False", out["checks"]["receipt_status_ok"] is False)

print(f"\nresult: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
