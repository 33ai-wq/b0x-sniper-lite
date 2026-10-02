#!/usr/bin/env python3
"""
opportunity_scanner.py
Module for prpo_ai / Hermes -- scans income opportunities on-chain (yield
farming, trending tokens), then has the LLM summarize them into a short
report. The summary itself is generated in Bahasa Indonesia, since that's
the language the operator reads reports in.

Data sources (free, no API key required):
- DeFiLlama Yields API   -> yield farming pools (APY, TVL, chain)
- CoinGecko Trending API -> tokens currently trending

Output:
- JSON log file + text summary (can be wired into a Telegram bot / dashboard)

Usage:
1. Set env vars NIM_API_KEY, NIM_BASE_URL, NIM_MODEL (the same NVIDIA NIM
   endpoint already used for Hermes/MiniMax-M3).
2. Run manually:  python3 opportunity_scanner.py
3. Or schedule via cron on the VPS, e.g. every 6 hours:
       0 */6 * * * cd /path/to/folder && /usr/bin/python3 opportunity_scanner.py >> scan.log 2>&1
   A systemd timer works too if you want something cleaner than cron.

Possible extensions (not implemented here, add new functions following the
same pattern):
- fetch_birdeye_solana_trending()  -> new Solana / pump.fun tokens
- fetch_arbitrage_gaps()           -> price gaps across DEXs (Jupiter/Raydium/Orca)
- send_telegram_alert(text)        -> push the summary to your Telegram bot
"""

import os
import json
import requests
from datetime import datetime, timezone

# ---------- Configuration ----------
NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_API_KEY = os.getenv("NIM_API_KEY", "")
NIM_MODEL = os.getenv("NIM_MODEL", "minimaxai/minimax-m3")

MIN_TVL_USD = 200_000     # filter out tiny/high-risk pools
MIN_APY = 8.0             # minimum APY worth looking at
MAX_APY = 200.0           # above this is usually a red flag / unsustainable
TARGET_CHAINS = {"Solana", "Ethereum", "Arbitrum", "Base"}

OUTPUT_DIR = "opportunity_reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_yield_opportunities():
    """Fetch yield farming pools from DeFiLlama, filtered by our criteria."""
    r = requests.get("https://yields.llama.fi/pools", timeout=30)
    r.raise_for_status()
    pools = r.json().get("data", [])

    filtered = []
    for p in pools:
        chain = p.get("chain")
        tvl = p.get("tvlUsd") or 0
        apy = p.get("apy") or 0
        if chain in TARGET_CHAINS and MIN_TVL_USD <= tvl and MIN_APY <= apy <= MAX_APY:
            filtered.append({
                "project": p.get("project"),
                "symbol": p.get("symbol"),
                "chain": chain,
                "apy": round(apy, 2),
                "tvl_usd": round(tvl, 0),
                "il_risk": p.get("ilRisk"),
                "pool_id": p.get("pool"),
            })
    filtered.sort(key=lambda x: x["apy"], reverse=True)
    return filtered[:15]


def fetch_trending_tokens():
    """Fetch trending tokens from CoinGecko."""
    r = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=30)
    r.raise_for_status()
    coins = r.json().get("coins", [])
    return [
        {
            "name": c["item"]["name"],
            "symbol": c["item"]["symbol"],
            "market_cap_rank": c["item"].get("market_cap_rank"),
            "score": c["item"].get("score"),
        }
        for c in coins
    ]


def build_prompt(yields, trending):
    """
    Instructions are in English (models generally follow English instructions
    more precisely), but explicitly ask the model to write the final report
    in Bahasa Indonesia since that's the language it gets read in.
    """
    return f"""You are a crypto opportunity analyst for an independent operator (not a licensed financial advisor).
The raw data below comes from an automated scan. Your task:

1. Summarize the 3-5 most interesting yield farming opportunities from the `yields` list -- mention APY, TVL, and the main risk (IL risk, unaudited/new protocol, etc).
2. Summarize trending tokens whose pattern looks worth watching further (NOT a buy recommendation).
3. Clearly flag any data that looks anomalous or risky (unrealistic APY, too-small TVL).
4. End with a short disclaimer that this is not financial advice, only a data summary for further research.

IMPORTANT: Write your entire response in Bahasa Indonesia. Keep it short and to the point, no fluff.

YIELD FARMING DATA:
{json.dumps(yields, indent=2)}

TRENDING TOKEN DATA:
{json.dumps(trending, indent=2)}
"""


def call_hermes(prompt):
    """Call the Hermes model via NVIDIA NIM (OpenAI-compatible endpoint)."""
    headers = {
        "Authorization": f"Bearer {NIM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NIM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 1000,
    }
    r = requests.post(f"{NIM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def main():
    print("[*] Fetching yield farming data...")
    yields = fetch_yield_opportunities()
    print(f"    -> {len(yields)} pools passed the filter")

    print("[*] Fetching trending token data...")
    trending = fetch_trending_tokens()
    print(f"    -> {len(trending)} trending tokens")

    prompt = build_prompt(yields, trending)

    summary = "(NIM_API_KEY not set, skipping LLM analysis)"
    if NIM_API_KEY:
        print("[*] Asking Hermes to summarize opportunities...")
        summary = call_hermes(prompt)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at_utc": timestamp,
        "yields_raw": yields,
        "trending_raw": trending,
        "summary": summary,
    }

    out_path = os.path.join(OUTPUT_DIR, f"report_{timestamp}.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[+] Report saved: {out_path}")
    print("\n=== SUMMARY ===\n")
    print(summary)


if __name__ == "__main__":
    main()
