# Plan: TradingAgents (arXiv 2412.20138) vs `trading_agent`

**Paper:** Xiao, Sun, Luo, Wang — *TradingAgents: Multi-Agents LLM Financial Trading Framework* (arXiv:2412.20138v7, 3 Jun 2025). Code: https://github.com/TauricResearch/TradingAgents  
**Ours:** phase desk (intelligence → research → CIO → preopen → intraday → performance → evening scan), options/PA/multi-method books, rule CIO + risk gates, Discord/OMS.

**Implementation status:**  
- **P0 shipped** — schemas/roles/empty reports/ReAct + `TRADING_AGENT_FIRM` (default off).  
- **P1 shipped** (2026-08-17) — four analysts with live gathers + heuristic reports; optional xAI (`XAI_API_KEY`) enrichment. P2+ still later.

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
| **Sentiment** | News-tone proxy (`gather_social`) until X/Reddit; optional LLM polish |
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
Still **only shortlist** (`TRADING_AGENT_FIRM_MAX_SYMBOLS`, default 5). Debate/trader/risk remain P2–P4 stubs.

### P2 — Researcher debate (fully missing)

- Bull researcher: only argues long/add from analyst reports.
- Bear researcher: only argues fade/avoid/risks.
- Facilitator: N rounds (config `FIRM_DEBATE_ROUNDS`, default 2–3), then structured verdict (`winner`, `confidence`, `open_risks`).
- **Do not** let debate bypass stay-in-cash / ADR / liquidity rails.

### P3 — Trader agent (partially missing)

- Today: scanners emit ENTER with method scores.
- Add: LLM trader consumes **four reports + debate verdict + our book geometry** → BUY / SELL / HOLD, size hint, timing.
- Output must include ReAct-style reasoning for Discord.
- Map to existing `auto_trade_book` fields (`action`, `side`, `thesis`, `confidence`) without dropping options structure (spreads, DTE, defined risk).

### P4 — Risk debate + manager (partially missing)

- Add three risk personas (aggressive / neutral / conservative) debating the **trader proposal vs live book** (vol, liquidity, correlation, open exposure).
- Facilitator + **CIO/manager** applies adjustment (cut size, tighten stop, veto).
- Keep **deterministic vetoes** (cash floor, max risk %, earnings hard block) as last word.

### P5 — Data gaps vs paper dataset

| Feed | Status | Later work |
|------|--------|------------|
| Prices / TA | Strong | Package a named **60-indicator** bundle for the tech analyst |
| News | Partial (yfinance/FMP) | Point-in-time daily cache for backtest |
| Social / X / Reddit | **Absent** | Optional collectors; degrade cleanly |
| Insider / Form 4 | Keywords only | Structured insider series |
| Financial statements | Thin yfinance | Deeper FMP/filings when keys exist |
| Economic calendar | Often omitted (paid FMP) | Paid plan or alternate calendar |
| Breadth (A/D, NH/NL) | Marked unavailable | Optional if we get a feed |

### P6 — Evaluation (paper §5–6)

- Daily **no-look-ahead** replay: firm sleeve vs B&H / MACD / KDJ+RSI / SMA / **our current multi-method**.
- Metrics already close: CR, AR, Sharpe, MDD in `performance/` / `backtest/` — add a **firm-sleeve** report.
- Cap universe and dates (paper used ~3 months, 3–5 names) because of LLM cost.
- Export decision sequences for audit (paper footnote on extreme Sharpe).

### P7 — Product integration (ours, not in paper)

- **Feature flag** `TRADING_AGENT_FIRM=0` default.
- Firm runs **after** research scanners, **before** CIO, on ranked symbols only.
- CIO still owns Approve/Modify/Reject.
- Discord: compact “firm card” (4 report bullets + debate winner + risk adjust).
- Never let firm output skip OMS/export eligibility / DTE policy.

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
