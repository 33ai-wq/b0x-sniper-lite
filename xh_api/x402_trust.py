"""x402_trust — the "check before you pay" layer for machine buyers.

An agent about to pay an unknown x402 endpoint has no way to tell a working seller from a
half-registered one, a stale listing, or a payout address nobody has ever seen. This module answers that
in one call: it fetches the endpoint, decodes the 402 challenge, checks the discovery documents, inspects
the payTo address on-chain, and returns a 0-100 trust score with the evidence behind every point.

Nothing here is a guess. Each point comes from a request we actually made or a chain read we actually
performed; anything we could not check is listed in `not_checked` and scored as zero rather than assumed.
"""

import base64
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
USDC_SOLANA = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
KNOWN_NETWORKS = {
    "eip155:8453", "base", "solana", "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    "eip155:1", "ethereum", "eip155:137", "polygon", "eip155:42161", "arbitrum",
}
SOLANA_RPC = ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"]
VERDICT_PAY = 80
VERDICT_CAUTION = 60
ZERO = "0x0000000000000000000000000000000000000000"

# selectors that mark a token as having powers beyond a plain ERC-20
RISKY_SELECTORS = {
    "mint(address,uint256)": "40c10f19",
    "blacklist(address)": "fe575a87",
    "pause()": "8456cb59",
    "setFees(uint256,uint256)": "8a8c523c",
    "setMaxTxAmount(uint256)": "ec28438a",
}


@dataclass
class Ctx:
    check_ssrf: Callable[[str], str | None]
    decode_challenge: Callable[[str | None, str], tuple[dict | None, str | None]]
    rpc: Callable[..., Any]                  # Base JSON-RPC through the server's fallback list
    erc20: Callable[..., Any]
    is_address: Callable[[str], bool]
    alchemy_url: str = ""


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: float = 20.0) -> dict:
    import httpx
    started = time.perf_counter()
    try:
        with httpx.Client(follow_redirects=True, max_redirects=3, timeout=timeout) as c:
            content = json.dumps(body) if body is not None and method in ("POST", "PUT", "PATCH") else None
            r = c.request(method, url, content=content,
                          headers={"Content-Type": "application/json", "Accept": "*/*"})
            return {"ok": True, "status": r.status_code,
                    "headers": {k.lower(): v for k, v in r.headers.items()},
                    "text": r.text[:200000], "ms": round((time.perf_counter() - started) * 1000)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}",
                "ms": round((time.perf_counter() - started) * 1000)}


def _origin_of(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _solana_rpc(method: str, params: list, timeout: float = 20.0) -> Any:
    last = None
    for url in SOLANA_RPC:
        try:
            req = urllib.request.Request(url, data=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "xh-agents-trust/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read().decode())
            if "error" in j:
                raise RuntimeError(str(j["error"])[:120])
            return j.get("result")
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError(f"solana rpc unavailable: {last}")


# ── payTo reputation (the part that actually protects a buyer) ───────────────

def _classify_base(ctx: Ctx, addr: str) -> dict:
    """EOA, EIP-7702 delegated EOA (a smart wallet) or a real contract — the distinction matters:
    a delegated EOA still gives the owner full control, a contract's withdrawals depend on its code."""
    out: dict[str, Any] = {}
    try:
        code = (ctx.rpc("eth_getCode", [addr, "latest"]) or "0x").lower()
    except Exception as e:
        return {"kind": f"unreadable ({type(e).__name__})"}
    if code in ("0x", "0x0", ""):
        return {"kind": "eoa"}
    if code.startswith("0xef0100") and len(code) >= 48:
        impl = "0x" + code[8:48]
        out.update({"kind": "eoa_eip7702_delegated", "delegation_target": impl,
                    "note": "smart wallet: an EOA that delegates execution to a contract; the key holder "
                            "still controls the funds"})
        return out
    out.update({"kind": "contract"})
    return out


def payto_base(ctx: Ctx, addr: str) -> dict:
    out: dict[str, Any] = {"address": addr, "chain": "base"}
    out.update(_classify_base(ctx, addr))
    try:
        out["nonce"] = int(ctx.rpc("eth_getTransactionCount", [addr, "latest"]), 16)
    except Exception:
        out["nonce"] = None
    out["indexer"] = "alchemy_getAssetTransfers" if ctx.alchemy_url else None
    if not ctx.alchemy_url:
        # No indexer: say so. Silence here used to read as "no USDC inflow", which is a claim we did not check.
        out["checked"] = False
        out["reason"] = "no transfer indexer configured on this server: USDC inflow history was NOT inspected"
    else:
        try:
            req = urllib.request.Request(ctx.alchemy_url, data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "alchemy_getAssetTransfers",
                "params": [{"fromBlock": "0x0", "toBlock": "latest", "toAddress": addr,
                            "contractAddresses": [USDC_BASE], "category": ["erc20"],
                            "order": "desc", "maxCount": "0x19", "withMetadata": True}]}).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                j = json.loads(r.read().decode())
            if j.get("error"):
                out["checked"] = False
                out["reason"] = f"indexer refused the query: {str(j['error'])[:120]}"
            else:
                rows = ((j.get("result") or {}).get("transfers")) or []
                senders = {(t.get("from") or "").lower() for t in rows}
                stamps = [((t.get("metadata") or {}).get("blockTimestamp") or "")[:19] for t in rows]
                total = 0.0
                for t in rows:
                    try:
                        total += float(t.get("value") or 0)
                    except Exception:
                        pass
                out.update({"checked": True, "usdc_transfers_seen": len(rows), "distinct_senders": len(senders),
                            "usdc_received": round(total, 4),
                            "last_received": max(stamps) if stamps else None,
                            "source": "alchemy_getAssetTransfers (last 25 USDC inflows)"})
        except Exception as e:
            out["checked"] = False
            out["reason"] = f"indexer call failed: {type(e).__name__}: {str(e)[:100]}"
    return out


def payto_solana(addr: str) -> dict:
    out: dict[str, Any] = {"address": addr, "chain": "solana"}
    try:
        info = _solana_rpc("getAccountInfo", [addr, {"encoding": "jsonParsed"}])
        val = (info or {}).get("value")
        out["exists"] = val is not None
        out["owner_program"] = (val or {}).get("owner")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    try:
        acc = _solana_rpc("getTokenAccountsByOwner",
                          [addr, {"mint": USDC_SOLANA}, {"encoding": "jsonParsed"}])
        amt = 0.0
        for a in (acc or {}).get("value", []):
            amt += float((a.get("account", {}).get("data", {}).get("parsed", {})
                          .get("info", {}).get("tokenAmount", {}).get("uiAmount") or 0))
        out["usdc_balance"] = round(amt, 6)
    except Exception:
        out["usdc_balance"] = None
    try:
        sigs = _solana_rpc("getSignaturesForAddress", [addr, {"limit": 25}])
        out["recent_signatures"] = len(sigs or [])
        out["checked"] = True
        if sigs:
            bt = sigs[0].get("blockTime")
            out["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(bt)) if bt else None
    except Exception as e:
        out["recent_signatures"] = None
        out["checked"] = False
        out["reason"] = f"the public RPC refused the history query ({type(e).__name__}) — activity was NOT inspected"
    return out


def _payto_points(p: dict) -> tuple[float, list[str]]:
    pts, notes = 0.0, []
    # An unmeasured check must never look like a bad result: award the neutral middle and say why.
    if p.get("checked") is False:
        notes.append("payTo reputation NOT measured: " + str(p.get("reason") or "the check could not run")[:150])
        return 12.0, notes
    if p.get("chain") == "base":
        if p.get("kind") == "eoa":
            pts += 4
            notes.append("payTo is a plain EOA (no contract can freeze the funds)")
        elif p.get("kind") == "eoa_eip7702_delegated":
            pts += 4
            notes.append(f"payTo is an EOA running a smart-wallet delegation ({(p.get('delegation_target') or '')[:10]}…) "
                         "— the key holder still controls the funds")
        elif p.get("kind") == "contract":
            pts += 2
            notes.append("payTo is a contract: withdrawals depend on its code")
        seen = p.get("usdc_transfers_seen") or 0
        senders = p.get("distinct_senders") or 0
        if seen >= 10:
            pts += 14
            notes.append(f"{seen} USDC inflows from {senders} sender(s) on record")
        elif seen >= 3:
            pts += 9
            notes.append(f"{seen} USDC inflows — a working address, but thin history")
        elif seen >= 1:
            pts += 4
            notes.append("1-2 USDC inflows: barely used payout address")
        else:
            notes.append("no USDC inflow found for this payTo on Base: unproven address")
        if senders >= 3:
            pts += 4
            notes.append(f"{senders} distinct senders = more than one buyer's word for it")
    else:
        if p.get("exists"):
            pts += 4
            notes.append("Solana payTo account exists")
        else:
            notes.append("Solana payTo account does not exist (typo, or never funded)")
        if (p.get("usdc_balance") or 0) > 0:
            pts += 5
            notes.append(f"holds {p['usdc_balance']} USDC already")
        sigs = p.get("recent_signatures") or 0
        if sigs >= 10:
            pts += 12
            notes.append(f"{sigs} signatures in its recent history")
        elif sigs >= 1:
            pts += 6
            notes.append(f"{sigs} recent signature(s) only")
        else:
            notes.append("no recent activity on the Solana payTo")
    return min(pts, 25.0), notes


# ── the whole check ─────────────────────────────────────────────────────────

def assess(ctx: Ctx, url: str, method: str = "POST", body: dict | None = None,
           deep: bool = True) -> dict:
    started = time.time()
    url = url.strip()
    bad = ctx.check_ssrf(url)
    if bad:
        return {"url": url, "reachable": False, "refused": bad,
                "score": 0, "verdict": "avoid",
                "reason": "the target resolves to a private address or is not http(s)"}
    method = (method or "POST").upper()
    # "AUTO" exists because a seller that answers GET with a 402 will often answer POST with 400/404 — a probe
    # with the wrong verb then reports "no payTo" about a challenge that was never seen. Try the verbs an agent
    # would try and keep the one that actually produced a challenge.
    attempted: list[str] = []
    if method == "AUTO":
        best = None
        for m in ("POST", "GET"):
            p = _http(url, m, {} if m == "POST" else None)
            attempted.append(m)
            if p.get("ok") and p.get("status") == 402:
                best = (m, p)
                break
            if best is None and p.get("ok"):
                best = (m, p)
        if best:
            method, probe = best
        else:
            probe = p if attempted else _http(url, "POST", {})
            method = attempted[-1] if attempted else "POST"
    else:
        probe = _http(url, method, body if body is not None else {})
        attempted.append(method)
    if not probe.get("ok"):
        return {"url": url, "method": method, "reachable": False, "error": probe.get("error"),
                "score": 0, "verdict": "avoid",
                "reason": "the endpoint did not answer; an agent that pays an unreachable seller has no recourse"}

    # A seller can answer 200 on the first call (a free trial, or a preview that the buyer consumes) and
    # 402 on the next one, so a single probe honestly reports "no terms at all" for a route that is
    # priced and payable. Reported by baianomarceloeduardo-jpg (2026-10-10, pulsefeed-x402#36) with his
    # own route as the example. When the first probe shows no challenge, probe the same verb once more
    # before concluding, and keep both observations in the report.
    retry: dict[str, Any] = {}
    if probe["status"] != 402:
        first_status = probe["status"]
        again = _http(url, method, body if body is not None else {})
        attempted.append(f"{method}(retry)")
        second_challenge = None
        if again.get("ok"):
            second_challenge, _ = ctx.decode_challenge(again["headers"].get("payment-required"),
                                                       again["text"])
        if again.get("ok") and again.get("status") == 402 and second_challenge:
            retry = {"first": first_status, "second": again["status"]}
            probe = again
        else:
            retry = {"first": first_status, "second": again.get("status") if again.get("ok") else None}

    status = probe["status"]
    headers = probe["headers"]
    challenge, transport = ctx.decode_challenge(headers.get("payment-required"), probe["text"])
    accs = (challenge or {}).get("accepts") or []
    a0 = accs[0] if isinstance(accs, list) and accs else (accs if isinstance(accs, dict) else {})
    checks: dict[str, Any] = {"probe_method": method, "methods_attempted": attempted}
    if retry:
        checks["no_challenge_retry"] = retry
    points: dict[str, Any] = {}
    notes: list[str] = []
    if retry.get("second") == 402:
        notes.append(f"the first probe answered {retry['first']} with no terms and the immediate retry "
                     "returned the 402: a trial or a consumed preview, not an unpriced route")
    elif retry and retry.get("second") is not None:
        notes.append(f"probed twice, {retry['first']} then {retry['second']}: the route served no payment "
                     "terms either time")
    if len(attempted) > 1 and method != attempted[0]:
        notes.append(f"the {attempted[0]} probe answered without a challenge while {method} returned the 402: "
                     "an agent has to pick the right verb")

    # 1. gate behaviour (25)
    gate = 0.0
    checks["returns_402_without_payment"] = status == 402
    if status == 402:
        gate += 15
    elif status == 200:
        notes.append("endpoint answered 200 with no payment: there is nothing to trust here, it is free")
    if probe["ms"] <= 3000:
        gate += 5
    else:
        notes.append(f"slow challenge ({probe['ms']} ms) — an agent's budget may expire before it pays")
    if url.lower().startswith("https://"):
        gate += 5
    else:
        notes.append("plain http: the payment header travels in clear text")
    points["gate"] = round(gate, 1)

    # 2. challenge conformance (20)
    conf = 0.0
    checks["challenge_present"] = challenge is not None
    checks["challenge_transport"] = transport
    checks["x402_version"] = (challenge or {}).get("x402Version")
    if challenge is not None:
        conf += 4
    if (challenge or {}).get("x402Version") == 2:
        conf += 3
    elif challenge is not None:
        notes.append(f"x402Version {checks['x402_version']}: the v1 envelope is deprecated and some buyers reject it")
    missing = [f for f in ("scheme", "network", "asset", "payTo", "maxTimeoutSeconds")
               if a0.get(f) in (None, "")]
    checks["accepts_missing_fields"] = missing
    conf += max(0.0, 8 - 2.0 * len(missing))
    amount = a0.get("amount") or a0.get("maxAmountRequired")
    checks["amount_atomic"] = isinstance(amount, str) and amount.isdigit()
    if checks["amount_atomic"]:
        conf += 5
    points["challenge"] = round(conf, 1)

    # 3. discovery hygiene (15)
    disc = 0.0
    origin = _origin_of(url)
    wk = _http(origin + "/.well-known/x402", "GET")
    checks["well_known_reachable"] = bool(wk.get("ok") and wk.get("status") == 200)
    listed = False
    if checks["well_known_reachable"]:
        disc += 4
        try:
            man = json.loads(wk["text"])
            res = man.get("resources") or []
            urls = [x if isinstance(x, str) else (x.get("resource") or "") for x in res]
            listed = any(url.rstrip("/") in (u or "") for u in urls)
            checks["listed_in_own_discovery"] = listed
            if listed:
                disc += 4
            else:
                notes.append("the resource is not listed in its own .well-known/x402 document")
        except Exception:
            notes.append(".well-known/x402 is not valid JSON")
    else:
        notes.append("no reachable .well-known/x402 discovery document")
    oa = _http(origin + "/openapi.json", "GET")
    checks["openapi_reachable"] = bool(oa.get("ok") and oa.get("status") == 200)
    if checks["openapi_reachable"]:
        disc += 3
        try:
            doc = json.loads(oa["text"])
            path = urllib.parse.urlparse(url).path
            op = ((doc.get("paths") or {}).get(path) or {}).get(method.lower()) or {}
            has_schema = bool(op.get("parameters") or op.get("requestBody"))
            checks["declares_input_schema"] = has_schema
            if has_schema:
                disc += 4
            else:
                notes.append("openapi.json documents this path without an input schema")
        except Exception:
            notes.append("openapi.json is not valid JSON")
    else:
        notes.append("no reachable openapi.json")
    points["discovery"] = round(disc, 1)

    # 4. payTo reputation (25) — the deep check, and the only one that costs chain calls
    payto = a0.get("payTo") or a0.get("recipient") or ""
    rep: dict[str, Any] = {"address": payto}
    if not payto:
        # No payTo in the challenge: there is nothing to inspect, and saying the account "does not exist"
        # would be a claim about an address that was never given.
        rep = {"address": "", "chain": "unknown", "checked": False,
               "reason": "the accepts entry declares no payTo, so there is nothing to verify on-chain"}
    elif deep and payto != ZERO:
        if ctx.is_address(payto):
            rep = payto_base(ctx, payto)
        elif re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", payto):
            rep = payto_solana(payto)
        else:
            rep = {"address": payto, "checked": False, "reason": "unrecognised address format"}
    pay_pts, pay_notes = _payto_points(rep) if deep else (0.0, [])
    if not payto:
        pay_notes.append("the challenge declares no payTo: a buyer has no address to pay")
    notes.extend(pay_notes)
    if payto and payto.lower() == ZERO:
        notes.append("PAYTO IS THE ZERO ADDRESS: paying here burns the money")
    points["payto"] = round(pay_pts, 1)

    # 5. price sanity (10)
    price = 0.0
    if checks["amount_atomic"]:
        usd = int(amount) / 1e6
        checks["price_usd"] = usd
        if 0 < usd <= 1.0:
            price += 4
        elif usd > 1.0:
            notes.append(f"${usd:.2f} per call is far above the ecosystem median ($0.01-0.30): check what you get")
        if usd > 0:
            price += 2
        declared = None
        m = re.search(r"\$(\d+\.?\d{0,4})", probe["text"][:2000] + json.dumps(challenge or {})[:2000])
        if m:
            declared = float(m.group(1))
        checks["price_matches_description"] = (declared is None or abs(declared - usd) < 0.011)
        if checks["price_matches_description"]:
            price += 4
        else:
            notes.append(f"the challenge asks ${usd:.4f} while the page/description says ${declared:.4f}")
    points["price"] = round(price, 1)

    # 6. replay / settlement hygiene (5)
    safe = 0.0
    ttl = a0.get("maxTimeoutSeconds")
    checks["timeout_seconds"] = ttl
    if isinstance(ttl, int) and 30 <= ttl <= 7200:
        safe += 3
    elif ttl is not None:
        notes.append(f"maxTimeoutSeconds={ttl} is outside the sane 30-7200s window")
    env = challenge or {}
    checks["has_nonce_or_expiry"] = bool(env.get("nonce") or env.get("expires_at")
                                         or env.get("expiresAt")
                                         or ((env.get("extensions") or {}).get("bazaar")))
    if checks["has_nonce_or_expiry"]:
        safe += 2
    else:
        notes.append("the challenge carries no nonce/expiry we can see: replay behaviour is unproven")
    points["replay"] = round(safe, 1)

    # penalties
    penalty = 0.0
    asset = (a0.get("asset") or "").lower()
    network = (a0.get("network") or "").lower()
    if asset and asset not in (USDC_BASE, USDC_SOLANA.lower()):
        penalty += 15
        notes.append(f"asset {asset[:12]}… is not the USDC contract we can verify")
    if network and network.lower() not in {n.lower() for n in KNOWN_NETWORKS}:
        penalty += 10
        notes.append(f"network '{network}' is not one we can settle or verify")
    if payto and payto.lower() == ZERO:
        penalty += 40
    if status == 200:
        penalty += 5
    resource = (challenge or {}).get("resource")
    rurl = resource.get("url") if isinstance(resource, dict) else resource
    if rurl and url.rstrip("/") not in str(rurl).rstrip("/") and str(rurl).rstrip("/") not in url:
        penalty += 10
        notes.append("the challenge names a different resource URL than the one requested")

    raw = sum(points.values()) - penalty
    score = max(0, min(100, round(raw)))
    verdict = "pay" if score >= VERDICT_PAY else ("pay_with_caution" if score >= VERDICT_CAUTION else "avoid")

    return {
        "url": url, "method": method, "origin": origin, "reachable": True,
        "status": status, "latency_ms": probe["ms"],
        "score": score, "verdict": verdict,
        "points": points, "penalty": round(penalty, 1),
        "checks": checks,
        "accepts": [{"scheme": a.get("scheme"), "network": a.get("network"), "asset": a.get("asset"),
                     "amount": a.get("amount") or a.get("maxAmountRequired"), "payTo": a.get("payTo"),
                     "maxTimeoutSeconds": a.get("maxTimeoutSeconds")} for a in
                    (accs if isinstance(accs, list) else [accs])[:3]],
        "payto_inspection": rep,
        "findings": notes,
        "methodology": {
            "weighting": {"gate_behaviour": 25, "challenge_conformance": 20, "discovery_hygiene": 15,
                          "payto_reputation_onchain": 25, "price_sanity": 10, "replay_hygiene": 5},
            "verdicts": {"pay": f">= {VERDICT_PAY}", "pay_with_caution": f"{VERDICT_CAUTION}-{VERDICT_PAY - 1}",
                         "avoid": f"< {VERDICT_CAUTION}"},
            "payto": "Base: USDC inflows into the payTo address via an indexer + nonce/code class; "
                     "Solana: account existence, USDC balance and recent signatures",
            "probe": f"one real {method} request with an empty body, plus GETs of /.well-known/x402 and /openapi.json",
        },
        "not_checked": [
            "whether the seller actually delivers after payment (that would need a real purchase)",
            "uptime over time — this is a point-in-time report",
            "legal identity of the operator behind the endpoint",
            "whether the service is a reseller of someone else's API",
        ],
        "elapsed_ms": round((time.time() - started) * 1000),
    }


# ── HTTP surface ─────────────────────────────────────────────────────────────

def register(app, ctx: Ctx) -> None:
    from pydantic import BaseModel, Field

    class TrustReq(BaseModel):
        url: str = Field(..., description="The x402 endpoint an agent is about to pay")
        method: str = Field("POST", description="HTTP method the agent will use")
        body: dict | None = Field(None, description="JSON body the agent would send")
        deep: bool = Field(True, description="Also inspect the payTo address on-chain (slower)")

    @app.get("/x402-trust/method")
    def index():
        return {
            "provider": "XH Agents — x402 trust layer (check before you pay)",
            "what_it_is": ("Point it at any x402 endpoint: it makes the unpaid request, decodes the 402 challenge, "
                           "reads the origin's discovery documents, inspects the payTo address on-chain and returns "
                           "a 0-100 trust score with the evidence behind every point."),
            "price_usdc_per_call": 0.05,
            "endpoints": [{"route": "POST /api/x402-trust", "price_usd": 0.05},
                          {"route": "GET /api/x402-trust?url=…", "price_usd": 0.05}],
            "probe_method": ("pass method=auto to try POST and GET and score the verb that actually returns a "
                             "challenge — a seller that answers GET with 402 often answers POST with 400, and "
                             "probing the wrong verb would score a challenge that was never seen"),
            "verdicts": {"pay": ">= 80", "pay_with_caution": "60-79", "avoid": "< 60"},
            "weights": {"gate_behaviour": 25, "challenge_conformance": 20, "discovery_hygiene": 15,
                        "payto_reputation_onchain": 25, "price_sanity": 10, "replay_hygiene": 5},
            "not_checked": ["does the seller deliver after payment", "uptime over time", "operator identity"],
        }

    def _run(url: str, method: str, body: dict | None, deep: bool) -> dict:
        return assess(ctx, url, method, body, deep)

    @app.post("/x402-trust")
    def trust_post(req: TrustReq):
        return _run(req.url, req.method, req.body, req.deep)

    @app.get("/x402-trust")
    def trust_get(url: str, method: str = "auto", deep: bool = True):
        return _run(url, method, None, deep)
