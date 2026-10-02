#!/usr/bin/env python3
"""daily_engine.py — the XH Agents daily revenue loop (2026-10-02).

Subcommands
  sense       build today's dated brief from free public sources + our own call log
  distribute  compose the day's X post (draft) and push a short summary to Telegram
  treasury    scan Base for USDC inflows to the treasury in the last 24h and report
  report      one combined status message (used by cron)

Design rules
  * Every number printed or sent comes from a fetch that happened in this run, or is labelled as
    a proxy. No invented figures, no round numbers that nobody measured.
  * A broken source is reported as broken, never as "quiet".
  * Nothing here spends money and nothing posts anywhere without an approved channel.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
HOME = "/home/ubuntu"
DAILY_DIR = os.environ.get("XH_DAILY_DIR", f"{HOME}/prpo_ai/xh_api/daily")
DAILY_FILE = os.path.join(DAILY_DIR, "daily_drop.json")
ARCHIVE_DIR = os.path.join(DAILY_DIR, "archive")
LOG_DB = os.environ.get("XH_API_LOG_DB", f"{HOME}/prpo_ai/xh_api/logs/xh_api.db")
TREASURY = os.environ.get("XH_TREASURY_BASE", "0x6cb53f00a586f7704e1f7121c2e397b579eb3ed0").lower()
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
RPC = os.environ.get("XH_RPC_URL", "https://base-rpc.publicnode.com")
RPC_FALLBACKS = [RPC, "https://mainnet.base.org", "https://base.llamarpc.com", "https://1rpc.io/base"]
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TELEGRAM_ENV = os.environ.get("XH_TELEGRAM_ENV", f"{HOME}/.hermes/profiles/prpo_ai/.env")
TELEGRAM_CHAT = os.environ.get("XH_TELEGRAM_CHAT", "1963809645")
TARGET_USD_DAY = float(os.environ.get("XH_DAILY_TARGET_USD", "1.0"))
UA = "XH-Agents-Daily-Drop/1.0 (+https://xhagents.xyz)"
# wallets we already know are ours or a marketplace's verification wallet, not buyers
KNOWN_TEST_WALLETS = {
    "0x85fc53d6a89bf64e563588efc37b12ee89c4e421": "our buyer test wallet",
    "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c": "payapi.market canary wallet",
    "0x4c934c63c786157fefd990945b25ea60a0fb0205": "payapi.market canary relayer",
}


def _get(url: str, timeout: float = 25.0, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _post(url: str, payload: dict, timeout: float = 25.0) -> str:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _rpc(method: str, params: list) -> object:
    last: Exception | None = None
    for url in RPC_FALLBACKS:
        try:
            req = urllib.request.Request(
                url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
            if body.get("result") is not None:
                return body["result"]
            last = RuntimeError(str(body.get("error"))[:200])
        except Exception as e:
            last = e
    raise last if last else RuntimeError("rpc failed")


# ── sources ──────────────────────────────────────────────────────────────────
def src_hackernews(days: int) -> tuple[list[dict], str | None]:
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    out: list[dict] = []
    try:
        for q in ("x402", "AI agent payments", "paid API agents"):
            u = ("https://hn.algolia.com/api/v1/search_by_date?query=" + urllib.parse.quote(q)
                 + f"&tags=story&numericFilters=created_at_i>{since},points>3&hitsPerPage=20")
            for h in json.loads(_get(u)).get("hits", []):
                out.append({"kind": "hackernews", "source": "hackernews", "query": q,
                            "title": h.get("title"), "score": h.get("points") or 0,
                            "comments": h.get("num_comments") or 0,
                            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                            "created_at": h.get("created_at")})
        uniq = {s["url"]: s for s in out}
        return sorted(uniq.values(), key=lambda s: s["score"], reverse=True), None
    except Exception as e:
        return [], f"hackernews: {e}"


def src_github(days: int) -> tuple[list[dict], str | None]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    out: list[dict] = []
    try:
        token = ""
        try:
            token = open(f"{HOME}/prpo_ai/keys/github_pat").read().strip()
        except Exception:
            pass
        hdrs = {"Accept": "application/vnd.github+json"}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        for q in (f"x402 in:title,body created:>{since}", f"agent payments in:title,body created:>{since}"):
            u = ("https://api.github.com/search/issues?sort=reactions&order=desc&per_page=15&q="
                 + urllib.parse.quote(q))
            for it in json.loads(_get(u, headers=hdrs)).get("items", []):
                out.append({"kind": "github", "source": "github", "query": q,
                            "title": it.get("title"), "score": (it.get("reactions") or {}).get("total_count") or 0,
                            "comments": it.get("comments") or 0, "url": it.get("html_url"),
                            "created_at": it.get("created_at"),
                            "repo": (it.get("repository_url") or "").replace("https://api.github.com/repos/", "")})
        uniq = {s["url"]: s for s in out}
        return sorted(uniq.values(), key=lambda s: s["score"], reverse=True), None
    except Exception as e:
        return [], f"github: {e}"


def src_polymarket(days: int) -> tuple[list[dict], str | None, dict]:
    kw = ("x402", "agent", "ai ", "stablecoin", "crypto payment", "usdc")
    out: list[dict] = []
    try:
        u = "https://gamma-api.polymarket.com/markets?closed=false&limit=200&order=volume24hr&ascending=false"
        markets = json.loads(_get(u))
        for m in markets if isinstance(markets, list) else []:
            title = (m.get("question") or "").lower()
            if any(k in title for k in kw):
                out.append({"kind": "polymarket", "source": "polymarket", "query": "keyword",
                            "title": m.get("question"), "score": float(m.get("volume24hr") or 0),
                            "url": f"https://polymarket.com/market/{m.get('slug')}",
                            "created_at": m.get("createdAt")})
        out.sort(key=lambda s: s["score"], reverse=True)
        return out[:10], None, {"markets_scanned": len(markets) if isinstance(markets, list) else 0}
    except Exception as e:
        return [], f"polymarket: {e}", {}


def src_payapi() -> tuple[dict, str | None]:
    """Marketplace snapshot: how many x402 APIs are listed, how many are settlement-verified."""
    try:
        snaps = {}
        for q in ("x402", "agent", "knowledge", "trading"):
            d = json.loads(_get(f"https://payapi.market/agent/search?q={q}"))
            snaps[q] = {"matches": d.get("total_matches"), "searched": d.get("searched")}
        return {"payapi": snaps}, None
    except Exception as e:
        return {}, f"payapi-market: {e}"


def our_stats(hours: int = 24) -> dict:
    """What our own paid endpoints did. Reads the request log written by xh_api."""
    out = {"db": LOG_DB, "available": False}
    try:
        con = sqlite3.connect(f"file:{LOG_DB}?mode=ro", uri=True, timeout=5)
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        cur = con.execute(
            "SELECT route, status, COUNT(*), SUM(CASE WHEN status=200 THEN 1 ELSE 0 END)"
            " FROM requests WHERE ts >= ? AND route IS NOT NULL GROUP BY route, status", (since,))
        rows = cur.fetchall()
        paid = con.execute("SELECT COUNT(*), COALESCE(SUM(price_usdc),0) FROM requests"
                           " WHERE ts >= ? AND paid = 1", (since,)).fetchone()
        total = con.execute("SELECT COUNT(*) FROM requests WHERE ts >= ?", (since,)).fetchone()[0]
        by_status: dict[str, int] = {}
        for r, status, n, _paid_n in rows:
            by_status[f"{r} {status}"] = by_status.get(f"{r} {status}", 0) + n
        out.update({
            "available": True, "requests_24h": total, "paid_calls_24h": paid[0] or 0,
            "revenue_usd_24h_proxy": round(float(paid[1] or 0), 6),
            "by_route_status": by_status,
            "revenue_note": "proxy = sum of the quoted price on calls that returned 200; the on-chain"
                            " treasury scan in `treasury` is the source of truth",
        })
        con.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def treasury_inflows(hours: int = 24) -> dict:
    """USDC transfers into the treasury wallet, read straight from Base."""
    out = {"hdrs": [], "scanned_hours": hours, "revenue_usd": 0.0, "transfers": 0,
           "senders": {}, "error": None}
    try:
        latest = int(str(_rpc("eth_blockNumber", [])), 16)
        blocks = int(hours * 3600 / 2)  # Base ~2s blocks
        start = max(0, latest - blocks)
        padded = "0x" + TREASURY[2:].rjust(64, "0")
        total = 0
        senders: dict[str, float] = {}
        step = int(os.environ.get("XH_RPC_LOG_STEP", "2000"))
        frm = start
        while frm <= latest:
            to = min(frm + step - 1, latest)
            try:
                logs = list(_rpc("eth_getLogs", [{"fromBlock": hex(frm), "toBlock": hex(to),
                                                  "address": USDC, "topics": [TRANSFER, None, padded]}]) or [])
            except Exception:
                if step > 500:            # public RPCs cap the span; halve and retry the same window
                    step = step // 2
                    continue
                raise
            for lg in logs:
                amount = int(lg["data"], 16) / 1e6
                sender = "0x" + lg["topics"][1][-40:]
                total += amount
                senders[sender.lower()] = round(senders.get(sender.lower(), 0.0) + amount, 6)
                out["hdrs"].append({"tx": lg["transactionHash"], "block": int(lg["blockNumber"], 16),
                                    "from": sender, "amount_usdc": round(amount, 6)})
            frm = to + 1
        out["revenue_usd"] = round(total, 6)
        out["transfers"] = len(out["hdrs"])
        out["senders"] = {s: {"usd": v, "label": KNOWN_TEST_WALLETS.get(s, "unknown (possible buyer)")}
                          for s, v in senders.items()}
        out["blocks"] = {"from": start, "to": latest}
    except Exception as e:
        out["error"] = str(e)
    return out


# ── sense ────────────────────────────────────────────────────────────────────
def cmd_sense(argv: list[str]) -> int:
    days = int(argv[0]) if argv else 30
    signals, failed, extra = [], [], {}
    for fn in (src_hackernews, src_github):
        got, err = fn(days)
        signals += got
        if err:
            failed.append(err)
    pm, err, meta = src_polymarket(days)
    signals += pm
    if err:
        failed.append(err)
    extra.update(meta)
    market, err = src_payapi()
    if err:
        failed.append(err)
    stats = our_stats(24)

    signals.sort(key=lambda s: (s.get("score") or 0), reverse=True)
    sources_ok = sorted({s["source"] for s in signals} | ({"payapi-market"} if market else set()))
    ours = stats.get("revenue_usd_24h_proxy", 0) if stats.get("available") else None
    headline_bits = [
        f"{len(signals)} signals from {len(sources_ok)} live sources",
        f"our paid calls 24h: {stats.get('paid_calls_24h', 'n/a') if stats.get('available') else 'log not live'}",
    ]
    if market:
        snaps = market.get("payapi", {})
        if snaps.get("x402", {}).get("searched"):
            headline_bits.append(f"payapi market: {snaps['x402']['searched']} APIs listed")
    doc = {
        "date": datetime.now(WIB).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "headline": "; ".join(headline_bits),
        "counts": {"signals": len(signals), "sources_ok": len(sources_ok),
                   "sources_failed": len(failed),
                   "our_paid_calls_24h": stats.get("paid_calls_24h") if stats.get("available") else None},
        "sources_ok": sources_ok,
        "sources_failed": failed,
        "signals": signals[:40],
        "market": market,
        "our_endpoints": stats,
        "methodology": {
            "signals": "Hacker News (Algolia, points>3) and GitHub issue/PR search scored by reactions;"
                       " Polymarket markets matched on payment/agent keywords and scored by 24h volume",
            "market": "payapi.market discovery API counts per query",
            "our_endpoints": "xh_api request log (402 = challenge served, 200 = paid and answered)",
            "revenue": f"proxy from quoted prices; on-chain treasury scan is authoritative "
                       f"(see `daily_engine.py treasury`)",
        },
        "not_checked": ["buyer intent behind a 402 challenge", "private/agent-only marketplaces",
                        "settlement for calls that were paid but never retried"],
    }
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with open(DAILY_FILE, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    with open(os.path.join(ARCHIVE_DIR, f"{doc['date']}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    print(f"[sense] {doc['date']} | {doc['headline']}")
    if failed:
        print("[sense] broken sources: " + "; ".join(failed))
    print(f"[sense] wrote {DAILY_FILE}")
    return 0


# ── telegram ─────────────────────────────────────────────────────────────────
def telegram(text: str) -> bool:
    """Try every bot token we hold and message the owner chat. First working token wins.

    Skipped when XH_DAILY_NO_TELEGRAM=1 (cron runs deliver stdout through the Hermes gateway
    instead, so the same report never arrives twice).
    """
    if os.environ.get("XH_DAILY_NO_TELEGRAM") == "1":
        print("[telegram] skipped (XH_DAILY_NO_TELEGRAM=1; the cron delivery carries this output)")
        return False
    candidates: list[str] = []
    for path in (TELEGRAM_ENV, f"{HOME}/.hermes/.env"):
        try:
            candidates += re.findall(r"(\d{8,10}:AA[A-Za-z0-9_-]{30,})", open(path, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
    seen: set[str] = set()
    for token in candidates:
        if token in seen:
            continue
        seen.add(token)
        try:
            data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT, "text": text[:3900],
                                           "disable_web_page_preview": "true"}).encode()
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                                        data=data, timeout=25) as r:
                if json.load(r).get("ok"):
                    return True
        except Exception as e:
            print(f"[telegram] token …{token[-6:]} failed: {e}")
    print("[telegram] no working token for chat", TELEGRAM_CHAT)
    return False


# ── distribute ───────────────────────────────────────────────────────────────
def cmd_distribute(argv: list[str]) -> int:
    try:
        doc = json.load(open(DAILY_FILE, encoding="utf-8"))
    except Exception as e:
        print("[distribute] cannot read the brief:", e)
        return 1
    top = (doc.get("signals") or [])[:3]
    lines = [f"XH Agents Daily Drop - {doc['date']}",
             "",
             "Where the agent-payment economy is actually moving (last {} days):".format(doc.get("window_days", 30))]
    for s in top:
        title = (s.get("title") or "").strip()
        lines.append(f"- {title} ({s.get('source')}, {s.get('score')})")
    lines += ["",
              f"Market: {doc.get('headline')}",
              "The dated brief (signals + our own endpoint numbers) is a paid x402 call:",
              f"POST https://xhagents.xyz/api/daily-drop - ${0.03} USDC on Base",
              "Free teaser: https://xhagents.xyz/api/daily-drop/preview",
              "",
              "#x402 #AIAgents #Base"]
    post = "\n".join(lines)
    path = os.path.join(DAILY_DIR, f"x_post_{doc['date']}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(post)
    print("[distribute] X post draft ->", path)
    print(post)
    ok = telegram("DISTRIBUTE (dry run, nothing posted)\n\n" + post)
    print("[distribute] telegram:", "sent" if ok else "failed")
    return 0


# ── treasury ─────────────────────────────────────────────────────────────────
def cmd_treasury(argv: list[str]) -> int:
    hours = int(argv[0]) if argv else 24
    t = treasury_inflows(hours)
    s = our_stats(hours)
    real = {k: v for k, v in (t.get("senders") or {}).items() if "unknown" in v["label"]}
    real_usd = round(sum(v["usd"] for v in real.values()), 6)
    pct = (t["revenue_usd"] / TARGET_USD_DAY * 100) if TARGET_USD_DAY else 0
    msg = [
        f"XH TREASURY - {hours}h",
        f"USDC into treasury: ${t['revenue_usd']:.4f} ({t['transfers']} transfers)",
        f"from wallets that are not ours: ${real_usd:.4f} ({len(real)} payer(s))",
        f"target ${TARGET_USD_DAY:.2f}/day -> {pct:.0f}%",
        f"paid calls (log): {s.get('paid_calls_24h', 'n/a')} | 402 challenges: "
        f"{sum(v for k, v in (s.get('by_route_status') or {}).items() if k.endswith(' 402'))}",
    ]
    if t.get("error"):
        msg.append(f"scan error: {t['error']}")
    if s.get("available") is False:
        msg.append("request log not readable yet")
    print("\n".join(msg))
    telegram("\n".join(msg))
    out = {"date": datetime.now(WIB).strftime("%Y-%m-%d"), "hours": hours,
           "treasury": t, "our_stats": s, "payers_not_ours_usd": real_usd, "target_usd_day": TARGET_USD_DAY}
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with open(os.path.join(ARCHIVE_DIR, f"treasury_{out['date']}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return 0


def cmd_morning(argv: list[str]) -> int:
    """06:00 WIB: rebuild the dated brief, then say what landed."""
    rc = cmd_sense(argv)
    try:
        doc = json.load(open(DAILY_FILE, encoding="utf-8"))
    except Exception as e:
        print("[morning] brief not readable:", e)
        return rc or 1
    top = (doc.get("signals") or [])[:3]
    lines = [f"XH DAILY DROP - {doc['date']}",
             f"{doc['headline']}",
             ""]
    for s in top:
        lines.append(f"- {(s.get('title') or '')[:90]} [{s.get('source')} {s.get('score')}]")
    if doc.get("sources_failed"):
        lines += ["", "sources broken: " + "; ".join(doc["sources_failed"])]
    lines += ["", f"paid: POST /api/daily-drop (${doc.get('counts', {}).get('price', 0.03) or 0.03})",
              "free teaser: https://xhagents.xyz/api/daily-drop/preview"]
    telegram("\n".join(lines))
    return rc


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sense"
    argv = sys.argv[2:]
    return {"sense": cmd_sense, "morning": cmd_morning, "distribute": cmd_distribute,
            "treasury": cmd_treasury}.get(
        cmd, lambda _a: (print(f"unknown command: {cmd}"), 2)[1])(argv)


if __name__ == "__main__":
    raise SystemExit(main())
