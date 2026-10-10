#!/usr/bin/env python3
"""test_guard.py - exercise the guards in xh_pay.validate_quote().

Attacks must be REFUSED; a normal challenge must be SIGNED.
Run: /home/ubuntu/prpo_ai/venv/bin/python test_guard.py
"""

import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai/dist/xh_agent")
import xh_pay  # noqa: E402

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
GOOD = {"payTo": TREASURY, "network": "eip155:8453", "asset": USDC,
        "asset_name": "USD Coin", "price_usdc": 0.05}

CASES = [
    ("normal challenge", GOOD, None, None),
    ("price above ceiling", dict(GOOD, price_usdc=0.5), "above the ceiling", None),
    ("other token (ceiling bypassed)",
     dict(GOOD, asset="0xdeadbeef00000000000000000000000000000000", price_usdc=0.001),
     "not canonical USDC", None),
    ("asset missing", dict(GOOD, asset=None, price_usdc=0.001), "not canonical USDC", None),
    ("asset name lies", dict(GOOD, asset_name="USDC (fake)"), "contradicts canonical USDC", None),
    ("wrong network (Solana)", dict(GOOD, network="solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"),
     "not supported", None),
    ("v1 shorthand 'base' accepted", dict(GOOD, network="base"), None, None),
    ("unknown shorthand still refused", dict(GOOD, network="base-sepolia"), "not supported", None),
    ("payTo missing", dict(GOOD, payTo=""), "no payTo", None),
    ("payTo not an address", dict(GOOD, payTo="0x123"), "not a well-formed EVM address", None),
    ("payTo outside allowlist", GOOD, "not in the --pay-to allowlist",
     ["0x1111111111111111111111111111111111111111"]),
    ("payTo inside allowlist", GOOD, None, [TREASURY]),
    ("price zero", dict(GOOD, price_usdc=0), "not sane", None),
    ("price unreadable", dict(GOOD, price_usdc=None), "not readable", None),
]

bad = 0
for label, info, expect, allow in CASES:
    reason = xh_pay.validate_quote(info, max_price=0.10, allow_pay_to=allow)
    if expect is None:
        ok = reason is None
    else:
        ok = reason is not None and expect in reason
    bad += 0 if ok else 1
    print("  %s %-34s -> %s" % ("PASS" if ok else "FAIL", label, reason or "signed"))

print("\nresult:", "ALL CORRECT" if not bad else "%d case(s) wrong" % bad)
sys.exit(1 if bad else 0)
