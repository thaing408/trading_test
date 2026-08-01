# Backtest run 2026-08-01 19:06 UTC

Suite: desk historical (costs) + walk-forward + ORB/VWAP + momentum + regime + scalp ETFs.

**Data:** 11 symbols, 252 bars, sources=['schwab']

## Desk path (baseline + costs)

| Config | n | WR | Exp | PnL | DD | Score |
|--------|---|-----|-----|-----|-----|-------|
| gates_ON_0cost | 347 | 20.8% | $-393.46 | $-136532.09 | $138,310 | -1522.0 |
| gates_ON_costs | 347 | 20.8% | $-395.21 | $-137139.09 | $138,890 | -1528.4 |
| gates_OFF_costs | 309 | 28.2% | $-295.97 | $-91454.45 | $98,182 | -1111.1 |

## Desk last ~2 weeks (lookback+10)

| Config | n | WR | Exp | PnL | Score |
|--------|---|-----|-----|-----|-------|
| gates_ON_0cost | 15 | 13.3% | $-511.12 | $-7666.81 | -1050.9 |
| gates_ON_costs | 15 | 13.3% | $-512.87 | $-7693.06 | -1054.6 |

## Walk-forward (train60/test10)

# Walk-forward — wf_costs
Bars: 252  Source: schwab
Symbols: SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD, META, AMZN, TSLA, JPM

## OOS aggregate
- **folds:** 14
- **folds_with_trades:** 14
- **oos_total_pnl:** -59237.88
- **oos_mean_expectancy:** -286.55
- **oos_mean_win_rate:** 0.2691
- **oos_total_trades:** 207
- **oos_mean_score:** -568.66

## Folds
- fold 0 bars[103:113] n=15 exp=$-620.23 WR=7% P/L=$-9303.42 DD=$9,303 score=-1279.7
- fold 1 bars[113:123] n=15 exp=$-86.56 WR=33% P/L=$-1298.35 DD=$2,486 score=-161.1
- fold 2 bars[123:133] n=15 exp=$-673.15 WR=7% P/L=$-10097.28 DD=$10,097 score=-1389.6
- fold 3 bars[133:143] n=15 exp=$-679.25 WR=7% P/L=$-10188.75 DD=$10,189 score=-1402.4
- fold 4 bars[143:153] n=15 exp=$-751.75 WR=0% P/L=$-11276.25 DD=$11,276 score=-1554.9
- fold 5 bars[153:163] n=15 exp=$-751.75 WR=0% P/L=$-11276.25 DD=$11,276 score=-1554.9
- fold 6 bars[163:173] n=15 exp=$-751.75 WR=0% P/L=$-11276.25 DD=$11,276 score=-1554.9
- fold 7 bars[173:183] n=15 exp=$+879.20 WR=93% P/L=$+13187.95 DD=$0 score=2022.4
- fold 8 bars[183:193] n=15 exp=$+497.47 WR=67% P/L=$+7462.01 DD=$1,004 score=1055.9
- fold 9 bars[193:203] n=15 exp=$+143.36 WR=53% P/L=$+2150.38 DD=$1,722 score=319.5
- fold 10 bars[203:213] n=15 exp=$-229.08 WR=33% P/L=$-3436.24 DD=$3,436 score=-456.5
- fold 11 bars[213:223] n=12 exp=$-312.66 WR=17% P/L=$-3751.96 DD=$4,510 score=-631.9
- fold 12 bars[223:233] n=15 exp=$-588.34 WR=13% P/L=$-8825.03 DD=$8,825 score=-1212.4
- fold 13 bars[233:243] n=15 exp=$-87.23 WR=47% P/L=$-1308.44 DD=$2,706 score=-160.8


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
Full: n=347 WR=20.8% exp=$-395.21 PnL=$-137139.09

## By regime
| Regime | n | WR | Exp | P/L |
|--------|---|-----|-----|-----|
| trend_up | 106 | 35% | $-69.82 | $-7400.95 |
| trend_down | 3 | 0% | $-751.75 | $-2255.25 |
| chop | 238 | 15% | $-535.64 | $-127482.89 |

**Chop-only:** {'n': 238.0, 'wr': 0.14705882352941177, 'pnl': -127482.89, 'exp': -535.64}
**Trend-only:** {'n': 109.0, 'wr': 0.3394495412844037, 'pnl': -9656.2, 'exp': -88.59}

**Suggestion:** Regime split inconclusive on this sample



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


## Quick read

- Desk 1y gates ON costs: see table above
- WF OOS: {'folds': 14, 'folds_with_trades': 14, 'oos_total_pnl': -59237.88, 'oos_mean_expectancy': -286.55, 'oos_mean_win_rate': 0.2691, 'oos_total_trades': 207, 'oos_mean_score': -568.66}
- ORB: n=173 WR=45.1% exp=$-14.15
- Momentum beat SPY: False (PnL $-7482.13 vs SPY $+7606.00)
- Scalp ETFs: n=279 WR=46.6% exp=$-9.22
