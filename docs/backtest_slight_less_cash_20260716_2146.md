# Slight-less-cash vs shipped A-tier (offline multi-regime)

Knobs: shipped conf60 / B-q70 / CIO65 vs slight conf55 / B-q65 / CIO55; both prefer_a_tier_only + full gates.

| config | n | WR% | exp $/t | P/L | PF | max DD | score |
|--------|--:|----:|--------:|----:|---:|-------:|------:|
| shipped_a_tier_full_discipline | 0 | 0.0 | 0.00 | 0.00 | 0.00 | 0.00 | -8.00 |
| slight_less_cash_a_tier | 0 | 0.0 | 0.00 | 0.00 | 0.00 | 0.00 | -8.00 |
| baseline_grade_C_book3 | 73 | 38.4 | -268.16 | -19575.93 | 0.40 | 26091.74 | -645.82 |

---
# Backtest Period — shipped_a_tier_full_discipline

## Assumptions
- Fill model: entry at decision close; stop/target or time exit over hold_bars
- Options P/L via underlying path scaled to risk budget × GRADE_TRADE_GEOMETRY size
- Multi-regime synthetic OHLCV (bull/chop/bear/recovery) — deterministic, offline
- News/calendar thinned; research risk+ranking+CIO is the measured core
- Neutral strategies lose on range breaks; directional hit stops in counter-trend

## Config
- min_confidence_score: 60.0
- min_setup_grade: B
- prefer_a_tier_only: True
- min_technical_score: 45.0
- cio_min_confidence: 65.0
- hold_bars: 5
- max_trades_per_day: 3

## Period metrics
- **Total P/L:** $+0.00
- **Expectancy:** $+0.00 / trade
- **Win rate:** 0.0% (0W / 0L)
- **Trade count:** 0
- **Profit factor:** 0.00
- **Max drawdown:** $0.00
- **Avg cash %:** 100.0%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -8.00

## Sample trades
- _No trades generated under this config._


---
# Backtest Period — slight_less_cash_a_tier

## Assumptions
- Fill model: entry at decision close; stop/target or time exit over hold_bars
- Options P/L via underlying path scaled to risk budget × GRADE_TRADE_GEOMETRY size
- Multi-regime synthetic OHLCV (bull/chop/bear/recovery) — deterministic, offline
- News/calendar thinned; research risk+ranking+CIO is the measured core
- Neutral strategies lose on range breaks; directional hit stops in counter-trend

## Config
- min_confidence_score: 55.0
- min_setup_grade: B
- prefer_a_tier_only: True
- min_technical_score: 45.0
- cio_min_confidence: 55.0
- hold_bars: 5
- max_trades_per_day: 3

## Period metrics
- **Total P/L:** $+0.00
- **Expectancy:** $+0.00 / trade
- **Win rate:** 0.0% (0W / 0L)
- **Trade count:** 0
- **Profit factor:** 0.00
- **Max drawdown:** $0.00
- **Avg cash %:** 100.0%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -8.00

## Sample trades
- _No trades generated under this config._


---
# Backtest Period — baseline_grade_C_book3

## Assumptions
- Fill model: entry at decision close; stop/target or time exit over hold_bars
- Options P/L via underlying path scaled to risk budget × GRADE_TRADE_GEOMETRY size
- Multi-regime synthetic OHLCV (bull/chop/bear/recovery) — deterministic, offline
- News/calendar thinned; research risk+ranking+CIO is the measured core
- Neutral strategies lose on range breaks; directional hit stops in counter-trend

## Config
- min_confidence_score: 55.0
- min_setup_grade: C
- prefer_a_tier_only: False
- min_technical_score: 40.0
- cio_min_confidence: 60.0
- hold_bars: 5
- max_trades_per_day: 3

## Period metrics
- **Total P/L:** $-19,575.93
- **Expectancy:** $-268.16 / trade
- **Win rate:** 38.4% (28W / 45L)
- **Trade count:** 73
- **Profit factor:** 0.40
- **Max drawdown:** $26,091.74
- **Avg cash %:** 93.4%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -645.82

## Sample trades
- NVDA Iron Condor [B] entry=80.01 exit=65.10 (range_break) P/L=$-750.00
- META Iron Condor [B] entry=289.31 exit=241.78 (range_break) P/L=$-750.00
- AMD Iron Condor [B] entry=96.48 exit=82.07 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.57 exit=67.11 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.29 exit=163.98 (range_break) P/L=$-750.00
- AAPL Iron Condor [B] entry=225.06 exit=197.61 (range_break) P/L=$-750.00
- AAPL Iron Condor [B] entry=227.68 exit=197.68 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=81.38 exit=66.87 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.95 exit=66.86 (range_break) P/L=$-750.00
- MSFT Iron Condor [B] entry=224.02 exit=197.27 (range_break) P/L=$-750.00

