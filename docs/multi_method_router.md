# Multi-method ticker router

Every ticker is evaluated by **all** registered methods on a **shared bar history**, then gets **PLAY / SKIP / CONFLICT / NO_DATA**.

## Methods run per symbol

| Method | What it checks |
|--------|----------------|
| `soulz_pa` | BRR + range + fib confluence |
| `top_winners` | Drop-fast + TA/HTF continuation (CALL-style) |
| `orb_vwap` | Opening-range break + VWAP |
| `odte_breakout` | OR close-beyond continuation |
| `fvg` | Fair value gap tag + rejection (`pa.fvg`) |
| `range_fade` | Pure range-edge fade (`pa.range_fade`) |
| `sweep` | Liquidity sweep + reclaim (`pa.sweep`) |
| `process_methods` | Process/risk tags (advisory; **cannot unlock PLAY alone**) |

HTF structure/daily bias soft-filters sides (see `pa/htf_bias.py`).

## Decision policy

1. Fetch bars once per ticker.  
2. Run every enabled method → `MethodVote(play, side, score, tags)`.  
3. **PLAY** if ≥ `min_play_methods` methods vote play with `score ≥ min_method_score`  
   (**default 2** = require-two confluence). Use `--allow-single` to relax.  
4. **CONFLICT** if strong CALL and PUT votes disagree.  
5. Best method = highest score among play votes (for prep / card suggestion).  
6. **EXPORT** (auto_trade_book) only if PLAY **and**:
   - `len(play_methods) ≥ 2` (configurable), **and**
   - `best_play_score ≥ 65` **or** `play_quality_score` (avg of play methods) **≥ 65**  

Note: **`aggregate_score`** averages *all* methods (including fails) and is **not** used for the export gate.

## CLI

```bash
# Explicit list
python -m trading_agent research multi-method QQQ,NVDA,AMD,TSLA

# Require ≥2 methods agreeing
python -m trading_agent research multi-method QQQ,NVDA --require-two

# Data-driven pool (no symbols arg)
python -m trading_agent research multi-method --limit 12

# Stricter score
python -m trading_agent research multi-method SPY,QQQ --min-score 65 --min-methods 2
```

## Code

- `trading_agent/strategy/multi_method.py`
- Tests: `tests/test_multi_method.py`

## Auto process cards (Step 2–3)

**Default on** for `research multi-method`:

- **Focus list** ← PLAY symbols (prepended)  
- **Trade card** per PLAY name from best method (trigger / stop / size / exit / why)

```bash
# default: write cards + focus + auto_trade_book
python -m trading_agent research multi-method QQQ,NVDA

# scan only
python -m trading_agent research multi-method QQQ,NVDA --no-write-cards --no-export-book

# cards but leave focus untouched
python -m trading_agent research multi-method QQQ,NVDA --no-focus

# size label on cards
python -m trading_agent research multi-method QQQ --card-size 1R
```

Still **manual**: Step 1 regime  
`python -m trading_agent process regime --bias trade --regime "…" --reason "…"`

OMS consume remains blocked until process gate Steps 1–3 pass.

## Auto-trade book export (wired)

**Default on:** PLAY names → ENTER rows in `~/.trading_agent/sync/auto_trade_book.json`  
(and session/grok state paths via `write_auto_trade_book`).

| Field | Value |
|-------|--------|
| `instrument` | **equity** (underlying geometry; no options chain in router) |
| `source` | `multi_method_router` |
| `setup_id` | `multi_{best_method}` |
| `method_tags` | `multi_method`, best method, other play methods |
| Merge | Existing desk/CIO entries kept; same symbol prefers multi-method row + merged tags |

```bash
# default export + merge desk book
python -m trading_agent research multi-method QQQ,NVDA

# multi-method only (overwrite merge behavior for new book content)
python -m trading_agent research multi-method QQQ,NVDA --no-merge-desk

# no book write
python -m trading_agent research multi-method QQQ --no-export-book
```

**Cash suppress:** if process bias is `cash`, export writes **empty entries** + `stay_in_cash=true`.

**Consume path:** same as desk — `oms consume` / Mac consumer reads `auto_trade_book.json`.

## Historical router backtest

Walk each RTH day, evaluate all methods **as-of decision time** (default 15:00 ET, no lookahead), take the **best PLAY** (default 1/day), simulate synthetic premium exit.

```bash
# Default universe (mega-caps) · 30d · 15m · 1 trade/day
python -m trading_agent research multi-method-backtest --period 30d

# Custom list
python -m trading_agent research multi-method-backtest QQQ,SPY,NVDA,AMD,TSLA --period 30d

# Stricter: need 2 methods + up to 2 trades/day
python -m trading_agent research multi-method-backtest QQQ,SPY,NVDA --require-two --max-per-day 2
```

Report includes win rate, P/L, **% of days with ≥1 PLAY**, and breakdown by best-method selected.

Code: `trading_agent/strategy/multi_method_backtest.py`

## Next (optional)

- OMS export only when PLAY + process gate Steps 1–3 (live already exports book; gate still applies)  
