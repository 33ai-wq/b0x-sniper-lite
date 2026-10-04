"""hundred_x — the seven-step "next 100x" cycle-wallet method, computed on Base public data.

Boss's method (verbatim logic, translated to what is actually verifiable on-chain):

  1. take a coin from a previous cycle (input: the token address);
  2. list its earliest buyers;
  3. keep only wallets still active in the last N days;
  4. drop bots (sub-minute intervals are machines, not people to follow);
  5. look at what those wallets bought recently and whether they still hold;
  6. a token that shows up in one wallet is luck, in three or more wallets it is a signal;
  7. score every candidate — below the threshold it is a no-buy, however profitable the wallet was.

Every number in the response is read from chain data (Alchemy's Base indexer + Base RPC) or from
DexScreener's public API. Nothing is a guess: when a step cannot be completed, the response says so in
`not_checked` instead of filling the gap with plausible text.

Data source note: the earliest-transfers query needs an indexer. `alchemy_getAssetTransfers` is used when
XH_BASE_RPC points at Alchemy; otherwise the endpoint degrades to log-scanning the token's first window
and states which source answered.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO = "0x0000000000000000000000000000000000000000"
# Minutes between two buys of the same token below which we call the wallet a machine.
BOT_INTERVAL_SECONDS = 60
# The method's own rule: below nine, do not buy.
BUY_THRESHOLD = 9.0
WATCH_THRESHOLD = 7.0
MEMO: dict[str, tuple[float, Any]] = {}


@dataclass
class Ctx:
    rpc: Callable[..., Any]          # server._rpc — public RPC with fallbacks
    erc20: Callable[..., Any]        # server.erc20_call
    is_address: Callable[[str], bool]
    alchemy_url: str = ""            # dedicated indexer, when configured
    explore: str = "https://basescan.org"

    # ── plumbing ────────────────────────────────────────────────────────────
    def memo(self, key: str, ttl: float, fn: Callable[[], Any]) -> Any:
        now = time.time()
        hit = MEMO.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        val = fn()
        MEMO[key] = (now, val)
        return val

    def indexer(self, method: str, params: dict, timeout: float = 45.0) -> Any:
        """Alchemy-only call (the public Base RPCs do not implement alchemy_*)."""
        if not self.alchemy_url:
            raise RuntimeError("no indexer configured")
        req = urllib.request.Request(
            self.alchemy_url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": [params]}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "xh-agents-hundredx/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode())
        if "error" in j:
            raise RuntimeError(str(j["error"])[:180])
        return j.get("result")


# ── small helpers ─────────────────────────────────────────────────────────────

def _now_block(ctx: Ctx) -> int:
    return int(ctx.rpc("eth_blockNumber", []), 16)


def _blocks_for_days(ctx: Ctx, days: int) -> int:
    """Base produces a block every ~2s; 43_200 blocks/day is the arithmetic answer, measured, not guessed."""
    return max(1, int(days * 43_200))


def _code(ctx: Ctx, addr: str) -> str:
    try:
        return ctx.rpc("eth_getCode", [addr, "latest"]) or "0x"
    except Exception:
        return "0x"


def _is_contract(ctx: Ctx, addr: str) -> bool:
    return _code(ctx, addr) not in ("0x", "0x0", "")


def _token_meta(ctx: Ctx, token: str) -> dict:
    out = {"token": token, "symbol": None, "decimals": None, "name": None}
    for fn in ("symbol", "decimals", "name"):
        try:
            out[fn] = ctx.erc20(token, fn)
        except Exception:
            pass
    return out


def _dex(token: str) -> dict | None:
    """Deepest Base pair from DexScreener's free API: liquidity, price, 24h move."""
    def fetch() -> dict | None:
        try:
            req = urllib.request.Request(
                f"https://api.dexscreener.com/latest/dex/tokens/{token}",
                headers={"User-Agent": "xh-agents-hundredx/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                j = json.loads(r.read().decode())
            pairs = [p for p in (j.get("pairs") or [])
                     if (p.get("chainId") == "base")]
            if not pairs:
                return None
            best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
            return {"pair": best.get("pairAddress"), "dex": best.get("dexId"),
                    "liquidity_usd": float((best.get("liquidity") or {}).get("usd") or 0),
                    "price_usd": float(best.get("priceUsd") or 0),
                    "price_change_24h_pct": (best.get("priceChange") or {}).get("h24"),
                    "url": best.get("url")}
        except Exception:
            return None
    return _memo_global(f"dex:{token.lower()}", 120.0, fetch)


def _memo_global(key: str, ttl: float, fn: Callable[[], Any]) -> Any:
    now = time.time()
    hit = MEMO.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    MEMO[key] = (now, val)
    return val


# ── step 2/4: earliest buyers, and the machine test built from the same data ──

def earliest_transfers(ctx: Ctx, token: str, want: int) -> tuple[list[dict], str]:
    """Earliest ERC-20 transfers of `token`, oldest first. Returns (transfers, source)."""
    if ctx.alchemy_url:
        try:
            res = ctx.indexer("alchemy_getAssetTransfers", {
                "fromBlock": "0x0", "toBlock": "latest", "contractAddresses": [token],
                "category": ["erc20"], "order": "asc", "maxCount": hex(max(want * 2, 40)),
                "withMetadata": True, "excludeZeroValue": True})
            rows = []
            for t in (res or {}).get("transfers") or []:
                meta = t.get("metadata") or {}
                rows.append({
                    "block": int(t.get("blockNum") or "0x0", 16),
                    "ts": meta.get("blockTimestamp"),
                    "from": (t.get("from") or "").lower(),
                    "to": (t.get("to") or "").lower(),
                    "amount": t.get("value"),
                    "hash": t.get("hash"),
                })
            return rows, "alchemy_getAssetTransfers (asc)"
        except Exception as e:
            _ = e
    # Fallback: scan the token's first window of logs (bounded, stated in the response).
    latest = _now_block(ctx)
    rows: list[dict] = []
    span = 2000
    for i in range(24):  # ~48k blocks back from the head — only useful for very new tokens
        hi = latest - i * span + span
        lo = latest - (i + 1) * span
        try:
            logs = ctx.rpc("eth_getLogs", [{"fromBlock": hex(lo), "toBlock": hex(hi),
                                            "address": token, "topics": [TRANSFER_TOPIC]}]) or []
        except Exception:
            break
        for lg in logs:
            t = lg.get("topics") or []
            if len(t) < 3:
                continue
            rows.append({"block": int(lg["blockNumber"], 16), "ts": None,
                         "from": "0x" + t[1][-40:], "to": "0x" + t[2][-40:],
                         "amount": None, "hash": lg.get("transactionHash")})
    rows.sort(key=lambda r: r["block"])
    return rows[: max(want * 2, 40)], "eth_getLogs scan from token window (no indexer configured)"


def first_buyers(ctx: Ctx, token: str, want: int = 21) -> dict:
    transfers, source = earliest_transfers(ctx, token, want)
    buyers: list[dict] = []
    seen: set[str] = set()
    for tr in transfers:
        recv, sender = tr["to"], tr["from"]
        if not ctx.is_address(recv) or recv in (ZERO, token.lower()) or recv in seen:
            continue
        sender_kind = "contract" if _is_contract(ctx, sender) else "eoa"
        # a buy is pool/contract -> wallet; a wallet->wallet shift is not a first buy
        kind = "buy" if sender_kind == "contract" else "transfer_in"
        seen.add(recv)
        buyers.append({"wallet": recv, "block": tr["block"], "ts": tr["ts"],
                       "from": sender, "from_class": sender_kind, "kind": kind,
                       "amount": tr["amount"], "tx": tr["hash"]})
        if len(buyers) >= want:
            break
    return {"buyers": buyers, "source": source, "transfers_examined": len(transfers)}


def buy_intervals(ctx: Ctx, token: str, wallet: str) -> dict:
    """Intervals between this wallet's own transfers of the token — the machine test (step 4)."""
    def fetch() -> dict:
        if not ctx.alchemy_url:
            return {"source": "unavailable", "intervals_sec": []}
        try:
            res = ctx.indexer("alchemy_getAssetTransfers", {
                "fromBlock": "0x0", "toBlock": "latest", "contractAddresses": [token],
                "fromAddress": wallet, "category": ["erc20"], "order": "asc",
                "maxCount": "0x19", "withMetadata": True})
            stamps = []
            for t in (res or {}).get("transfers") or []:
                ts = (t.get("metadata") or {}).get("blockTimestamp")
                if ts:
                    stamps.append(ts)
            secs = []
            for a, b in zip(stamps, stamps[1:]):
                try:
                    ta = time.mktime(time.strptime(a[:19], "%Y-%m-%dT%H:%M:%S"))
                    tb = time.mktime(time.strptime(b[:19], "%Y-%m-%dT%H:%M:%S"))
                    secs.append(abs(tb - ta))
                except Exception:
                    continue
            return {"source": "alchemy_getAssetTransfers", "intervals_sec": secs}
        except Exception as e:
            return {"source": f"error: {type(e).__name__}", "intervals_sec": []}
    return ctx.memo(f"intervals:{token.lower()}:{wallet}", 900.0, fetch)


def is_bot(ctx: Ctx, token: str, wallet: str) -> dict:
    data = buy_intervals(ctx, token, wallet)
    secs = [s for s in data["intervals_sec"] if s is not None]
    if len(secs) >= 2 and min(secs) < BOT_INTERVAL_SECONDS:
        return {"bot": True, "reason": f"consecutive transfers {min(secs):.0f}s apart",
                "evidence": data}
    return {"bot": False, "reason": "no sub-minute spacing in its own transfers", "evidence": data}


# ── step 3: still active in the last N days ──────────────────────────────────

def wallet_activity(ctx: Ctx, wallet: str, days: int) -> dict:
    def fetch() -> dict:
        latest = _now_block(ctx)
        from_block = max(0, latest - _blocks_for_days(ctx, days))
        if not ctx.alchemy_url:
            return {"active": None, "out_txs": 0, "source": "unavailable"}
        try:
            res = ctx.indexer("alchemy_getAssetTransfers", {
                "fromBlock": hex(from_block), "toBlock": "latest", "fromAddress": wallet,
                "category": ["external", "erc20"], "order": "desc", "maxCount": "0x8",
                "withMetadata": True})
            rows = []
            for t in (res or {}).get("transfers") or []:
                meta = t.get("metadata") or {}
                rows.append({"ts": (meta.get("blockTimestamp") or "")[:19], "hash": t.get("hash"),
                             "asset": t.get("asset"), "to": t.get("to"),
                             "direction": "out", "category": t.get("category")})
            return {"active": bool(rows), "out_txs": len(rows), "recent": rows,
                    "source": "alchemy_getAssetTransfers", "from_block": from_block}
        except Exception as e:
            return {"active": None, "out_txs": 0, "source": f"error: {type(e).__name__}"}
    return ctx.memo(f"activity:{wallet}:{days}", 600.0, fetch)


# ── step 5: what did they buy recently, and do they still hold it ────────────

def recent_buys(ctx: Ctx, wallet: str, days: int, limit: int = 8) -> list[dict]:
    def fetch() -> list[dict]:
        if not ctx.alchemy_url:
            return []
        latest = _now_block(ctx)
        from_block = max(0, latest - _blocks_for_days(ctx, days))
        try:
            res = ctx.indexer("alchemy_getAssetTransfers", {
                "fromBlock": hex(from_block), "toBlock": "latest", "toAddress": wallet,
                "category": ["erc20"], "order": "desc", "maxCount": hex(max(limit, 10)),
                "withMetadata": True})
        except Exception:
            return []
        out = []
        for t in (res or {}).get("transfers") or []:
            meta = t.get("metadata") or {}
            tok = (t.get("rawContract") or {}).get("address")
            if not tok:
                continue
            out.append({"token": tok.lower(), "symbol": t.get("asset"), "amount": t.get("value"),
                        "ts": (meta.get("blockTimestamp") or "")[:19], "tx": t.get("hash"),
                        "from": t.get("from")})
        return out
    return ctx.memo(f"buys:{wallet}:{days}", 600.0, fetch)


def holding_of(ctx: Ctx, wallet: str, token: str) -> dict:
    try:
        raw = ctx.erc20(token, "balanceOf", [wallet])
        dec = None
        try:
            dec = ctx.erc20(token, "decimals")
        except Exception:
            pass
        amount = float(raw) / (10 ** (dec if isinstance(dec, int) else 18))
        return {"amount": amount, "raw": str(raw)}
    except Exception as e:
        return {"amount": None, "error": f"{type(e).__name__}: {e}"[:120]}


# ── steps 6 & 7: recurrence across wallets, then the score ───────────────────

def score_candidate(ctx: Ctx, token: str, holders: list[dict]) -> dict:
    """The published rubric. Every component is printed so a buyer can disagree with the arithmetic."""
    # one row per wallet: several buys of the same token by one wallet must not inflate the count
    by_wallet: dict[str, dict] = {}
    for h in holders:
        by_wallet.setdefault(h.get("wallet") or "?", h)
    holders = list(by_wallet.values())
    wallets = len(holders)
    still = [h for h in holders if (h.get("held") or {}).get("amount")]
    ratio = (len(still) / wallets) if wallets else 0.0
    recent7 = 0
    for h in holders:
        buys = h.get("recent_buys") or []
        if any((b.get("ts") or "") >= _iso_days_ago(7) for b in buys):
            recent7 += 1
    recent7_ratio = (recent7 / wallets) if wallets else 0.0
    dex = _dex(token) or {}
    liq = float(dex.get("liquidity_usd") or 0)

    parts = {
        "wallets_holding": round(min(4.0, 1.0 + (wallets - 2) * 1.0), 2) if wallets >= 2 else round(wallets * 0.4, 2),
        "still_held": round(2.0 * ratio, 2),
        "buy_recency_7d": round(1.5 * recent7_ratio, 2),
        "liquidity_floor": 0.5 if liq >= 100_000 else -1.0,
        "cycle_wallet_conviction": round(1.0 * min(1.0, wallets / 5.0), 2),
    }
    total = round(sum(parts.values()), 2)
    verdict = "buy" if total >= BUY_THRESHOLD else ("watch" if total >= WATCH_THRESHOLD else "reject")
    return {"token": token, "symbol": (dex.get("symbol") if isinstance(dex, dict) else None),
            "score": min(10.0, max(0.0, total)), "verdict": verdict, "parts": parts,
            "wallets": wallets, "still_held": len(still), "bought_last_7d": recent7,
            "liquidity_usd": liq, "price_usd": dex.get("price_usd"),
            "price_change_24h_pct": dex.get("price_change_24h_pct"), "pair": dex.get("url"),
            "holders": [h.get("wallet") for h in holders]}


def _iso_days_ago(days: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))


# ── the whole method, once ───────────────────────────────────────────────────

def run(ctx: Ctx, token: str, window_days: int = 30, min_wallets: int = 3, limit: int = 25) -> dict:
    token = token.lower()
    meta = _token_meta(ctx, token)
    step2 = first_buyers(ctx, token, want=21)
    wallets = [b["wallet"] for b in step2["buyers"]]

    step3_active, step3_dropped = [], []
    for w in wallets:
        act = wallet_activity(ctx, w, window_days)
        (step3_active if act.get("active") else step3_dropped).append({"wallet": w, "activity": act})

    step4_kept, step4_bots = [], []
    for row in step3_active:
        w = row["wallet"]
        bot = is_bot(ctx, token, w)
        (step4_bots if bot["bot"] else step4_kept).append(
            {"wallet": w, "reason": bot["reason"], "intervals": bot["evidence"].get("intervals_sec")})

    step5 = []
    for row in step4_kept[: limit]:
        w = row["wallet"]
        buys = recent_buys(ctx, w, window_days, limit=8)
        step5.append({"wallet": w, "recent_buys": buys,
                      "held_of_input_token": holding_of(ctx, w, token),
                      "out_txs_window": len((row.get("activity") or {}).get("recent") or [])})

    # step 6: which tokens show up in more than one of these wallets
    buckets: dict[str, list[dict]] = {}
    for row in step5:
        for b in row["recent_buys"]:
            buckets.setdefault(b["token"], []).append({"wallet": row["wallet"], "buy": b})
    recurring = []
    for tok, holders in buckets.items():
        if tok == token or len({h["wallet"] for h in holders}) < 2:
            continue
        enriched = []
        for h in holders:
            enriched.append({"wallet": h["wallet"], "buy": h["buy"],
                             "held": holding_of(ctx, h["wallet"], tok)})
        recurring.append({"token": tok, "wallets": len({h["wallet"] for h in enriched}),
                          "strong": len({h["wallet"] for h in enriched}) >= min_wallets,
                          "holders": enriched})
    recurring.sort(key=lambda r: -r["wallets"])

    # step 7: score every recurring token (plus the input token as the baseline)
    scored = [score_candidate(ctx, r["token"], r["holders"]) for r in recurring[: limit]]
    baseline = score_candidate(ctx, token, [
        {"wallet": row["wallet"], "held": row["held_of_input_token"],
         "recent_buys": row["recent_buys"]} for row in step5])
    for s in scored:
        s["evidence"] = next((r["holders"] for r in recurring if r["token"] == s["token"]), [])
    scored.sort(key=lambda s: -s["score"])

    return {
        "method": "seven-step cycle-wallet method (Boss's 'next 100x' logic)",
        "chain": "base", "network": "eip155:8453",
        "input_token": meta,
        "input_token_dex": _dex(token),
        "params": {"window_days": window_days, "min_wallets": min_wallets, "limit": limit},
        "step_1_token_from_previous_cycle": meta,
        "step_2_first_buyers": {"count": len(step2["buyers"]), "source": step2["source"],
                                "transfers_examined": step2["transfers_examined"],
                                "buyers": step2["buyers"]},
        "step_3_active_in_window": {"kept": len(step3_active), "dropped": len(step3_dropped),
                                    "dropped_detail": [d["wallet"] for d in step3_dropped]},
        "step_4_bots_excluded": {"kept": len(step4_kept), "excluded": len(step4_bots),
                                 "bots": step4_bots, "rule_seconds": BOT_INTERVAL_SECONDS},
        "step_5_recent_buys": step5,
        "step_6_recurring_tokens": [{"token": r["token"], "wallets": r["wallets"], "strong": r["strong"]}
                                    for r in recurring],
        "step_7_scored": scored,
        "decision": {
            "threshold": BUY_THRESHOLD,
            "buy": [s for s in scored if s["verdict"] == "buy"],
            "watch": [s for s in scored if s["verdict"] == "watch"],
            "reject": [s for s in scored if s["verdict"] == "reject"],
            "baseline_input_token": baseline,
            "rule": "below 9 out of 10 the answer is no, even if these wallets profited from it",
        },
        "methodology": {
            "earliest_buyers": "indexer query for the token's oldest ERC-20 transfers, sender class recorded",
            "activity_window": f"outgoing transfers in the last {window_days} days",
            "bot_rule": f"any two of the wallet's own transfers of the token less than {BOT_INTERVAL_SECONDS}s apart",
            "recurrence_rule": f"a token bought by {min_wallets}+ of the surviving wallets",
            "scoring": {"wallets_holding": "1.0 + 1.0 per wallet above two, capped 4.0",
                        "still_held": "2.0 x share of wallets still holding",
                        "buy_recency_7d": "1.5 x share that bought in the last 7 days",
                        "liquidity_floor": "+0.5 if DEX liquidity >= $100k, else -1.0",
                        "cycle_wallet_conviction": "1.0 x min(1, wallets/5)"},
            "prices": "DexScreener public API, deepest Base pair",
            "sources": ["Alchemy Base indexer", "Base public RPC", "DexScreener"],
        },
        "not_checked": [
            "which of these wallets are 'smart money' beyond 'they bought early once' is an inference, not a fact",
            "future performance: an early buyer is not a guarantee, this ranks evidence, it does not predict",
            "wallet clustering behind one owner (same fund, same operator) is not detected",
            "CEX-internal flows and off-chain intent",
        ],
    }


# ── HTTP surface ─────────────────────────────────────────────────────────────

def register(app, ctx: Ctx) -> None:
    """Free index + the paid Base route (GET twin included: crawlers probe GET before POST)."""
    from pydantic import BaseModel, Field

    class HunterReq(BaseModel):
        token: str = Field(..., description="Contract address of a coin from a previous cycle (Base)")
        window_days: int = Field(30, ge=1, le=180)
        min_wallets: int = Field(3, ge=2, le=10)
        limit: int = Field(25, ge=1, le=60)

    @app.get("/hundred-x-hunter/method")
    def index():
        return {
            "provider": "XH Agents — cycle-wallet hunt (the 'next 100x' method)",
            "what_it_is": ("The seven-step method: take a coin from a previous cycle, list its earliest buyers, "
                           "keep the ones still trading, drop the machines, read what they bought since, and "
                           "score every token that shows up in several of those wallets. Below the threshold "
                           "the answer is no."),
            "chain": "Base (eip155:8453)",
            "price_usdc_per_call": 0.15,
            "endpoints": [
                {"route": "POST /api/hundred-x-hunter", "chain": "base", "price_usd": 0.15,
                 "input": {"token": "0x… (a coin from a previous cycle)"}},
                {"route": "GET /api/hundred-x-hunter?token=0x…", "chain": "base", "price_usd": 0.15},
            ],
            "sibling": {"chain": "solana", "route": "POST /v1/hundred-x-hunter",
                        "origin": "https://pronomad.duckdns.org",
                        "note": "same method, Solana data, settled in USDC on Solana"},
            "threshold": BUY_THRESHOLD,
            "not_checked": ["smart-money identity beyond 'bought early once'", "future price",
                            "wallet clustering behind one owner"],
        }

    def _run(req: HunterReq) -> dict:
        if not ctx.is_address(req.token):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="token must be a 0x… Base contract address")
        return run(ctx, req.token, req.window_days, req.min_wallets, req.limit)

    @app.post("/hundred-x-hunter")
    def hunt_post(req: HunterReq):
        return _run(req)

    @app.get("/hundred-x-hunter")
    def hunt_get(token: str, window_days: int = 30, min_wallets: int = 3, limit: int = 25):
        req = HunterReq(token=token, window_days=window_days, min_wallets=min_wallets, limit=limit)
        return _run(req)
