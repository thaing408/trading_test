# Backtest: last ~2 weeks (generated 2026-08-01)

**Data mode:** historical (Schwab/yfinance)
**Sources:** ['schwab']
**Symbols:** SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD, META, AMZN, TSLA, JPM
**Bars available:** 64 (3mo request); evaluation window ~lookback+10 bars

## Full 3mo context

| Config | Trades | Expectancy | WR | Total P/L | Max DD | Score |
|--------|--------|------------|-----|-----------|--------|-------|
| A_baseline_gates_ON | 33 | $-514.76 | 15% | $-16987.24 | $16,987 | -1104.5 |
| B_baseline_costs_5bps_c1 | 33 | $-516.51 | 15% | $-17044.99 | $17,045 | -1108.3 |
| C_gates_OFF | 33 | $-576.83 | 21% | $-19035.55 | $19,036 | -1236.1 |
| D_strict_a_tier | 0 | $+0.00 | 0% | $+0.00 | $0 | -8.0 |

## Last ~2 weeks (windowed series)

| Config | Trades | Expectancy | WR | Total P/L | Max DD | Score |
|--------|--------|------------|-----|-----------|--------|-------|
| A_baseline_gates_ON | 15 | $-511.12 | 13% | $-7666.81 | $7,667 | -1050.9 |
| B_baseline_costs_5bps_c1 | 15 | $-512.87 | 13% | $-7693.06 | $7,693 | -1054.6 |
| C_gates_OFF | 15 | $-330.82 | 33% | $-4962.30 | $4,962 | -667.7 |
| D_strict_a_tier | 0 | $+0.00 | 0% | $+0.00 | $0 | -8.0 |

## Walk-forward OOS

# Walk-forward — wf_baseline_costs
Bars: 64  Source: schwab
Symbols: SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD, META, AMZN, TSLA, JPM

## OOS aggregate
- **folds:** 0
- **folds_with_trades:** 0
- **oos_total_pnl:** 0.0
- **oos_mean_expectancy:** 0.0
- **oos_mean_win_rate:** 0.0
- **oos_total_trades:** 0
- **oos_mean_score:** 0.0

## Folds
- _No walk-forward windows (need longer history)._


## ML vs baseline (paper signal only)

# Feature ranker walk-forward (vs classical baseline)
Schema: 1.0.0  horizon=5
Folds: 0  ML beats: 0
**Promote ML (paper only):** False
_Keep classical baseline; ML not promoted_

## Folds
- _No folds (need longer history)._


## Interpretation

- **Costs (B vs A):** applying 5 bps + $1 commission shows whether 'improvement' survives friction.
- **Gates OFF (C):** more trades / often worse DD — quality filters still matter.
- **Strict A (D):** capital preservation path; may print zero trades on short windows.
- **ML promote:** only means OOS IC/dir beat momentum baseline on feature folds — **not** wired to LIVE entries.

---

## Follow-up: 1y history (generated 2026-08-01)

**Bars:** 252  **Source:** ['schwab']

### Full 1y gates ON + costs
- trades=345 exp=$-418.29 WR=19.4% PnL=$-144310.56 DD=$146,062 score=-1610.8

### Walk-forward (1y)
# Walk-forward — wf_costs
Bars: 252  Source: schwab
Symbols: SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD, META, AMZN, TSLA, JPM

## OOS aggregate
- **folds:** 14
- **folds_with_trades:** 0
- **oos_total_pnl:** 0
- **oos_mean_expectancy:** 0.0
- **oos_mean_win_rate:** 0.0
- **oos_total_trades:** 0
- **oos_mean_score:** -8.0

## Folds
- fold 0 bars[103:113] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 1 bars[113:123] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 2 bars[123:133] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 3 bars[133:143] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 4 bars[143:153] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 5 bars[153:163] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 6 bars[163:173] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 7 bars[173:183] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 8 bars[183:193] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 9 bars[193:203] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 10 bars[203:213] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 11 bars[213:223] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 12 bars[223:233] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0
- fold 13 bars[233:243] n=0 exp=$+0.00 WR=0% P/L=$+0.00 DD=$0 score=-8.0

### ML (1y)
# Feature ranker walk-forward (vs classical baseline)
Schema: 1.0.0  horizon=5
Folds: 16  ML beats: 10
**Promote ML (paper only):** True
_ML wins majority of OOS folds — eligible for paper ranking experiment_

## Folds
- fold 0: base_IC=0.1561 ml_IC=-0.1027 base_dir=0.5455 ml_dir=0.3273 n=55 beats=False
- fold 1: base_IC=-0.6723 ml_IC=0.2825 base_dir=0.4364 ml_dir=0.5455 n=55 beats=True
- fold 2: base_IC=-0.4626 ml_IC=0.0057 base_dir=0.4727 ml_dir=0.3818 n=55 beats=True
- fold 3: base_IC=-0.2225 ml_IC=0.2998 base_dir=0.4182 ml_dir=0.6182 n=55 beats=True
- fold 4: base_IC=-0.3509 ml_IC=0.1265 base_dir=0.4182 ml_dir=0.6545 n=55 beats=True
- fold 5: base_IC=-0.2886 ml_IC=0.0009 base_dir=0.3091 ml_dir=0.6182 n=55 beats=True
- fold 6: base_IC=-0.0343 ml_IC=0.033 base_dir=0.7636 ml_dir=0.4727 n=55 beats=True
- fold 7: base_IC=0.2262 ml_IC=0.0163 base_dir=0.7273 ml_dir=0.2727 n=55 beats=False
- fold 8: base_IC=0.3098 ml_IC=-0.3067 base_dir=0.5636 ml_dir=0.0909 n=55 beats=False
- fold 9: base_IC=0.7565 ml_IC=-0.3984 base_dir=0.6545 ml_dir=0.3273 n=55 beats=False
- fold 10: base_IC=0.5558 ml_IC=0.6181 base_dir=0.7273 ml_dir=0.5273 n=55 beats=True
- fold 11: base_IC=0.3123 ml_IC=0.3962 base_dir=0.5273 ml_dir=0.5091 n=55 beats=True
- fold 12: base_IC=-0.5264 ml_IC=-0.4325 base_dir=0.1455 ml_dir=0.2909 n=55 beats=True
- fold 13: base_IC=0.4461 ml_IC=0.1492 base_dir=0.6727 ml_dir=0.4182 n=55 beats=False
- fold 14: base_IC=-0.5543 ml_IC=-0.1322 base_dir=0.3091 ml_dir=0.5818 n=55 beats=True
- fold 15: base_IC=0.0436 ml_IC=-0.2197 base_dir=0.4182 ml_dir=0.4 n=55 beats=False

### Bottom line

1. **Last 2 weeks (Schwab daily):** desk path with book gates was **net negative** on this window (premium strategies hitting stops/range breaks).
2. **Adding costs** slightly worsened P/L (as expected); not a fake improvement.
3. **Gates OFF** lost less $ on the 2w window but is **not** a general improvement (3mo/1y context still poor; more risk).
4. **Strict A-tier** printed **zero** trades — preservation, not alpha.
5. **ML ranker** is evaluated separately; only promote to *paper ranking* if majority of OOS folds beat momentum baseline — does **not** fix options fill model P/L by itself.
6. Short 3mo (64 bars) was too short for default WF; 1y enables folds.

## Walk-forward fix (lookback included in slices)

# Walk-forward — wf_costs
Bars: 252  Source: schwab
Symbols: SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD, META, AMZN, TSLA, JPM

## OOS aggregate
- **folds:** 14
- **folds_with_trades:** 14
- **oos_total_pnl:** -64917.14
- **oos_mean_expectancy:** -313.59
- **oos_mean_win_rate:** 0.25
- **oos_total_trades:** 207
- **oos_mean_score:** -625.3

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
- fold 10 bars[203:213] n=15 exp=$-378.04 WR=27% P/L=$-5670.65 DD=$5,671 score=-769.5
- fold 11 bars[213:223] n=12 exp=$-312.66 WR=17% P/L=$-3751.96 DD=$4,510 score=-631.9
- fold 12 bars[223:233] n=15 exp=$-642.98 WR=7% P/L=$-9644.74 DD=$9,645 score=-1327.5
- fold 13 bars[233:243] n=15 exp=$-262.24 WR=33% P/L=$-3933.58 DD=$3,934 score=-525.5

# Feature ranker walk-forward (vs classical baseline)
Schema: 1.0.0  horizon=5
Folds: 16  ML beats: 10
**Promote ML (paper only):** True
_ML wins majority of OOS folds — eligible for paper ranking experiment_

## Folds
- fold 0: base_IC=0.1561 ml_IC=-0.1027 base_dir=0.5455 ml_dir=0.3273 n=55 beats=False
- fold 1: base_IC=-0.6723 ml_IC=0.2825 base_dir=0.4364 ml_dir=0.5455 n=55 beats=True
- fold 2: base_IC=-0.4626 ml_IC=0.0057 base_dir=0.4727 ml_dir=0.3818 n=55 beats=True
- fold 3: base_IC=-0.2225 ml_IC=0.2998 base_dir=0.4182 ml_dir=0.6182 n=55 beats=True
- fold 4: base_IC=-0.3509 ml_IC=0.1265 base_dir=0.4182 ml_dir=0.6545 n=55 beats=True
- fold 5: base_IC=-0.2886 ml_IC=0.0009 base_dir=0.3091 ml_dir=0.6182 n=55 beats=True
- fold 6: base_IC=-0.0343 ml_IC=0.033 base_dir=0.7636 ml_dir=0.4727 n=55 beats=True
- fold 7: base_IC=0.2262 ml_IC=0.0163 base_dir=0.7273 ml_dir=0.2727 n=55 beats=False
- fold 8: base_IC=0.3098 ml_IC=-0.3067 base_dir=0.5636 ml_dir=0.0909 n=55 beats=False
- fold 9: base_IC=0.7565 ml_IC=-0.3984 base_dir=0.6545 ml_dir=0.3273 n=55 beats=False
- fold 10: base_IC=0.5558 ml_IC=0.6181 base_dir=0.7273 ml_dir=0.5273 n=55 beats=True
- fold 11: base_IC=0.3123 ml_IC=0.3962 base_dir=0.5273 ml_dir=0.5091 n=55 beats=True
- fold 12: base_IC=-0.5264 ml_IC=-0.4325 base_dir=0.1455 ml_dir=0.2909 n=55 beats=True
- fold 13: base_IC=0.4461 ml_IC=0.1492 base_dir=0.6727 ml_dir=0.4182 n=55 beats=False
- fold 14: base_IC=-0.5543 ml_IC=-0.1322 base_dir=0.3091 ml_dir=0.5818 n=55 beats=True
- fold 15: base_IC=0.0436 ml_IC=-0.2197 base_dir=0.4182 ml_dir=0.4 n=55 beats=False

