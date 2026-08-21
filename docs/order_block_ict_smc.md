# Order Blocks — ICT vs Common SMC (mechanical map)

This doc maps **two popular order-block (OB) definitions** into code under
`trading_agent/pa/order_block.py`. Both are **rule-based approximations**, not
a full transcript of any paid mentorship or every YouTube variant.

| Style | Code | Zone geometry | Displacement trigger |
|-------|------|---------------|----------------------|
| **ICT-style** | `style="ict"` | Candle **body** (open–close) | Impulse that **leaves an FVG** + ATR expansion |
| **SMC / retail** | `style="smc"` | Full candle **range** (high–low) by default | **N consecutive** directional candles + body strength + ATR expansion |

Multi-method id: **`order_block`** (scores both; boosts when ICT + SMC agree on side).

---

## Shared narrative (both camps)

1. Price prints a **last opposing candle** (or small base).
2. A **strong impulse** leaves that area (institutional “orders filled”).
3. Price later **returns (mitigates)** into that zone.
4. Trade **continuation** if the zone holds; if price **closes through**, many
   treat it as a **breaker** (role flip).

What differs is *how* you draw the zone and *what counts* as displacement.

---

## ICT-style rules (our codification)

Aligned with common ICT language (order block + displacement + inefficiency),
not every historical ICT rename (propulsion, rejection block, etc.).

| Step | Rule in code |
|------|----------------|
| Displacement | 3-candle **FVG** forms at bar `i` **and** impulse range ≥ `min_disp_atr × ATR` |
| Bullish OB | Last **down-close** candle **before** the impulse window |
| Bearish OB | Last **up-close** candle before the impulse window |
| Zone | **Body only**: `[min(o,c), max(o,c)]` |
| Mitigation | Later bar’s range overlaps the body zone |
| Invalidation / breaker | **Close** below bullish zone low (or above bearish zone high) → `is_breaker` |

**Why body?** ICT “refined” OBs often emphasize the body / mean threshold rather
than the full wick extremes.

**Why FVG?** Ties OB to *inefficient* displacement (same family as Venom / FVG
methods already in this repo).

---

## Common SMC / YouTube-style rules (our codification)

What most short-form SMC content means by “order block”:

| Step | Rule in code |
|------|----------------|
| Displacement | `impulse_bars` (default 3) **consecutive** bullish or bearish closes, strong bodies (`min_body_ratio`), range ≥ `min_disp_atr × ATR` |
| Bullish OB | Last **bearish** candle before that run |
| Bearish OB | Last **bullish** candle before that run |
| Zone | Full **H–L** of that candle (`use_full_range=True`); optional body-only |
| Mitigation / breaker | Same touch + close-through logic as ICT |

**No FVG required** — many YouTube setups only need “strong move off a candle.”

---

## Breaker blocks

When an OB is **invalidated by close-through**:

| Original OB | After break | New role |
|-------------|-------------|----------|
| Bullish support | Close &lt; zone low | **Bearish breaker** (resistance on retest) |
| Bearish resistance | Close &gt; zone high | **Bullish breaker** (support on retest) |

Code: `to_breaker`, `find_breakers`. Entry scorer can take breaker retests at a
slightly lower base score than fresh OBs.

---

## Entry scoring (`score_order_block_entry`)

On the current bar:

1. Collect active (non-invalidated) ICT + SMC OBs.
2. Require **price touch** of zone; prefer **rejection** wick/close (same helper as FVG).
3. Score bonuses:
   - ICT style &gt; SMC base
   - Rejection, mitigating, HTF align
   - **`ict+smc_confluence`** when both styles have active same-side OBs
4. Stop beyond zone extreme; target = `r_multiple` × risk (default 1.5R).
5. Soft HTF: against-trend sides demoted / blocked like other PA methods.

---

## How this fits the desk stack

| Piece | Role |
|-------|------|
| `pa/fvg` | Inefficiency / fill entries |
| `pa/order_block` | **Where** the impulse “originated” (zone) |
| `pa/venom` | Timed NY box + sweep; OB is often the candle *before* displacement after sweep |
| `pa/sweep` | Liquidity grab; OB often sits *inside* after reclaim |
| Multi-method `order_block` | One more PLAY vote (confluence with FVG/sweep is ideal) |

Typical confluence story: **sweep → displacement (FVG) → mark OB → enter on OB/FVG mitigation.**

---

## What we deliberately do *not* claim

- Exact ICT mentorship definitions for every named array.
- That OBs alone have positive expectancy (they usually need context).
- That YouTube “guaranteed” OB systems are validated.

Always treat scores as **research votes**, not live OMS authority unless you
wire and backtest them intentionally.

---

## Quick API

```python
from trading_agent.pa.order_block import (
    detect_ict_order_block_at,
    detect_smc_order_block_at,
    find_active_order_blocks,
    find_breakers,
    score_order_block_entry,
)

# All recent zones
obs = find_active_order_blocks(o, h, l, c, styles=("ict", "smc"))

# Entry vote
play, side, score, tags, entry, stop, target = score_order_block_entry(
    h, l, o, c, htf_direction="up"
)
```

CLI / multi-method: method id **`order_block`** on the methods router.
