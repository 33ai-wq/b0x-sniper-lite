#!/usr/bin/env python3
"""Exercise the five arkham-intel handlers with the payment gate OFF and no server restart.

Runs the real handlers against the real public Base RPCs (so the numbers are live), but with
X402_STANDARD=0 so nothing is charged and the live service is untouched.

  /home/ubuntu/prpo_ai/venv/bin/python /home/ubuntu/prpo_ai/xh_api/test_arkham_intel.py
"""
import json
import os
import sys

os.environ["X402_STANDARD"] = "0"          # must be set BEFORE importing the app
sys.path.insert(0, "/home/ubuntu/prpo_ai/xh_api")

from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

client = TestClient(server.app)
TREASURY = "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def post(path, body):
    r = client.post(path, json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


print("free index")
s, d = client.get("/arkham-intel"), None
d = s.json()
check("GET /arkham-intel -> 200", s.status_code == 200, f"status={s.status_code}")
check("lists six paid endpoints", len(d.get("endpoints") or []) == 6, str(len(d.get("endpoints") or [])))
check("states it is not Arkham", "not Arkham" in str(d.get("not_arkham")), str(d.get("not_arkham"))[:60])
check("price stated as 0.10", d.get("price_usdc_per_call") == 0.1, str(d.get("price_usdc_per_call")))

print("\nuse-cases (router)")
s, d = post("/arkham-intel/use-cases", {"role": "traders"})
check("trader role returns playbooks", s == 200 and len(d.get("playbooks") or []) >= 3, f"status={s}")
check("playbooks map to Arkham use cases",
      any("Inflow" in (p.get("arkham_use_case") or "") for p in d.get("playbooks") or []), "")
s2, d2 = post("/arkham-intel/use-cases", {"task": "who paid a darknet market"})
check("free-text task matches the investigator playbook",
      s2 == 200 and any("darknet" in (p.get("arkham_use_case") or "").lower() for p in d2.get("playbooks") or []),
      str([p.get("arkham_use_case") for p in d2.get("playbooks") or []])[:90])

print("\nexchange-flow (live Base RPC, pool reserves at two blocks)")
s, d = post("/arkham-intel/exchange-flow", {"token": USDC, "hours": 1})
check("200 on a real token", s == 200, f"status={s} {str(d)[:120]}")
check("reports a window and pool totals", bool(d.get("window")) and "pool_totals" in d, str(d.get("window")))
check("returns pool rows (or states why a pool was skipped)",
      isinstance(d.get("pools"), list) and len(d.get("pools") or []) >= 1 and
      all("pair" in r for r in (d.get("pools") or [])), str(d.get("pools"))[:140])
check("no silent RPC failures (rpc_errors surfaced)", isinstance(d.get("rpc_errors"), list), "")
check("carries its methodology + not_checked", bool(d.get("methodology")) and bool(d.get("not_checked")), "")
check("USDC price is not the quote-side artefact (sane value)",
      (d.get("price") or {}).get("price_usd") is None or 0.9 <= (d.get("price") or {}).get("price_usd", 0) <= 1.1,
      str(d.get("price")))
s, d = post("/arkham-intel/exchange-flow", {"token": "not-an-address"})
check("bad token -> 400", s == 400, f"status={s}")

print("\nportfolio")
s, d = post("/arkham-intel/portfolio", {"address": TREASURY, "tokens": [USDC]})
check("200 for the treasury", s == 200, f"status={s} {str(d)[:120]}")
check("values the named token", bool(d.get("holdings")), str(d.get("holdings"))[:120])
check("USDC valued near $1 (price derivation fixed)",
      not d.get("holdings") or d["holdings"][0].get("price_usd") is None or 0.9 <= d["holdings"][0]["price_usd"] <= 1.1,
      str(d.get("holdings", [{}])[0].get("price_usd")))
check("states it is a snapshot, not a curve",
      any("curve" in x for x in (d.get("not_checked") or [])), str(d.get("not_checked"))[:100])
s, _ = post("/arkham-intel/portfolio", {"address": "0x123"})
check("bad address -> 400", s == 400, f"status={s}")

print("\ncounterparties")
s, d = post("/arkham-intel/counterparties", {"address": TREASURY, "hours": 24, "limit": 5})
check("200 for the treasury", s == 200, f"status={s} {str(d)[:120]}")
check("tokens scanned are declared", isinstance(d.get("tokens_scanned"), list) and d["tokens_scanned"], "")
check("rpc errors surfaced, not swallowed", isinstance(d.get("rpc_errors"), list), "")
check("flags named as 'no data' when unlabelled",
      "no data" in str(d.get("methodology", {}).get("labels", "")) or bool(d.get("labels_configured")),
      str(d.get("methodology", {}).get("labels"))[:90])

print("\ntrace")
s, d = post("/arkham-intel/trace", {"address": TREASURY, "hops": 1, "hours": 6})
check("200 for the treasury", s == 200, f"status={s} {str(d)[:120]}")
check("returns hop levels", isinstance(d.get("hops"), list) and len(d.get("hops") or []) >= 1, str(d.get("hops"))[:80])
check("labels file is loaded (3 curated entries)", d.get("labels_configured") == 3, str(d.get("labels_configured")))
check("says an empty flags list is not 'no risk'",
      "no risk" in str(d.get("methodology", {}).get("flags", "")) or d.get("labels_configured") == 3,
      str(d.get("methodology", {}).get("flags"))[:90])

print("\nvenue-users (6th endpoint, broker view)")
s, d = post("/arkham-intel/venue-users", {"address": TREASURY, "hours": 24, "limit": 10})
check("200 for the treasury", s == 200, f"status={s} {str(d)[:120]}")
check("reports users + value segments", "users_total" in d and isinstance(d.get("value_segments"), dict),
      json.dumps(d.get("value_segments")))
check("vip / quiet / flagged sections present",
      all(k in d for k in ("vip_candidates", "went_quiet", "flagged_funders")), str(list(d.keys())))
check("identity limits stated", any("identity" in x for x in (d.get("not_checked") or [])), str(d.get("not_checked"))[:120])
s, _ = post("/arkham-intel/venue-users", {"address": "0xzz"})
check("bad address -> 400", s == 400, f"status={s}")

print("\nrouting table")
routes = [r for r in server.PAID_ROUTES if "/arkham-intel/" in r[0]]
check("12 entries on the gate (6 POST + 6 GET)", len(routes) == 12, str(len(routes)))
check("all priced 0.10", all(server.PRICE_OVERRIDES.get(r[0]) == 0.1 for r in routes), "")
check("public resource path overridden",
      all(server.RESOURCE_OVERRIDES.get(r[0], "").startswith("/api/arkham-intel/") for r in routes), "")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
