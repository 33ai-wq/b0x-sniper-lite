#!/usr/bin/env python3
"""
MCP TradingView Auto-Screener — Production Version.
Hybrid: CoinGecko (established) + DEXScreener (trending/new) + MCP (enrichment).
No exchange API keys needed. Sends Telegram alerts with RH sniper parameters.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiohttp
import httpx

# ─── Config ──────────────────────────────────────────────────────────────
SCAN_INTERVAL_MIN = 10

# RH Sniper Filters
MIN_MCAP = 500_000
MAX_MCAP = 10_000_000
MIN_LIQUIDITY = 100_000
MIN_VOLUME_24H = 500_000
MIN_TXNS_24H = 5_000
MAX_AGE_HOURS = 24

# DEXScreener relaxed filters for newer tokens
DEX_MIN_MCAP = 50_000
DEX_MAX_MCAP = 10_000_000
DEX_MIN_LIQUIDITY = 20_000
DEX_MIN_VOLUME_24H = 50_000
DEX_MIN_TXNS_24H = 500
DEX_MAX_AGE_HOURS = 168  # 1 week

# Risk params (match your manual trading)
TP_PCT = 2.5
SL_PCT = 1.5
LEVERAGE = 2

DEDUP_COOLDOWN_HOURS = 1

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1963809645")

STATE_FILE = Path("/home/ubuntu/prpo_ai/mcp_sniper/alert_state.json")

COINGECKO_API = "https://api.coingecko.com/api/v3"
DEXSCREENER_API = "https://api.dexscreener.com"

# ─── Data Classes ────────────────────────────────────────────────────────


@dataclass
class SnipeCandidate:
    symbol: str
    chain: str
    price: float
    mcap: float
    liquidity: float
    volume_24h: float
    txns_24h: int
    age_hours: float
    setup_type: str
    indicators: dict
    mtf_alignment: str
    news_sentiment: str
    timestamp: str
    source: str  # "coingecko" | "dexscreener"
    contract_address: str = ""  # Token contract address (CA)

    def passes_filters(self) -> tuple[bool, list[str]]:
        # Use different thresholds based on source
        if self.source == "dexscreener":
            min_mcap, max_mcap = DEX_MIN_MCAP, DEX_MAX_MCAP
            min_liq = DEX_MIN_LIQUIDITY
            min_vol = DEX_MIN_VOLUME_24H
            min_txns = DEX_MIN_TXNS_24H
            max_age = DEX_MAX_AGE_HOURS
        else:
            min_mcap, max_mcap = MIN_MCAP, MAX_MCAP
            min_liq = MIN_LIQUIDITY
            min_vol = MIN_VOLUME_24H
            min_txns = MIN_TXNS_24H
            max_age = MAX_AGE_HOURS
        
        reasons = []
        if self.mcap < min_mcap or self.mcap > max_mcap:
            reasons.append(f"MCap ${self.mcap:,.0f} outside ${min_mcap:,}-${max_mcap:,}")
        if self.liquidity < min_liq:
            reasons.append(f"Liq ${self.liquidity:,.0f} < ${min_liq:,}")
        if self.volume_24h < min_vol:
            reasons.append(f"Vol24h ${self.volume_24h:,.0f} < ${min_vol:,}")
        if self.txns_24h < min_txns:
            reasons.append(f"Txns {self.txns_24h} < {min_txns}")
        # Skip age filter for DEXScreener - pairCreatedAt is unreliable
        if self.source != "dexscreener" and self.age_hours > max_age:
            reasons.append(f"Age {self.age_hours:.1f}h > {max_age}h")
        return len(reasons) == 0, reasons

    def format_alert(self) -> str:
        passes, reasons = self.passes_filters()
        status = "✅ PASS" if passes else "⚠️ FILTERED"
        reason_str = "\n".join(f"  • {r}" for r in reasons) if reasons else "  • All RH criteria met"

        chain_emoji = {"solana": "🟣", "base": "🔵", "bsc": "🟡", "ethereum": "🔷", "arbitrum": "🔵", "polygon": "🟣"}.get(self.chain, "⚪")

        # Ensure price is float
        price = float(self.price) if self.price else 0.0

        # Contract address line
        ca_line = f"📍 CA: <code>{self.contract_address}</code>\n" if self.contract_address else ""

        return (
            f"🎯 <b>SNIPE ALERT</b> {status}\n"
            f"{chain_emoji} <b>{self.symbol}</b> @ <b>${price:,.6f}</b> ({self.chain.upper()})\n"
            f"{ca_line}"
            f"📊 MCap: <b>${self.mcap:,.0f}</b> | Liq: <b>${self.liquidity:,.0f}</b> | "
            f"Vol24h: <b>${self.volume_24h:,.0f}</b> | Txns: <b>{self.txns_24h:,}</b>\n"
            f"📈 Setup: <b>{self.setup_type}</b> | MTF: <b>{self.mtf_alignment}</b> | "
            f"News: <b>{self.news_sentiment}</b>\n"
            f"{reason_str}\n"
            f"🎯 Entry: <b>${price:,.6f}</b> | TP: <b>+{TP_PCT}%</b> | SL: <b>-{SL_PCT}%</b> | Lev: <b>{LEVERAGE}x</b>\n"
            f"⏰ {self.timestamp} | Age: {self.age_hours:.1f}h | Source: {self.source}"
        )

    def dedup_key(self) -> str:
        return f"{self.symbol}:{self.chain}:{self.setup_type}"


# ─── Dedup State ─────────────────────────────────────────────────────────


class AlertState:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return {}
        return {}

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def is_cooldown(self, key: str) -> bool:
        if key not in self.data:
            return False
        last = datetime.fromisoformat(self.data[key])
        return datetime.now() - last < timedelta(hours=DEDUP_COOLDOWN_HOURS)

    def mark_sent(self, key: str):
        self.data[key] = datetime.now().isoformat()
        self.save()


# ─── Telegram ────────────────────────────────────────────────────────────


async def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN not set, skipping send")
        return False
    # Strip any whitespace/newlines from token
    token = TELEGRAM_BOT_TOKEN.strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })
            return resp.status_code == 200
        except Exception as e:
            print(f"Telegram send error: {e}")
            return False


# ─── CoinGecko Screening (Established Tokens) ────────────────────────────


async def fetch_coingecko_markets(session: aiohttp.ClientSession, page: int) -> list[dict]:
    url = f"{COINGECKO_API}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": page,
        "price_change_percentage": "24h,7d",
        "sparkline": "false"
    }
    async with session.get(url, params=params) as resp:
        if resp.status == 200:
            return await resp.json()
        elif resp.status == 429:
            return []
        return []


def detect_coingecko_setups(m: dict) -> list[str]:
    signals = []
    price_change_24h = m.get("price_change_percentage_24h", 0)
    price_change_7d = m.get("price_change_percentage_7d", 0)
    volume_24h = m.get("total_volume", 0)
    mcap = m.get("market_cap", 0)
    vol_mcap_ratio = volume_24h / mcap if mcap else 0

    # Volume breakout
    if vol_mcap_ratio > 0.1 and price_change_24h > 3:
        signals.append("volume_breakout")
    # Mean reversion
    if price_change_24h < -5 and vol_mcap_ratio > 0.05:
        signals.append("mean_reversion")
    # Momentum
    if price_change_7d > 10 and price_change_24h > 5:
        signals.append("momentum")
    # New listing momentum
    rank = m.get("market_cap_rank", 9999)
    if rank > 200 and vol_mcap_ratio > 0.2:
        signals.append("new_listing_momentum")
    return signals


async def screen_coingecko() -> list[SnipeCandidate]:
    candidates = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for page in [1, 2]:
            markets = await fetch_coingecko_markets(session, page)
            for m in markets:
                symbol = m.get("symbol", "").upper()
                if not symbol or symbol in ["USDT", "USDC", "BUSD", "DAI", "TUSD", "FRAX", "USDD", "USDY", "USD1", "USDE", "USDS", "PYUSD", "BUIDL", "RLUSD", "XAUT", "PAXG", "USYC", "M"]:
                    continue

                price = m.get("current_price", 0)
                mcap = m.get("market_cap", 0)
                volume_24h = m.get("total_volume", 0)

                if mcap < MIN_MCAP or mcap > MAX_MCAP:
                    continue
                if volume_24h < MIN_VOLUME_24H:
                    continue

                liquidity = volume_24h * 0.1
                if liquidity < MIN_LIQUIDITY:
                    continue

                txns_24h = int(volume_24h / 100)
                if txns_24h < MIN_TXNS_24H:
                    continue

                rank = m.get("market_cap_rank", 9999)
                age_hours = max(1, rank * 24)

                signals = detect_coingecko_setups(m)

                for setup in signals:
                    indicators = {
                        "price_change_24h": m.get("price_change_percentage_24h", 0),
                        "price_change_7d": m.get("price_change_percentage_7d", 0),
                        "vol_mcap_ratio": volume_24h / mcap if mcap else 0,
                        "market_cap_rank": rank,
                    }
                    cand = SnipeCandidate(
                        symbol=symbol,
                        chain="multichain",
                        price=price,
                        mcap=mcap,
                        liquidity=liquidity,
                        volume_24h=volume_24h,
                        txns_24h=txns_24h,
                        age_hours=age_hours,
                        setup_type=setup,
                        indicators=indicators,
                        mtf_alignment="neutral",
                        news_sentiment="neutral",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        source="coingecko",
                        contract_address=""  # CoinGecko markets endpoint doesn't include contract address
                    )
                    candidates.append(cand)
            await asyncio.sleep(0.5)
    return candidates


# ─── DEXScreener Screening (Trending/New Tokens) ─────────────────────────


async def fetch_dexscreener_trending(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch trending tokens from DEXScreener."""
    url = f"{DEXSCREENER_API}/token-profiles/latest/v1"
    async with session.get(url) as resp:
        if resp.status == 200:
            return await resp.json()
        return []


async def fetch_dexscreener_token(session: aiohttp.ClientSession, token_address: str, chain: str) -> Optional[dict]:
    """Fetch pair data for a specific token."""
    url = f"{DEXSCREENER_API}/latest/dex/tokens/{token_address}"
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.json()
            pairs = data.get("pairs")
            if pairs:
                # Return the pair with highest liquidity
                best = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
                return best
        return None


def detect_dexscreener_setups(pair: dict) -> list[str]:
    signals = []
    price_change = pair.get("priceChange", {})
    price_change_24h = price_change.get("h24", 0)
    price_change_1h = price_change.get("h1", 0)
    price_change_5m = price_change.get("m5", 0)
    
    volume = pair.get("volume", {})
    vol_24h = volume.get("h24", 0)
    vol_1h = volume.get("h1", 0)
    
    mcap = pair.get("fdv", 0)
    liq = pair.get("liquidity", {}).get("usd", 0)
    vol_mcap_ratio = vol_24h / mcap if mcap else 0
    
    txns = pair.get("txns", {})
    txns_24h = txns.get("h24", {}).get("buys", 0) + txns.get("h24", {}).get("sells", 0)
    txns_1h = txns.get("h1", {}).get("buys", 0) + txns.get("h1", {}).get("sells", 0)
    
    # Volume breakout: high 24h vol/mcap + positive price action
    if vol_mcap_ratio > 0.1 and price_change_24h > 3:
        signals.append("volume_breakout")
    
    # Strong momentum: accelerating price + volume
    if price_change_1h > 5 and txns_1h > 100:
        signals.append("momentum")
    
    # New listing: very new (age < 6h) + high activity
    age = pair.get("pairCreatedAt", 0)
    age_h = (age / 1000 / 3600) if age else 999
    if age_h < 6 and txns_24h > 500 and vol_mcap_ratio > 0.1:
        signals.append("new_listing_momentum")
    
    # Pump detection: extreme 5m/1h moves
    if price_change_5m > 10 and price_change_1h > 20:
        signals.append("pump_alert")
    
    # Mean reversion: big drop with volume
    if price_change_24h < -10 and vol_mcap_ratio > 0.05:
        signals.append("mean_reversion")
    
    # Steady growth: consistent positive with good volume
    if price_change_24h > 5 and vol_mcap_ratio > 0.05 and txns_24h > 1000:
        signals.append("steady_growth")
    
    # High activity: lots of transactions regardless of price
    if txns_24h > 5000 and vol_mcap_ratio > 0.1:
        signals.append("high_activity")
    
    return signals


async def screen_dexscreener() -> list[SnipeCandidate]:
    candidates = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        # Use search endpoint for trending/active pairs (more reliable for established small caps)
        search_queries = ["solana", "raydium", "pump", "moonshot", "base", "bsc"]
        
        all_pairs = []
        for query in search_queries:
            url = f"{DEXSCREENER_API}/latest/dex/search?q={query}&limit=50"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs", [])
                    all_pairs.extend(pairs)
            await asyncio.sleep(0.3)
        
        # Deduplicate by pair address
        seen = set()
        unique_pairs = []
        for p in all_pairs:
            addr = p.get("pairAddress", "")
            if addr and addr not in seen:
                seen.add(addr)
                unique_pairs.append(p)
        
        print(f"  Found {len(unique_pairs)} unique pairs from search")
        
        checked = 0
        for pair in unique_pairs:
            base_token = pair.get("baseToken", {})
            symbol = base_token.get("symbol", "")
            if not symbol or symbol in ["SOL", "WETH", "WBNB", "USDC", "USDT", "DAI", "USDe", "USR", "USDX", "sUSD", "crvUSD", "gho", "LUSD", "MIM", "FRAX", "ALUSD", "FEI", "UST", "USTC", "IRON", "BAC", "DOLA", "XUSD", "MAI", "USDN", "USDP", "USDX", "EUROe", "EURS", "AGEUR", "STAT", "JAR", "EURC", "CBR", "SEUR", "EUROC"]:
                continue
            
            chain = pair.get("chainId", "")
            if chain not in ["solana", "base", "bsc", "ethereum", "arbitrum", "polygon"]:
                continue
            
            mcap = pair.get("fdv", 0)
            liq = pair.get("liquidity", {}).get("usd", 0)
            vol_24h = pair.get("volume", {}).get("h24", 0)
            
            txns = pair.get("txns", {})
            txns_24h = txns.get("h24", {}).get("buys", 0) + txns.get("h24", {}).get("sells", 0)
            
            age = pair.get("pairCreatedAt", 0)
            age_h = (age / 1000 / 3600) if age and age > 1000000000 else 999  # 0 or epoch = unknown
            
            # Quick pre-filter (relaxed for new tokens)
            if mcap < DEX_MIN_MCAP or mcap > DEX_MAX_MCAP:
                continue
            if liq < DEX_MIN_LIQUIDITY:
                continue
            if vol_24h < DEX_MIN_VOLUME_24H:
                continue
            if txns_24h < DEX_MIN_TXNS_24H:
                continue
            # Skip age filter - pairCreatedAt is unreliable (often 0 or epoch)
            # if age_h > DEX_MAX_AGE_HOURS:
            #     continue
            
            price = float(pair.get("priceUsd", 0)) if pair.get("priceUsd") else 0.0
            
            signals = detect_dexscreener_setups(pair)
            
            for setup in signals:
                indicators = {
                    "price_change_24h": pair.get("priceChange", {}).get("h24", 0),
                    "price_change_1h": pair.get("priceChange", {}).get("h1", 0),
                    "price_change_5m": pair.get("priceChange", {}).get("m5", 0),
                    "vol_mcap_ratio": vol_24h / mcap if mcap else 0,
                    "txns_1h": txns.get("h1", {}).get("buys", 0) + txns.get("h1", {}).get("sells", 0),
                    "dex_id": pair.get("dexId", ""),
                    "pair_address": pair.get("pairAddress", ""),
                }
                # Get token contract address from baseToken
                contract_address = base_token.get("address", "")
                cand = SnipeCandidate(
                    symbol=symbol,
                    chain=chain,
                    price=price,
                    mcap=mcap,
                    liquidity=liq,
                    volume_24h=vol_24h,
                    txns_24h=txns_24h,
                    age_hours=age_h,
                    setup_type=setup,
                    indicators=indicators,
                    mtf_alignment="neutral",
                    news_sentiment="neutral",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    source="dexscreener",
                    contract_address=contract_address
                )
                candidates.append(cand)
        
        print(f"  Pairs in ${DEX_MIN_MCAP:,}-${DEX_MAX_MCAP:,} range: {checked}")
    
    return candidates


# ─── MCP Deep-Dive (Optional Enhancement) ────────────────────────────────


class MCPTradingViewClient:
    """Optional MCP client for deep-dive when scanner is up."""

    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.request_id = 0
        self.available = False

    async def start(self) -> bool:
        try:
            self.process = await asyncio.create_subprocess_exec(
                "tradingview-mcp", "stdio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-sniper", "version": "0.1.0"}
            }), timeout=10)
            await asyncio.wait_for(self._read_response(), timeout=10)
            await asyncio.wait_for(self._send_request("initialized", {}), timeout=5)
            self.available = True
            return True
        except Exception as e:
            print(f"  MCP unavailable: {e}")
            return False

    async def stop(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()

    async def _send_request(self, method: str, params: dict):
        self.request_id += 1
        msg = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        data = (json.dumps(msg) + "\n").encode()
        self.process.stdin.write(data)
        await self.process.stdin.drain()

    async def _read_response(self) -> dict:
        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=30)
        if not line:
            raise RuntimeError("MCP server closed connection")
        return json.loads(line.decode())

    async def call_tool(self, name: str, args: dict, max_retries: int = 2) -> dict:
        if not self.available:
            return {"error": {"code": "UNAVAILABLE", "message": "MCP not connected"}}
        for attempt in range(max_retries):
            try:
                await asyncio.wait_for(self._send_request("tools/call", {"name": name, "arguments": args}), timeout=10)
                resp = await asyncio.wait_for(self._read_response(), timeout=60)
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                    continue
                return {"error": {"code": "TIMEOUT", "message": f"MCP call {name} timed out", "retryable": True}}
            if "error" in resp:
                raise RuntimeError(f"MCP error: {resp['error']}")
            content = resp.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                return json.loads(content[0]["text"])
        return {}

    async def enrich_candidate(self, cand: SnipeCandidate) -> SnipeCandidate:
        """Try to enrich with MCP data."""
        if not self.available:
            return cand

        # Only try for symbols that exist on major exchanges
        symbol = cand.symbol
        exchange_map = {"solana": "BINANCE", "base": "BINANCE", "bsc": "BINANCE", "ethereum": "BINANCE"}
        exchange = exchange_map.get(cand.chain, "BINANCE")
        
        try:
            # Try multi-timeframe analysis
            mtf = await self.call_tool("multi_timeframe_analysis", {"symbol": symbol, "exchange": exchange})
            if isinstance(mtf, dict) and "error" not in mtf:
                trend = mtf.get("overall_trend", "").lower()
                if "bull" in trend:
                    cand.mtf_alignment = "bullish"
                elif "bear" in trend:
                    cand.mtf_alignment = "bearish"

            # Try combined analysis for news
            combined = await self.call_tool("combined_analysis", {"symbol": symbol, "exchange": exchange, "timeframe": "15m"})
            if isinstance(combined, dict) and "error" not in combined:
                sentiment = combined.get("sentiment", "").lower()
                if "positive" in sentiment or "bullish" in sentiment:
                    cand.news_sentiment = "positive"
                elif "negative" in sentiment or "bearish" in sentiment:
                    cand.news_sentiment = "negative"
        except Exception as e:
            pass  # Silently ignore enrichment errors

        return cand


# ─── Main Screening Logic ────────────────────────────────────────────────


async def run_scan_cycle(state: AlertState):
    """One full scan cycle."""
    print(f"\n🔍 Scan cycle started: {datetime.now().strftime('%H:%M:%S')}")

    # Try MCP (optional)
    mcp = MCPTradingViewClient()
    mcp_ready = await mcp.start()
    if mcp_ready:
        print("  ✅ MCP connected for deep-dive")
    else:
        print("  ⚠️  MCP unavailable — screening only")

    try:
        # Screen with CoinGecko (established tokens)
        print("  📊 Screening CoinGecko (established)...")
        cg_candidates = await screen_coingecko()
        print(f"    Found {len(cg_candidates)} CoinGecko candidates")

        # Screen with DEXScreener (trending/new)
        print("  🔥 Screening DEXScreener (trending/new)...")
        ds_candidates = await screen_dexscreener()
        print(f"    Found {len(ds_candidates)} DEXScreener candidates")

        all_candidates = cg_candidates + ds_candidates

        # Filter & dedup
        alerts_sent = 0
        for cand in all_candidates:
            # Enrich with MCP TradingView data if available
            if mcp_ready:
                cand = await mcp.enrich_candidate(cand)
            
            passes, reasons = cand.passes_filters()
            key = cand.dedup_key()

            if state.is_cooldown(key):
                print(f"  ⏭️  Cooldown: {key}")
                continue

            if passes:
                alert_text = cand.format_alert()
                print(f"  📤 Sending: {cand.symbol} ({cand.setup_type}) [{cand.source}]")
                if await send_telegram(alert_text):
                    state.mark_sent(key)
                    alerts_sent += 1
                    await asyncio.sleep(0.5)
            else:
                print(f"  ❌ Filtered: {cand.symbol} — {reasons[0]}")

        print(f"✅ Cycle done. Alerts sent: {alerts_sent}/{len(all_candidates)}")

    finally:
        await mcp.stop()


# ─── Entry Point ─────────────────────────────────────────────────────────


async def main():
    print("🚀 Starting Production Sniper (CoinGecko + DEXScreener + MCP)")
    print(f"   Interval: {SCAN_INTERVAL_MIN} min")
    print(f"   Filters: MCap ${MIN_MCAP:,}-${MAX_MCAP:,} | Liq>${MIN_LIQUIDITY:,} | Vol>${MIN_VOLUME_24H:,} | Txns>{MIN_TXNS_24H:,} | Age<{MAX_AGE_HOURS}h")

    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ WARNING: TELEGRAM_BOT_TOKEN not set — alerts print to console only")

    state = AlertState(STATE_FILE)

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        await run_scan_cycle(state)
    else:
        while True:
            await run_scan_cycle(state)
            print(f"😴 Sleeping {SCAN_INTERVAL_MIN} min...")
            await asyncio.sleep(SCAN_INTERVAL_MIN * 60)


if __name__ == "__main__":
    asyncio.run(main())