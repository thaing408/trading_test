# Qullamaggie entry dials (Muninn study)

**Source:** [James Muninn (@Muninn) — 2026-08-14](https://x.com/Muninn/status/2088292776047751193)  
**Data:** ~900 long trades by Market Wizard Kristjan Kullamägi (Qullamaggie), 2019–2022  
**Method (author):** same names / same stop (LOD as of entry) / hold to stop or first close under 10-day MA; only the *dial* changes  

Not affiliated. Notes for the desk — **not** a signal to copy-trade or change live rails without a test.

**Related on this repo:**

- ORB + VWAP sleeve: `trading_agent/sleeves/orb_vwap.py`
- ADR / strength: `trading_agent/analysis/strength.py`, screener gates
- Stops / 2 RT per ticker: `trading_agent/oms/pretrade.py`, `oms/exits.py`
- PA map: `docs/price_action.md`
- **Weekend implement plan:** `docs/qullamaggie_weekend_plan.md`

---

## Thesis

Aspiring traders want **one number** for every variable (which OR, how much risk, how late, where the stop, market vs limit). There is no single answer. Each is a **dial** whose cost depends on account size, risk tolerance, the stock, and how far it has already run.

Muninn’s claim: he measured the **cost of turning each dial** on Qullamaggie’s longs. Several answers contradict common teaching.

---

## Five repeating questions

| Question | Taught answer (often) | Study / Qullamaggie take |
|----------|------------------------|---------------------------|
| Which opening range? 1 / 5 / 15 / 30 / 60m | “There is a correct one” | No right window. Pick one and own the cost. |
| How much to risk? | Fixed share size | Risk first; stop from the chart; size falls out. |
| How extended is too extended? | Hard % (e.g. 4%) | Scale to **ADR/ATR**, not a fixed %. Too *early* hurts more than chase. |
| Where does the stop go? | Arbitrary / BE too soon | Stop **width** is the conversion of a move into R. LOD-as-of-entry in the sim. |
| Market, limit, or buy-stop? | “Never chase / never buy-stops” | If you have to ask → **market**. He *does* use buy-stops. Limits came from **size / slippage**. |

Two extra findings he says changed him more than the five:

1. **The entry is not one click** (scale-in).  
2. **A stop-out is not the end of the idea** (re-buy).

---

## Dial 1 — Opening range window

Qullamaggie (stream 2020-01-07): *no right answer; 1 / 3 / 5 / 10m all fine; pick your own.* He uses several. Faster windows: **lower accuracy, earlier fill**.

**Sim:** buy break of 1 / 5 / 15 / 30m OR high, stop = LOD as of entry, then hold to stop or first close under 10-day MA.

Author’s reported tradeoff (same names, only window changes):

| Window | Win rate (reported) | Mean R (reported) | Other |
|--------|---------------------|-------------------|--------|
| 1m ORB | ~24% | ~3.61R | Tight stop; win less often, paid more per R |
| 30m ORB | ~36% (+12 pp) | ~1.54R (~half) | Stop ~3× as wide as 1m |

- Waiting 30m: fewer setups even fire (author: **~1 in 5** take out the 30m OR high).  
- **Skipped faster setups lose money** at the 1m entry (waiting is a **filter**, not a missed-edge cost). Author: the 30 names the 5m window drops **all stopped out same day**.  
- A 1m winner tends to still be a 30m winner — **worse fill**.  
- **Invisible cost:** worse fill + wider stop on trades you *still take*. Across **805** setups he reports **1m harvest ~2865R vs 30m ~976R** — waiting “gives up” **~1889R (~66%)**. Skipped names save money; the bill is the wider stop on everything else.  
- Idealized: **not realistic to take every 1m ORB**. Conceptual case for fast vs slow.

**Personality:** fast = uncomfortable, wrong ~3/4, ~3× total R. Slow = comfortable, higher WR, leave R on the table. Pick what you can sit with.

**EP vs breakout:** a gap dumps vol at the open. Fast entries give EP **no room**. On a 30m range he reports EP near a **coin flip (49%)** and median trade **stops losing**. Same fixed window **punishes EPs hardest**.

**No cutoff time** (stream 2021-03-09): if it breaks later, buy the break **after a range exists**.

**Desk note:** our ORB sleeve should treat window as a **config dial** (1 vs 5 vs 15 vs 30), log WR vs mean R separately for **EP vs breakout**, and not treat “missed 1m” as a bug.

---

## Dial 2 — Extension (ADR, not a fixed %)

Hard 4% rules fail: 3% on a **10-ADR** name ≠ 3% on a **4-ADR** name.

Qullamaggie (2020-08-03): usually **don’t buy if the stock is up more than ATR on the day**; prefers entry at **~1/3 to 2/3 ATR**.

**What he actually did** (closest match of stated vs live in the study):

| Stat | Value |
|------|--------|
| Median extension at entry | **0.47 ADR** |
| 75% of entries | **< 0.68 ADR** (top of his stated band) |
| 87% of entries | **< 1 ADR** (“too high to buy”) |

**Does extension predict?** Median trade is **−1R** in almost every bucket (3/4 stop out). Tail pays **over days/weeks**, so use **mean R of the whole trade**, not same-day median.

**Expensive mistake = too early, not too late.**

- Entry **< 0.25 ADR** off the low: stop ~**1.3%** wide → **~91% stopped out**. Fast execution is **not** the edge. Stop sits inside noise.  
- **0.25–0.50 ADR bucket:** best **5% of trades produce ~99% of that bucket’s total R**. Averages sit on a fat-tail; entry mechanics decide how many tail trades you still hold.  
- **Above his 1 ADR line:** data does **not** punish in this sample, but you are **outside his rule**.

**Chase:** don’t skip the name — **size down** (½, ⅕). Strongest stocks “don’t give you an entry.” He breaks his own rules with smaller size.

**Caveat (reply @RafGysels_):** Revere AM study on ~1k trades argued the **opposite** on 0–0.25 ATR (higher WR if closer to LOD). Likely **setup-dependent**: pullbacks vs ORB/EP/breakout. Volume / RVOL not in Muninn’s tables.

**Desk note:** measure **day range used / ADR** before entry. Soft-warn or size-cut **< 0.25 ADR** (noise stop) and **> 1 ADR** (outside Qullamaggie band). Do not hard-block >1 ADR without a sleeve test.

---

## Dial 3 — Order type

- If you need to ask → **market**.  
- He **does** use **buy-stops** (e.g. CODX: 11% in 10s then halt; 60k shares already working). Stream troll (2021-02-12): “I never use stop orders to buy” — contradicted by fills.  
- Drift toward **limits** was **account size / slippage**, not a beginner rule.  
- **Hotkeys:** he says he never used them (Sterling, mouse). Not the edge.

**Desk note:** Schwab path already uses working orders. Buy-stops at ORH are closer to his practice than discretionary click-chase.

---

## Two things “nobody argues about”

### Entry is not one click

Up to **~1 in 4** entries is a **scale-in** (not stop-out + new idea). Conservative end **~1 in 7**.

Examples from streams: PM starter + 1m ORH + add on 5m; half size PM, add full on OR **low** takeout. **EPs ~2× as likely to be scaled** as breakouts.

### A stop-out is not the end

If stopped and the stock **retests highs**, he **re-enters ~half the time**. About **1 in 8** of all entries is a **same-day second attempt**. Messy: buy → stopped → buy ⅓ size → add.

A stop is the **cost of one attempt**, not a verdict on the thesis.

**Desk tension:** our OMS **2 round-trips per symbol per day** already allows a second attempt. Pulse **2-loss sleeve halt** is harsher than his “go again.” Do not “fix” Pulse to match this without deciding Pulse vs swing Qullamaggie.

---

## Three numbers to keep

1. **< 4 in 10** finishes green at any OR window. Median trade = **full stop**. Median hold **1–3 days**. Expectancy is positive **only because of the tail**.  
2. He had **31 losers in a row**. If you cannot sit that, none of the dials matter.  
3. **The stop converts the move into R.** Every table changes with stop width. ADR line and OR window are the **same decision** (how much room / how much risk).

**Move stop to breakeven:** he tested day 3 / 5 / 10 vs original stop on Qullamaggie’s own entries — framed as **comfort, not profit**. (Chart on the original post.)

---

## Pre-market

Stated: “almost never” / “pre-market is for gamblers and tiny accounts” (2021-01-04). Actual: not never. Conditions he agrees with: **liquid, EP, real catalyst, small size**. Muninn: PM can have edge for **small accounts** under those filters.

---

## What is Qullamaggie vs common knowledge

ORH + stop under LOD is used by **Dan Zanger, Jeff Sun, much of Traderlion**. Several refuse to pick one entry time. First-30-minute clustering is **when breakouts happen**, not a secret.

**Entry time is not the edge. The trigger is common. The work is making the dials fit.**

**Counterpoint:** @jfsrev waits **30 minutes** after the open from **8 years of his own data**. Same problem, opposite conclusion. Trading is hard.

---

## Nine changes Muninn lists

1. Stopped hunting the “correct” entry time. Picked one dial end.  
2. **Risk first**; stop from chart; size last (not fixed shares then discover R).  
3. Stop-out ≠ idea dead. ~⅓ of entry days stop; he goes again ~half the time.  
4. Uses **buy-stops** (also works for 9–5).  
5. Tests every rule; untested guru-speak is discarded.  
6. Measures **ADR extension** first — not for a ceiling, to avoid **too-early** noise stops (91% die < 0.25 ADR). Above 1 ADR = own judgment.  
7. **Different entry for EPs vs breakouts.**  
8. Stopped mourning trades that got away; real leak is **worse fills + wider stops** on names you still take.  
9. Stopped treating **BE move** as risk management.

---

## Implementation later (do not ship without tests)

| Dial | Possible desk hook | Do not |
|------|--------------------|--------|
| OR window | Config on `orb_vwap` / Pulse levels | Hard-code 30m as “correct” |
| EP vs BO | Separate window / size for gap/EP | Same 1m ORB on EPs |
| Extension | Tag `day_range/ADR`; size-cut <0.25 or >1 | Fixed 4% chase rule |
| Scale-in | Optional add on 5m after 1m starter | Ignore 2-RT / cash rails |
| Re-entry | Already: 2 RT/symbol on OMS | Pulse 2-loss sleeve halt ≠ this |
| BE | Optional comfort trail; not default edge | Call BE “risk management” |

---

## Source

- https://x.com/Muninn/status/2088292776047751193  
- Author: James Muninn (@Muninn). Qullamaggie quotes from his streams (2019–2021 dates as cited in the post).  
- Captured 2026-08-18 for `trading_agent` notes.
