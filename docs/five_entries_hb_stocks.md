# Five entries, run cold — Haseeb Badar (@hb_stocks)

Source thread: [STOP COLLECTING STRATEGIES. YOU NEED 5 ENTRIES…](https://x.com/hb_stocks/status/2090087644642558210) (2026-08-19).

**Not affiliated.** Educational rewrite of the five visual playbooks. Charts in the thread are NSE/NASDAQ examples (HEG, Cochin Shipyard, Zen Technologies, Delta Corp, Sandisk). The rules travel; the tickers do not.

Thesis from the thread:

> Stop collecting strategies. You need **five entries, run cold, on repeat.**  
> Breakout. Pullback. Shakeout. Pivot. Opening range.  
> Five entries are only half the job. Knowing **which one fits the chart in front of you** is the other half.

Collecting more setups → freeze at execution. Master five → entries stop being the moment you bleed.

Original chart cards (downloaded from the thread):

| # | Entry | Image |
|---|--------|--------|
| 1 | Standard breakout | [docs/media/hb_stocks_five_entries/01_breakout.jpg](media/hb_stocks_five_entries/01_breakout.jpg) |
| 2 | Pullback | [docs/media/hb_stocks_five_entries/02_pullback.jpg](media/hb_stocks_five_entries/02_pullback.jpg) |
| 3 | Shakeout | [docs/media/hb_stocks_five_entries/03_shakeout.jpg](media/hb_stocks_five_entries/03_shakeout.jpg) |
| 4 | Pivot breakout | [docs/media/hb_stocks_five_entries/04_pivot.jpg](media/hb_stocks_five_entries/04_pivot.jpg) |
| 5 | Opening range breakout | [docs/media/hb_stocks_five_entries/05_opening_range.jpg](media/hb_stocks_five_entries/05_opening_range.jpg) |

---

## Shared process (all five)

Same skeleton on every card. Do not skip the last two.

1. **Context first** — trend vs chop, sector, higher-timeframe bias.
2. **Define the level** — resistance, MA/support, pivot box, ORH/ORL.
3. **Wait for the trigger** — close + volume / reclaim candle. Not the first tick through.
4. **Stop is structural** — beyond the level that invalidates the idea, not a round number.
5. **Targets in R** — take 1R–2R, then trail. “Book partials. Trail the rest.”
6. **Confirmations** — candle close location, volume, follow-through. A break without them is just a wick.

Formula on the cards: **patience + discipline + confirmation = consistent profits.**

---

## 1. Standard breakout

**Enter when price breaks a well-tested level with momentum and volume.**

Example in thread: HEG Ltd daily — multiple tests of ~₹95, then a wide-range close on high volume.

| Piece | Rule |
|--------|------|
| Idea | Price tests resistance (or support) many times. Sellers weaken. Buyers finally win with volume. New buyers chase the close. |
| Works best | Uptrend for longs. High relative volume. Tight structure into the level. Leading names in strong sectors. |
| Avoid | Low-volume breaks. Chop / range-bound tape. Extended far from MAs. Major news/event risk. |
| Enter long | Close **above** resistance with strong volume, **or** small pullback to the breakout as new support. |
| Stop | Below the breakout level (tight structure) **or** below the recent swing low. Small risk; let the trade prove itself. |
| Targets | 1: 1R–2R. 2: prior swing / measured move. 3: trail remaining. |
| Confirm | High relative volume. Strong close near the high. Level was respected. Market/sector in favor. |
| Higher odds | Break near the **start** of the trend. Price above key MAs. Strong sector + tight base before the break. |

**Key point:** a breakout is not the first candle across the line. Look for close above, strong volume, follow-through.

Repo map: range break + volume (`orb_vwap` / `odte_breakout` on HTF), Soulz `brr` if you wait for retest.

---

## 2. Pullback (trend continuation)

**Better price. Lower risk. Higher probability.** Board the train at the station — do not chase the last car.

Example: Cochin Shipyard daily — HH/HL uptrend, pullback to 50 EMA, hold, reclaim, continuation.

| Piece | Rule |
|--------|------|
| Idea | Trend is up (or down). Price temporarily moves against it into MA / prior breakout / demand. Enter when strength returns. |
| Psychology | Pullbacks are healthy. They dump weak hands and give a better location. |
| Works best | Clear trend. Pullback **holds** a key support. Volume dries on the dip, expands on the move up. |
| Avoid | Chop. Pullback **breaks** the support. Volume stays high on the dip (distribution). |
| Enter | Wait for the pullback to support. Bullish candle / reclaim of minor resistance. Enter on the strength candle. |
| Stop | Below the support area **or** below the pullback swing low. Tight. |
| Targets | Prior swing / resistance. Then 2R. Then trail. |
| Confirm | Trend up. Low-volume pullback. Support holds. Bullish reclaim. Volume up on continuation. |
| Higher odds | Strong sector. Market trend with you. HTF also up. The **prior** breakout was strong. |

**Reminder:** you are not calling the exact bottom of the dip. You join when buyers show again.

Repo map: Soulz `fib` (38.2–61.8 of impulse), `fvg` fill, `order_block` mitigation, top-winners pullback.

---

## 3. Shakeout (undercut & reclaim)

**Fear creates the shakeout. Strength creates the reversal.** Visual: shark attack, then liftoff.

Example: Zen Technologies daily — uptrend, brief break below 50 MA / support, fast reclaim, continuation.

| Piece | Rule |
|--------|------|
| Idea | Price **briefly** dips below support or MA, trips stops, then **quickly** reclaims and reverses. Traps sellers. |
| Psychology | Weak hands panic. Stops fire. Strong hands absorb. Reclaim + new buyers. |
| Works best | Strong uptrend. Well-respected level or MA. Volume **up on the reclaim**, not only on the dump. Healthy tape. |
| Avoid | Downtrends. Weak/broken support. High volume on the breakdown (real distribution). Chop. |
| Enter | Wait for the undercut. Watch for quick reclaim + bullish rejection. Enter next candle or on confirmation. |
| Stop | Below the **shakeout low**. Tight. Small % of capital. |
| Targets | Prior swing high. Then 1R–2R. Then trail. |
| Confirm | Strong reclaim close **back above** support/MA. Higher volume on reclaim. Follow-through next day. |
| Higher odds | Strong sector. Above key MAs. Market trend favorable. Accumulation (not one-way selling). |

**Goal is not to predict the shakeout. Goal is to react to the reclaim.**

Repo map: `pa.sweep` / multi `sweep` (liquidity sweep + reclaim). Same family as failed breakout.

---

## 4. Pivot breakout (tight range)

**The tighter the pivot, the stronger the break.** Coiled spring: crouch, then sprint.

Example: Delta Corp daily — tight box, volume dies inside, then high-volume close out of the range.

| Piece | Rule |
|--------|------|
| Idea | Price compresses in a **tight** range (pivot). Weak hands leave. Smart money builds. Break + volume = expansion. |
| Works best | Consolidation / tight ranges **before** a continuation. Volume drying **inside** the pivot. Overall market strength. |
| Avoid | Chop, news-driven chaos. Pivot **too wide** (no compression). Near major HTF resistance / events. |
| Enter | Draw the box (top = resistance, bottom = support). Long on close **above** the box with volume. Short on close **below** with volume. |
| Stop | Below pivot support (long) or above pivot resistance (short). Small. Let it prove. |
| Targets | 1R–1.5R. Then prior swing. Then 2R–3R / trail. |
| Confirm | Volume expansion on the break. Strong close outside the box. Market with you. Optional flag/pennant after. |
| Higher odds | Tight box. High volume on break. Strong sector + market. News/results support (optional, not required). |

**Job:** identify tightness early. Do not predict direction. Let the close pick the side.

Repo map: chart-pattern flags/triangles (`pa.chart_patterns`), range then `orb_vwap`-style expansion.

---

## 5. Opening range breakout (ORB)

**Intraday.** First 5 / 15 / 30 minutes define the box. Break of ORH or ORL with volume is the start gun.

Example: Sandisk 5-minute — OR 09:15–09:20, later break of ORH with a volume spike, then trend day.

| Piece | Rule |
|--------|------|
| Idea | Opening range = battle. Break = one side won. Momentum traders pile in. |
| Works best | Strong directional bias. High-vol days. Volume **at the break**. Liquid hours. |
| Avoid | Low-vol / range days. Inside-week blackout. OR **too wide** (noise). Weak volume on the break. |
| Enter | Define OR (5 / 15 / 30 min). Buy above ORH or sell below ORL. On breakout close **or** small pullback. |
| Stop | Long: below ORL. Short: above ORH. Or a few cents/ticks beyond the range. |
| Targets | 1R–2R. Prior high/low or measured move. Trail with VWAP / EMA / structure. |
| Confirm | Strong breakout candle. Volume > OR average. Market trend / news / relative volume with you. |
| Higher odds | Market trending. **Tight** OR. Aligns with pre-market trend or news. Volume rising. Liquid name. |

**Key point:** the first real move of the day often sets the tone. Define range → wait for break → confirm volume → manage risk → let momentum work.

Repo map: `orb_vwap`, `odte_breakout`, Venom NY box (`docs/venom_model_ict.md`), `pa.levels` session high/low.

---

## Which entry fits **this** chart?

That is the half of the job the thread says takes reps. Use this filter **before** looking for a trigger.

| Chart in front of you | Use |
|------------------------|-----|
| Repeated tests of a **clear horizontal**, then a wide-range volume close | **1 Breakout** |
| Clean HH/HL (or LH/LL), dip into MA / prior break, buyers return | **2 Pullback** |
| Trend intact, **brief** undercut of support/MA, fast reclaim | **3 Shakeout** |
| **Tight** multi-session box, volume dying, then expansion | **4 Pivot** |
| RTH open, first 5–30 min box, then directional break | **5 ORB** |
| Wide chop, no level, no volume, mixed HTF | **None. Sit.** |

Do not stack all five on the same bar. One primary. A pullback **after** a breakout is still a pullback, not a second breakout.

---

## Risk template (desk)

Keep it identical so the entry type is the only variable.

| Item | Default |
|------|---------|
| Invalidation | Structural (beyond level / shakeout low / OR opposite side) |
| First scale | 1R–2R |
| Remainder | Trail structure / VWAP / swing |
| Size | Small enough that a full stop is boring |
| Skip | No close, no volume, wrong regime |

---

## Map onto this repo

| Five-entry name | Closest code / docs today |
|-----------------|---------------------------|
| Breakout | OR continuation, Soulz `brr` (retest variant) |
| Pullback | Soulz `fib`, `fvg`, `order_block`, top-winners |
| Shakeout | `pa.sweep` / multi `sweep` |
| Pivot | `pa.chart_patterns` (flag / triangle / range) |
| ORB | `orb_vwap`, `odte_breakout`, Venom box |

Related: [price_action.md](price_action.md) · [soulz_pa_scalp.md](soulz_pa_scalp.md) · [multi_method_router.md](multi_method_router.md) · [venom_model_ict.md](venom_model_ict.md)

This doc is the **playbook**. It is not a new auto-trade method until someone wires explicit detectors + backtest the same way Soulz / FVG / OB were wired.
