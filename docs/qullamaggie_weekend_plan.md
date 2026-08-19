# Weekend plan: Qullamaggie / Muninn dials on our desk

**Do this weekend. Do not flip LIVE defaults until the offline checks pass.**

**Source study:** [Muninn @ 2088292776047751193](https://x.com/Muninn/status/2088292776047751193) · notes in `docs/qullamaggie_entry_dials.md`  
**Gap (have / not have):** see that doc + the table below.

We are **not** cloning his 2019–22 equity swing book. We add **three measured dials** onto paths we already have, keep Pulse sleeve-halt and OMS 2-RT rails, and leave scale-in / BE-as-edge / “copy 30m OR” out.

---

## What we already have (do not rebuild)

| Piece | Where | Keep |
|-------|--------|------|
| 30m ORB+VWAP research BT | `sleeves/orb_vwap.py` | Extend window as **config**, still research until promoted |
| Daily ORB *proxy* in ranking | `strategy/competition.py` `orb_vwap_*` | Stay a proxy; do not pretend it is a 1m OR |
| Min ADR% volatility gate | `analysis/strength.py`, `screener_params.py` | Floor for “does it move”; **not** extension-from-low |
| Structure / LFD / ATR stops | `analysis/lfd_breakout.py` | Still primary geometry for options book |
| Risk-defined size | OMS `max_risk_dollars` | Keep |
| 2 RT **per ticker** (desk) | `oms/pretrade.py` | Second attempt allowed; not Pulse |
| Pulse 2-loss **sleeve** halt | Mac Pulse + `scalp/pulse_halt.py` | Different product; do not “fix” to match Qullamaggie rebuy |
| Named Pulse halt card | `scalp/pulse_halt.py` | Already shipped |

---

## What we will not implement this weekend

- Copy his **LOD + 10-day MA** hold as the live options exit (wrong instrument).
- Declare **30m** (or 1m) the “correct” OR.
- **Scale-in** (PM + 1m + 5m adds) — conflicts with `max_symbol_lots=1` until we design it.
- Treat **move-to-BE** as risk management / default trail.
- Resting **buy-stop on ORH** as Pulse default (optional later; Schwab path is enough).
- Pre-market EP tiny-size live path.
- Fat-tail “best 5% = 99% R” live filter.
- Changing Pulse **sleeve halt** to “rebuy half the time.”

---

## Weekend build (priority order)

Ship as **flag-off** extras. Default desk behavior unchanged until a flag is on.

### P1 — ADR extension at entry (highest value)

**Problem:** We gate *how volatile the name is* (`min_adr_pct`). We do **not** measure *how much of today’s range is already used* vs ADR. Muninn: **too early** (&lt;0.25 ADR off the low) dies (~91% stopped); his live band is ~0.33–0.68 ADR (median 0.47); &gt;1 ADR is outside his rule — **size down**, don’t skip.

**Build**

1. Helper `trading_agent/analysis/extension.py` (or add to `strength.py`):

   ```
   adr_used = (entry - session_low) / ADR    # longs
   adr_used = (session_high - entry) / ADR   # shorts
   ```

   ADR = same lookback as screener (20). Session low/high = RTH so far (or prior bar if pre-break).

2. Tag on candidates / book rows:

   - `adr_used`
   - `adr_bucket`: `lt_025` | `025_050` | `050_100` | `gt_100`
   - `extension_note`

3. Policy (env, default **soft**):

   | Bucket | Weekend default |
   |--------|-----------------|
   | `lt_025` | **size_cut** 0.5× (stop in noise) — do not hard-block |
   | `025_050` / `050_100` | full size (his band) |
   | `gt_100` | **size_cut** 0.5× (or 0.2× if we add a chase flag) — do not skip |

   Flags: `TRADING_AGENT_ADR_EXTENSION=1` to apply size cuts on book/CIO. Off = tag only.

4. Discord / CIO: one line `ADR used 0.41 (band)` so we can see it live.

**Files:** `analysis/extension.py`, `ranking/ranker.py` or `export/auto_trade_book.py`, `cio/` size path, `tests/test_extension.py`.

**Done when:** fixture name shows `adr_used` + bucket; flag off → same size as today; flag on → &lt;0.25 and &gt;1.0 cut size; tests for long/short math.

---

### P2 — OR window as a **dial** (research sleeve only)

**Problem:** `orb_vwap.py` hard-codes **30m** (two 15m bars). Muninn: window is a dial (1m faster / more R / more stops vs 30m slower / higher WR / half mean R). We need the **table**, not a winner declared.

**Build**

1. Config: `or_minutes: 5 | 15 | 30` (1m later if we have 1m bars; yfinance 15m cannot do 1m).
2. CLI: `research methods-backtest --method orb --or-minutes 15,30` (or repeat).
3. Report columns: trades, WR, mean R, total R — **same symbols / period**, only window changes.
4. Optional: count **skipped** names that broke 15m ORH but not 30m ORH (his “filter vs cost” point). Tag only.

**Do not** wire a new window into live Pulse or CIO this weekend.

**Files:** `sleeves/orb_vwap.py`, `__main__.py` methods-backtest args, `docs/methods_sleeves_backtest.md` (append a weekend run).

**Done when:** one command prints 15 vs 30 side by side; defaults still 30m; no live path change.

---

### P3 — EP vs breakout (split the dial)

**Problem:** Same fast window **punishes episodic pivots** in his tables. We already tag news/gap/catalyst. We do **not** change entry window or size for EP vs clean breakout.

**Build**

1. Classifier (reuse news + gap book):

   - `ep` if gap + named catalyst (earnings / contract / upgrade) or existing gap-continuation tag
   - else `breakout`

2. On book / CIO notes: `setup_family=ep|breakout`.
3. Soft policy (flag `TRADING_AGENT_EP_SLOW=1`, default **off**):

   - EP: prefer **slower** confirmation (15–30m range or skip 1m-style Pulse chase); optional 0.5× size
   - Breakout: unchanged

4. ORB BT (P2) split WR/mean R **by family** if we can label historically (gap day = EP proxy).

**Files:** small `analysis/setup_family.py` or `discipline/`; ranker/book tag; tests with fixture gap vs no-gap.

**Done when:** CRWD-style gap handoff shows `ep`; quiet breakout shows `breakout`; flag off → no size/window change.

---

### P4 — Wire tags into CIO / Discord only (no new live strategy)

After P1–P3 exist:

- CIO governance line: `ADR 0.41 · family=ep · OR research=30m`
- Auto-trade book fields: `adr_used`, `adr_bucket`, `setup_family`
- Do **not** change stay-in-cash, DTE, or Pulse halt.

**Done when:** one dry-run session JSON includes the three fields; bit-identical book if all new flags are 0.

---

## Explicit non-goals (write on the whiteboard)

| Tempting | Why not this weekend |
|----------|----------------------|
| Promote ORB sleeve to LIVE | Still net-negative in our own BTs; window dial first |
| Pulse rebuy after 2 losers | Product is a day-halt scalp bot, not his swing |
| Scale-in / pyramid | Needs `max_symbol_lots` redesign + cash |
| 1m ORB live | Need 1m data; yfinance path is 15m |
| Hard-block &gt;1 ADR | His own data does not punish; he sizes down |
| Hard-block &lt;0.25 ADR | Size-cut first; measure before we DQ |

---

## Suggested Saturday / Sunday split

**Saturday (code, flags off)**

1. P1 helper + tests + book tags  
2. P2 OR minutes config + 15 vs 30 report  
3. P3 family tag + tests  

**Sunday (observe, then maybe flags)**

1. Dry-run desk (`session --fixture --dry-run` or live dry-run) — confirm tags  
2. Run ORB 15 vs 30 on QQQ/SPY/IWM + a gap-heavy name; paste table into `docs/methods_sleeves_backtest.md`  
3. Only if numbers look sane: turn `TRADING_AGENT_ADR_EXTENSION=1` on **paper / dry-run** (size cuts only)  
4. Leave `TRADING_AGENT_EP_SLOW` off until we see a week of `setup_family` tags  

---

## Acceptance (end of weekend)

- [ ] `docs/qullamaggie_entry_dials.md` still matches what we built (update if we diverge)
- [ ] Flags default **off** → existing tests + book unchanged
- [ ] `adr_used` / `adr_bucket` / `setup_family` on book or CIO notes
- [ ] ORB 15 vs 30 table checked in (not used as a live switch)
- [ ] Pulse halt card still names tickers (`pulse_halt.py`)
- [ ] No change to Pulse 2-loss sleeve halt or OMS 2-RT-per-symbol without a separate decision

---

## Owner notes

- Implement on **`trading_agent`** (`C:\Personal\Grok\trading_agent` / Mac clone).  
- Mac Pulse import of `pulse_halt` is already documented in `docs/screener.md` — still needs the one-liner in `~/.grok/scripts/scalp-market-pulse.py` if not done.  
- If time dies: **P1 only**. Extension-from-low is the only dial that would have changed his (and our) “am I too early / am I chasing?” on the same day.
