# ORB + VWAP sleeve (60d)

## Assumptions
- 15m bars via yfinance; OR = first 30m (2 bars) 9:30–10:00 ET
- Long: close > OR high and close > session VWAP; short inverse
- Stop: OR midpoint; target: 1.5R; one trade per symbol per day
- Equity-style P/L in $ per share × 100 shares (not options premium)
- RTH only; no news filter

**Trades:** 173  **WR:** 45.1%  **Exp:** $-14.15  **Total:** $-2447.37  **Avg R:** +0.05

| Symbol | n | WR | Exp | P/L | Avg R |
|--------|---|-----|-----|-----|-------|
| QQQ | 58 | 45% | $-49.36 | $-2863.10 | -0.04 |
| SPY | 58 | 52% | $+20.18 | $+1170.27 | +0.27 |
| IWM | 57 | 39% | $-13.24 | $-754.54 | -0.07 |

# Cross-sectional momentum / RS sleeve

## Assumptions
- Daily bars (yfinance or Schwab via historical loader)
- Signal: 60d return excluding most recent 5d; rebalance weekly (every 5 bars)
- Hold top 3 of universe; equal weight; 100 shares notional unit per name for $ P/L
- Exit: leave top half of ranks OR close < entry - 2*ATR14
- No costs in base; optional 5 bps round-trip applied in report

**Trades:** 31  **WR:** 25.8%  **Exp:** $-241.36  **Total:** $-7482.13
**SPY buy-hold (100 sh):** $+7606.00  **Beat SPY:** False
Meta: {'period': '1y', 'top_k': 3, 'n_bars': 252, 'slip_bps': 5.0}


# Premium path × market regime ablation

Period: 1y
Full: n=345 WR=19.4% exp=$-418.29 PnL=$-144310.56

## By regime
| Regime | n | WR | Exp | P/L |
|--------|---|-----|-----|-----|
| trend_up | 105 | 31% | $-126.41 | $-13273.06 |
| trend_down | 3 | 0% | $-751.75 | $-2255.25 |
| chop | 237 | 14% | $-543.39 | $-128782.25 |

**Chop-only:** {'n': 237.0, 'wr': 0.14345991561181434, 'pnl': -128782.25, 'exp': -543.39}
**Trend-only:** {'n': 108.0, 'wr': 0.3055555555555556, 'pnl': -15528.31, 'exp': -143.78}

**Suggestion:** Regime split inconclusive on this sample

