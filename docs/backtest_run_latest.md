# Backtest config comparison

**Objective:** maximize expectancy+PF+win_rate+P/L − drawdown − churn (capital preservation)
**Best config:** **baseline_grade_C_book3**

## Ranking
1. **baseline_grade_C_book3** — score 940.37 | P/L $+15,737.04 | exp $+414.13 | WR 84% | n=38 | DD $0.00 | cash 96%
2. **wide_book5_grade_C** — score 940.37 | P/L $+15,737.04 | exp $+414.13 | WR 84% | n=38 | DD $0.00 | cash 96%
3. **high_confidence_book3** — score 940.37 | P/L $+15,737.04 | exp $+414.13 | WR 84% | n=38 | DD $0.00 | cash 96%
4. **baseline_C_book3_gates_off** — score 119.98 | P/L $+5,741.18 | exp $+82.02 | WR 57% | n=70 | DD $19,866.75 | cash 94%
5. **strict_a_tier_book3** — score -8.00 | P/L $+0.00 | exp $+0.00 | WR 0% | n=0 | DD $0.00 | cash 100%
6. **shipped_a_tier_full_discipline** — score -8.00 | P/L $+0.00 | exp $+0.00 | WR 0% | n=0 | DD $0.00 | cash 100%

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
- **Total P/L:** $+15,737.04
- **Expectancy:** $+414.13 / trade
- **Win rate:** 84.2% (32W / 6L)
- **Trade count:** 38
- **Profit factor:** 5.86
- **Max drawdown:** $0.00
- **Avg cash %:** 96.5%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** 940.37

## Sample trades
- AMD Covered Call [B] entry=96.49 exit=97.44 (time_exit) P/L=$+194.47
- AMD Covered Call [B] entry=96.12 exit=98.49 (time_exit) P/L=$+495.56
- AMD Covered Call [B] entry=97.38 exit=98.69 (time_exit) P/L=$+328.35
- TSLA Covered Call [B] entry=139.43 exit=142.16 (time_exit) P/L=$+431.12
- AMD Covered Call [B] entry=97.08 exit=99.82 (time_exit) P/L=$+709.76
- TSLA Covered Call [B] entry=141.57 exit=143.46 (time_exit) P/L=$+297.41
- AMD Covered Call [B] entry=97.44 exit=99.65 (time_exit) P/L=$+598.46
- JPM Covered Call [B] entry=193.94 exit=201.11 (profit_target) P/L=$+1250.58
- JPM Covered Call [B] entry=194.84 exit=201.79 (profit_target) P/L=$+1250.00
- AMD Covered Call [B] entry=98.49 exit=100.17 (time_exit) P/L=$+456.39
- TSLA Covered Call [B] entry=141.66 exit=142.68 (time_exit) P/L=$+170.29
- JPM Covered Call [B] entry=196.86 exit=192.72 (stop_loss) P/L=$-750.00

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
- **Total P/L:** $+15,737.04
- **Expectancy:** $+414.13 / trade
- **Win rate:** 84.2% (32W / 6L)
- **Trade count:** 38
- **Profit factor:** 5.86
- **Max drawdown:** $0.00
- **Avg cash %:** 96.5%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** 940.37

## Sample trades
- AMD Covered Call [B] entry=96.49 exit=97.44 (time_exit) P/L=$+194.47
- AMD Covered Call [B] entry=96.12 exit=98.49 (time_exit) P/L=$+495.56
- AMD Covered Call [B] entry=97.38 exit=98.69 (time_exit) P/L=$+328.35
- TSLA Covered Call [B] entry=139.43 exit=142.16 (time_exit) P/L=$+431.12
- AMD Covered Call [B] entry=97.08 exit=99.82 (time_exit) P/L=$+709.76
- TSLA Covered Call [B] entry=141.57 exit=143.46 (time_exit) P/L=$+297.41
- AMD Covered Call [B] entry=97.44 exit=99.65 (time_exit) P/L=$+598.46
- JPM Covered Call [B] entry=193.94 exit=201.11 (profit_target) P/L=$+1250.58
- JPM Covered Call [B] entry=194.84 exit=201.79 (profit_target) P/L=$+1250.00
- AMD Covered Call [B] entry=98.49 exit=100.17 (time_exit) P/L=$+456.39
- TSLA Covered Call [B] entry=141.66 exit=142.68 (time_exit) P/L=$+170.29
- JPM Covered Call [B] entry=196.86 exit=192.72 (stop_loss) P/L=$-750.00

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
- **Total P/L:** $+15,737.04
- **Expectancy:** $+414.13 / trade
- **Win rate:** 84.2% (32W / 6L)
- **Trade count:** 38
- **Profit factor:** 5.86
- **Max drawdown:** $0.00
- **Avg cash %:** 96.5%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** 940.37

## Sample trades
- AMD Covered Call [B] entry=96.49 exit=97.44 (time_exit) P/L=$+194.47
- AMD Covered Call [B] entry=96.12 exit=98.49 (time_exit) P/L=$+495.56
- AMD Covered Call [B] entry=97.38 exit=98.69 (time_exit) P/L=$+328.35
- TSLA Covered Call [B] entry=139.43 exit=142.16 (time_exit) P/L=$+431.12
- AMD Covered Call [B] entry=97.08 exit=99.82 (time_exit) P/L=$+709.76
- TSLA Covered Call [B] entry=141.57 exit=143.46 (time_exit) P/L=$+297.41
- AMD Covered Call [B] entry=97.44 exit=99.65 (time_exit) P/L=$+598.46
- JPM Covered Call [B] entry=193.94 exit=201.11 (profit_target) P/L=$+1250.58
- JPM Covered Call [B] entry=194.84 exit=201.79 (profit_target) P/L=$+1250.00
- AMD Covered Call [B] entry=98.49 exit=100.17 (time_exit) P/L=$+456.39
- TSLA Covered Call [B] entry=141.66 exit=142.68 (time_exit) P/L=$+170.29
- JPM Covered Call [B] entry=196.86 exit=192.72 (stop_loss) P/L=$-750.00

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
- **Total P/L:** $+5,741.18
- **Expectancy:** $+82.02 / trade
- **Win rate:** 57.1% (40W / 30L)
- **Trade count:** 70
- **Profit factor:** 1.24
- **Max drawdown:** $19,866.75
- **Avg cash %:** 93.6%
- **Days simulated:** 55
- **Symbols:** NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM
- **Score:** 119.98

## Sample trades
- AMD Iron Condor [A+] entry=96.48 exit=86.74 (range_break) P/L=$-1100.00
- NVDA Iron Condor [B] entry=80.01 exit=75.52 (range_break) P/L=$-750.00
- AMZN Iron Condor [B] entry=183.49 exit=173.67 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=79.62 exit=75.11 (range_break) P/L=$-750.00
- AAPL Iron Condor [A] entry=225.06 exit=212.50 (range_break) P/L=$-1000.00
- MSFT Iron Condor [A] entry=225.90 exit=211.45 (range_break) P/L=$-1000.00
- NVDA Iron Condor [B] entry=81.38 exit=76.79 (range_break) P/L=$-750.00
- NVDA Iron Condor [B] entry=80.95 exit=76.31 (range_break) P/L=$-750.00
- MSFT Iron Condor [B] entry=224.02 exit=213.14 (range_break) P/L=$-750.00
- MSFT Iron Condor [A] entry=225.20 exit=210.82 (range_break) P/L=$-1000.00
- TSLA Iron Condor [A] entry=155.50 exit=142.68 (range_break) P/L=$-1000.00
- AAPL Iron Condor [B] entry=219.71 exit=208.64 (range_break) P/L=$-750.00

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
