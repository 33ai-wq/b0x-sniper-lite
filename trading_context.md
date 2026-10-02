# Trading Context for Hermes + TradingView MCP
# For: $8.5 USDC capital on Base, manual OKX trading
# Strategy: Mean-reversion + Multi-indicator (EMA/RSI/MACD/ADX)

## Capital & Risk
- **Total Capital**: $8.5 USDC (on Base, bridged to OKX)
- **Risk per Trade**: 25% = $2.12
- **Max Concurrent Positions**: 2
- **Daily Loss Limit**: 10% = $0.85
- **Max Exposure**: 80% = $6.80
- **Leverage**: 2x (perpetuals only)
- **Max Hold Time**: 8 hours

## TP/SL
- **Take Profit**: 2.5%
- **Stop Loss**: 1.5%
- **Trailing Stop**: None (fixed TP/SL)

## Markets (OKX)
### Perpetuals (USDT-margined, 2x leverage)
- BTC-USDT-SWAP
- ETH-USDT-SWAP
- SOL-USDT-SWAP
- DOGE-USDT-SWAP
- ARB-USDT-SWAP
- OP-USDT-SWAP
- APT-USDT-SWAP
- SUI-USDT-SWAP

### Spot (no leverage, no short)
- BTC/USDT
- ETH/USDT
- SOL/USDT
- DOGE/USDT
- ARB/USDT
- OP/USDT
- APT/USDT
- SUI/USDT

## Strategy Rules
### Entry Signals (LONG)
1. **Mean-reversion**: Price ≥1% below EMA21
2. **Trend confirmation**: EMA9 > EMA21 > EMA200 + ADX > 20
3. **Momentum**: RSI < 30 (oversold) OR MACD bullish cross

### Entry Signals (SHORT) - Perp only
1. **Mean-reversion**: Price ≥1% above EMA21
2. **Trend confirmation**: EMA9 < EMA21 < EMA200 + ADX > 20
3. **Momentum**: RSI > 70 (overbought) OR MACD bearish cross

### Exit Rules
- **TP Hit**: Close position at +2.5%
- **SL Hit**: Close position at -1.5%
- **Time Exit**: Close after 8 hours
- **Emergency**: Close all if daily loss > $0.85

## TradingView MCP Queries to Use
- "Screen for bullish RSI divergence on 4H timeframe"
- "Show current technical setup on [SYMBOL] with bull/bear case"
- "Check if [SYMBOL] has bullish MACD cross on 1H"
- "Get key support/resistance levels for [SYMBOL]"
- "Screen watchlist for price >1% below EMA21 with ADX > 20"

## Invalidation Rules
- **LONG invalidated if**: Price breaks below SL, or RSI > 70, or MACD bearish cross
- **SHORT invalidated if**: Price breaks above SL, or RSI < 30, or MACD bullish cross
- **Daily stop**: No new trades if daily loss > $0.85

## Position Sizing
- Fixed $2.12 per trade (25% of capital)
- Quantity = $2.12 / entry_price
- Round down to exchange precision

## Reporting
- Daily summary at 8am UTC: open positions, PnL, signals generated
- Per-trade alert: entry, TP, SL, quantity, reasoning
- Weekly review: win rate, avg win/loss, max drawdown

## Notes
- Manual execution on OKX app/web
- USDC on Base → bridge to OKX → trade
- No auto-trading — signals only
- Telegram alerts for all signals