# How we raise same-day WR (C) — experiment ladder

LIVE already executes **C2: `chart_patterns` only** (~65.5% n=29 on 60d synth).  
We do **not** add methods or poll faster. Each extra gate is **BT → paper → LIVE flag**.

Promote only if **WR up** and **n ≥ 15** on 60d, then **same direction** on 10d Schwab.

## Phase 0 — already shipped (do not revert)

- Split books: same-day vs swing
- Same-day execute = `chart_patterns` only
- Swing sidecar, no PUT, no 0DTE

## Phase 1 — backtest extra gates (this week)

Same 60d 15m load as C2. Variants:

| ID | Gate | Why |
|----|------|-----|
| T | SPY SMA10≥SMA20 and VIX≤20 **as-of prior close** | Live WR desk tape (not in old C BT) |
| N1 | Max **1** name/day (highest pattern score) | Starve book, keep best |
| R | 15m RVOL ≥ 1.5 at 15:00 | Skip dead breakouts |
| W | Wait: pattern PLAY **yesterday too** (no first fire) | Retest / confirmation |
| Combos | T+N1, T+W | Stack only if singles help |

**Not in Phase 1** (heavier): real OCC marks, Grok veto.

Script: `scripts/ablate_wr_c.py` (raise block at bottom of `docs/wr_c_ablation_60d.md`).

### Phase 1 result (60d Yahoo, 2026-08-21)

| Gate | n | WR | Ship? |
|------|---|----|--------|
| C2 patterns only | 29 | 65.5% | already LIVE execute |
| **T tape** | **12** | **83.3%** | **Phase 2** (n thin; LIVE already has `WR_TAPE=1`) |
| **N1 1 name/day** | **22** | **68.2%** | **Phase 2** — next flag to add |
| R RVOL≥1.5 | 4 | 50% | kill |
| W wait yesterday | 4 | 50% | kill |
| T+N1 | 10 | 80% | after T and N1 each confirm |
| T+W / +R stacks | 1–2 | noise | kill |

Tape is **already default on** in `evaluate_wr_enter` (`TRADING_AGENT_WR_TAPE=1`). Old C BT ignored it, so **live same-day may already look more like T than C2**. Confirm consumer logs `wr_tape_*` skips before adding N1.

## Phase 2 — 10d Schwab confirm

Winners from Phase 1 only, `source=schwab` 10d. If WR drops or n&lt;5, **do not ship**.

### Phase 2 result (10d Schwab 15m, 14 names, 2026-08-21)

Artifact: `docs/wr_c_ablation_schwab10d.md`.

| Gate | n | WR | vs 60d Yahoo | Verdict |
|------|---|----|----------------|---------|
| C2 patterns only | 8 | **87.5%** | 65.5% n=29 | baseline |
| T tape | 8 | **87.5%** | 83% n=12 | **Same as C2** this window (tape was push every day). No contradiction. **Already LIVE.** |
| N1 1 name/day | 5 | **100%** | 68% n=22 | WR **up** both feeds, but **n=5** on Schwab — **do not ship LIVE**. Paper only if we want it. |
| T+N1 | 5 | 100% | 80% n=10 | same as N1 this window |
| R / W | 2 / 0 | — | failed 60d | stay **killed** |

**Ship from Phase 2:** nothing new. Keep C2 + existing tape.

**Next:** Phase 3 paper for N1 is optional (`TRADING_AGENT_WR_MAX_PER_DAY=1` still not wired). Skip LIVE N1 until a longer Schwab window or paper fills ≥8.

## Phase 3 — paper (`trading_test` / IBKR)

Env only, default off on LIVE:

```bash
# already default: chart_patterns execute
TRADING_AGENT_WR_DESK=1
TRADING_AGENT_WR_TAPE=1          # T
TRADING_AGENT_WR_MAX_PER_DAY=1   # N1 (if BT wins)
```

**Wired:** `TRADING_AGENT_WR_MAX_PER_DAY` (default **0 / off**).  
Export keeps top-N same-day names by technical score; OMS skips extras (`wr_max_per_day`). Swing book uncapped.

Enable **paper only** (`trading_test` / me-ai `~/.trading_test/trading-test.env`):

```bash
TRADING_AGENT_WR_MAX_PER_DAY=1
```

Watch `#ibkr-tradings` 3–5 sessions: fills, skips `wr_max_per_day`, realized WR vs C2.

## Phase 4 — LIVE Mac (only after 2+3)

One flag at a time in `~/.grok/trading-agent.env`. Keep a kill switch: `TRADING_AGENT_WR_DESK=0` restores old export (not recommended).

## Kill rules

- Faster scanners / more methods / AI “find more” — already **failed** (~50% WR)
- n collapses below ~1 trade/week — gate is too tight, park it
- Paper WR < C2 by >10 pts over ≥8 fills — revert

## Later (not blocking)

- **Real option marks in BT** — honest WR, likely **lower**; use before retuning TP/SL
- **Grok veto** — LLM may **reject** a C2 name, never invent one; log vetoes vs outcome
- **Failed-break geometry** in `score_chart_pattern_entry` (retest bar) if W wins in BT
