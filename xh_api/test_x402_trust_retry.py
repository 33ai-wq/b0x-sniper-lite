#!/usr/bin/env python3
"""test_x402_trust_retry.py - prove the "200 first, 402 on retry" handling in x402_trust.assess().

Case taken from baianomarceloeduardo-jpg's report (pulsefeed-x402#36, 2026-10-10): his paid route
answered 200 with `x-free-trial: true` on one call and 402 on the next, so a single-probe scorer can
honestly report "no terms at all" for a route that is priced and payable.

No network: x402_trust._http and the Ctx callables are stubbed. Run with the prpo_ai venv python.
"""
import json
import sys

sys.path.insert(0, "/home/ubuntu/prpo_ai")
from xh_api import x402_trust as m  # noqa: E402

CHALLENGE = {
    "x402Version": 2,
    "accepts": [{
        "scheme": "exact", "network": "eip155:8453", "maxAmountRequired": "50000",
        "payTo": "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "resource": "https://example.invalid/api/thing", "maxTimeoutSeconds": 60,
        "extra": {"name": "USD Coin", "version": "2"},
    }],
}


class Ctx:
    alchemy_url = ""

    def check_ssrf(self, url):
        return None

    def decode_challenge(self, header, text):
        if header:
            return CHALLENGE, "header"
        return None, None

    def rpc(self, *a, **k):
        return None

    def erc20(self, *a, **k):
        return None

    def is_address(self, a):
        return isinstance(a, str) and a.startswith("0x") and len(a) == 42


def probe(status, has_challenge, ms=120):
    headers = {"payment-required": "stub"} if has_challenge else {}
    return {"ok": True, "status": status, "headers": headers,
            "text": json.dumps(CHALLENGE) if has_challenge else "{}", "ms": ms}


def run(script, label, expect_challenge):
    calls = {"n": 0}

    def fake_http(url, method="GET", body=None, timeout=20.0):
        i = calls["n"]
        calls["n"] += 1
        return probe(*script[min(i, len(script) - 1)])

    m._http = fake_http
    out = m.assess(Ctx(), "https://example.invalid/api/thing", "POST", {}, deep=False)
    checks = out.get("checks") or {}
    notes = out.get("notes") or []
    got = bool(checks.get("returns_402_without_payment"))
    retry = checks.get("no_challenge_retry")
    ok = (got == expect_challenge)
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print(f"        probes={calls['n']} status={out.get('status')} 402-without-payment={got} "
          f"no_challenge_retry={retry}")
    for n in notes:
        if "trial" in n or "probed twice" in n or "verb" in n:
            print(f"        note: {n}")
    return ok


results = [
    run([(200, False), (402, True)], "trial: 200 then 402 -> scored as a priced route", True),
    run([(200, False), (200, False)], "free both times -> not a priced route", False),
    run([(402, True)], "plain 402 -> no retry needed", True),
    run([(200, False), (500, False)], "200 then error -> reports 'no terms either time'", False),
]
print("\nresult:", "ALL CORRECT" if all(results) else f"{results.count(False)} case(s) wrong")
sys.exit(0 if all(results) else 1)
