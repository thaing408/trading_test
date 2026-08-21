# Plan: TradingAgents (arXiv 2412.20138) vs `trading_agent`

**Paper:** Xiao, Sun, Luo, Wang — *TradingAgents: Multi-Agents LLM Financial Trading Framework* (arXiv:2412.20138v7, 3 Jun 2025). Code: https://github.com/TauricResearch/TradingAgents  
**Ours:** phase desk (intelligence → research → CIO → preopen → intraday → performance → evening scan), options/PA/multi-method books, rule CIO + risk gates, Discord/OMS.

**Implementation status:**  
- **P0–P7 shipped** (2026-08-17) — firm sleeve end-to-end under `trading_agent/firm/` with flag `TRADING_AGENT_FIRM` (default off).  
- Live OMS / multi-method desk unchanged unless `TRADING_AGENT_FIRM_BOOK_MERGE=1`.

---

## What the paper actually specifies

A simulated **trading firm** of specialized LLM agents, not a single prompt.

| Team | Roles | Job |
|------|--------|-----|
| Analysts | Fundamental, Sentiment, News, Technical | Gather + write **structured reports** |
| Researchers | Bull, Bear, debate facilitator | **N-round NL debate** on analyst reports; facilitator records prevailing view |
| Trader | One trader | BUY/SELL/HOLD + size/timing from reports + debate |
| Risk | Risky / Neutral / Safe + facilitator | N-round debate on trader proposal vs volatility/liquidity/exposure |
| Fund manager | Approves, adjusts, executes | Final state update + execution |

**Communication:** hybrid — structured documents as the source of truth (avoid “telephone effect”); NL only inside debates. Shared global agent state. ReAct (think → tool → act).

**Data (paper §5.2):** OHLCV; news (Bloomberg/Yahoo/EODHD/FinnHub/Reddit); social + sentiment (X/Reddit + aux LLM scores); insider/SEDI; statements/earnings; company profiles; **~60 technical indicators**.

**LLM routing:** “quick” models for retrieval/summarization; “deep” models for analysis, debate, trade, risk. Analysts/researchers/traders = deep; tool I/O = quick.

**Eval:** daily walk-forward Jan–Mar 2024, no look-ahead; signals BUY/SELL/HOLD; metrics CR, AR, Sharpe, MDD vs B&H, MACD, KDJ+RSI, ZMR, SMA. Short window (~3 months); ~11 LLM + 20+ tool calls per prediction.

---

## What we already have (do not rebuild)

| Paper idea | Our analog | Notes |
|------------|------------|--------|
| Technical analysis | `analysis/technical.py`, PA (`soulz`, FVG, sweep), multi-method router, 888 TI panel | Rule/quant, not an LLM analyst report |
| News ingest | `collectors/news.py` (FMP + yfinance + keyword categories) | Headlines + tags; no reasoned news thesis |
| Market / macro snapshot | `synthesis/`, `intelligence.json` (futures, VIX, sectors, DXY, catalysts) | Rule scoring; calendar often omitted (FMP paid) |
| Fundamentals numbers | `fundamentals/quality.py` (PE, margin, growth, D/E, earnings proximity) | Live books often show **`fundamental_score: 0.0`** — path exists, underfed |
| Trader + book | Multi-method / gap / playlist / CIO candidates → `auto_trade_book.json` | Thesis strings are method tags, not debate synthesis |
| Risk team (partial) | `risk/manager.py`, CIO stay-in-cash, ADR/EMA/52w gates, concentration in `cio/portfolio.py` | **Hard rules**, no aggressive/neutral/conservative debate |
| Fund manager | `cio/pipeline.py` Approve / Modify / Reject + allocation | Deterministic; no LLM review of risk debate |
| Execution | OMS, Schwab/IBKR, Mac consumer, manage JSONL | **Beyond** the paper (paper is sim-only) |
| Backtest | `backtest/` walk-forward, sleeves, CR-style reports | Rule/method backtests, not LLM daily replay |
| Explainability | Discord reports, rejection reasons, book `thesis`/`notes` | Machine-readable but not ReAct traces |

**Architecture mismatch (important):** we are a **rule + scan desk** with a CIO gate. The paper is **role-specialized LLMs + structured reports + two debate loops**. We should **add an optional sleeve**, not replace CIO/risk rails or live OMS.

---

## Gaps (missing vs paper) — implement later

### P0 — Firm graph + structured state (foundation) — **DONE**

Package: `trading_agent/firm/` (`roles`, `reports`, `protocol`, `state`, `tools`, `react`, `runner`).

1. **Agent role contracts** — `roles.py` (`FIRM_ROLES`)  
2. **Structured empty reports** — under `~/.trading_agent/sessions/{date}/firm/{symbol}/`  
3. **ReAct stub loop** — tool registry stubs + thought/tool/observation log  

```bash
# Dry-run write (even with flag off)
python -m trading_agent firm --symbol AAPL --force

# Enable on desk (after research scanners, before CIO) — still empty reports until P1
echo 'TRADING_AGENT_FIRM=1' >> ~/.grok/trading-agent.env
```

Flag off → orchestrator hook is a no-op (bit-identical book).

### P1 — Analyst team — **DONE (heuristics + optional LLM)**

| Agent | Implementation |
|-------|----------------|
| **Fundamental** | `gather_fundamentals` (yfinance score) → `FundamentalReport`; LLM narrative if `XAI_API_KEY` |
| **Sentiment** | News-tone + Reddit JSON (`gather_social`); optional LLM polish. Crowd score is informational, never auto-ENTER. |
| **News** | `collect_news_catalysts` → name/macro lists; optional LLM “what moves next” |
| **Technical** | OHLCV + `analysis.technical` bundle → regime/bias/timing; optional LLM write-up |

```bash
# Heuristics only (no LLM)
TRADING_AGENT_FIRM_LLM=0 python -m trading_agent firm --symbol AAPL --force

# Heuristics + SpaceXAI/xAI enrichment
export XAI_API_KEY=...
TRADING_AGENT_FIRM=1   # optional: enable on desk shortlist
python -m trading_agent firm --symbol AAPL --force
```

Env: `TRADING_AGENT_FIRM_LLM` (default 1), `TRADING_AGENT_FIRM_LLM_MODEL` (default `grok-4.5`).  
Still **only shortlist** (`TRADING_AGENT_FIRM_MAX_SYMBOLS`, default 5). Risk/manager remain P4 stubs.

### P2 — Researcher debate — **DONE**

Module: `trading_agent/firm/debate.py`.

- Bull / bear opening points from P1 reports; N rounds of rebuttal (`TRADING_AGENT_FIRM_DEBATE_ROUNDS`, default **2**).
- Facilitator scores → `winner` (`bull`|`bear`|`draw`), `confidence`, `open_risks` (always includes `advisory_only_hard_rails_still_apply`).
- Optional LLM polish of the verdict when `XAI_API_KEY` set.
- Artifacts: `debate_verdict.json`, `debate_transcript.json`; firm card `status=p2_debate`.

```bash
TRADING_AGENT_FIRM_LLM=0 python -m trading_agent firm --symbol AAPL --force --no-llm
```

### P3 — Trader agent — **DONE**

Module: `trading_agent/firm/trader.py`.

- Consumes P1 reports + P2 debate (+ optional `auto_trade_book` geometry).
- Emits `TraderProposal`: BUY/SELL/HOLD, side, size_hint, timing, confidence, thesis, `book_hints.react_reasoning`.
- Maps to book fields via `proposal_to_book_fields` (BUY→ENTER, HOLD→ineligible, SELL/Bearish→ENTER put path).
- Optional merge: `TRADING_AGENT_FIRM_BOOK_MERGE=1` patches sync book (default **off**).
- Still does **not** place orders; OMS/DTE/cash unchanged.

```bash
python -m trading_agent firm --symbol AAPL --force --no-llm
# enable book patch (careful on LIVE Mac):
# echo 'TRADING_AGENT_FIRM_BOOK_MERGE=1' >> ~/.grok/trading-agent.env
```

### P4 — Risk debate + manager — **DONE**

- `risk_debate.py`: aggressive/neutral/conservative votes + facilitator; deterministic earnings/open-lot vetoes.
- `manager.py`: approve/modify/reject/defer + `cio_handoff`.
- Firm card includes risk + manager; trader size/action adjusted on veto/cut.

### P5 — Data gaps — **PARTIAL (packaged + degrade-clean)**

| Feed | Status |
|------|--------|
| Prices / TA | **`firm_ta_pack_v1`** (~40–60 features) in `indicators.py` / `data_pack.json` |
| News | Existing collectors |
| Social | News-tone + public Reddit JSON (`gather_social` / `SentimentReport.reddit`). X still absent. Informational only. |
| Insider | News-category proxy |
| Calendar | `gather_calendar` → empty/unavailable without paid FMP |
| Breadth | Explicitly `unavailable` in pack |

### P6 — Evaluation — **DONE (day audit)**

- `eval.py`: `evaluate_firm_day` / `eval_report.json` — BUY/SELL/HOLD counts, vetoes, agreement vs multi-method ENTERs.
- CLI: `python -m trading_agent firm --eval-only --date YYYY-MM-DD`

### P7 — Product integration — **DONE**

- Flag `TRADING_AGENT_FIRM=0` default; desk hook after scanners / before CIO.
- Discord firm cards opt-in: `TRADING_AGENT_FIRM_DISCORD=1` or `firm --post-discord`.
- Eligibility: manager reject/defer / risk veto → `oms_eligible=false` (no silent OMS skip of DTE/cash).

```bash
python -m trading_agent firm --symbol AAPL --force --no-llm
python -m trading_agent firm --eval-only --date 2026-08-17
```

---

## Recommended later implementation order

1. **State + schemas + flag** — empty reports, no LLM, CIO unchanged.
2. **Technical + news analyst** — reuse existing collectors; first real LLM reports.
3. **Fundamental analyst** — fix zero scores + narrative.
4. **Bull/bear + facilitator** — one symbol e2e (e.g. AAPL fixture).
5. **Trader proposal → book merge**.
6. **Risk trio + manager overlay** on CIO.
7. **Sentiment/social** when a legal/cheap feed exists.
8. **Walk-forward firm backtest** vs current sleeves.
9. **Cost controls** — cache reports per symbol/date; skip HOLD-only names.

---

## Out of scope / do not copy blindly

- Paper results are a **short, costly, single-regime** backtest; do not treat 26% CR / SR 8 as a target.
- Paper is **equity long/short sim**; we are **options + defined risk + live desk**. Keep our instrument model.
- Do not replace rule risk with LLM-only risk.
- Do not run full firm graph on the entire scan universe (34+ names) — cost and latency.
- Social scrapers: respect TOS; start optional.

---

## Success criteria (when we implement)

- Per-symbol `firm/` artifacts for a fixture date.
- CIO can cite `debate.winner` and `risk.adjustment` in governance notes.
- `fundamental_score` non-zero when yfinance info exists.
- Feature flag off → bit-identical book vs today.
- Small walk-forward: firm sleeve metrics logged next to multi-method.

---

## Source map (ours)

- Desk phases: `README.md`, `session/`
- CIO: `trading_agent/cio/pipeline.py`
- Risk: `trading_agent/risk/`
- News: `trading_agent/collectors/news.py`
- Fundamentals: `trading_agent/fundamentals/quality.py`
- Synthesis: `trading_agent/synthesis/`
- Books: `export/auto_trade_book.py`
- Live artifacts: `~/.trading_agent/sessions/{date}/`
