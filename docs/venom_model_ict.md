# ICT Venom Model — Analysis Notes

## Canonical source (original)

| Field | Value |
|-------|--------|
| **Title** | 2025 Lecture Series — ICT Venom Model Tutorial \| 04/03/2025 |
| **Channel** | [The Inner Circle Trader](https://www.youtube.com/channel/UCtjxa77NqamhVC8atV85Rog) (ICT) |
| **URL** | https://www.youtube.com/watch?v=7wL2oyebbvU |
| **Length** | ~43 minutes |
| **Published** | ~2025-04-04 (lecture date labeled 04/03/2025) |
| **Scale** | ~160k+ views · official teacher material |

This is the **original Venom Model tutorial**. Study this before any clip/repost.

### Secondary / derivative media

| Media | Role |
|-------|------|
| [JeRRy MMXM X post](https://x.com/JeRRyMMXM/status/2087572772159357370) (2026-08-12) | Promo clip (~18 min amplify) — “EXPOSED… 123% accuracy” marketing, not the full lecture |
| [JeRRy earlier X](https://x.com/JeRRyMMXM/status/2074872591483805840) | Same author pointing at ICT Venom |
| [ICT Gems — ICT Teaches Venom Model](https://www.youtube.com/watch?v=6KjDaYGm4dY) | Explicitly cites `7wL2oyebbvU` as source (~18 min cut) |
| Community notes / TradingView / FX Replay Venom writeups | Checklists distilled from the same lecture series |

**Doc purpose:** Anchor the desk to the **official ICT lecture**, separate hype from process, and map Venom to our PA stack.  
**Not:** a full word-for-word transcript of the 43-minute video (not available in-session). Steps below = standard reconstruction from ICT 2025 Venom public material + lecture metadata.

---

## 1. What the X *repost* claims (not ICT’s wording)

| Claim (post text) | Analysis |
|-------------------|----------|
| “EXPOSED, AND FOR FREE! THE VENOM MODEL” | Marketing framing: ICT concept packaged as a free “model” breakdown. |
| “ICT A+ SETUP MODEL WITH **123% ACCURACY**” | **Not a valid statistical claim.** Accuracy cannot exceed 100% for binary win/loss. “123%” is hype / engagement bait, not a backtest metric. |
| “If ICT charged $15,000 … still worth every penny” | Social proof / FOMO language; no data attached in the post text. |
| Long video attachment | Study asset; without transcript, implement from **public ICT Venom** structure (below), then refine if/when you scrub the video yourself. |

**Engagement signal:** High bookmarks vs replies → people save it as a checklist more than debate it.

**Reply noise:** “@grok translate the video” (Arabic) — demand for transcription exists; still no official text model in the thread.

---

## 2. What the Venom Model *is* (public ICT / community reconstruction)

The **ICT Venom Model (2025 lecture series)** is an **intraday NY-session** model, mainly discussed on **US indices** (NQ/ES/YM). It is a timed **liquidity sweep of a pre-open range**, then **structure + FVG/BPR** for entry — same family as Power of 3 (AMD: accumulation → manipulation → distribution).

### Core time window (New York local)

| Phase | Time (ET) | Role |
|-------|-----------|------|
| **Venom Box / Initial range** | **08:00 – 09:30** | Mark session high/low of this 90-minute window |
| **Cash open / manipulation** | **~09:30** | Expect sweep of box high **or** low (stop run) |
| **Delivery / distribution** | After open | Reversal / expansion after sweep + confirmation |

Be at the screen by **08:00 ET**; model is LTF (often 1m–5m) execution after the box is known.

### Building blocks (checklist)

1. **Mark the Venom Box**  
   - High = max high 08:00–09:30 ET  
   - Low = min low 08:00–09:30 ET  

2. **Bias (optional but preferred)**  
   - HTF narrative (daily/1H structure, prior day high/low, economic calendar).  
   - Venom still often traded as **reaction to the box sweep** even with soft bias.

3. **At/after 09:30: liquidity sweep**  
   - Price **takes** box high (buy-side liquidity) **or** box low (sell-side liquidity).  
   - Sweep = wick/trade through then failure to hold outside (classic stop-hunt narrative).

4. **Displacement + inefficiency**  
   - Strong move back **inside** the box / opposite direction after the sweep.  
   - Look for **FVG** (and often **BPR / balanced price range** — overlapping FVGs / BISI+SIBI pairing in community notes).

5. **Structure confirmation**  
   - **MSS** (market structure shift) and/or **CISD** (change in state of delivery) on LTF.  
   - Do not chase the first tick of the open; wait for shift + discount/premium array.

6. **Entry**  
   - Common variants in public writeups:  
     - **Retest of FVG / BPR** after MSS/CISD  
     - **Engulfing / “Venom breakout” candle** open as aggressive trigger  
   - Stop: beyond the sweep extreme (or structure swing).  

7. **Target / management**  
   - Opposite side of Venom Box  
   - Fixed **~2R** (some prop-style notes: no management, fixed TP)  
   - Or scale at opposing liquidity / session levels  

### Bullish sketch

```
08:00–09:30: box forms
09:30+: sweep BELOW box low (sell-side raid)
→ bullish displacement + FVG/BPR
→ MSS/CISD up
→ long on FVG retest / confirmation
→ targets: box mid/high, then buy-side above box
```

### Bearish sketch

```
08:00–09:30: box forms
09:30+: sweep ABOVE box high (buy-side raid)
→ bearish displacement + FVG/BPR
→ MSS/CISD down
→ short on FVG retest / confirmation
→ targets: box mid/low, then sell-side below box
```

---

## 3. Honest evaluation of the post’s “accuracy” framing

| Issue | Note |
|-------|------|
| **123% accuracy** | Ignore as quantitative truth. Use for entertainment only. |
| **Survivorship / selection** | Free promo videos cherry-pick clean days (indices, clean range, clean sweep). |
| **Session dependence** | Model is **NY open–centric**; poor fit for pure cash-session equity swing or covered-call income. |
| **Asset class** | Taught on futures indices; equity names (IREN/SPCX/CSCO) may not print the same 08:00–09:30 “Venom Box” dynamics (premarket vs RTH). |
| **Overlap with existing edge** | Sweep + FVG + structure is already in our PA stack; Venom mainly adds a **strict clock + named box**. |

**Useful takeaway:** Venom is a **time-boxed process** (when to mark levels, when to expect the raid), not a magic win-rate.

---

## 4. Map to our stack (`trading_test` / `trading_agent` PA)

| Venom idea | Existing module / concept |
|------------|---------------------------|
| Venom Box high/low | Opening-range / session levels; extend with explicit **08:00–09:30 ET** window |
| Sweep of box | `pa.sweep` / stop-hunt labels in `analysis.patterns` |
| FVG | `pa.fvg` |
| Structure shift | `pa.structure` (BOS/CHoCH proxy for MSS) |
| Multi-method confluence | Require-two already prefers multi-engine agreement |
| Fixed 2R | Risk package / measured move targets |

**Optional future method id:** `venom_ny` — only if we implement the **08:00–09:30 ET box + 09:30 sweep + FVG/MSS** gate on 1m/5m (indices first). Not required for weekly CC income research.

---

## 5. Process checklist (if you trade Venom manually)

**Before 08:00 ET**

- [ ] Calendar (FOMC, CPI, NFP) — skip or size down if binary  
- [ ] HTF bias note (optional)  

**08:00–09:30 ET**

- [ ] Draw Venom Box high/low; do not enter yet  

**09:30 onward**

- [ ] Identify which side was swept  
- [ ] Wait for displacement + FVG/BPR  
- [ ] Wait for MSS/CISD  
- [ ] Entry only on retest or defined trigger candle  
- [ ] Stop beyond sweep extreme  
- [ ] Target opposite box liquidity or fixed R  

**Journal**

- [ ] Box range size (pts/%)  
- [ ] Sweep side  
- [ ] Entry type (FVG retest vs breakout candle)  
- [ ] R multiple achieved  
- [ ] Was HTF aligned?  

---

## 6. Relationship to other desk work

| Desk work | Venom relevance |
|-----------|-----------------|
| Multi-method / PA (15m) | Partial overlap (sweep/FVG); **missing** hard 08:00–09:30 clock unless added |
| Swing scan (daily) | Low overlap |
| Weekly CC income (IREN/SPCX/CSCO) | **Different job** — stock-backed premium, not NY open scalp |
| Researcher watchlist | Could flag “Venom candidates” only for index ETFs (QQQ/SPY) if we ever code the box |

---

## 7. Sources

| Source | Role |
|--------|------|
| **[ICT Venom Model Tutorial 04/03/2025](https://www.youtube.com/watch?v=7wL2oyebbvU)** | **Original / primary** — full ~43m lecture |
| [X post 2087572772159357370](https://x.com/JeRRyMMXM/status/2087572772159357370) | Social clip + hype claims (“123% accuracy”) |
| [ICT Gems cut](https://www.youtube.com/watch?v=6KjDaYGm4dY) | Shorter re-upload citing the official video |
| Public explainers (innercircletrader.net Venom 2025, TradingFinder, FX Replay) | Checklist aids after watching ICT |

---

## 8. Bottom line

- **Original material:** ICT’s own [Venom Model Tutorial](https://www.youtube.com/watch?v=7wL2oyebbvU) (~43 min, 2025 lecture series).  
- **X post:** compressed/promotional clip of that ecosystem — ignore “123% accuracy.”  
- **Model core:** **90m range 08:00–09:30 ET → 09:30 liquidity sweep → FVG/BPR + MSS/CISD → entry → box/2R targets**.  
- Desk use: process/time discipline; optional future `venom_ny` on indices; **not** the same job as weekly CC income or CIO equity book.

---

## 9. Can we code it? (feasibility)

**Yes — a mechanical v1 is codeable.** We already have most building blocks; Venom is mainly **timed wiring**: box + sweep + FVG/BPR + structure + fixed R.

### Spec from original lecture + public formalizations (FX Replay / community)

| Element | Mechanical rule (v1) |
|---------|----------------------|
| **Venom Box** | High/low of bars in **08:00–09:30 ET** (90m) |
| **Trigger window** | From **09:30 ET** open onward (session NY AM) |
| **Sweep** | Trade through box high **or** low then fail/reclaim (liquidity raid) |
| **BPR** | Two overlapping FVGs (bullish + bearish) after displacement — *community formalization of lecture idea* |
| **Entry A** | Limit on **BPR retest**; SL at recent swing / beyond sweep |
| **Entry B** | **Venom breakout:** strong engulfing that inverts initial FVG; SL at engulf open |
| **TP** | Fixed **2R** (simple prop-style); optional opposite box extreme |
| **Invalidation** | 2R hit before entry; or cannot achieve 2R before opposite range side |

Official video ([7wL2oyebbvU](https://www.youtube.com/watch?v=7wL2oyebbvU)) is narrative + chart examples (e.g. NQ 1m, opening range / 9:30 context). We cannot get a full timestamped transcript in-session; **FX Replay / public checklists** give the first codable rule table; refine after manual scrub of the lecture.

### What we already have vs net-new

| Piece | Status |
|-------|--------|
| Time-sliced OR / session HL | Partial — `odte/breakout.py` uses **30m RTH OR (9:30+)**, **not** 08:00–09:30 Venom Box |
| Sweep + reclaim | Yes — `pa.sweep` |
| FVG | Yes — `pa.fvg` |
| Structure / BOS | Yes — `pa.structure` |
| Fixed R targets | Yes — multi-method / risk package |
| **BPR detector** | **New** |
| **08:00–09:30 box + 09:30 sweep gate** | **New** |
| Engulf invert FVG entry | **New** (small) |

### Recommended v1 build

- **Repo:** `trading_test` (methods lab, no CIO)  
- **Module:** `trading_agent/pa/venom.py`  
- **Symbols first:** QQQ / SPY (1m or 5m; premarket required)  
- **CLI:** `research venom-backtest --symbol QQQ --period 60d`  
- **Later:** multi-method id `venom_ny` (optional weight)

```text
day loop:
  box = HL(bars in [08:00, 09:30) ET)
  for bars after 09:30:
    if sweep_low + bull FVG/BPR + structure up → long (BPR retest or engulf)
    if sweep_high + bear FVG/BPR + structure down → short
    SL beyond sweep; TP = 2R (and/or box opposite)
```

### What we should not claim

- Bit-identical to ICT’s discretionary reading of every chart  
- “123% accuracy” or any unverified win rate  
- Works on weekly CC names (IREN/SPCX/CSCO income) — different product  

### Effort

| Scope | Effort |
|-------|--------|
| Detectors + unit tests | ~0.5–1 day |
| Historical BT + report | ~0.5 day |
| Multi-method / Discord card | ~0.5 day |

**Verdict: Code it — yes.** Encode checklist rules above as v1; backtest QQQ; only then promote to live research cards.

### Implemented (v1)

| Piece | Location |
|-------|----------|
| Detectors | `trading_agent/pa/venom.py` |
| Backtest | `trading_agent/strategy/venom_backtest.py` |
| CLI | `python -m trading_agent research venom-backtest` (default **QQQ,SPY**) |
| Tests | `tests/test_venom.py` |

```bash
python -m trading_agent research venom-backtest
python -m trading_agent research venom-backtest QQQ,SPY --period 59d --interval 5m
python -m trading_agent research venom-backtest --no-structure -o venom_bt.md
```

---

*Generated for desk research. Not financial advice. Verify any rule against your own journal and official ICT lectures before size.*
