# Offline backtest findings (research + CIO)

## Method
- Entry: `python -m trading_agent backtest`
- Multi-regime synthetic OHLCV (bull / chop / bear / recovery) — deterministic (`adler32` seeds, not `hash()`)
- Real paths: `evaluate_risk` → `build_opportunities` → CIO `process_all_candidates`
- Fill model: directional stop/target/time; iron condors break on range expansion
- Risk scaled by shipped `GRADE_TRADE_GEOMETRY` size multipliers
- Score: expectancy + profit factor + win rate + total P/L − drawdown − churn
- **Invariants:** `stop_loss` exits never positive for bullish/credit; Bull Put fallback direction is **Bullish**

## Sweep results (reproducible offline)

| Rank | Config | Trades | Expectancy | Win rate | Max DD |
|------|--------|--------|------------|----------|--------|
| **1** | **strict_a_tier_book3** | 53 | **$349** | **75%** | **$8.1k** |
| 2 | baseline_grade_C_book3 | 70 | $82 | 57% | $19.9k |
| 3 | high_confidence_book3 | 68 | $81 | 57% | $19.6k |
| 4 | wide_book5_grade_C | 125 | −$4 | 50% | **$41.9k** |

## Shipped improvements (from winner)
1. `RiskConfig.prefer_a_tier_only = True`
2. `RiskConfig.min_confidence_score = 60.0`
3. `RiskConfig.min_technical_score = 45.0`
4. `RiskConfig.min_setup_grade = "B"`
5. `RiskConfig.top_candidates = 3` (book3 beat book5)
6. Fills use `GRADE_TRADE_GEOMETRY[*][3]` size
7. Strategy selector: fallback Bull Put is **Bullish**, not Neutral
8. Stable seeds via `zlib.adler32` (PYTHONHASHSEED-safe)

## Caveats
Underlying-path options proxy, not full chain. Rankings are relative under documented fill assumptions — not a live-profit guarantee.

---

# QQQ 0DTE Shen-style playbook (live 1m)

## Method
- Entry: `python -m trading_agent odte --symbol QQQ --backtest --period 7d`
- Rules: first touch of whole-$ / PDH-PDL / PMH-PML / OR levels + 1m RSI extreme (≈74/26) in **9:30–11:15 ET**
- Synthetic premium $1.00; delta≈0.55 × underlying $ move; bracket **+20% TP / −12.5% SL**
- Max 3 trades/day; one position at a time; contracts=2 × 100
- **Data limit:** Yahoo 1m history ≈ **7–8 days max** per request (60d not available)

## Results (as of 2026-07-13 run)

| Metric | Value |
|--------|--------|
| Days | 7 |
| Trades | 11 |
| Winners / Losers | 2 / 9 |
| **Win rate (success rate)** | **18.2%** |
| Total P/L | −$145 |
| Expectancy | −$13.18 / trade |
| Avg premium P/L % | −6.6% |
| Profit factor | 0.36 |
| Max drawdown | $160 |
| CALL | n=6 · WR 16.7% · −$85 |
| PUT | n=5 · WR 20.0% · −$60 |
| Exits | stop_loss 9 · take_profit 2 |

## Interpretation
- Under this premium proxy, the Shen-style QQQ 0DTE book was **net losing** over the latest week: stops hit ~4.5× more often than targets.
- Sample is **small** (11 trades) and **not** full options IV/chain pricing — live P/L will differ with IV crush and spreads.
- Relative to the offline multi-regime desk book (**strict_a_tier_book3** ~75% WR on synthetic OHLCV), this intraday 0DTE path needs more data or rule filters before treating as shippable.

## Sample losing pattern
Many whole-dollar / OR first-touches with RSI already extreme still faded through the −12.5% premium stop within the morning window (e.g. 2026-07-06/07/09/13 clusters).
