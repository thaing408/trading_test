# Offline backtest findings (research + CIO)

## Method
- Entry: `python -m trading_agent backtest --sweep`
- Multi-regime synthetic OHLCV (bull / chop / bear / recovery) — deterministic (`adler32` seeds, not `hash()`)
- Real paths: `evaluate_risk` → `build_opportunities` (book gates) → CIO `process_all_candidates`
- Fill model: directional stop/target/time; iron condors break on range expansion
- Risk scaled by shipped `GRADE_TRADE_GEOMETRY` size multipliers
- Score: expectancy + profit factor + win rate + total P/L − drawdown − churn
- **Invariants:** `stop_loss` exits never positive for bullish/credit; Bull Put fallback direction is **Bullish**
- Full report snapshot: `docs/backtest_run_latest.md`

## Sweep results — post book-discipline + expanded screener (2026-07-14 re-run)

Offline multi-regime path still uses fixed synthetic universe  
(`NVDA,AMD,AAPL,MSFT,SPY,QQQ,TSLA,META,AMZN,JPM`) — **not** the live ~113-name scan list.  
Screener expansion improves **live** candidate count; this sweep measures **trade-path gates**.

With SMB + Investopedia TA + playbook + MTF + rails **ON**:

| Rank | Config | Trades | Expectancy | Win rate | Max DD | Score |
|------|--------|--------|------------|----------|--------|-------|
| **1** | **baseline_grade_C_book3** (gates ON) | **38** | **$414** | **84%** | **$0** | **940** |
| 1-tie | wide_book5_grade_C / high_confidence_book3 | 38 | $414 | 84% | $0 | 940 |
| 4 | **baseline_C_book3_gates_off** | 70 | $82 | 57% | **$19.9k** | 120 |
| 5 | strict_a_tier_book3 (gates ON) | **0** | $0 | 0% | $0 | −8 |
| 5-tie | shipped_a_tier_full_discipline | **0** | $0 | 0% | $0 | −8 |

### Book-discipline ablation (same grade-C book3)
| Gates | n | WR | Expectancy | Max DD |
|-------|---|-----|------------|--------|
| **ON** (playbook+MTF+SMB+TA+rails) | 38 | **84%** | **$414** | **$0** |
| OFF | 70 | 57% | $82 | $19.9k |

**Takeaway:** Book gates cut churn and deep DD on this synthetic multi-regime set; quality > quantity.  
**Caveat:** `prefer_a_tier_only=True` + full gates yields **zero** trades on synthetic bars (A-tier MTF/playbook rarely clears). Shipped defaults still prefer A-tier for live capital preservation; offline best score is grade-C with gates ON.

### Live screener note (not in offline sweep)
- Default scan universe **~113** liquid symbols; soft strength + scan floors feed more watchlist names.
- Trade path still RiskConfig RVOL 2.0 / ADV 2M + book gates — more scanned ≠ more auto-trades.

## Historical sweep (pre book-discipline wiring)

| Rank | Config | Trades | Expectancy | Win rate | Max DD |
|------|--------|--------|------------|----------|--------|
| 1 | strict_a_tier_book3 | 53 | $349 | 75% | $8.1k |
| 2 | baseline_grade_C_book3 | 70 | $82 | 57% | $19.9k |
| 3 | high_confidence_book3 | 68 | $81 | 57% | $19.6k |
| 4 | wide_book5_grade_C | 125 | −$4 | 50% | $41.9k |

## Shipped risk defaults (capital preservation; not auto-flipped by latest score)
1. `RiskConfig.prefer_a_tier_only = True`
2. `RiskConfig.min_confidence_score = 60.0`
3. `RiskConfig.min_technical_score = 45.0`
4. `RiskConfig.min_setup_grade = "B"`
5. `RiskConfig.top_candidates = 3`
6. Book gates: playbook, edge, MTF, SMB, Investopedia TA, rails (all default ON)
7. Fills use `GRADE_TRADE_GEOMETRY[*][3]` size
8. Stable seeds via `zlib.adler32`

## Caveats
Underlying-path options proxy, not full chain. Rankings are relative under documented fill assumptions — not a live-profit guarantee.

---

# QQQ 0DTE Shen-style playbook (live 1m)

## Method
- Entry: `python -m trading_agent odte --symbol QQQ --backtest --period 10d --source schwab`  
  (or `--source yfinance`; `auto` prefers Schwab/TOS when `~/.schwab-mcp/token.json` is present)
- Rules: first touch of whole-$ / PDH-PDL / PMH-PML / OR + 1m RSI extreme (≈74/26) in **9:30–11:15 ET**
- Synthetic premium $1.00; delta≈0.55 × underlying $ move; bracket **+15% TP / −18% SL** (was +20% / −12.5%)
- Max 3 trades/day; one position at a time; contracts=2 × 100
- **Data:** Schwab Market Data API = thinkorswim feed; Yahoo 1m ≈ **7–8d** max; Schwab minute ≈ **10d** max

## A/B on Schwab/TOS 1m (2026-06-26 → 2026-07-10, 13 430 bars)

| Rules | Trades | **Win rate** | P/L | Expectancy | Exits |
|-------|--------|--------------|-----|------------|-------|
| **Legacy** whole-$ + TP20/SL12.5 | 14 | **21.4%** | −$155 | −$11.07 | SL11 / TP3 |
| Structural-only + TP15/SL18 | 9 | 11.1% | −$258 | −$28.67 | SL8 / TP1 |
| **Shipped** whole-$ + **TP15/SL18** | 14 | **28.6%** | −$240 | −$17.14 | SL10 / TP4 |

- **WR lift (TOS 10d):** 21.4% → **28.6%** (+7.2pp) with same trade count (14), non-empty sample.
- Structural-only **hurt** on this longer TOS window (cut winners with whole-$ losers still net worse).
- Last ~7d of same TOS file: legacy 33.3% (n=3) vs whole+TP15/SL18 **66.7%** (n=3) vs structural-only 100% (n=1 — too thin).

## Yahoo 1m re-run (2026-07-14, period=7d, source=auto→yfinance)

Confirmed after expanded-screener push (same window / proxy model):

| Rules | Trades | **Win rate** | P/L | Expectancy | Exits |
|-------|--------|--------------|-----|------------|-------|
| **Shipped** whole-$ + TP15/SL18 | **12** | **41.7%** | −$102 | −$8.50 | SL7 / TP5 |
| **Legacy** TP20/SL12.5 | 12 | 16.7% | −$170 | −$14.17 | SL10 / TP2 |

- Shipped bracket still **beats legacy WR** on this window (+25pp) but remains net-negative expectancy under synthetic premium.
- CALL WR 50% vs PUT WR 33% on shipped rules.

## Yahoo 1m note (earlier 7d ending ~2026-07-13)
On a short Yahoo window, structural-only + TP15/SL18 briefly showed **18.2% → 60%** (n=11 → 5). That slice is **not** confirmed on the full TOS 10d sample — TOS is the authoritative broker feed for re-tuning defaults.

## Shipped defaults (after TOS A/B)
1. `use_whole_dollar_levels=True` (keep whole-$ + structural)
2. `take_profit_pct=0.15`, `stop_loss_pct=0.18`
3. CLI: `--source schwab|tos|yfinance|auto`, `--legacy-rules` for A/B
4. Helpers: `signal_side_for_touch`, `level_allowed_for_entry`, `rejection_close_ok`

## Interpretation
- Under synthetic premium, **easier TP / slightly wider SL** raised hit-rate on TOS without zeroing trades.
- Book is still **net losing** on expectancy for the 10d TOS sample (wider SL costs more on losers) — WR improved, expectancy did not; size small.
- Not full options IV/chain pricing — live 0DTE P/L differs with IV crush and spreads.

## CLI examples
```bash
# TOS/Schwab feed (improved defaults)
python -m trading_agent odte --symbol QQQ --backtest --period 10d --source schwab

# Legacy rules on same feed
python -m trading_agent odte --symbol QQQ --backtest --period 10d --source schwab --legacy-rules

# Puts-only 0DTE (higher WR on TOS/Yahoo A/B)
python -m trading_agent odte --symbol QQQ --backtest --period 10d --source schwab --puts-only
```

---

# QQQ multi-DTE (weeklies / 2–3 DTE) on higher TF

## Method
- Entry: `python -m trading_agent odte --mode weekly --backtest --source schwab`  
  or `--dte 2|3|5 --interval 15m`
- Bars: **15m** (default), window **09:45–14:00 ET**, optional rejection close
- Target DTE label 2 / 3 / 5 (weekly) — educational expiry tag, not OCC chain pick
- Synthetic premium with **delta≈0.40** (milder than 0DTE 0.55); bracket default **+25% / −20%**
- Motivation: fast QQQ + 0DTE gamma is a churn factory; HTF structure + more extrinsic

## CLI
```bash
# Weekly-style (DTE≈5) 15m on Schwab/TOS
python -m trading_agent odte --mode weekly --backtest --source schwab --period 10d

# 2DTE / 3DTE
python -m trading_agent odte --mode 2dte --backtest --source auto
python -m trading_agent odte --dte 3 --interval 15m --backtest --puts-only

# Brief only
python -m trading_agent odte --mode weekly
```

---

# Breakout vs mean reversion (desk styles)

| Style | Bet | Desk command | Notes |
|-------|-----|--------------|--------|
| **mean_reversion** (default) | Fade RSI extreme at S/R | `odte --style mean_reversion` / 0DTE Shen / multi-DTE RSI | Opposite of chasing the break |
| **breakout** | Continuation after OR high/low break | `odte --style breakout --backtest --source schwab` | Aligns with 888 TI breakout philosophy |

```bash
# Mean reversion 0DTE (default style)
python -m trading_agent odte --style mean_reversion --backtest --period 10d --source schwab

# Breakout OR continuation on 15m (live Schwab)
python -m trading_agent odte --style breakout --backtest --period 10d --source schwab
```

Do not mix styles on the same signal without re-labeling risk (false break ≠ RSI fade).
