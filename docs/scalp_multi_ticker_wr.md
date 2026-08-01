# QQQ-style scalp multi-ticker backtest (60d)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)

## Aggregate
- **Trades:** 782
- **Win rate:** 34.9% (273W / 509L)
- **Total P/L:** $-40,198.13 (synthetic $1 premium)
- **Expectancy:** $-51.40 / trade
- **Symbols:** QQQ, SPY, IWM, AAPL, AMZN, MSFT, NVDA, META, TSLA

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| IWM | 99 | 51% | 50/49 | $-1.39 | $-137.30 |
| SPY | 78 | 50% | 39/39 | $-4.30 | $-335.38 |
| QQQ | 102 | 40% | 41/61 | $-20.59 | $-2100.20 |
| MSFT | 79 | 32% | 25/54 | $-39.66 | $-3133.06 |
| AAPL | 89 | 31% | 28/61 | $-54.85 | $-4881.68 |
| AMZN | 70 | 30% | 21/49 | $-33.13 | $-2318.77 |
| NVDA | 91 | 30% | 27/64 | $-31.73 | $-2887.17 |
| TSLA | 91 | 24% | 22/69 | $-148.38 | $-13502.64 |
| META | 83 | 24% | 20/63 | $-131.35 | $-10901.93 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 448 | 40% | $-8709.11 |
| bear_breakdown | 223 | 15% | $-31504.49 |
| pullback_long | 111 | 54% | $+15.47 |

## Sample trades (first 25)

- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=+23.9% ($+23.85)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=-87.3% ($-87.32)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ bear_breakdown PUT premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-14 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-14 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-15 QQQ bear_breakdown PUT underlying_stop pnl=-30.0% ($-30.00)
- 2026-05-15 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-18 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-18 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-19 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-19 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-20 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-20 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-22 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-22 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-26 QQQ bull_breakout CALL underlying_target pnl=-30.6% ($-30.60)
- 2026-05-26 QQQ bull_breakout CALL underlying_target pnl=-133.2% ($-133.24)
- 2026-05-28 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
