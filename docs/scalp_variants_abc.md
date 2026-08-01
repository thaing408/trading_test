# Scalp rule variants — comparison

Baseline vs (a) no bear_breakdown, (b) ETFs only, (c) last ~10 sessions (2 weeks).

| Run | Trades | WR | Expectancy | Total P/L |
|-----|--------|-----|------------|-----------|
| A_no_bear_all_tickers_60d | 585 | 43.9% | $-14.77 | $-8638.69 |
| B_etfs_only_60d | 279 | 46.6% | $-9.22 | $-2572.88 |
| C_last_2w_all_tickers | 134 | 29.1% | $-102.71 | $-13763.77 |
| D_no_bear_etfs_60d | 264 | 50.4% | $-6.29 | $-1659.97 |
| E_no_bear_etfs_last_2w | 46 | 52.2% | $-1.22 | $-56.30 |
| F_baseline_all_60d | 782 | 34.9% | $-51.40 | $-40198.13 |

## Interpretation

- **(a) no bear:** removes the worst setup from the prior run; WR and expectancy should improve if bear was the bleed.
- **(b) ETFs only:** QQQ/SPY/IWM only — historically higher WR than single names.
- **(c) last 2 weeks:** short sample; use for recent regime check, not promotion alone.
- **(d/e) combos:** best practical filters stacked.

# Scalp variants comparison (a/b/c + combos)


---

## A_no_bear_all_tickers_60d


# QQQ-style scalp multi-ticker backtest (60d_no_bear)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)
- bear_breakdown entries DISABLED

## Aggregate
- **Trades:** 585
- **Win rate:** 43.9% (257W / 328L)
- **Total P/L:** $-8,638.69 (synthetic $1 premium)
- **Expectancy:** $-14.77 / trade
- **Symbols:** QQQ, SPY, IWM, AAPL, AMZN, MSFT, NVDA, META, TSLA

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| IWM | 93 | 56% | 52/41 | $+0.30 | $+28.35 |
| SPY | 78 | 51% | 40/38 | $-3.87 | $-301.82 |
| NVDA | 55 | 47% | 26/29 | $-9.29 | $-510.82 |
| QQQ | 93 | 44% | 41/52 | $-14.91 | $-1386.50 |
| MSFT | 49 | 43% | 21/28 | $-26.40 | $-1293.61 |
| TSLA | 48 | 40% | 19/29 | $-32.86 | $-1577.34 |
| AMZN | 44 | 39% | 17/27 | $-13.20 | $-580.68 |
| AAPL | 70 | 39% | 27/43 | $-13.29 | $-930.03 |
| META | 55 | 25% | 14/41 | $-37.93 | $-2086.24 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 450 | 40% | $-8835.86 |
| pullback_long | 135 | 57% | $+197.17 |

## Sample trades (first 25)

- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=+23.9% ($+23.85)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=-87.3% ($-87.32)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-14 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-14 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-15 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
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


---

## B_etfs_only_60d


# QQQ-style scalp multi-ticker backtest (60d_etf)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)
- Universe: ETFs only (QQQ, SPY, IWM)

## Aggregate
- **Trades:** 279
- **Win rate:** 46.6% (130W / 149L)
- **Total P/L:** $-2,572.88 (synthetic $1 premium)
- **Expectancy:** $-9.22 / trade
- **Symbols:** QQQ, SPY, IWM

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| IWM | 99 | 51% | 50/49 | $-1.39 | $-137.30 |
| SPY | 78 | 50% | 39/39 | $-4.30 | $-335.38 |
| QQQ | 102 | 40% | 41/61 | $-20.59 | $-2100.20 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 186 | 48% | $-1781.00 |
| pullback_long | 63 | 52% | $-35.37 |
| bear_breakdown | 30 | 27% | $-756.51 |

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


---

## C_last_2w_all_tickers


# QQQ-style scalp multi-ticker backtest (60d_last10sess)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)
- Only last 10 RTH sessions scored

## Aggregate
- **Trades:** 134
- **Win rate:** 29.1% (39W / 95L)
- **Total P/L:** $-13,763.77 (synthetic $1 premium)
- **Expectancy:** $-102.71 / trade
- **Symbols:** QQQ, SPY, IWM, AAPL, AMZN, MSFT, NVDA, META, TSLA

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| SPY | 17 | 53% | 9/8 | $-0.27 | $-4.61 |
| MSFT | 14 | 43% | 6/8 | $-18.12 | $-253.71 |
| IWM | 15 | 40% | 6/9 | $-2.31 | $-34.65 |
| AMZN | 8 | 38% | 3/5 | $-54.40 | $-435.18 |
| QQQ | 16 | 31% | 5/11 | $-13.93 | $-222.90 |
| AAPL | 17 | 24% | 4/13 | $-149.76 | $-2546.00 |
| TSLA | 15 | 20% | 3/12 | $-276.24 | $-4143.59 |
| NVDA | 17 | 18% | 3/14 | $-45.66 | $-776.24 |
| META | 15 | 0% | 0/15 | $-356.46 | $-5346.89 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 69 | 35% | $-1277.47 |
| bear_breakdown | 45 | 9% | $-12490.90 |
| pullback_long | 20 | 55% | $+4.60 |

## Sample trades (first 25)

- 2026-07-20 QQQ bull_breakout CALL underlying_target pnl=-82.8% ($-82.80)
- 2026-07-20 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-21 QQQ bull_breakout CALL underlying_target pnl=-16.6% ($-16.65)
- 2026-07-21 QQQ bull_breakout CALL underlying_target pnl=-1.4% ($-1.35)
- 2026-07-23 QQQ bear_breakdown PUT underlying_stop pnl=-10.3% ($-10.35)
- 2026-07-23 QQQ bear_breakdown PUT premium_target pnl=+25.0% ($+25.00)
- 2026-07-24 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-24 QQQ pullback_long CALL time_exit pnl=+9.9% ($+9.90)
- 2026-07-27 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-27 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-28 QQQ bear_breakdown PUT underlying_stop pnl=-21.6% ($-21.60)
- 2026-07-28 QQQ bear_breakdown PUT underlying_target pnl=+5.0% ($+4.95)
- 2026-07-29 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-29 QQQ bear_breakdown PUT underlying_stop pnl=-30.0% ($-30.00)
- 2026-07-31 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-31 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-20 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-20 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-21 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-21 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-23 SPY pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-23 SPY bear_breakdown PUT underlying_stop pnl=-8.6% ($-8.56)
- 2026-07-24 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-24 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-27 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)


---

## D_no_bear_etfs_60d


# QQQ-style scalp multi-ticker backtest (60d_no_bear_etf)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)
- bear_breakdown entries DISABLED
- Universe: ETFs only (QQQ, SPY, IWM)

## Aggregate
- **Trades:** 264
- **Win rate:** 50.4% (133W / 131L)
- **Total P/L:** $-1,659.97 (synthetic $1 premium)
- **Expectancy:** $-6.29 / trade
- **Symbols:** QQQ, SPY, IWM

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| IWM | 93 | 56% | 52/41 | $+0.30 | $+28.35 |
| SPY | 78 | 51% | 40/38 | $-3.87 | $-301.82 |
| QQQ | 93 | 44% | 41/52 | $-14.91 | $-1386.50 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 186 | 48% | $-1781.00 |
| pullback_long | 78 | 56% | $+121.03 |

## Sample trades (first 25)

- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-07 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=+23.9% ($+23.85)
- 2026-05-08 QQQ bull_breakout CALL underlying_target pnl=-87.3% ($-87.32)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-11 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-12 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-13 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-14 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-05-14 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-05-15 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
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


---

## E_no_bear_etfs_last_2w


# QQQ-style scalp multi-ticker backtest (60d_last10sess_no_bear_etf)

## Assumptions
- Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins
- Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday
- Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target
- Delta≈0.45 for premium move from underlying; first of stop/target/premium wins
- One open scalp per symbol; daily max_round_trips / max_losing / max_winning
- No live IV richness / VIX filter in offline run (unless vix= passed)
- bear_breakdown entries DISABLED
- Universe: ETFs only (QQQ, SPY, IWM)
- Only last 10 RTH sessions scored

## Aggregate
- **Trades:** 46
- **Win rate:** 52.2% (24W / 22L)
- **Total P/L:** $-56.30 (synthetic $1 premium)
- **Expectancy:** $-1.22 / trade
- **Symbols:** QQQ, SPY, IWM

## Win rate by symbol

| Symbol | Trades | WR | W/L | Expectancy | Total P/L |
|--------|--------|-----|-----|------------|-----------|
| SPY | 17 | 59% | 10/7 | $+1.70 | $+28.95 |
| IWM | 15 | 53% | 8/7 | $+2.04 | $+30.65 |
| QQQ | 14 | 43% | 6/8 | $-8.28 | $-115.90 |

## By setup (all symbols)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| bull_breakout | 28 | 43% | $-175.90 |
| pullback_long | 18 | 67% | $+119.60 |

## Sample trades (first 25)

- 2026-07-20 QQQ bull_breakout CALL underlying_target pnl=-82.8% ($-82.80)
- 2026-07-20 QQQ bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-21 QQQ bull_breakout CALL underlying_target pnl=-16.6% ($-16.65)
- 2026-07-21 QQQ bull_breakout CALL underlying_target pnl=-1.4% ($-1.35)
- 2026-07-24 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-24 QQQ pullback_long CALL time_exit pnl=+9.9% ($+9.90)
- 2026-07-27 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-27 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-28 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-28 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-29 QQQ pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-29 QQQ pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-31 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-31 QQQ bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-20 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-20 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-21 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-21 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-23 SPY pullback_long CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-23 SPY pullback_long CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-24 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-24 SPY bull_breakout CALL premium_target pnl=+25.0% ($+25.00)
- 2026-07-27 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-28 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)
- 2026-07-28 SPY bull_breakout CALL premium_stop pnl=-30.0% ($-30.00)


---

## F_baseline_all_60d


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
