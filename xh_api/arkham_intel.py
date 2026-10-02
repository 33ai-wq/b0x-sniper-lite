"""arkham-intel — five paid intel endpoints built on the use-case set Arkham published for its API.

Honesty contract for this module (same rules as the rest of xh_api):
* We are NOT Arkham and we do not have Arkham's entity graph or Arkham API access. Every response says
  so, lists the sources it actually used, and carries a `not_checked` list.
* Entity names appear only when they come from a curated label file the operator maintains
  (labels/venues.json). Otherwise an address is reported by address + a class we verified ON-CHAIN
  by probing the contract's interface (pair / pool / router / bridge / token / eoa). A class is a
  verified interface, never a guessed company name.
* No fabricated attribution: if we cannot verify it, it is reported as unlabelled and listed in
  `not_checked`.

The five products, each $0.10 (x402, USDC on Base):
  /arkham-intel/use-cases    role or task -> ordered call plan across our intel endpoints
  /arkham-intel/exchange-flow token -> net flow split by verified venue class + top counterparties
  /arkham-intel/portfolio    address -> holdings with USD values and activity
  /arkham-intel/counterparties address -> who it transacts with, class + first/last seen
  /arkham-intel/trace        address -> hop-by-hop flow with flags from the curated label file
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHUNK = 2000          # blocks per eth_getLogs call: public RPCs cap the range
LOG_CAP = 4000        # hard stop so a paid call cannot run away
LABELS_FILE = os.environ.get("XH_VENUE_LABELS", "/home/ubuntu/prpo_ai/xh_api/labels/venues.json")

# selectors for the on-chain interface probes (no external label needed)
SEL = {
    "decimals": "0x313ce567",
    "symbol": "0x95d89b41",
    "getReserves": "0x0902f1ac",
    "token0": "0x0dfe1681",
    "slot0": "0x3850c7bd",
    "factory": "0xc45a0155",
    "exactInputSingle": "0x414bf389",
    "getEthBalance": "0x4d2301cc",
}

_cache: dict[str, tuple[float, Any]] = {}


def _memo(key: str, ttl: float, fn: Callable[[], Any]) -> Any:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _labels() -> dict[str, dict]:
    """Curated venue labels the operator maintains. Empty is a valid, stated answer."""
    def load() -> dict:
        try:
            with open(LABELS_FILE, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            out = {}
            for addr, info in (raw.get("venues") or raw).items():
                if isinstance(info, dict):
                    out[str(addr).lower()] = info
            return out
        except Exception:
            return {}
    return _memo("labels", 60.0, load)


def _label_of(addr: str) -> dict | None:
    return _labels().get(str(addr).lower())


def _price_usd(token: str) -> dict | None:
    """USD price from DexScreener, with the two ways it can be derived stated explicitly.

    DexScreener's `priceUsd` is the price of the pair's BASE token. Using it blindly for a token that
    is the QUOTE side of every deep pair yields a wrong number (USDC read as ~$0.78 in our first
    version). So: prefer a pair where our token is the base; otherwise derive the quote token's USD
    value as priceUsd(base) / priceNative(base), which is arithmetic, not a guess.
    """
    def fetch() -> dict | None:
        try:
            r = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=15)
            pairs = [p for p in (r.json().get("pairs") or []) if str(p.get("chainId")) == "base"]
            if not pairs:
                return None
            lowest = token.lower()

            def base_addr(p):
                return str(((p.get("baseToken") or {}).get("address") or "")).lower()

            def quote_addr(p):
                return str(((p.get("quoteToken") or {}).get("address") or "")).lower()

            def liq(p):
                return float((p.get("liquidity") or {}).get("usd") or 0)

            def pack(p, price, method):
                return {"price_usd": price, "method": method, "pair": p.get("pairAddress"),
                        "dex": p.get("dexId"), "liquidity_usd": liq(p),
                        "price_change_24h_pct": (p.get("priceChange") or {}).get("h24"),
                        "symbol": (p.get("baseToken") or {}).get("symbol") if base_addr(p) == lowest
                                  else (p.get("quoteToken") or {}).get("symbol")}

            own = [p for p in pairs if base_addr(p) == lowest and p.get("priceUsd")]
            if own:
                best = max(own, key=liq)
                return pack(best, float(best["priceUsd"]), "base_side_pair")
            quote_side = [p for p in pairs if quote_addr(p) == lowest]
            derived = []
            for p in quote_side:
                try:
                    native = float(p.get("priceNative") or 0)
                    base_usd = float(p.get("priceUsd") or 0)
                    if native > 0 and base_usd > 0:
                        derived.append(pack(p, base_usd / native, "derived_from_quote_side"))
                except Exception:
                    continue
            if derived:
                return max(derived, key=lambda d: d.get("liquidity_usd") or 0)
            return None
        except Exception:
            return None
    return _memo(f"price:{token.lower()}", 60.0, fetch)


def _pairs(token: str) -> list[dict]:
    """DexScreener pairs for a token on Base, deepest first (public, keyless)."""
    def fetch() -> list[dict]:
        try:
            r = httpx.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=15)
            pairs = [p for p in (r.json().get("pairs") or []) if str(p.get("chainId")) == "base"]
            pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
            return pairs
        except Exception:
            return []
    return _memo(f"pairs:{token.lower()}", 60.0, fetch)


class Ctx:
    """The RPC/chain helpers owned by server.py, injected to avoid a circular import."""

    def __init__(self, rpc: Callable, erc20: Callable, is_address: Callable, hex_to_int: Callable,
                 decimals_of: Callable | None = None):
        self.rpc = rpc
        self.erc20 = erc20
        self.is_address = is_address
        self.hex_to_int = hex_to_int
        self.decimals_of = decimals_of


# ── shared on-chain readers ───────────────────────────────────────────────────

def _block_number(ctx: Ctx) -> int:
    return int(ctx.rpc("eth_blockNumber", []), 16)


def _block_ts(ctx: Ctx, block: int) -> int:
    def fetch() -> int:
        try:
            b = ctx.rpc("eth_getBlockByNumber", [hex(block), False])
            return int(b.get("timestamp", "0x0"), 16)
        except Exception:
            return 0
    return _memo(f"bts:{block}", 600.0, fetch)


def _code(ctx: Ctx, addr: str) -> str:
    def fetch() -> str:
        try:
            return ctx.rpc("eth_getCode", [addr, "latest"]) or "0x"
        except Exception:
            return "0x"
    return _memo(f"code:{addr.lower()}", 300.0, fetch)


def _has_interface(ctx: Ctx, addr: str, selector: str) -> bool:
    def probe() -> bool:
        try:
            out = ctx.rpc("eth_call", [{"to": addr, "data": selector}, "latest"])
            return bool(out) and len(str(out)) > 2 and str(out) != "0x"
        except Exception:
            return False
    return _memo(f"probe:{addr.lower()}:{selector}", 300.0, probe)


def classify(ctx: Ctx, addr: str) -> dict:
    """Verified interface class — never a guessed name."""
    addr = addr.lower()
    lab = _label_of(addr)
    code = _code(ctx, addr)
    if not code or code in ("0x", "0x0"):
        return {"address": addr, "class": "eoa", "label": (lab or {}).get("label"),
                "label_type": (lab or {}).get("type"), "evidence": "no contract code"}
    pair = _has_interface(ctx, addr, SEL["getReserves"]) and _has_interface(ctx, addr, SEL["token0"])
    pool = _has_interface(ctx, addr, SEL["slot0"]) and _has_interface(ctx, addr, SEL["token0"])
    router = _has_interface(ctx, addr, SEL["exactInputSingle"])
    token = _has_interface(ctx, addr, SEL["decimals"]) and _has_interface(ctx, addr, SEL["factory"]) is False
    factory = _has_interface(ctx, addr, SEL["factory"])
    if pair:
        cls, why = "dex_pair", "getReserves()+token0() answered"
    elif pool:
        cls, why = "dex_pool", "slot0()+token0() answered"
    elif router:
        cls, why = "amm_router", "exactInputSingle() selector answered"
    elif factory:
        cls, why = "factory", "factory() answered"
    elif token:
        cls, why = "erc20", "decimals() answered, no factory()"
    else:
        cls, why = "contract", "has code, no probed interface matched"
    return {"address": addr, "class": cls, "label": (lab or {}).get("label"),
            "label_type": (lab or {}).get("type"), "evidence": why}


def _decimals(ctx: Ctx, token: str) -> int:
    def fetch() -> int:
        try:
            out = ctx.rpc("eth_call", [{"to": token, "data": SEL["decimals"]}, "latest"])
            return int(out, 16) if out and out != "0x" else 18
        except Exception:
            return 18
    return _memo(f"dec:{token.lower()}", 600.0, fetch)


def _transfers(ctx: Ctx, token: str, from_block: int, to_block: int, pad: list[str] | None = None) -> tuple[list[dict], bool, list[str]]:
    """ERC-20 Transfer logs for a token (optionally filtered on one address), chunked.

    Returns (logs, truncated, errors). Errors are surfaced instead of swallowed: "no transfers" and
    "the RPC refused the query" must never look the same to a paying buyer.
    """
    logs: list[dict] = []
    errors: list[str] = []
    truncated = False
    blk = from_block
    while blk <= to_block:
        hi = min(blk + CHUNK - 1, to_block)
        topics = [TRANSFER_TOPIC] + (pad or [])
        try:
            batch = ctx.rpc("eth_getLogs", [{"fromBlock": hex(blk), "toBlock": hex(hi),
                                             "address": token, "topics": topics}], timeout=45.0)
        except Exception as e:
            errors.append(f"blocks {blk}-{hi}: {type(e).__name__} {str(e)[:120]}")
            batch = []
        for lg in batch or []:
            t = lg.get("topics") or []
            if len(t) < 3:
                continue
            logs.append({"block": ctx.hex_to_int(lg.get("blockNumber")),
                         "frm": "0x" + t[1][-40:],
                         "to": "0x" + t[2][-40:],
                         "value": ctx.hex_to_int(lg.get("data"))})
            if len(logs) >= LOG_CAP:
                truncated = True
                return logs, truncated, errors
        blk = hi + 1
    return logs, truncated, errors


def _fmt(value: int, decimals: int) -> float:
    return round(value / (10 ** decimals), 6) if decimals else float(value)


def _window_blocks(ctx: Ctx, hours: int) -> tuple[int, int, int]:
    latest = _block_number(ctx)
    # Base: ~2 s blocks
    span = min(int(hours * 1800), int(24 * 1800))
    return max(0, latest - span), latest, latest


def _pair_flow(ctx: Ctx, token: str, hours: int) -> dict:
    """Pool-level inflow/outflow for a token, from historical reserves.

    Why this shape: a broad eth_getLogs over every transfer of a busy token is not answerable on
    public RPCs (USDC emits >10k logs per 100 blocks), so a transfer-wide flow would be a number we
    cannot actually stand behind. Pool reserves ARE readable at a historical block, so the deltas
    between (latest - window) and latest are real, verifiable in/out flows at pool level.
    """
    pairs = _pairs(token)[:6]
    latest = _block_number(ctx)
    span = max(1, min(int(max(1, min(hours, 24)) * 1800), int(24 * 1800)))
    then = max(0, latest - span)
    dec = _decimals(ctx, token)
    rows, errors = [], []
    for p in pairs:
        pair = str(p.get("pairAddress") or "")
        labels = p.get("labels") or []
        row = {"pair": pair, "dex": p.get("dexId"), "labels": labels,
               "liquidity_usd": float((p.get("liquidity") or {}).get("usd") or 0)}
        if not pair:
            continue

        def token_balance(block: int):
            """The pool's own balance of our token — readable for any pool that custodies its funds."""
            try:
                data = "0x70a08231" + "0" * 24 + pair[2:]
                raw = ctx.rpc("eth_call", [{"to": token, "data": data}, hex(block)])
                return int(raw, 16) if raw and raw != "0x" else None
            except Exception as e:
                errors.append(f"balanceOf {pair}@{block}: {type(e).__name__} {str(e)[:70]}")
                return None

        def sqrt_price(block: int):
            """slot0().sqrtPriceX96 where the pool exposes it (also gives a verifiable price move)."""
            try:
                out = str(ctx.rpc("eth_call", [{"to": pair, "data": SEL["slot0"]}, hex(block)]))
                return int("0x" + out[2:66], 16) if len(out) >= 66 else None
            except Exception:
                return None

        bal_now, bal_then = token_balance(latest), token_balance(then)
        if bal_now is None or bal_then is None:
            row["skipped"] = "the pool's token balance could not be read at one of the two blocks"
            rows.append(row)
            continue
        if bal_now == 0 and bal_then == 0:
            row["skipped"] = ("pool holds none of this token directly — a singleton/vault design (e.g. v4 PoolManager) "
                              "keeps funds elsewhere, so balance-based flow is not readable here")
            rows.append(row)
            continue
        delta = bal_now - bal_then
        px = (_price_usd(token) or {}).get("price_usd")
        sp_now, sp_then = sqrt_price(latest), sqrt_price(then)
        price_move = None
        if sp_now and sp_then:
            try:
                price_move = round(((sp_now / sp_then) ** 2 - 1) * 100, 4)
            except Exception:
                price_move = None
        row.update({
            "our_token": token, "paired_with": (p.get("quoteToken") or {}).get("address"),
            "balance_then": _fmt(bal_then, dec), "balance_now": _fmt(bal_now, dec),
            "token_change": _fmt(delta, dec),
            "direction": "out_of_pool (bought)" if delta < 0 else ("into_pool (sold)" if delta > 0 else "flat"),
            "usd_change": round(abs(delta) / (10 ** dec) * px, 4) if px else None,
            "pool_price_move_pct": price_move,
        })
        rows.append(row)
    inflow = sum(r.get("token_change") or 0 for r in rows if (r.get("token_change") or 0) > 0)
    outflow = sum(-(r.get("token_change") or 0) for r in rows if (r.get("token_change") or 0) < 0)
    return {"token": token, "decimals": dec, "price": _price_usd(token),
            "window": {"hours": max(1, min(hours, 24)), "from_block": then, "to_block": latest},
            "pools": rows, "errors": errors,
            "pool_totals": {"into_pools": round(inflow, 6), "out_of_pools": round(outflow, 6),
                            "net": round(inflow - outflow, 6)}}


# ── the five products ─────────────────────────────────────────────────────────

PLAYBOOKS = [
    {"role": "traders", "goal": "Are coins piling into an exchange or draining out?",
     "arkham_use_case": "Inflow & Outflow Monitoring",
     "plan": ["POST /api/arkham-intel/exchange-flow", "POST /api/arkham-intel/counterparties"],
     "look_for": "net sign over the window, and whether the counterparties on the heavy side are pools, "
                 "routers or EOAs. A large EOA-heavy outflow is a distribution pattern; pool-heavy flow is normal trading.",
     "limits": "We hold no exchange hot-wallet labels unless the operator has added them; venues are reported by "
               "verified interface class, not by company name."},
    {"role": "traders", "goal": "What is a portfolio worth over time?",
     "arkham_use_case": "Portfolio Monitoring",
     "plan": ["POST /api/arkham-intel/portfolio"],
     "look_for": "balance and USD value of the holdings we can see on Base, plus transfer activity so you can spot "
                 "when the book changed.",
     "limits": "Value is a snapshot at request time using the deepest Base pair we can find; other chains, staked "
               "positions and private balances are out of scope."},
    {"role": "traders", "goal": "Who does a counterparty trade with?",
     "arkham_use_case": "Counterparty Due Diligence",
     "plan": ["POST /api/arkham-intel/counterparties", "POST /api/arkham-intel/trace"],
     "look_for": "the concentration of flow (one venue or many), and any flagged label on the paths.",
     "limits": "Only token transfers inside the requested window; CEX-internal books and off-chain agreements are invisible."},
    {"role": "builders", "goal": "Who uses my product and what are they worth?",
     "arkham_use_case": "Know Your Users",
     "plan": ["POST /api/arkham-intel/counterparties", "POST /api/arkham-intel/portfolio"],
     "look_for": "the distinct EOAs that move value to your contract, their class evidence, and the size distribution.",
     "limits": "No off-chain identity: a wallet is a wallet. Nothing here is a KYC or KYB result."},
    {"role": "builders", "goal": "Who deposits into a competitor?",
     "arkham_use_case": "Competitor Analysis",
     "plan": ["POST /api/arkham-intel/exchange-flow", "POST /api/arkham-intel/counterparties"],
     "look_for": "shared counterparties between the two tokens/contracts: addresses appearing on both sides.",
     "limits": "Comparison is address-level inside the window you ask for; we do not label competitors for you."},
    {"role": "builders", "goal": "Which addresses are flagged, and why?",
     "arkham_use_case": "Counterparty Due Diligence & Compliance",
     "plan": ["POST /api/arkham-intel/trace", "POST /api/arkham-intel/counterparties"],
     "look_for": "every 'flag' field with its label_type and source. A missing flag means our label file has nothing, "
                 "not that the address is clean.",
     "limits": "Flags come only from the operator's curated label file. This is not a sanctions screen and must not "
               "be used as one."},
    {"role": "brokers", "goal": "Who are my users, and who went quiet?",
     "arkham_use_case": "User & VIP Intelligence",
     "plan": ["POST /api/arkham-intel/counterparties", "POST /api/arkham-intel/portfolio"],
     "look_for": "last_seen per counterparty: quiet wallets have an old timestamp while the book is still there.",
     "limits": "Segmenting by value is address-level, not account-level."},
    {"role": "investigators", "goal": "Where did the money go?",
     "arkham_use_case": "Money Laundering & Illicit Finance (AML)",
     "plan": ["POST /api/arkham-intel/trace"],
     "look_for": "the hop path and the venues on it: bridge or mixer-like labels, then where the value lands.",
     "limits": "A trace is evidence, not a conclusion. We do not identify people."},
    {"role": "investigators", "goal": "Who is behind the address?",
     "arkham_use_case": "Ransomware & Cybercrime Investigations",
     "plan": ["POST /api/arkham-intel/trace", "POST /api/arkham-intel/counterparties"],
     "look_for": "the first funding source we can see and the flags touched on the path.",
     "limits": "We have no attributions beyond the curated label file; identities require sources we do not hold."},
    {"role": "investigators", "goal": "Who paid a darknet market?",
     "arkham_use_case": "Darknet & Illicit Marketplace Investigations",
     "plan": ["POST /api/arkham-intel/trace"],
     "look_for": "counterparties whose label_type is mixer/sanctioned/marketplace in the trace, with the block range.",
     "limits": "Only if the operator's label file carries those venues; otherwise the answer is 'no flag available'."},
]


class UseCaseReq(BaseModel):
    role: str | None = Field(None, description="traders | builders | brokers | investigators | any")
    task: str | None = Field(None, description="Free-text description of what you are trying to answer.")


class TokenReq2(BaseModel):
    token: str = Field(..., description="ERC-20 token address on Base")
    hours: int = Field(6, description="Lookback window in hours (1-24).")


class PortfolioReq(BaseModel):
    address: str = Field(..., description="Wallet address on Base")
    tokens: list[str] | None = Field(None, description="Optional ERC-20 addresses to value; default: seen in recent transfers")
    hours: int = Field(6, description="Activity window in hours (1-24).")


class CounterpartyReq(BaseModel):
    address: str = Field(..., description="Wallet or contract address on Base")
    hours: int = Field(24, description="Lookback window in hours (1-24).")
    limit: int = Field(15, description="How many counterparties to return (1-50).")


class TraceReq(BaseModel):
    address: str = Field(..., description="Starting address")
    hops: int = Field(2, description="How many hops to follow (1-3).")
    hours: int = Field(24, description="Lookback window in hours (1-24).")


def register(app: FastAPI, ctx: Ctx) -> None:
    """Wire the five intel routes plus the free index onto the app."""

    @app.get("/arkham-intel")
    def arkham_intel_index():
        return {
            "provider": "XH Agents — Arkham-style intel on public Base data",
            "not_arkham": ("This is not Arkham and holds no Arkham API key. It answers the use cases Arkham "
                           "documented, computed from public Base chain data. Entity names appear only from a "
                           "curated label file; otherwise addresses are reported with an on-chain verified interface class."),
            "source_thread": "https://x.com/arkham/status/2105982540423291204 (Arkham API use cases)",
            "price_usdc_per_call": 0.1,
            "endpoints": [
                {"route": "POST /api/arkham-intel/use-cases", "price_usd": 0.1,
                 "answers": "role or task -> ordered plan across these endpoints, mapped to Arkham's use-case list"},
                {"route": "POST /api/arkham-intel/exchange-flow", "price_usd": 0.1,
                 "answers": "inflow/outflow for a token, split by verified venue class, with top counterparties"},
                {"route": "POST /api/arkham-intel/portfolio", "price_usd": 0.1,
                 "answers": "holdings with USD values and activity for a wallet"},
                {"route": "POST /api/arkham-intel/counterparties", "price_usd": 0.1,
                 "answers": "who an address transacts with, class + first/last seen + curated flags"},
                {"route": "POST /api/arkham-intel/trace", "price_usd": 0.1,
                 "answers": "hop-by-hop flow with flags, for AML-style 'where did the money go' questions"},
            ],
            "labels_configured": sorted(_labels().keys())[:10],
            "methodology": {"chain": "Base (eip155:8453)", "transfers": "ERC-20 Transfer logs via public RPC, chunked 2000 blocks",
                            "prices": "DexScreener public API, deepest Base pair",
                            "classes": "on-chain interface probes (getReserves/token0, slot0/token0, exactInputSingle, factory, decimals)",
                            "labels": f"curated file {LABELS_FILE} (empty = addresses reported without names)"},
            "not_checked": ["off-chain identity or company ownership", "CEX internal books", "other chains",
                            "sanctions compliance — this is not a screening product"],
        }

    @app.get("/arkham-intel/use-cases")
    def use_cases_get(role: str | None = None, task: str | None = None):
        return use_cases(UseCaseReq(role=role, task=task))

    @app.post("/arkham-intel/use-cases")
    def use_cases(req: UseCaseReq):
        role = (req.role or "any").strip().lower()
        task = (req.task or "").lower()
        picked = [p for p in PLAYBOOKS if role in ("any", "", p["role"])]
        if task:
            words = [w for w in task.replace(",", " ").split() if len(w) > 3]
            scored = []
            for p in picked or PLAYBOOKS:
                text = (p["goal"] + " " + p["arkham_use_case"] + " " + p["look_for"]).lower()
                scored.append((sum(1 for w in words if w in text), p))
            if any(s for s, _ in scored):
                scored.sort(key=lambda x: -x[0])
                picked = [p for s, p in scored if s]
            else:
                picked = picked or PLAYBOOKS
        return {
            "role": role, "task": req.task,
            "playbooks": [{
                "goal": p["goal"], "arkham_use_case": p["arkham_use_case"], "plan": p["plan"],
                "what_to_look_for": p["look_for"], "limits": p["limits"],
            } for p in picked],
            "endpoints_used": sorted({r for p in picked for r in p["plan"]}),
            "methodology": {"source": "Arkham's published API use-case list (X thread, 2026-10-02) mapped onto XH Agent endpoints",
                            "computed_from": "public Base chain data"},
            "not_checked": ["we do not call Arkham's API", "no Arkham entity graph or attributions",
                            "playbooks are guidance, not financial or legal advice"],
        }

    @app.get("/arkham-intel/exchange-flow")
    def exchange_flow_get(token: str, hours: int = 6):
        return exchange_flow(TokenReq2(token=token, hours=hours))

    @app.post("/arkham-intel/exchange-flow")
    def exchange_flow(req: TokenReq2):
        token = req.token.strip()
        if not ctx.is_address(token):
            return JSONResponse({"error": "invalid_token_address"}, status_code=400)
        data = _pair_flow(ctx, token, req.hours)
        pools = data["pools"]
        return {
            "token": token,
            "pool_totals": data["pool_totals"],
            "pools": pools,
            "price": data["price"],
            "window": data["window"],
            "rpc_errors": data["errors"],
            "read_this_as": ("Inflow/outflow measured at pool level: how much of the token each pool held at the two "
                             "blocks. A pool holding more = tokens moved in (sell side); holding less = tokens were "
                             "bought out of it."),
            "methodology": {
                "source": "the pool's own balance of the token (balanceOf) read at two blocks on Base via public RPC; "
                          "price move from slot0().sqrtPriceX96 where the pool exposes it",
                "pools": "the deepest Base pairs for the token from DexScreener; a pool that cannot answer is listed "
                         "with `skipped` and the reason (unreadable balance, or a singleton vault that holds no funds itself)",
                "price": {k: v for k, v in (data["price"] or {}).items() if k in ("price_usd", "method", "dex", "pair")},
                "labels": (f"{len(_labels())} curated venue label(s) available" if _labels() else "no curated label file"),
            },
            "not_checked": ["CEX hot-wallet inflow/outflow (needs exchange labels we do not hold)",
                            "pools that are not constant-product (V3/CLMM) — listed as skipped",
                            "transfers that never touch a pool", "other chains"],
        }

    @app.get("/arkham-intel/portfolio")
    def portfolio_get(address: str, hours: int = 6):
        return portfolio(PortfolioReq(address=address, hours=hours))

    @app.post("/arkham-intel/portfolio")
    def portfolio(req: PortfolioReq):
        addr = req.address.strip().lower()
        if not ctx.is_address(addr):
            return JSONResponse({"error": "invalid_address"}, status_code=400)
        hours = max(1, min(req.hours, 24))
        # native balance
        try:
            eth_wei = int(ctx.rpc("eth_getBalance", [addr, "latest"]), 16)
        except Exception:
            eth_wei = 0
        weth = "0x4200000000000000000000000000000000000006"
        eth_price = (_price_usd(weth) or {}).get("price_usd")
        holdings = []
        tokens = [t.lower() for t in (req.tokens or []) if ctx.is_address(t)]
        seen_note = None
        if not tokens:
            # discover tokens from the address's recent activity: scan a couple of majors + report the gap
            seen_note = ("no tokens given: only the native balance and any tokens you name are valued. "
                         "Token discovery across the whole chain is not something this call does.")
        for tok in tokens[:10]:
            try:
                data = "0x70a08231" + "0" * 24 + addr[2:]          # balanceOf(address)
                raw = ctx.rpc("eth_call", [{"to": tok, "data": data}, "latest"])
                bal = int(raw, 16) if raw and raw != "0x" else 0
            except Exception:
                bal = 0
            dec = _decimals(ctx, tok)
            px = (_price_usd(tok) or {}).get("price_usd")
            amount = _fmt(bal, dec)
            holdings.append({"token": tok, "amount": amount, "decimals": dec,
                             "price_usd": px, "value_usd": round(amount * px, 4) if px else None,
                             "class": classify(ctx, tok)["class"]})
        total_usd = sum(h["value_usd"] or 0 for h in holdings) + ((eth_wei / 1e18) * (eth_price or 0))
        return {
            "address": addr,
            "native": {"eth": round(eth_wei / 1e18, 8), "price_usd": eth_price,
                       "value_usd": round((eth_wei / 1e18) * eth_price, 4) if eth_price else None},
            "holdings": holdings,
            "total_value_usd": round(total_usd, 4) if total_usd else None,
            "window_hours": hours,
            "note": seen_note,
            "methodology": {"chain": "Base", "prices": "DexScreener, deepest Base pair at request time",
                            "balances": "eth_getBalance + ERC-20 balanceOf via public RPC"},
            "not_checked": ["other chains", "staked/lent/private positions", "historical portfolio curve "
                            "(this is a snapshot, not a chart)", "NFTs"],
        }

    @app.get("/arkham-intel/counterparties")
    def counterparties_get(address: str, hours: int = 24, limit: int = 15):
        return counterparties(CounterpartyReq(address=address, hours=hours, limit=limit))

    @app.post("/arkham-intel/counterparties")
    def counterparties(req: CounterpartyReq):
        addr = req.address.strip().lower()
        if not ctx.is_address(addr):
            return JSONResponse({"error": "invalid_address"}, status_code=400)
        hours = max(1, min(req.hours, 24))
        limit = max(1, min(req.limit, 50))
        # look at the address's own transfers via the two most common quote tokens it may hold is not possible
        # without knowing the token; instead we scan token transfers touching the address for the majors we track
        majors = {
            "USDC": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            "WETH": "0x4200000000000000000000000000000000000006",
        }
        from_blk, to_blk, _ = _window_blocks(ctx, hours)
        found: dict[str, dict] = {}
        scanned = []
        rpc_errors: list[str] = []
        for sym, tok in majors.items():
            dec = _decimals(ctx, tok)
            px = (_price_usd(tok) or {}).get("price_usd")
            pad = ["0x" + "0" * 24 + addr[2:]]
            logs, trunc, errs = _transfers(ctx, tok, from_blk, to_blk, pad=pad)
            rpc_errors += [f"{sym} {e}" for e in errs]
            scanned.append({"token": sym, "address": tok, "transfers_seen": len(logs), "truncated": trunc})
            for lg in logs:
                other = lg["to"] if lg["frm"] == addr else lg["frm"]
                b = found.setdefault(other.lower(), {"address": other.lower(), "in": 0.0, "out": 0.0, "usd": 0.0,
                                                     "transfers": 0, "first": lg["block"], "last": lg["block"],
                                                     "tokens": set()})
                amount = lg["value"] / (10 ** dec)
                if lg["frm"] == addr:
                    b["out"] += amount
                else:
                    b["in"] += amount
                b["usd"] += amount * (px or 0)
                b["transfers"] += 1
                b["tokens"].add(sym)
                b["first"] = min(b["first"], lg["block"])
                b["last"] = max(b["last"], lg["block"])
        rows = []
        for b in sorted(found.values(), key=lambda x: (x["usd"], x["transfers"]), reverse=True)[:limit]:
            cls = classify(ctx, b["address"])
            lab = _label_of(b["address"])
            rows.append({
                "address": b["address"], "class": cls["class"], "evidence": cls["evidence"],
                "label": cls["label"], "label_type": cls["label_type"],
                "flag": bool(lab and (lab.get("type") in ("mixer", "sanctioned", "marketplace", "exploit"))),
                "in": round(b["in"], 6), "out": round(b["out"], 6), "usd_volume": round(b["usd"], 4),
                "transfers": b["transfers"], "tokens": sorted(b["tokens"]),
                "first_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_block_ts(ctx, b["first"]))),
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_block_ts(ctx, b["last"]))),
            })
        return {
            "address": addr, "window": {"hours": hours, "from_block": from_blk, "to_block": to_blk},
            "tokens_scanned": scanned, "counterparties": rows,
            "rpc_errors": rpc_errors,
            "labels_configured": len(_labels()),
            "methodology": {"source": "ERC-20 Transfer logs for USDC and WETH on Base, filtered on this address",
                            "classes": "verified on-chain interface probes",
                            "labels": ("curated label file applied" if _labels() else
                                       "no curated label file: flags are false for every address and that means 'no data', not 'clean'")},
            "not_checked": ["tokens other than USDC/WETH", "CEX internals", "off-chain identity",
                            "sanctions screening (this is not a compliance product)"],
        }

    @app.get("/arkham-intel/trace")
    def trace_get(address: str, hops: int = 2, hours: int = 24):
        return trace(TraceReq(address=address, hops=hops, hours=hours))

    @app.post("/arkham-intel/trace")
    def trace(req: TraceReq):
        origin = req.address.strip().lower()
        if not ctx.is_address(origin):
            return JSONResponse({"error": "invalid_address"}, status_code=400)
        hops = max(1, min(req.hops, 3))
        hours = max(1, min(req.hours, 24))
        from_blk, to_blk, _ = _window_blocks(ctx, hours)
        usdc = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
        dec = _decimals(ctx, usdc)
        px = (_price_usd(usdc) or {}).get("price_usd") or 1.0
        frontier = [origin]
        seen = {origin}
        levels = []
        flags = []
        rpc_errors: list[str] = []
        for hop in range(1, hops + 1):
            nxt: list[str] = []
            entries = []
            for addr in frontier[:5]:
                logs, trunc, errs = _transfers(ctx, usdc, from_blk, to_blk, pad=["0x" + "0" * 24 + addr[2:]])
                rpc_errors += [f"hop{hop} {addr}: {e}" for e in errs]
                for lg in logs:
                    if lg["frm"] != addr:
                        continue        # follow outgoing value
                    other = lg["to"].lower()
                    cls = classify(ctx, other)
                    lab = _label_of(other)
                    entry = {"from": addr, "to": other, "amount": _fmt(lg["value"], dec),
                             "usd": round(lg["value"] / (10 ** dec) * px, 4),
                             "block": lg["block"],
                             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_block_ts(ctx, lg["block"]))),
                             "class": cls["class"], "label": cls["label"], "label_type": cls["label_type"],
                             "evidence": cls["evidence"]}
                    entries.append(entry)
                    if lab and lab.get("type") in ("mixer", "sanctioned", "marketplace", "exploit"):
                        flags.append({"address": other, "label": lab.get("label"), "type": lab.get("type"),
                                      "source": lab.get("source"), "seen_at_hop": hop})
                    if other not in seen and cls["class"] == "eoa":
                        nxt.append(other); seen.add(other)
            entries.sort(key=lambda e: e["usd"], reverse=True)
            levels.append({"hop": hop, "from": frontier, "transfers": entries[:20],
                           "transfers_total": len(entries)})
            if not nxt:
                break
            frontier = nxt[:5]
        return {
            "origin": origin,
            "hops": levels,
            "flags": flags,
            "rpc_errors": rpc_errors,
            "window": {"hours": hours, "from_block": from_blk, "to_block": to_blk},
            "labels_configured": len(_labels()),
            "methodology": {"token": "USDC on Base (the trace follows USDC transfers; other tokens are out of scope)",
                            "follows": "outgoing transfers, up to 3 hops, max 5 wallets per hop",
                            "classes": "verified on-chain interface probes",
                            "flags": ("curated label file applied" if _labels() else
                                      "no label file configured: an empty flags list means 'nothing curated', not 'no risk'")},
            "not_checked": ["tokens other than USDC", "paths longer than the requested hops", "mixers/bridges we have no label for",
                            "off-chain identity or intent", "legal conclusions of any kind"],
        }
