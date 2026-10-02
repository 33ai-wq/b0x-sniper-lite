#!/usr/bin/env python3
"""
scan_and_alert.py — signal-only scanner for GitHub Actions cron.
No execution, just identify candidates and send Telegram alerts.
Suitable for periodic 15-minute scans when SnapDeploy is unavailable.
"""
import os
import sys
import json
import time
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Tunables
MIN_LIQ_USD = 15000
MIN_VOL24H_USD = 25000
MIN_HOLDERS = 150
TOP_N = 5


def fetch_json(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"err fetch {url}: {e}", file=sys.stderr)
    return None


def get_boosted_tokens(limit=20):
    data = fetch_json("https://api.dexscreener.com/token-boosts/latest/v1")
    if not data or not isinstance(data, list):
        return []
    out = []
    for item in data:
        if item.get("chainId") == "solana":
            addr = item.get("tokenAddress")
            if addr:
                out.append(addr)
    return out[:limit]


def get_search_pairs():
    pairs = []
    for q in ["solana%20meme", "solana%20pump"]:
        data = fetch_json(f"https://api.dexscreener.com/latest/dex/search?q={q}")
        if data and data.get("pairs"):
            for p in data["pairs"]:
                if p.get("chainId") == "solana":
                    pairs.append(p)
    return pairs


def candidate_from_pair(p):
    base = p.get("baseToken") or {}
    mint = base.get("address")
    if not mint:
        return None
    liq = (p.get("liquidity") or {}).get("usd") or 0
    vol24 = (p.get("volume") or {}).get("h24") or 0
    age_ms = p.get("pairCreatedAt")
    age_h = (time.time() * 1000 - age_ms) / (1000 * 3600) if age_ms else 9999
    pc24 = (p.get("priceChange") or {}).get("h24") or 0
    pc1 = (p.get("priceChange") or {}).get("h1") or 0
    txns = (p.get("txns") or {}).get("h24", {}) or {}
    buys = txns.get("buys") or 0
    sells = txns.get("sells") or 0
    return {
        "mint": mint,
        "symbol": base.get("symbol") or mint[:6],
        "price_usd": float(p.get("priceUsd") or 0),
        "liq_usd": liq,
        "vol24h": vol24,
        "age_h": age_h,
        "pc_1h": pc1,
        "pc_24h": pc24,
        "bs_ratio": (buys / (buys + sells)) if (buys + sells) else 0,
        "url": p.get("url"),
        "dex": p.get("dexId"),
    }


def score(c):
    if c["liq_usd"] < MIN_LIQ_USD: return -1
    if c["vol24h"] < MIN_VOL24H_USD: return -1
    if c["age_h"] > 72 or c["age_h"] < 0.25: return -1
    if c["pc_24h"] < -50: return -1
    if c["bs_ratio"] < 0.30: return -1
    s = 0.0
    s += min(c["liq_usd"] / 50000, 2.0)
    s += min(c["vol24h"] / 100000, 2.0)
    if 1 <= c["age_h"] <= 6: s += 1.5
    elif c["age_h"] <= 24: s += 1.0
    if 10 < c["pc_1h"] < 200: s += min(c["pc_1h"] / 50, 1.5)
    if c["bs_ratio"] > 0: s += min(c["bs_ratio"] * 1.5, 1.2)
    return round(s, 2)


def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("telegram: no creds", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"tg err: {e}", file=sys.stderr)
        return False


def main():
    print("[scan] collecting...")
    mints = get_boosted_tokens()
    cands = {}
    for m in mints[:8]:
        d = fetch_json(f"https://api.dexscreener.com/latest/dex/tokens/{m}")
        if d and d.get("pairs"):
            for p in d["pairs"]:
                if p.get("chainId") == "solana":
                    c = candidate_from_pair(p)
                    if c:
                        s = score(c)
                        if s > 0:
                            cands[c["mint"]] = {**c, "score": s}
                    break

    # Add search pairs
    for p in get_search_pairs():
        c = candidate_from_pair(p)
        if not c:
            continue
        s = score(c)
        if s < 0:
            continue
        prev = cands.get(c["mint"])
        if not prev or s > prev["score"]:
            cands[c["mint"]] = {**c, "score": s}

    out = sorted(cands.values(), key=lambda x: x["score"], reverse=True)
    print(f"[scan] qualified: {len(out)}")

    # Build message
    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    if not out:
        msg = f"📡 <b>prpo_ai SCAN</b>  {ts}\nqualified: <b>0</b>\nmarket quiet — no fresh setups"
    else:
        lines = [f"📡 <b>prpo_ai SCAN</b>  {ts}",
                 f"qualified: <b>{len(out)}</b>",
                 ""]
        for c in out[:TOP_N]:
            lines.append(
                f"<b>{c['symbol']}</b>  score={c['score']:.2f}\n"
                f"  liq ${c['liq_usd']:,.0f} | vol24h ${c['vol24h']:,.0f}\n"
                f"  age {c['age_h']:.1f}h | pc1h {c['pc_1h']:+.1f}% | B/S {c['bs_ratio']:.2f}\n"
                f"  <a href=\"{c['url']}\">DexScreener</a> | "
                f"<a href=\"https://jup.ag/swap/SOL-{c['mint']}\">Jupiter</a>"
            )
        msg = "\n".join(lines)

    if send_telegram(msg):
        print("[scan] telegram ok")
    else:
        print("[scan] telegram failed")
        print(msg)


if __name__ == "__main__":
    main()
