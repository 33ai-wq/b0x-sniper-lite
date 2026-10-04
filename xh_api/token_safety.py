"""token_safety — a 0-100 safety score for a Base token, with the evidence behind every point.

Built for agents that must decide *before* buying: liquidity, who holds it, whether the contract keeps
owner powers, whether the creator has a habit of launching tokens, and what a small trade would cost in
slippage. Every component is read from a public source at request time (Blockscout Base, the Base RPC,
DexScreener). Checks we cannot perform honestly (buy/sell tax, honeypot simulation, off-chain intent) are
listed in `not_checked` instead of being guessed.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

BLOCKSCOUT = "https://base.blockscout.com/api/v2"
ZERO = "0x0000000000000000000000000000000000000000"
BURN = {"0x000000000000000000000000000000000000dEaD".lower(), ZERO}
VERDICT_SAFE = 75
VERDICT_CAUTION = 50

RISKY_SELECTORS = {
    "0x40c10f19": "mint(address,uint256) — supply can be increased",
    "0xfe575a87": "blacklist(address) — an address can be blocked",
    "0x8456cb59": "pause() — transfers can be halted",
    "0x8a8c523c": "setFees(uint256,uint256) — fees can be changed",
    "0xec28438a": "setMaxTxAmount(uint256) — trade size can be capped",
}
LP_LOCK_LABELS = ("lock", "vesting", "safe", "timelock")


@dataclass
class Ctx:
    rpc: Callable[..., Any]
    erc20: Callable[..., Any]
    is_address: Callable[[str], bool]
    alchemy_url: str = ""


def _get(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "xh-agents-safety/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _rpc(ctx: Ctx, method: str, params: list) -> Any:
    return ctx.rpc(method, params)


def _dex(token: str) -> dict | None:
    try:
        j = _get(f"https://api.dexscreener.com/latest/dex/tokens/{token}")
        pairs = [p for p in (j.get("pairs") or []) if p.get("chainId") == "base"]
        if not pairs:
            return None
        best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        return {"pair": best.get("pairAddress"), "dex": best.get("dexId"),
                "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0),
                "volume_24h_usd": float((best.get("volume") or {}).get("h24") or 0),
                "price_usd": float(best.get("priceUsd") or 0),
                "price_change_24h_pct": (best.get("priceChange") or {}).get("h24"),
                "created_at": best.get("pairCreatedAt"),
                "url": best.get("url")}
    except Exception:
        return None


def _sourcify_verified(token: str) -> dict:
    """Second opinion on verification: Sourcify's keyless API, chain 8453 (Base)."""
    try:
        d = _get(f"https://sourcify.dev/server/v2/contract/8453/{token}?fields=match,creationMatch")
        return {"match": d.get("match"), "creationMatch": d.get("creationMatch")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:80]}"}


def _holders(token: str, limit: int = 50) -> dict:
    try:
        d = _get(f"{BLOCKSCOUT}/tokens/{token}/holders")
        items = d.get("items") or []
        rows = []
        for it in items[:limit]:
            a = it.get("address") or {}
            raw = it.get("value") or "0"
            rows.append({"address": (a.get("hash") or "").lower(), "label": a.get("name"),
                         "is_contract": bool(a.get("is_contract")), "raw": raw})
        return {"top": rows, "pages_available": bool(d.get("next_page_params"))}
    except Exception as e:
        return {"top": [], "error": f"{type(e).__name__}: {str(e)[:120]}"}


def _address_info(token: str) -> dict:
    try:
        d = _get(f"{BLOCKSCOUT}/addresses/{token}")
        return {"is_contract": d.get("is_contract"), "is_verified": d.get("is_verified"),
                "name": d.get("name"), "creator": (d.get("creator_address_hash") or "").lower() or None,
                "creation_tx": d.get("creation_tx_hash"),
                "holder_count": (d.get("token") or {}).get("holders")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _bytecode_risks(ctx: Ctx, token: str) -> dict:
    try:
        code = (_rpc(ctx, "eth_getCode", [token, "latest"]) or "").lower()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:100]}", "length": 0}
    found = [desc for sel, desc in RISKY_SELECTORS.items() if sel in code]
    return {"length": max(0, (len(code) - 2) // 2), "risky_selectors": found}


def _owner(ctx: Ctx, token: str) -> dict:
    try:
        o = ctx.erc20(token, "owner")
        return {"owner": (o or "").lower(), "renounced": (o or "").lower() in BURN}
    except Exception:
        return {"owner": None, "renounced": None,
                "note": "no owner() function — either renounced/immutable or not a standard Ownable"}


def _proxy(ctx: Ctx, token: str) -> dict:
    slot = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
    try:
        raw = _rpc(ctx, "eth_getStorageAt", [token, slot, "latest"]) or "0x"
        impl = "0x" + raw[-40:]
        upgradeable = impl.lower() not in (ZERO, "0x" + "0" * 40)
        return {"upgradeable": upgradeable, "implementation": impl if upgradeable else None}
    except Exception:
        return {"upgradeable": None}


def _deployer_history(ctx: Ctx, creator: str | None) -> dict:
    if not creator:
        return {"deployer": None, "note": "creator unknown from the explorer"}
    out: dict[str, Any] = {"deployer": creator}
    try:
        out["deployer_nonce"] = int(_rpc(ctx, "eth_getTransactionCount", [creator, "latest"]), 16)
    except Exception:
        out["deployer_nonce"] = None
    try:
        d = _get(f"{BLOCKSCOUT}/addresses/{creator}/transactions?filter=from")
        items = d.get("items") or []
        out["recent_outgoing_txs"] = len(items)
        out["note"] = "transaction count is a floor, not a full launch history"
    except Exception:
        pass
    return out


def _slippage(liquidity_usd: float, trade_usd: float = 1000.0) -> dict:
    """Constant-product arithmetic on the pool's USD liquidity: a floor, not a quote."""
    if liquidity_usd <= 0:
        return {"trade_usd": trade_usd, "price_impact_pct": None}
    # x*y=k with the pool's USD value on both sides approximated by liquidity/2 per side
    side = liquidity_usd / 2.0
    impact = trade_usd / (side + trade_usd) * 100.0
    return {"trade_usd": trade_usd, "price_impact_pct": round(impact, 3),
            "assumption": "constant product, liquidity split evenly across the pair"}


def assess(ctx: Ctx, token: str) -> dict:
    started = time.time()
    token = token.lower()
    if not ctx.is_address(token):
        return {"token": token, "error": "not a Base contract address", "score": 0, "verdict": "avoid"}

    checks: dict[str, Any] = {}
    points: dict[str, Any] = {}
    findings: list[str] = []

    meta = {"token": token}
    for fn in ("symbol", "decimals", "name", "totalSupply"):
        try:
            meta[fn] = ctx.erc20(token, fn)
        except Exception:
            pass
    dex = _dex(token)
    info = _address_info(token)
    holders = _holders(token)
    code = _bytecode_risks(ctx, token)
    owner = _owner(ctx, token)
    proxy = _proxy(ctx, token)
    deployer = _deployer_history(ctx, info.get("creator"))
    checks.update({"bytecode": code, "owner": owner, "proxy": proxy, "deployer": deployer,
                   "address_info": info})

    # 1. liquidity (25)
    liq = float((dex or {}).get("liquidity_usd") or 0)
    vol = float((dex or {}).get("volume_24h_usd") or 0)
    p = 0.0
    if liq >= 250_000:
        p += 25
        findings.append(f"deep liquidity (${liq:,.0f})")
    elif liq >= 50_000:
        p += 18
        findings.append(f"workable liquidity (${liq:,.0f})")
    elif liq >= 10_000:
        p += 10
        findings.append(f"thin liquidity (${liq:,.0f}) — exits will move the price")
    elif liq > 0:
        p += 4
        findings.append(f"very thin liquidity (${liq:,.0f})")
    else:
        findings.append("no Base pair found: nothing to sell into")
    points["liquidity"] = round(p, 1)

    # 2. holder concentration (25) — top-10 share of supply from the explorer's holder list
    p = 0.0
    conc = None
    try:
        total = float(meta.get("totalSupply") or 0)
        top = holders.get("top") or []
        if total > 0 and top:
            parts = []
            for h in top[:10]:
                try:
                    parts.append(float(h["raw"]) / total)
                except Exception:
                    continue
            conc = sum(parts)
            checks["top10_share_pct"] = round(conc * 100, 2)
            checks["top10_addresses"] = [{"address": h["address"], "label": h.get("label"),
                                          "is_contract": h.get("is_contract")} for h in top[:10]]
            if conc <= 0.25:
                p += 25
                findings.append(f"holders are spread out (top 10 hold {conc*100:.1f}%)")
            elif conc <= 0.45:
                p += 16
                findings.append(f"moderate concentration (top 10 hold {conc*100:.1f}%)")
            elif conc <= 0.65:
                p += 8
                findings.append(f"concentrated (top 10 hold {conc*100:.1f}%) — a few wallets can dump")
            else:
                p += 2
                findings.append(f"extremely concentrated (top 10 hold {conc*100:.1f}%)")
            lp_like = [h for h in top[:10]
                       if h.get("is_contract") and any(k in (h.get("label") or "").lower() for k in LP_LOCK_LABELS)]
            if lp_like:
                p += 3
                findings.append(f"a lock/vesting contract sits in the top holders ({lp_like[0]['label']})")
        else:
            # unmeasured is not the same as bad: give a neutral floor and say so
            p += 12
            findings.append("holder concentration could not be measured (explorer returned no holder list) "
                            "— scored neutral, treat this component as unknown")
    except Exception as e:
        p += 12
        findings.append(f"concentration check failed ({type(e).__name__}) — scored neutral")
    points["concentration"] = round(min(p, 25.0), 1)

    # 3. contract powers (20)
    p = 0.0
    risks = code.get("risky_selectors") or []
    if risks:
        p += max(0, 12 - 4 * len(risks))
        findings.extend(f"contract exposes {r}" for r in risks[:3])
    else:
        p += 12
        findings.append("no mint/blacklist/pause/fee setters found in the bytecode")
    if owner.get("renounced") is True:
        p += 8
        findings.append("ownership is renounced")
    elif owner.get("owner"):
        findings.append("an owner address still exists — it may retain powers")
        p += 3
    elif owner.get("renounced") is None:
        p += 4
        findings.append(owner.get("note", "owner state unknown"))
    points["contract_powers"] = round(min(p, 20.0), 1)

    # 4. upgradeability + verification (15)
    p = 0.0
    if proxy.get("upgradeable") is True:
        findings.append(f"proxy contract: logic can be replaced ({proxy.get('implementation')})")
        p += 3
    elif proxy.get("upgradeable") is False:
        p += 7
        findings.append("not upgradeable")
    else:
        p += 4
    verified = info.get("is_verified")
    sourcify = _sourcify_verified(token)
    checks["is_verified"] = verified
    checks["sourcify"] = sourcify
    if verified or sourcify.get("match"):
        p += 8
        findings.append("source is verified"
                        + ("" if verified else " (Sourcify) ")
                        + ("on the explorer" if verified else ""))
    else:
        findings.append("source is NOT verified in either explorer — its behaviour cannot be read from code")
        p += 1
    points["upgradeability_verification"] = round(min(p, 15.0), 1)

    # 5. creator history (10)
    p = 0.0
    nonce = deployer.get("deployer_nonce")
    if deployer.get("deployer") is None:
        p += 4
    elif isinstance(nonce, int):
        if nonce <= 50:
            p += 8
            findings.append(f"creator has a short history ({nonce} txs)")
        elif nonce <= 500:
            p += 5
        else:
            p += 2
            findings.append(f"creator wallet is heavily used ({nonce} txs) — serial launcher possible")
    else:
        p += 4
    points["creator_history"] = round(min(p, 10.0), 1)

    # 6. tradability / slippage (5)
    p = 0.0
    slip = _slippage(liq)
    checks["slippage"] = slip
    impact = slip.get("price_impact_pct")
    if impact is None:
        p += 0
    elif impact <= 1:
        p += 5
        findings.append(f"a $1k trade costs about {impact}% in price impact")
    elif impact <= 5:
        p += 3
        findings.append(f"a $1k trade moves the price about {impact}%")
    else:
        p += 1
        findings.append(f"a $1k trade would move the price {impact}% — effectively illiquid")
    if vol > 5_000:
        p = min(5.0, p + 0)
    points["tradability"] = round(min(p, 5.0), 1)

    raw = sum(points.values())
    score = max(0, min(100, round(raw)))
    verdict = ("safe" if score >= VERDICT_SAFE else
               "caution" if score >= VERDICT_CAUTION else "danger")

    return {
        "token": token, "symbol": meta.get("symbol"), "name": meta.get("name"),
        "decimals": meta.get("decimals"),
        "score": score, "verdict": verdict,
        "points": points,
        "weights": {"liquidity": 25, "concentration": 25, "contract_powers": 20,
                    "upgradeability_verification": 15, "creator_history": 10, "tradability": 5},
        "market": dex,
        "holders": checks.get("top10_addresses"),
        "top10_share_pct": checks.get("top10_share_pct"),
        "holder_count": info.get("holder_count"),
        "contract": {"verified": info.get("is_verified"), "proxy": proxy,
                     "bytecode_bytes": code.get("length"), "risky_selectors": code.get("risky_selectors"),
                     "owner": owner},
        "creator": deployer,
        "findings": findings,
        "methodology": {
            "liquidity": "DexScreener public API, deepest Base pair",
            "holders": f"explorer holder list ({BLOCKSCOUT}), top 10 measured against totalSupply",
            "bytecode": "function selectors searched in the deployed bytecode (mint/blacklist/pause/fee/maxTx)",
            "owner": "owner() read directly; renounced = owner is the zero address or the burn address",
            "upgradeability": "EIP-1967 implementation slot read from storage",
            "creator": "explorer creator address + its nonce",
            "slippage": "constant-product arithmetic from pool liquidity, stated as an estimate",
        },
        "not_checked": [
            "buy/sell tax and honeypot behaviour (needs a simulated swap on a forked node)",
            "hidden owner powers that are not visible as standard selectors",
            "off-chain intent, team identity, or social provenance",
            "whether the top holders are one person behind several wallets",
        ],
        "verdicts": {"safe": f">= {VERDICT_SAFE}", "caution": f"{VERDICT_CAUTION}-{VERDICT_SAFE - 1}",
                     "danger": f"< {VERDICT_CAUTION}"},
        "elapsed_ms": round((time.time() - started) * 1000),
    }


def register(app, ctx: Ctx) -> None:
    from pydantic import BaseModel, Field

    class SafetyReq(BaseModel):
        token: str = Field(..., description="Base token contract address")

    @app.get("/token-safety/method")
    def index():
        return {
            "provider": "XH Agents — token safety score (Base)",
            "what_it_is": ("One 0-100 number for a Base token plus the evidence behind it: liquidity, top-10 holder "
                           "concentration, owner powers in the bytecode, upgradeability, verification, creator "
                           "history and the price impact of a small trade. Built so an agent can refuse before it "
                           "buys, not after."),
            "price_usdc_per_call": 0.05,
            "endpoints": [{"route": "POST /api/token-safety", "price_usd": 0.05},
                          {"route": "GET /api/token-safety?token=0x…", "price_usd": 0.05}],
            "verdicts": {"safe": ">= 75", "caution": "50-74", "danger": "< 50"},
            "weights": {"liquidity": 25, "concentration": 25, "contract_powers": 20,
                        "upgradeability_verification": 15, "creator_history": 10, "tradability": 5},
            "sibling": {"chain": "solana", "route": "GET /v1/token-safety?mint=…",
                        "origin": "https://pronomad.duckdns.org"},
            "not_checked": ["buy/sell tax", "honeypot simulation", "off-chain team identity"],
        }

    def _run(token: str) -> dict:
        return assess(ctx, token)

    @app.post("/token-safety")
    def safety_post(req: SafetyReq):
        return _run(req.token)

    @app.get("/token-safety")
    def safety_get(token: str):
        return _run(token)
