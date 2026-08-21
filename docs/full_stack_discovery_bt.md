# Full-stack discovery backtest — trading_agent (live desk)

Pool: `COIN, NVDA, AMD, TSLA, QQQ, SPY, AAPL, MSFT, META, AMZN`
Period **30d** 15m yfinance · decision 15:00 ET · no lookahead.
Premium path +25% / −20% (same as multi-method router BT).
Load errors: none

### Method PLAY votes (all symbol-days, before picking a trade)

| Method | PLAY votes |
|--------|------------|
| `chart_patterns` | 281 |
| `swing_daily` | 270 |
| `odte_breakout` | 161 |
| `orb_vwap` | 153 |
| `soulz_pa` | 74 |
| `range_fade` | 62 |
| `fvg` | 50 |
| `sweep` | 35 |
| `top_winners` | 27 |

### Policies

## A — Discovery (any PLAY, min 1 method)
n=96  WR=51.0%  exp=$1.31  PnL=$126  (synth $1 prem ×100)

| Method | n | WR | PnL |
|--------|---|----|-----|
| `chart_patterns` | 18 | 50% | $-20 |
| `fvg` | 1 | 0% | $-20 |
| `orb_vwap` | 5 | 40% | $-41 |
| `soulz_pa` | 12 | 75% | $102 |
| `sweep` | 1 | 0% | $-20 |
| `swing_daily` | 52 | 44% | $-5 |
| `top_winners` | 7 | 86% | $130 |

## B — Book export (2 methods + chart_patterns + score gate)
n=84  WR=53.6%  exp=$2.33  PnL=$195  (synth $1 prem ×100)

| Method | n | WR | PnL |
|--------|---|----|-----|
| `chart_patterns` | 16 | 50% | $-16 |
| `fvg` | 1 | 0% | $-20 |
| `orb_vwap` | 3 | 67% | $-1 |
| `soulz_pa` | 11 | 73% | $77 |
| `sweep` | 1 | 0% | $-20 |
| `swing_daily` | 46 | 46% | $25 |
| `top_winners` | 6 | 100% | $150 |

## C — same-day book (B + CALL + patterns/fvg/soulz; skip if swing-led)
n=17  WR=64.7%  exp=$2.91  PnL=$49  (synth $1 prem ×100)

| Method | n | WR | PnL |
|--------|---|----|-----|
| `chart_patterns` | 8 | 75% | $54 |
| `fvg` | 1 | 0% | $-20 |
| `soulz_pa` | 8 | 62% | $15 |

## C+EOD flatten 15:45 (same-day book, no overnight)
n=17  WR=64.7%  exp=$2.91  PnL=$49  (synth $1 prem ×100)

| Method | n | WR | PnL |
|--------|---|----|-----|
| `chart_patterns` | 8 | 75% | $54 |
| `fvg` | 1 | 0% | $-20 |
| `soulz_pa` | 8 | 62% | $15 |

## S — swing book (swing_daily only, hold overnight → next 10:30)
n=78  WR=47.4%  exp=$1.35  PnL=$105  (synth $1 prem ×100)

| Method | n | WR | PnL |
|--------|---|----|-----|
| `swing_daily` | 78 | 47% | $105 |

### Read
- A = what scanners *see*.
- B = what would land in `auto_trade_book` (same-day).
- C = same-day WR execute (patterns/soulz/fvg; no swing substitute).
- C+EOD = flatten 15:45 same day.
- S = sidecar `auto_trade_book_swing.json` (overnight hold, DTE≥7).
- Cash/chop tape is **not** in this BT (session flag).

