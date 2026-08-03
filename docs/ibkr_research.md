# IBKR research-only market data

**Purpose:** Use Interactive Brokers TWS/Gateway as a **read-only** historical OHLCV source for research (backtests, strength gates, technicals). **Live order placement stays on Schwab (Mac).** This path never calls `placeOrder`.

## Prerequisites

1. TWS or IB Gateway running with **Enable ActiveX and Socket Clients**.
2. Prefer **Read-Only API** in TWS API settings (expected Error 321 if something tries to trade).
3. `pip install ib_insync` (optional dependency; desk runs without it).
4. Socket listening — typical ports:
   - TWS live: **7496**, paper: 7497
   - Gateway live: 4001, paper: 4002

## Env

```bash
export IBKR_ENABLED=1
export IBKR_HOST=127.0.0.1
export IBKR_PORT=7496
export IBKR_CLIENT_ID=17
export IBKR_READONLY=1
# Optional: force IBKR only (fail-closed, no yfinance fallback)
# export TRADING_AGENT_MARKET_DATA=ibkr
```

Default `TRADING_AGENT_MARKET_DATA=auto` chain:

1. **IBKR** if `IBKR_ENABLED` and `ib_insync` importable and TWS returns bars  
2. **Schwab** if token available  
3. **yfinance**

## Ping

```bash
IBKR_ENABLED=1 python scripts/ibkr_research_ping.py
IBKR_ENABLED=1 python scripts/ibkr_research_ping.py --via-provider
IBKR_ENABLED=1 TRADING_AGENT_MARKET_DATA=ibkr python -c "
from trading_agent.market_data.provider import get_ohlcv, last_ohlcv_source, reset_ohlcv_cache
reset_ohlcv_cache()
b = get_ohlcv('SPY', period='5d')
print(len(b['close']), last_ohlcv_source('SPY'))
"
```

## Code

| Module | Role |
|--------|------|
| `trading_agent/market_data/ibkr_ohlcv.py` | Connect, paced `reqHistoricalData`, cache, `ping_ibkr` |
| `trading_agent/market_data/provider.py` | `get_ohlcv` preference chain + `last_ohlcv_source` |

## CIO visibility (no IBKR trading)

Research stamps each ranked setup with `market_data_source` (`ibkr` / `schwab` / `yfinance` / `fixture`).  
That flows into `cio_inputs.json` and the **CIO Final Approval** Discord block as:

```text
**Research board (CIO visibility — decide trade/no-trade; not IBKR execution):** N setup(s) | K with bars=`IBKR`
- #1 **SPY** [A] Bullish … | bars=`IBKR`
```

CIO still uses the same approve/modify/reject rules. IBKR only labels **where bars came from** so you can trust the research list. Live place path remains Schwab.

## Notes

- Client IDs must not collide with other API apps on the same TWS.
- IB pacing: module spaces historical requests (~0.35s). Heavy multi-symbol scans may still hit IB limits — fall back to Schwab/yf or slow the loop.
- Intraday bar history depth is subject to IB market-data entitlements.
