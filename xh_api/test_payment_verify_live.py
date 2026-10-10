#!/usr/bin/env python3
"""Live-chain check of the upgraded POST /payment-verify against two known settlements.

Read-only and free: it calls the handler function directly (the x402 gate sits in the HTTP
middleware, so nothing is charged and the running service is untouched) and hits the real public
Base RPCs.

The two cases are our own $0.004 USDC payments to PulseFeed's payTo, settled through EIP-3009
`transferWithAuthorization` by two *different* facilitators — exactly the pattern that made
`tx.from` unusable as "the payer".

Run: /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/xh_api/test_payment_verify_live.py
"""
import os
import sys

os.environ["X402_STANDARD"] = "0"
sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")
sys.path.insert(0, "/home/ubuntu/prpo_ai")

import server as srv  # noqa: E402

PAYER = "0x99Cc2cA01841ca704C834415b5909bE591f36d27"
THEIRS = "0x7f5f784Ba98cEcFC0bA4336f0E48222A3d4d69a8"
CASES = [
    ("0x8496d711d84e49d7bc775db02f465bea4f82721e3932a3649b552ab295679e48",
     "0x97acce27d5069544480bde0f04d9f47d7422a016", 52397554),
    ("0x5e466bdf354a63a352bd0310871f61dcc4733e2abf4ff7d1188a20c7c37248fa",
     "0x772003a2e9c2ccc8af956870a37a66f64f8cec38", 52397654),
]

failed = 0


def check(name, ok, detail=""):
    global failed
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{'' if ok else '  <- ' + str(detail)}")
    if not ok:
        failed += 1


print(f"RPC primary  : {srv.RPC_LIST[0]}")
print(f"log endpoints: {', '.join(srv.LOGS_ENDPOINTS)}")
print(f"window       : {srv.LOGS_WINDOW_BLOCKS} blocks x {srv.LOGS_MAX_WINDOWS} windows\n")

for tx, expected_broadcaster, expected_block in CASES:
    print(f"tx {tx[:18]}…")
    out = srv.payment_verify(srv.VerifyReq(tx_hash=tx, to=THEIRS, min_amount=0.004,
                                           **{"from": PAYER}))
    for k in ("verified", "reason", "payer", "broadcaster", "relayed", "block_number", "block_time",
              "status", "gas_used", "amount_usdc", "unreadable", "windows_read", "windows_refused"):
        print(f"    {k:14}: {out[k]}")
    print(f"    read          : receipt={out['read']['receipt']} tx={out['read']['transaction']} "
          f"block={out['read']['block']} log_search_attempted={out['read']['log_search'].get('attempted')}")
    check("verified against the live chain", out["verified"] is True, out["reason"])
    check("payer is the Transfer log's from (our wallet)",
          out["payer"] == PAYER.lower(), out["payer"])
    check("broadcaster is the facilitator, not the payer",
          out["broadcaster"] == expected_broadcaster, out["broadcaster"])
    check("relayed flagged", out["relayed"] is True)
    check("EIP-3009 transferWithAuthorization detected",
          out["eip3009"] == {"is_transfer_with_authorization": True, "selector": "0xe3ee160e"},
          out["eip3009"])
    check("block_number", out["block_number"] == expected_block, out["block_number"])
    check("block_time is UTC", str(out["block_time"]).endswith("Z"), out["block_time"])
    check("status == 1", out["status"] == 1, out["status"])
    check("gas_used > 21000 (a real relayed transfer)", (out["gas_used"] or 0) > 21000, out["gas_used"])
    check("asked for from=payer: understood as the payer",
          out["checks"]["payer_matches_requested_from"] is True)
    check("nothing unreadable on this path", out["unreadable"] is False, out["unreadable_parts"])
    check("no receipt log search was needed", out["read"]["log_search"].get("attempted") is False)

    # The facilitator pinned by address must pass, a different one must not.
    ok_b = srv.payment_verify(srv.VerifyReq(tx_hash=tx, to=THEIRS, min_amount=0.004,
                                            expected_broadcaster=expected_broadcaster))
    check("expected_broadcaster == the relayer passes", ok_b["verified"] is True, ok_b["reason"])
    bad = srv.payment_verify(srv.VerifyReq(tx_hash=tx, to=THEIRS, min_amount=0.004,
                                           expected_broadcaster="0x" + "1" * 40))
    check("expected_broadcaster = someone else is refused",
          bad["verified"] is False and bad["reason"] == "broadcaster_mismatch", bad["reason"])
    print()

print("windowed eth_getLogs behaviour (the honest-refusal path), 1 window:")
lg, meta = srv._scan_transfer_windows(CASES[0][0], THEIRS, max_windows=1)
print(f"    windows_read={meta['windows_read']} windows_refused={meta['windows_refused']} "
      f"unreadable={meta['unreadable']} found={bool(lg)}")
for e in meta["errors"][:4]:
    print(f"      refused: {e[:150]}")
check("a 4800-block window was read or explicitly refused (never silently empty)",
      meta["windows_read"] + meta["windows_refused"] == 1,
      f"{meta['windows_read']}/{meta['windows_refused']}")
check("the head block was readable", not meta["errors"] or "eth_blockNumber" not in meta["errors"][0],
      meta["errors"][:1])

print("\nwide range, to document why the scan uses short windows:")
wide, werr = srv._rpc_any("eth_getLogs", [{"fromBlock": hex(52397654 - 10000), "toBlock": "latest",
                                          "address": srv.USDC_BASE,
                                          "topics": [srv.TRANSFER_TOPIC, None, srv._addr_topic(THEIRS)]}],
                         srv.LOGS_ENDPOINTS)
print(f"    10,000-block range -> {'read' if wide is not None else 'all endpoints refused'}")
if werr:
    print(f"      last error: {werr[:200]}")
check("a 10,000-block range is refused by every endpoint (so short windows are required)",
      wide is None, "one endpoint served it")

print(f"\nresult: {'ALL CORRECT' if failed == 0 else str(failed) + ' check(s) failed'}")
sys.exit(0 if failed == 0 else 1)
