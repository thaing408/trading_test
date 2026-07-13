# External data sources → 7-phase trading desk

This document is the authoritative mapping of OBJECTIVE libraries/APIs into desk
phases. Code reads the same identifiers via `trading_agent.providers.registry`.

## Desk phases

| Phase id | Schedule role |
|----------|----------------|
| `intelligence` | Market Intelligence (overnight macro / bias) |
| `research` | Trading Research (screener, multi-TF, options) |
| `cio_approval` | CIO Final Approval (consumes research) |
| `preopen` | Pre-Open Check |
| `intraday` | Trading Desk cycles |
| `performance` | Performance Review |
| `cio_review` | CIO Daily Review |

## Source catalog (resolved OBJECTIVE URLs)

| Source id | Resolved URL / package | Role | Primary phases | Notes |
|-----------|------------------------|------|----------------|-------|
| `yfinance` | https://github.com/ranaroussi/yfinance | market_data, news, options | intelligence, research, preopen, intraday, performance | Default free path; already wired |
| `pandas_datareader` | https://pandas-datareader.readthedocs.io/en/latest/ | market_data (macro/historical) | intelligence, performance | Optional import; FRED/Yahoo backends |
| `ibkr_tws` | https://interactivebrokers.github.io/tws-api/ | brokerage | preopen, intraday, performance | Requires running TWS/Gateway — optional, fail-closed |
| `alpha_vantage` | https://github.com/RomelTorres/alpha_vantage | market_data | intelligence, research | Env: `ALPHA_VANTAGE_API_KEY` |
| `nasdaq_data_link` | https://github.com/Nasdaq/data-link-python | market_data (alt/fundamentals) | intelligence, research | Env: `NASDAQ_DATA_LINK_API_KEY` |
| `twelve_data` | https://github.com/twelvedata/twelvedata-python | market_data | intelligence, research, preopen | Env: `TWELVE_DATA_API_KEY` |
| `massive` | https://github.com/massive-com/client-python (Polygon lineage) | market_data | intelligence, research, intraday | Env: `MASSIVE_API_KEY` or `POLYGON_API_KEY` |
| `tradier` | https://documentation.tradier.com/ | market_data, options, brokerage | research, preopen, intraday, performance | Env: `TRADIER_ACCESS_TOKEN`, `TRADIER_ACCOUNT_ID` |
| `alpaca` | https://github.com/alpacahq/alpaca-py | brokerage, market_data | preopen, intraday, performance | Env: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` |
| `finnhub` | https://github.com/Finnhub-Stock-API/finnhub-python | market_data, news | intelligence, research | Env: `FINNHUB_API_KEY` |
| `marketstack` | https://marketstack.com/documentation | market_data | intelligence, research | Env: `MARKETSTACK_API_KEY` |
| `tiingo` | https://www.tiingo.com/documentation | market_data, news | intelligence, research | Env: `TIINGO_API_KEY` |

Also used by the desk (pre-existing, not in OBJECTIVE list):

| Source id | Role | Phases |
|-----------|------|--------|
| `fmp` | calendar, news | intelligence, research | Env: `FMP_API_KEY` |

## Phase fit summary

### intelligence
Multi-source macro/quotes/news: **yfinance** (default), **Tiingo**, **Twelve Data**, **Finnhub** news, **Marketstack**, **Nasdaq Data Link**, **pandas-datareader**, **Alpha Vantage**, **Massive**.

### research
OHLCV / options liquidity: **yfinance**, **Tradier** options (when configured), **Twelve Data**, **Alpha Vantage**, **Finnhub**.

### cio_approval / cio_review
Consume research outputs only — **no raw vendor required**.

### preopen / intraday
Live quotes / positions: **Alpaca**, **Tradier**, **IBKR TWS** (optional), **yfinance** fallback.

### performance
Historical fills/prices: brokerage history (**Alpaca**, **Tradier**, **IBKR**) or **yfinance** / **pandas-datareader**.

## Integration rules

1. **Never** silent fixture-fill on live paths when a key is missing → `source=unavailable`.
2. **yfinance** remains offline-friendly default for market quotes when live is enabled without paid keys.
3. Brokerage clients are **optional**; unconfigured sessions must not crash.
4. Provider selection order is env-configurable (`TRADING_AGENT_QUOTE_PROVIDERS`, `TRADING_AGENT_NEWS_PROVIDERS`).
