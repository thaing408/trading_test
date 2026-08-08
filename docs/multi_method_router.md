# Multi-method ticker router

Every ticker is evaluated by **all** registered methods on a **shared bar history**, then gets **PLAY / SKIP / CONFLICT / NO_DATA**.

## Methods run per symbol

| Method | What it checks |
|--------|----------------|
| `soulz_pa` | BRR + range + fib confluence |
| `top_winners` | Drop-fast + TA/HTF continuation (CALL-style) |
| `orb_vwap` | Opening-range break + VWAP |
| `odte_breakout` | OR close-beyond continuation |
| `process_methods` | Process/risk tags (advisory; **cannot unlock PLAY alone**) |

## Decision policy

1. Fetch bars once per ticker.  
2. Run every enabled method → `MethodVote(play, side, score, tags)`.  
3. **PLAY** if ≥ `min_play_methods` methods vote play with `score ≥ min_method_score` (default **any one** method can give a chance).  
4. **CONFLICT** if strong CALL and PUT votes disagree.  
5. Best method = highest score among play votes (for prep / card suggestion).

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
# default: write cards + focus
python -m trading_agent research multi-method QQQ,NVDA

# scan only
python -m trading_agent research multi-method QQQ,NVDA --no-write-cards

# cards but leave focus untouched
python -m trading_agent research multi-method QQQ,NVDA --no-focus

# size label on cards
python -m trading_agent research multi-method QQQ --card-size 1R
```

Still **manual**: Step 1 regime  
`python -m trading_agent process regime --bias trade --regime "…" --reason "…"`

OMS consume remains blocked until process gate Steps 1–3 pass.

## Next (optional)

- OMS export only when PLAY + process gate Steps 1–3  
