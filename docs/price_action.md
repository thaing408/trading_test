# Price Action (reference + implementation map)

Living notes on **price action (PA)** for the desk, with **code** under `trading_agent/pa/`.

**Related:**

- PA package: `trading_agent/pa/` (structure, levels, FVG, sweep, range fade, HTF bias, journal)
- Soulz-style PA: `docs/soulz_pa_scalp.md`, `trading_agent/scalp/soulz_pa.py` (BRR + range + fib)
- Multi-method router: `docs/multi_method_router.md` (includes `fvg`, `range_fade`, `sweep`)
- Systematic process: `docs/systematic_process.md`

---

## What it is

**Price action** is trading from **what price is doing on the chart**—candles, swings, levels, structure—without depending on a stack of lagging indicators (RSI, MACD, etc.) as the *main* decision engine.

Indicators may still be used as **context or filters**. The core read is the **path of price** (OHLCV and the levels it creates).

---

## Core ideas

| Concept | Meaning |
|--------|---------|
| **Structure** | Higher highs / higher lows (uptrend), lower highs / lower lows (downtrend), or range (sideways). |
| **Levels** | Prior highs/lows, session open, round numbers, gaps, range edges—places where buyers/sellers have shown up. |
| **Rejection** | Long wick / failed break / close back inside = “tried to go there, got pushed back.” |
| **Acceptance** | Closes and holds beyond a level = market is OK with new prices. |
| **Break & retest** | Level breaks → price returns to retest it → continues (classic PA setup). |
| **Liquidity** | Stops cluster above highs / below lows; sweeps (take the stops) then reverse are common PA narratives. |
| **Context** | Same candle means different things in a trend vs a range vs after news. |

Fibonacci, VWAP, EMAs, volume are often **helpers**, not the definition of PA. Pure PA may ignore them; hybrid systems use them as confluence.

---

## What PA traders usually look at

1. **Market structure** — trend, range, or transition (break of structure / change of character).  
2. **Key levels** — where the story happened before.  
3. **Candle behavior** at those levels — engulfs, pins, inside bars, displacement.  
4. **Location** — mid-range noise vs edge / after a clear impulse.  
5. **Timeframe stack** (optional) — higher TF bias, lower TF entry.

---

## Common PA setups (names vary)

| Setup | Idea | In this repo (today) |
|-------|------|----------------------|
| **Break → retest → continue (BRR)** | Avoid chasing first break; enter on retest hold | Soulz `brr` |
| **Range fade** | Buy/sell range edges with rejection | Soulz `range` + `pa.range_fade` / multi `range_fade` |
| **Range breakout (+ retest)** | Leave the box, optional retest | ORB / breakout methods |
| **Pullback in trend** | Buy discount in uptrend / sell premium in downtrend | Fib + top-winners + **FVG** |
| **Failed breakout / sweep** | Take stops beyond high/low then reverse | `pa.sweep` / multi `sweep` |
| **Opening range / session structure** | ORH/ORL as day structure | `orb_vwap`, `odte_breakout`, `pa.levels` |
| **FVG / IFVG** | Imbalance fill + rejection | `pa.fvg` (shared), QT delegates |

---

## Strengths

- Direct: trading the thing that pays (price).  
- Portable across markets (stocks, futures, crypto, FX).  
- Forces **scenario thinking** (if level holds… if it fails…).  
- Fits a **written process** (when to trade, when to sit).

## Weaknesses

- **Subjective** without rules (everyone draws different “structure”).  
- Easy to **curve-fit** hindsight charts.  
- Lower TFs = noise, fees, stop hunts.  
- Without **regime** (trend vs chop), the same pattern wins one week and fails the next.

---

## Price action vs indicators

| | Price action | Indicator-heavy |
|--|--------------|-----------------|
| Input | OHLCV path, levels | Smoothed transforms of price/volume |
| Lag | Less (you see the event) | Often more |
| Clarity | Needs discipline/rules | Can feel “objective” but still discretionary |
| Best use | Structure + location + reaction | Filters, alerts, secondary confirmation |

Many strong systems are **hybrids**: PA for *what* and *where*, a few tools for *filter*.

---

## Design principles for implementation (later)

When coding more PA into the agent, prefer:

1. **Objective structure definitions**  
   - Swings: pivot N bars left/right, or fractal rules.  
   - Trend: HH/HL vs LH/LL on a fixed TF.  
   - Range: rolling high/low or session box with min height.

2. **Explicit acceptance vs rejection**  
   - Rejection: wick through level + close back inside.  
   - Acceptance: close beyond level (optional: hold N bars).

3. **Regime gate first**  
   - Trend → prefer BRR / pullback.  
   - Range → prefer edge fade.  
   - Expansion/news → reduce size or sit.

4. **Confluence policy**  
   - Single setup = more trades, more noise.  
   - ≥2 of {structure, level, rejection, fib/VWAP} = fewer, cleaner (router already supports multi-method).

5. **Hard invalidation**  
   - Stop beyond retest extreme / beyond range edge.  
   - No mid-box entries without a written exception.

6. **Process integration**  
   - PA signals → multi-method vote → PLAY → process trade card → OMS only if Steps 1–3 pass.

---

## Implemented modules (`trading_agent/pa/`)

| Module | File | Role |
|--------|------|------|
| Structure | `pa/structure.py` | Pivots, HH/HL, BOS/CHoCH, trend/range |
| Levels | `pa/levels.py` | PDH/PDL, session H/L/open, OR, whole-$ |
| Reactions | `pa/reactions.py` | Acceptance / rejection at level |
| FVG | `pa/fvg.py` | Detect, fill %, active gaps, entry score, IFVG |
| Sweep | `pa/sweep.py` | Liquidity sweep + reclaim |
| Range fade | `pa/range_fade.py` | Pure edge fade to mid |
| HTF bias | `pa/htf_bias.py` | Direction filter from structure / daily bars |
| Journal | `pa/journal.py` | Standard PA review fields |

**Multi-method votes added:** `fvg`, `range_fade`, `sweep` (+ optional HTF soft filter).

| Still optional later | Notes |
|----------------------|--------|
| Session templates (Asia/London/NY) | Extend `levels` / schedule |
| Wire PA journal into OMS closed trades | Use `pa_journal_fields` |

---

## Map to current desk

| Desk concept | PA angle |
|--------------|----------|
| Systematic Step 1 (regime) | Trade only when structure regime matches method |
| Step 2 (select) | Prefer names at levels / with clear structure |
| Step 3 (prepare) | Predefine level, invalidation, targets before open |
| Step 4 (execute) | No redrawing structure mid-trade |
| Step 5 (review) | Tag wins/losses by setup type + regime |
| Multi-method router | Each PA/hybrid method votes PLAY; any (or ≥N) can unlock a card |

---

## Bottom line

**Price action** is reading **structure, levels, and reactions**—trading the auction, not the oscillator. It is powerful when rules are tight and regime-aware; weak when it is freehand storytelling on every candle.

**Status:** core engines **implemented** under `trading_agent/pa/`; multi-method + QT FVG share geometry.

---

## Fair Value Gaps (FVG)

A **Fair Value Gap (FVG)** is a short **imbalance** on the chart: a three-candle pattern where price moved so fast that the middle candle’s range leaves a **gap in traded prices** between candle 1 and candle 3. Traders treat that zone as an area the market may **revisit** to “rebalance” (fill) before continuing—or as a level that **holds** if the move was strong.

Also called: **imbalance**, **inefficiency**, **void** (related ideas; FVG is the common three-candle ICT/SMC-style label).

### How to spot one (standard 3-candle rule)

**Bullish FVG** (after sharp up / buy-side imbalance):

- Candles: 1 → 2 (displacement) → 3  
- **Low of candle 3 > high of candle 1**  
- Gap zone = from **high of candle 1** up to **low of candle 3**

**Bearish FVG** (after sharp down / sell-side imbalance):

- **High of candle 3 < low of candle 1**  
- Gap zone = from **low of candle 1** down to **high of candle 3**

```text
Bullish FVG (schematic):

  | c3 |     ← low of c3 sits above high of c1
  | c2 |     ← big body / displacement
  | c1 |
       ^^^^ gap (FVG zone)
```

**In this repo (already coded):** `trading_agent/qt/model.py`

- Bullish: `low[i] > high[i-2]`  
- Bearish: `high[i] < low[i-2]`  
- **IFVG:** FVG that later **trades back through** (inverse) as confirmation (`detect_fvg`, `ifvg_confirm`)

### What traders use FVGs for

| Use | Idea |
|-----|------|
| **Entry on fill** | Price returns into FVG; enter with structure (e.g. long into bullish FVG in uptrend) |
| **Confluence** | FVG + HTF level, OR, VWAP, BRR retest, fib zone |
| **Targets / magnets** | Price often “seeks” nearby unfilled FVGs |
| **Invalidation** | Close deep through far side of gap = idea failed |
| **IFVG / inversion** | Gap fills and breaks through → old gap becomes opposite bias level |

### Context (same as all PA)

- **With trend:** Pullback into bullish FVG in an uptrend is a common long.  
- **Against trend:** Fading every FVG is easy to overtrade.  
- **Timeframe:** 1m FVGs are often noise; **15m / 1H / D** tend to matter more.  
- **Fill behavior:**  
  - Full fill → often rebalance / mean-reversion  
  - Partial fill + rejection → continuation (trend traders)  
  - No fill → strong displacement; gap may act as S/R later  

### Strengths / weaknesses

**Strengths:** objective 3-candle geometry (easy to code); marks auction “skip”; combines with structure and multi-TF bias.

**Weaknesses:** charts fill with tiny FVGs; hindsight bias; without regime + HTF direction, FVG-only systems chop.

### Implementation notes (later)

1. **Filter size:** only FVGs larger than X% of price or ATR.  
2. **HTF first:** only trade FVGs aligned with higher-TF direction (see multi-timeframe map below).  
3. **Freshness:** prefer unfilled / recently formed gaps.  
4. **Reaction required:** wait for rejection or reclaim—don’t blindly market into mid-gap.  
5. **One role per gap:** entry zone *or* target, not both without a plan.  
6. **Desk flow:** FVG signal → multi-method vote → process card → OMS only after Steps 1–3.

### Map to this desk (today)

| Concept | Status |
|---------|--------|
| FVG detect / IFVG | `pa/fvg.py` (canonical); `qt/model.py` delegates |
| Multi-method FVG vote | `fvg` method in router |
| Min size / age / fill / rejection | `find_active_fvgs`, `score_fvg_entry` |
| Journal fields | `pa/journal.py` → `fvg_side`, `fill_pct`, `ifvg` |

---

## Multi-timeframe map (note)

**Source:** [Market Rebellion @RebellioMarket](https://x.com/RebellioMarket/status/2086548107651867098) (2026-08-09)  
**Rule of thumb:** *Higher timeframe = direction. Lower timeframe = entry.*

| Timeframe | Role (from post) |
|-----------|------------------|
| **3M** (quarterly) | Big macro cycle; long-term capital rotation |
| **1M** (monthly) | Major trend; institutional positioning |
| **1W** (weekly) | Primary direction; swing bias; key S/R |
| **1D** (daily) | Trade planning; pattern validation; trend strength |
| **4H** | Swing entries; structure breaks; trend continuation |
| **2H** | Refined swing timing; momentum confirmation |
| **1H** | Intraday bias; clean setups; risk control |
| **30m** | Entry preparation; consolidation vs expansion |
| **15m** | Execution zone; breakouts and pullbacks |
| **5m** | Precision entries; volume spikes; tight stops |
| **3m** | Scalping confirmation; momentum shifts |
| **1m** | Fast execution; liquidity grabs; high focus |
| **Tick** | Order flow; micro price; extreme precision |

### How to use later (implementation notes)

1. **Bias stack (top-down):** pick 1–2 HTFs for direction (e.g. W + D, or D + 4H) before any LTF entry.  
2. **Entry stack (bottom-up only after bias):** e.g. 15m/5m for stocks desk; 1m only if scalping with hard rules.  
3. **Do not reverse bias on LTF noise** — 1m liquidity grabs should not flip a weekly long bias without HTF structure break.  
4. **Desk mapping (today):**  
   - Process Step 1 (regime) ≈ D / W context  
   - Multi-method / Soulz / ORB ≈ 15m (sometimes 5m) execution  
   - Top-winners first-30m logic ≈ session structure on 1m–5m under D bias  
5. **HTF bias engine:** `pa/htf_bias.py` → multi-method soft (or strict) side filter.

### Practical stack examples

| Style | Direction TF | Plan TF | Entry TF |
|-------|--------------|---------|----------|
| Swing | W / D | D / 4H | 4H / 1H |
| Intraday equity | D | 1H / 30m | 15m / 5m |
| Scalp | 1H / 15m | 15m / 5m | 3m / 1m |
| Process desk (this repo) | D (+ optional W) | 15m | 15m / 5m |

---

## References (informal)

- Classic PA: structure, S/R, break-retest, range, FVG/imbalance.  
- Public education examples (e.g. BRR + range + fib packaging) — see `docs/soulz_pa_scalp.md`.  
- Multi-timeframe hierarchy: [@RebellioMarket](https://x.com/RebellioMarket/status/2086548107651867098).  
- FVG geometry already in `trading_agent/qt/model.py`.  
- Not financial advice; paper rules first.
