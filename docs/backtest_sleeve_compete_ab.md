# Sleeve competition A/B — 2026-08-01 19:24 UTC

**Data:** 11 symbols, 252 bars, sources=['schwab']
**Costs:** 5 bps + $1 commission. Gates: shipped baseline (ON).

## Full 1y

| Mode | Trades | WR | Expectancy | Total P/L | Max DD | Score |
|------|--------|-----|------------|-----------|--------|-------|
| COMPETE_ON | 347 | 20.8% | $-395.21 | $-137139.09 | $138,890 | -1528.4 |
| COMPETE_OFF | 345 | 19.4% | $-418.29 | $-144310.56 | $146,062 | -1610.8 |

**Delta (ON − OFF):** trades +2, exp $+23.08, PnL $+7171.47, WR +1.3pp

## Last ~2 weeks

| Mode | Trades | WR | Expectancy | Total P/L | Score |
|------|--------|-----|------------|-----------|-------|
| COMPETE_ON | 15 | 13.3% | $-512.87 | $-7693.06 | -1054.6 |
| COMPETE_OFF | 15 | 13.3% | $-512.87 | $-7693.06 | -1054.6 |

**Delta (ON − OFF):** trades +0, exp $+0.00, PnL $+0.00

## Strategy mix (1y)

### COMPETE_ON
- Iron Condor: 209
- Covered Call: 133
- Bull Put Credit Spread: 3
- Debit Spread: 1
- Long Call: 1

### COMPETE_OFF
- Iron Condor: 210
- Covered Call: 132
- Debit Spread: 1
- Bull Put Credit Spread: 1
- Long Call: 1

## Read

- COMPETE_ON = multi-sleeve scoreboard picks strategy per ticker (default).
- COMPETE_OFF = legacy single `select_strategy` only.
- Both still use the same book gates / risk / fill model after strategy pick.
