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
