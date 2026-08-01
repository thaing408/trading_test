# Backtest config comparison

**Objective:** maximize expectancy+PF+win_rate+P/L − drawdown − churn (capital preservation)
**Best config:** **strict_a_tier_book3**

## Ranking
1. **strict_a_tier_book3** — score -8.00 | P/L $+0.00 | exp $+0.00 | WR 0% | n=0 | DD $0.00 | cash 100%
2. **shipped_a_tier_full_discipline** — score -8.00 | P/L $+0.00 | exp $+0.00 | WR 0% | n=0 | DD $0.00 | cash 100%
3. **baseline_C_book3_gates_off** — score -58.65 | P/L $-169.87 | exp $-2.43 | WR 57% | n=70 | DD $20,071.03 | cash 94%
4. **gates_off_discovery_x3** — score -406.14 | P/L $-11,519.87 | exp $-137.14 | WR 48% | n=84 | DD $31,421.03 | cash 92%
5. **high_confidence_book3** — score -522.46 | P/L $-14,915.59 | exp $-216.17 | WR 43% | n=69 | DD $23,091.74 | cash 94%
6. **baseline_grade_C_book3** — score -645.82 | P/L $-19,575.93 | exp $-268.16 | WR 38% | n=73 | DD $26,091.74 | cash 93%
7. **wide_book5_grade_C** — score -645.82 | P/L $-19,575.93 | exp $-268.16 | WR 38% | n=73 | DD $26,091.74 | cash 93%
8. **gates_on_discovery_x3** — score -910.42 | P/L $-32,325.93 | exp $-359.18 | WR 31% | n=90 | DD $38,841.74 | cash 92%

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

---
# Backtest Period — wide_book5_grade_C

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
- max_trades_per_day: 5

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

---
# Backtest Period — strict_a_tier_book3

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
# Backtest Period — high_confidence_book3

## Assumptions
- Fill model: entry at decision close; stop/target or time exit over hold_bars
- Options P/L via underlying path scaled to risk budget × GRADE_TRADE_GEOMETRY size
- Multi-regime synthetic OHLCV (bull/chop/bear/recovery) — deterministic, offline
- News/calendar thinned; research risk+ranking+CIO is the measured core
- Neutral strategies lose on range breaks; directional hit stops in counter-trend

## Config
- min_confidence_score: 70.0
- min_setup_grade: B
- prefer_a_tier_only: False
- min_technical_score: 50.0
- cio_min_confidence: 70.0
- hold_bars: 5
- max_trades_per_day: 3

## Period metrics
- **Total P/L:** $-14,915.59
- **Expectancy:** $-216.17 / trade
- **Win rate:** 43.5% (30W / 39L)
- **Trade count:** 69
- **Profit factor:** 0.47
- **Max drawdown:** $23,091.74
- **Avg cash %:** 93.7%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -522.46

## Sample trades
- NVDA Iron Condor [B] entry=80.01 exit=65.10 (range_break) P/L=$-750.00
- META Iron Condor [B] entry=289.31 exit=241.78 (range_break) P/L=$-750.00
- AMD Iron Condor [B] entry=96.48 exit=82.07 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.57 exit=67.11 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.29 exit=163.98 (range_break) P/L=$-750.00
- AAPL Iron Condor [B] entry=225.06 exit=197.61 (range_break) P/L=$-750.00
- TSLA Iron Condor [B] entry=155.77 exit=130.52 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=81.38 exit=66.87 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.95 exit=66.86 (range_break) P/L=$-750.00
- AAPL Iron Condor [B] entry=222.66 exit=194.29 (range_break) P/L=$-750.00

---
# Backtest Period — baseline_C_book3_gates_off

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
- **Total P/L:** $-169.87
- **Expectancy:** $-2.43 / trade
- **Win rate:** 57.1% (40W / 30L)
- **Trade count:** 70
- **Profit factor:** 0.99
- **Max drawdown:** $20,071.03
- **Avg cash %:** 93.6%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -58.65

## Sample trades
- AMD Iron Condor [A+] entry=96.48 exit=79.48 (range_break) P/L=$-1100.00
- NVDA Iron Condor [B] entry=80.01 exit=65.10 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- AAPL Iron Condor [A] entry=225.06 exit=192.69 (range_break) P/L=$-1000.00
- MSFT Iron Condor [A] entry=225.90 exit=192.18 (range_break) P/L=$-1000.00
- NVDA Iron Condor [B] entry=81.38 exit=66.87 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.95 exit=66.86 (range_break) P/L=$-750.00
- MSFT Iron Condor [B] entry=224.02 exit=197.27 (range_break) P/L=$-750.00
- MSFT Iron Condor [A] entry=225.20 exit=192.29 (range_break) P/L=$-1000.00
- TSLA Iron Condor [A] entry=155.50 exit=128.84 (range_break) P/L=$-1000.00
- AAPL Iron Condor [B] entry=219.71 exit=198.99 (range_break) P/L=$-750.00

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
# Backtest Period — gates_on_discovery_x3

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
- **Total P/L:** $-32,325.93
- **Expectancy:** $-359.18 / trade
- **Win rate:** 31.1% (28W / 62L)
- **Trade count:** 90
- **Profit factor:** 0.28
- **Max drawdown:** $38,841.74
- **Avg cash %:** 91.8%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -910.42

## Sample trades
- NVDA Iron Condor [B] entry=80.01 exit=65.10 (range_break) P/L=$-750.00
- META Iron Condor [B] entry=289.31 exit=241.78 (range_break) P/L=$-750.00
- AMD Iron Condor [B] entry=96.48 exit=82.07 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.57 exit=67.11 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.57 exit=67.11 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.57 exit=67.11 (range_break) P/L=$-750.00

---
# Backtest Period — gates_off_discovery_x3

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
- **Total P/L:** $-11,519.87
- **Expectancy:** $-137.14 / trade
- **Win rate:** 47.6% (40W / 44L)
- **Trade count:** 84
- **Profit factor:** 0.67
- **Max drawdown:** $31,421.03
- **Avg cash %:** 92.4%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** -406.14

## Sample trades
- AMD Iron Condor [A+] entry=96.48 exit=79.48 (range_break) P/L=$-1100.00
- NVDA Iron Condor [B] entry=80.01 exit=65.10 (range_break) P/L=$-750.00
- AMD Iron Condor [A+] entry=96.48 exit=79.48 (range_break) P/L=$-1100.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=164.64 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=65.23 (range_break) P/L=$-750.00
- AAPL Iron Condor [A] entry=225.06 exit=192.69 (range_break) P/L=$-1000.00
- MSFT Iron Condor [A] entry=225.90 exit=192.18 (range_break) P/L=$-1000.00
- AAPL Iron Condor [A] entry=225.06 exit=192.69 (range_break) P/L=$-1000.00

---
