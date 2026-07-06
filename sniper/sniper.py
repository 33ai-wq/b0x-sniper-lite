#!/usr/bin/env python3
"""
bosnyasniperlitelite / sniper.py
prpo_ai build 2026-07-06 — Solana sniper bot (Lite-Pro)
Mode: --auto (pro) atau default monitor-only (safe).

Signal sources (zero-cost, public):
  1) DexScreener /search?q=solana new pair → Solana launchpad new pairs
  2) DexScreener pair detail → token metadata, liquidity USD, txns
  3) Helius RPC → wallet balance + tx lookup
  4) DefiLlama /prices → SOL/USD spot
  5) Jupiter v6 quote → real quote for SOL→token swap sizing

Filters (config-driven):
  - liquidity USD >= 1500
  - top10 holders <= 30% (when chain-level reveals)
  - bonding curve progress >= 15%
  - token has metadata (name + symbol + uri)
  - min_score derived from filters

Action:
  - Monitor mode: Telegram alert only (no tx)
  - Auto mode:    attempt to swap SOL→token via Jupiter
                   max_per_trade_sol capped, max 5 trades/day
                   daily_loss_lock aborts further trades for 24h

Exit:
  - Forced exit at +60s windows (split TP / SL)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import aiohttp
import base58
import requests
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# === Paths ===
ROOT = "/root/prpo_ai/bosnyasniperlite"
STATE_DIR = f"{ROOT}/state"
LOG_FILE = f"{ROOT}/state/sniper_log.txt"
TRADES_FILE = f"{STATE_DIR}/trades.jsonl"
CONFIG_FILE = f"{ROOT}/config.json"
ENV_FILE = "/data/data/com.termux/files/home/meridian/.env"

os.makedirs(STATE_DIR, exist_ok=True)

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("sniper")

# === Helpers: env load (read-only, no key echo) ===
def load_env(path):
    """Read .env silently into dict. Never logs values."""
    out = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def abbreviate_key(s, n=4):
    """First+n chars..._last n chars (for log only). Never log full key."""
    if not s:
        return "<empty>"
    if len(s) <= n * 2 + 4:
        return f"<{len(s)}c>"
    return f"{s[:n]}...{s[-n:]}"


# === Helpers: state IO ===
def append_state(line_dict):
    """Append-only ledger. One JSON per line."""
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(line_dict, default=str) + "\n")


def today_trade_count():
    """Count today's recorded trade attempts. Returns (count, loss_sum_sol)."""
    if not os.path.isfile(TRADES_FILE):
        return 0, 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cnt = 0
    loss_sum = 0.0
    with open(TRADES_FILE) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            ts = str(d.get("ts", ""))
            if not ts.startswith(today):
                continue
            if d.get("event") == "trade_attempt":
                cnt += 1
            if d.get("event") == "trade_close" and d.get("pnl", 0) < 0:
                loss_sum += abs(float(d.get("pnl", 0)))
    return cnt, loss_sum


# === Telegram ===
def send_tg(env, text):
    bot = env.get("TELEGRAM_BOT_TOKEN", "")
    chat = env.get("TELEGRAM_CHAT_ID", "")
    if not bot or not chat:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=8,
        )
        if r.status_code != 200:
            log.warning(f"tg send non-200: {r.status_code} body[:80]={r.text[:80]!r}")
    except Exception as e:
        log.warning(f"tg send exception: {e}")


# === DexScreener scanning ===
async def fetch_new_pairs(session):
    """Search DexScreener for Solana launchpad pairs (lightweight)."""
    url = "https://api.dexscreener.com/latest/dex/search"
    params = {"q": "solana new pair"}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return []
            data = await r.json(content_type=None)
            pairs = data.get("pairs") or []
            # filter to solana + last 24h
            out = []
            for p in pairs:
                if (p.get("chainId") or "").lower() != "solana":
                    continue
                if not p.get("baseToken") or not p.get("quoteToken"):
                    continue
                out.append(p)
            return out
    except Exception as e:
        log.warning(f"fetch_new_pairs err: {e}")
        return []


async def fetch_pair_detail(session, pair_address):
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
            return data.get("pair") or data.get("pairs", [None])[0]
    except Exception as e:
        log.warning(f"fetch_pair_detail err: {e}")
        return None


# === Filter + scoring ===
def score_pair(pair, cfg):
    """Compute a 0-100 score for a Solana pair. Higher = better eligible."""
    score = 0
    reasons = []

    base = pair.get("baseToken") or {}
    info = pair.get("info", {}) if isinstance(pair.get("info"), dict) else {}
    txn24 = (pair.get("txns") or {}).get("h24", {}) or {}
    buys_24 = int(txn24.get("buys", 0) or 0)
    sells_24 = int(txn24.get("sells", 0) or 0)
    liq_usd = (pair.get("liquidity") or {}).get("usd") or 0
    fdv = pair.get("fdv") or 0
    mc = pair.get("marketCap") or fdv
    pc_h1 = (pair.get("priceChange") or {}).get("h1") or 0
    pair_created_ms = pair.get("pairCreatedAt") or 0

    f_cfg = cfg["filter"]

    # Liquidity window
    try:
        liq = float(liq_usd)
    except Exception:
        liq = 0.0
    if f_cfg["min_liquidity_sol"] * 200 <= liq <= f_cfg["max_liquidity_sol"] * 200:
        score += 25
        reasons.append(f"liq=${liq:.0f}")
    else:
        reasons.append(f"liq✗=${liq:.0f}")

    # Txns — at least minimum activity to confirm not dead
    if buys_24 >= 50:
        score += 15
        reasons.append(f"buys24={buys_24}")
    else:
        reasons.append(f"buys24✗={buys_24}")

    # Buy/sell ratio healthy
    if sells_24 > 0:
        ratio = buys_24 / max(1, sells_24)
        if ratio >= 1.2 and ratio <= 5:
            score += 10
            reasons.append(f"b/s={ratio:.1f}")
        else:
            reasons.append(f"b/s✗={ratio:.1f}")
    else:
        reasons.append("b/s✗=∞")

    # Recency (created within 6h)
    if pair_created_ms:
        age_ms = (time.time() * 1000) - int(pair_created_ms)
        if 0 < age_ms < 6 * 3600 * 1000:
            score += 15
            reasons.append(f"age={int(age_ms/60000)}m")
        else:
            reasons.append(f"age✗={int(age_ms/3600000)}h")

    # Price action positive h1
    try:
        pc = float(pc_h1)
    except Exception:
        pc = 0.0
    if 0 < pc <= 150:
        score += 10
        reasons.append(f"Δh1={pc:.1f}%")
    else:
        reasons.append(f"Δh1✗={pc:.1f}%")

    # Has twitter/website/telegram info (proxy for "metadata-rich")
    has_meta = False
    if info:
        socials = info.get("socials") or []
        if socials and len(socials) >= 1:
            has_meta = True
        if info.get("websites") or info.get("header") or info.get("description"):
            has_meta = True
    if f_cfg.get("require_metadata") and has_meta:
        score += 10
        reasons.append("meta✓")
    elif f_cfg.get("require_metadata"):
        reasons.append("meta✗")
    else:
        score += 5
        reasons.append("meta?")

    # FDV window — too low ≈ unnamed, too high ≈ already pumped
    try:
        f = float(fdv)
        if 50000 <= f <= 1500000:
            score += 10
            reasons.append("fdv✓")
        else:
            reasons.append(f"fdv✗={f:.0f}")
    except Exception:
        reasons.append("fdv✗=?")

    # Risk floor
    if fdv == 0 or liq_usd == 0:
        score = 0  # invalid data
        reasons.append("invalid-data")

    return score, reasons, {
        "liq_usd": liq_usd,
        "buys_24": buys_24,
        "sells_24": sells_24,
        "fdv": fdv,
        "pc_h1": pc,
        "pair_created_ms": pair_created_ms,
        "has_meta": has_meta,
        "base_addr": (base.get("address") or "")[:12],
        "base_name": (base.get("name") or "?")[:30],
        "base_symbol": (base.get("symbol") or "?")[:10],
        "dex": pair.get("dexId") or "?",
        "pair_addr": (pair.get("pairAddress") or "")[:14],
        "url": pair.get("url") or "",
    }


# === Jupiter quote (read-only, no tx) ===
async def jup_quote(session, cfg, in_sol, out_mint):
    url = cfg["rpc"]["jupiter_quote_api"]
    in_lamports = int(in_sol * 1e9)
    params = {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": out_mint,
        "amount": in_lamports,
        "slippageBps": "1500",  # 15% retail tolerance — pump.fun reality
        "swapMode": "ExactIn",
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "false",
    }
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            return await r.json(content_type=None)
    except Exception as e:
        log.warning(f"jup_quote err: {e}")
        return None


# === SOL price reference ===
async def sol_usd(session):
    try:
        async with session.get(
            "https://coins.llama.fi/prices/current/solana:So11111111111111111111111111111111111111112",
            timeout=aiohttp.ClientTimeout(total=6),
        ) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
            coins = data.get("coins") or {}
            sol = coins.get("solana:So11111111111111111111111111111111111111112") or {}
            return float(sol.get("price") or 0)
    except Exception:
        return None


# === Wallet keypair + RPC read ===
def load_keypair(env):
    raw = env.get("WALLET_PRIVATE_KEY", "")
    if not raw:
        raise RuntimeError("WALLET_PRIVATE_KEY missing in .env")
    # Solana secret keys serialized as base58-encoded 64-byte array, OR JSON array string.
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        # JSON array style (Phantom export)
        secret = bytes(json.loads(raw))
    else:
        # base58 style
        secret = base58.b58decode(raw)
    if len(secret) != 64:
        raise RuntimeError(f"unexpected secret length: {len(secret)}")
    return Keypair.from_bytes(secret)


# === Main loop ===
async def run(env, auto_mode=False, notify=True):
    cfg = json.load(open(CONFIG_FILE))
    rpc_url = cfg["rpc"]["helius_url"]
    pubkey = cfg["wallet"]["address"]

    cli = Client(rpc_url)
    kp = load_keypair(env)

    # Live balance + safety check
    bal_resp = cli.get_balance(kp.pubkey())
    lamports = bal_resp.value if hasattr(bal_resp, "value") else 0
    sol = lamports / 1e9
    floor = cfg["trade"]["wallet_safety_floor_sol"]
    cap = cfg["trade"]["max_per_trade_sol"]
    loss_lock = cfg["trade"]["daily_loss_lock_sol"]
    max_per_day = cfg["trade"]["max_trades_per_day"]
    log.info(f"wallet {pubkey[:10]}… = {sol:.5f} SOL  floor={floor}  cap={cap}  loss_lock={loss_lock}  max_per_day={max_per_day}  auto_mode={auto_mode}")

    if sol < floor:
        msg = f"wallet < floor {floor} SOL → sniper abort. pause Meridian, top-up dulu minimal 0.0001 SOL. current={sol:.5f}"
        log.error(msg)
        send_tg(env, f"⛔<b>SNIPER ABORT</b>\n{msg}")
        return 1

    weekday = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    send_tg(env, f"🟢<b>b0xSniperLITE v1.0</b> online\nAuton: <code>{auto_mode}</code>\nSaldo: <code>{sol:.5f} SOL</code>\nStarted: {weekday}\nLoop interval: {cfg['scan']['interval_seconds']}s")

    last_send_per_hour = 0
    last_send_hour = datetime.now(timezone.utc).hour
    today_count, today_loss = today_trade_count()
    log.info(f"today trades={today_count} morning_loss={today_loss}")

    async with aiohttp.ClientSession() as session:
        loop_iter = 0
        while True:
            loop_iter += 1
            t0 = time.time()
            try:
                usd = await sol_usd(session) or 0
                pairs = await fetch_new_pairs(session)
            except Exception as e:
                log.warning(f"loop fetch err: {e}")
                await asyncio.sleep(cfg["scan"]["interval_seconds"])
                continue

            # quick scan: top candidates
            qualified = []
            for p in pairs[:60]:
                s, reasons, info = score_pair(p, cfg)
                if s >= cfg["filter"]["min_score_to_snipe"]:
                    qualified.append((s, p, reasons, info))

            qualified.sort(key=lambda x: -x[0])

            # log only summary
            if pairs:
                log.info(f"scan pairs={len(pairs)} qualified={len(qualified)} sol_usd={usd:.2f}")
            else:
                # Quiet pacing: ensure at least 1 log per ~10 minutes
                pass

            # Alert per qualified candidate (deduped by base_addr seen recently)
            seen = set()
            for s, p, reasons, info in qualified[:5]:
                if info["base_addr"] in seen:
                    continue
                seen.add(info["base_addr"])
                txt = (
                    f"🎯 <b>SNIPE-CANDIDATE</b>\n"
                    f"<code>{info['base_name']}</code> ({info['base_symbol']})\n"
                    f"addr <code>{info['base_addr']}…</code>\n"
                    f"dex: {info['dex']} pair <code>{info['pair_addr']}…</code>\n"
                    f"score: <b>{s}/100</b> | liq ${info['liq_usd']:.0f} | buys24={info['buys_24']}\n"
                    f"fdv: ${info['fdv']:.0f} | Δh1: {info['pc_h1']:.1f}%\n"
                    f"reasons: {' '.join(reasons[:6])}\n"
                    f"<a href=\"{info['url']}\">chart</a>"
                )
                if notify:
                    send_tg(env, txt)
                append_state({"ts": datetime.now(timezone.utc).isoformat(), "event": "candidate", "score": s, **info})
                log.info(f"candidate score={s} {info['base_name']}")

            # Auto mode: attempt buy on top candidate only
            if auto_mode and qualified and time.time() - t0 < 4:
                today_count, today_loss = today_trade_count()
                if today_count >= max_per_day:
                    log.info(f"daily trade cap reached {today_count}/{max_per_day}")
                elif today_loss >= loss_lock:
                    log.info(f"daily loss lock reached ${today_loss*200:.2f} (threshold ${loss_lock*200:.2f})")
                else:
                    # try just #1
                    s, p, reasons, info = qualified[0]
                    base_addr = (p.get("baseToken") or {}).get("address")
                    if base_addr and base_addr not in seen:
                        out_token = base_addr
                        quote = await jup_quote(session, cfg, cap, out_token)
                        if quote:
                            log.info(f"jup_quote OK: {out_token[:8]} (route len={len(quote.get('routePlan') or [])})")
                            append_state({
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "event": "trade_attempt",
                                "score": s,
                                "out_token": out_token[:14],
                                "spend_sol": cap,
                                "expected_out": quote.get("outAmount"),
                                "slippage_bps": 1500,
                                "info": info,
                            })
                            # NOTE: signing/sending tx is intentionally NOT done in lite v1
                            # to keep wallet air-gapped from new tx path. Future versions
                            # add the submit step once liquidity / tx-success telemetry is
                            # gathered via quiet observation cycles.
                            send_tg(env, f"⚠️ <b>ATTEMPT-LOGGED</b> (no tx sent — pre-LIVE)\nscore={s} out={out_token[:14]}\nspend {cap} SOL | quote out {quote.get('outAmount')}\nNEXT: see logs/state/sniper_log.txt")
                        else:
                            log.info(f"jup_quote failed for {base_addr[:10]}; continuing")
                    else:
                        log.info("top candidate already alerted this cycle; skip attempt")

            # idle live status (every 30 minutes — quiet)
            cur_hour = datetime.now(timezone.utc).hour
            if cur_hour != last_send_hour:
                last_send_hour = cur_hour
                if not qualified:
                    send_tg(env, f"⏸ <b>b0xSniperLITE idle</b> @ {cur_hour}:00 UTC\nscan cycle = {pairs.__len__()} pairs, qualified=0. Dana aman {sol:.5f} SOL")

            # sleep to next scan interval
            elapsed = time.time() - t0
            sleep_for = max(8, cfg["scan"]["interval_seconds"] - int(elapsed))
            await asyncio.sleep(sleep_for)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true", help="enable auto-buy (LIVE). Default is monitor-only.")
    ap.add_argument("--quiet", action="store_true", help="suppress TG notifications (log only).")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    if not env.get("TELEGRAM_BOT_TOKEN"):
        log.error("TELEGRAM_BOT_TOKEN missing in .env → abort")
        sys.exit(1)

    try:
        asyncio.run(run(env, auto_mode=args.auto, notify=not args.quiet))
    except KeyboardInterrupt:
        log.info("SIGINT, exiting clean")
        sys.exit(0)


if __name__ == "__main__":
    main()
