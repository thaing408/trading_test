# Later work: `tradingview-mcp` (atilaahmettaner)

**Upstream:** https://github.com/atilaahmettaner/tradingview-mcp  
**PyPI:** `tradingview-mcp-server` (v0.8.0 as of this note)  
**License:** MIT  
**Status:** analysis only — **do not implement in this commit.** Revisit when we want extra research-side TA / screener / crypto without wiring it into OMS.

Recorded: 2026-08-19.

---

## What it is

An **MCP server** that exposes ~37 tools for market data, TradingView-style technicals, screeners, sentiment/news, and simple strategy backtests. Clients: Claude, ChatGPT, Cursor, Copilot, OpenClaw (Telegram wrapper).

It is **not** TradingView Inc., does **not** log into a TradingView account, and does **not** drive TradingView Desktop. Data path is third-party public endpoints via:

| Dependency | Pin / range | Role |
|------------|-------------|------|
| `tradingview-ta` | `>=3.3.0` | Per-symbol TA (RSI/MACD/BB consensus BUY/SELL/HOLD) |
| `tradingview-screener` | **`==3.0.0`** | Scanner queries (crypto/futures break if bumped to 3.2.0 stock preset) |
| `httpx` | `>=0.27` | Yahoo quotes, async tools |
| `feedparser` | `>=6.0.12` | RSS news |
| `mcp[cli]` | `>=1.14.0,<2` | FastMCP 1.x only (2.x dropped `mcp.server.fastmcp`) |
| Python | `>=3.10,<3.14` | **3.14 unsupported** — pin 3.13 on Windows (`uvx --python 3.13`) |

Optional: `MARKETAUX_API_TOKEN` for licensed news/sentiment. Hosted paid twin: [pro.cryptosieve.com](https://pro.cryptosieve.com) ($9/$29 mo). Self-host stays free.

**Layout:** `src/tradingview_mcp/server.py` (tools) + `core/{data,services,errors,portfolio,types,utils}` + `coinlist/*.txt`. Entry: `tradingview_mcp.server:main`.

---

## Tool surface (group for later mapping)

**Backtest (Yahoo OHLCV, not our `backtest/` engine)**  
`backtest_strategy`, `compare_strategies`, `walk_forward_backtest_strategy`  
9 strategies: rsi, bollinger, macd, ema_cross, supertrend, donchian, rsi_pullback, keltner_breakout, triple_ema. Timeframes `1d` / `1h`. Metrics: Sharpe, Calmar, expectancy, PF, vs B&H, optional trade log + equity curve. Walk-forward verdicts: ROBUST / MODERATE / WEAK / OVERFITTED.

**Quotes / snapshot**  
`yahoo_price`, `stock_extended_hours`, `market_snapshot` (SPX, NDX, VIX, BTC, ETH, FX, ETFs).

**Screeners**  
`top_gainers`, `top_losers`, `bollinger_scan`, `rating_filter`, `volume_breakout_scanner`, `smart_volume_scanner`, `stock_screener`, `stock_prices`, `screen_stocks`, `scan_by_signal`, crypto on Binance/KuCoin/Bybit, US NASDAQ/NYSE, EGX helpers, BIST via TV screener, futures movers.

**TA**  
`get_technical_analysis`, `get_multiple_analysis`, `get_bollinger_band_analysis` (±3 proprietary BB rating), `get_stock_decision`, `get_candlestick_patterns` (15 patterns), `get_multi_timeframe_analysis` (W→D→4H→1H→15m).

**Sentiment / confluence**  
`market_sentiment` (Reddit), `financial_news` (Yahoo / MarketWatch / CNBC / CoinDesk / CoinTelegraph RSS; Marketaux if keyed), `combined_analysis` (TA + Reddit + news).

**Ops notes from upstream**  
Retry + 60s TTL on screener; TA throttle (default 4 concurrent, 0.8s spacing); structured error envelope `{error: {code, message, retryable}}` on some scanners; async on a subset of hot tools.

---

## Overlap with `trading_agent` (do not rebuild)

| Their tool | Our analog | Notes |
|------------|------------|--------|
| `yahoo_price` / `market_snapshot` | `collectors/market.py`, `market_data/provider.py` (IBKR → Schwab → yfinance) | We already have a **better** bar chain for US equities |
| `financial_news` | `collectors/news.py` (FMP + yfinance + providers) | RSS vs our FMP/yfinance mix |
| `get_technical_analysis` | `analysis/technical.py`, 888 TI, PA (`soulz`) | We are rule/quant, not TV consensus rating |
| `get_multi_timeframe_analysis` | `discipline/mtf_gate.py`, multi-method | Different TF set (we care RTH/session) |
| `stock_screener` / `screen_stocks` | `collectors/screener.py`, `screener/`, `data/tradingview_screener_params.json` | We already store TV screener **params**; they execute TV screener **live** |
| Backtest 9 toys | `backtest/` + sleeves + walk_forward | Their strategies are generic TA toys; ours are book/sleeve/OMS-aware |
| `combined_analysis` | CIO + firm sleeve + synthesis | They dump STRONG BUY; we require CIO/risk rails |
| OpenClaw Telegram | Discord posters + desk UI | Messaging is not a gap |

**Architecture mismatch:** they are a **headless analysis API for chat agents**. We are a **rule desk** (Windows research / Mac LIVE OMS). Never let their BUY/SELL strings place orders.

---

## Gaps they have that we might steal later

1. **Live TradingView screener + `tradingview_ta` consensus** for crypto and global listings (Binance/KuCoin/Bybit, EGX, BIST) — our params JSON is US-desk oriented.  
2. **Rating / BB ±3 scan** as an extra research column, not a CIO vote.  
3. **Crypto top-gainer / volume-breakout** universe for a future crypto sleeve (desk is equity/options first).  
4. **Candlestick pattern dump** as optional tags on research cards.  
5. **Error envelope + TA throttle** pattern if we ever batch TV HTTP.  
6. **MCP adapter** so Grok/Claude can query the same research without duplicating collectors — read-only, Windows-side.

Not interesting later: hosted cryptosieve billing, MCP Apps candlestick widgets, OpenClaw, their backtester (weaker than ours).

---

## Risks (must respect if we integrate)

- **ToS / scrape risk:** public TV endpoints, not official API. Rate-limit cliff (empty JSON body). Throttle is mandatory.  
- **Not real-time guaranteed;** delayed/wrong data disclaimer is explicit.  
- **Pins are load-bearing:** `tradingview-screener==3.0.0`, `mcp<2`, Python `<3.14`.  
- **No execution, no brokerage.** Dual-system: if used, **research host only** (`docs/dual_system.md`). Mac OMS stays Schwab.  
- Independent project; hosted service is a third-party SaaS — do not make production desk depend on `pro.cryptosieve.com`.

---

## Recommended later plan (when we pick this up)

### Option A — thin MCP client (preferred)

- Optional extra: run `uvx --python 3.13 --from tradingview-mcp-server tradingview-mcp` on the **Windows research** box.  
- Desk calls 2–4 tools only: `get_technical_analysis`, `get_multi_timeframe_analysis`, `top_gainers` (crypto), `bollinger_scan`.  
- Stamp results onto research JSON as `tv_mcp_*` fields; CIO treats them as **informational**, never auto-approve.  
- Flag off by default: `TRADING_AGENT_TV_MCP=0`.

### Option B — library import (avoid)

Vendoring `tradingview_mcp` into this repo duplicates Yahoo/news/backtest and fights our provider chain.

### Option C — copy algorithms only

Port BB ±3 rating and candlestick names into `analysis/` if we want the math without MCP process.

**Do not:** merge their STRONG BUY into `auto_trade_book.json`; do not call MCP from Mac execute.

---

## Quick eval commands (later)

```bash
# Isolated; do not add to trading_agent deps until we decide Option A
uvx --python 3.13 --from tradingview-mcp-server tradingview-mcp

# Manual: ask the MCP client for
#   get_technical_analysis NVDA
#   get_multi_timeframe_analysis GC1!
#   top_gainers exchange=BINANCE
```

Compare one symbol vs `trading_agent.analysis.technical` + `market_data.provider.get_ohlcv` and record disagreements in this doc.

---

## Decision log

| Date | Decision |
|------|----------|
| 2026-08-19 | Parked. Useful as optional research MCP / TV-screener source. Not a replacement for collectors, CIO, OMS, or `backtest/`. |
