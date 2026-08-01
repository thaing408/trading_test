# Quant / institutional roadmap + fully auto-trade gaps

**Source conversation:** [AI Trading: Quant Institutions Guide](https://grok.com/share/bGVnYWN5_a49fc10b-6dec-4bb0-ba5f-d62144f8ec23) (2026-07-31)  
**Repo context:** multi-phase options desk (`trading_agent`) with dual Windows research / macOS execute.  
**Related:** `docs/options_auto_trade.md`, `docs/dual_system.md`, `docs/backtest_findings.md`

This document is the checked-in future-development plan. It has two parts:

1. **Institutional train→trade goals** (from the shared guide)  
2. **Missing pieces for ultimate fully auto trade** on *this* stack (research → book → place → manage → exit → journal)

---

## Part A — How institutions automate (summary)

Institutions treat AI as **one layer** inside a scientific + engineering pipeline—not “train a net on prices and trade.”

### Five layers

| Layer | Role |
|-------|------|
| **Data** | Market + alt data; point-in-time; no look-ahead; quality is the moat |
| **Research / signals** | Features → forecasts (returns/vol/regime/NLP); GBMs, sequence models, ensembles |
| **Decision / portfolio** | Sizing, allocation, constraints; sometimes sequential / RL-style |
| **Execution** | Separate impact/slippage models; slice/route |
| **Production** | Ingest → research → backtest → serve → live → monitor; drift, kill switches, compliance |

### Practical pipeline

1. Define edge / hypothesis  
2. Data + rigorous preprocessing  
3. Features + labels (horizon-aligned, cost-aware)  
4. Model training (supervised / RL / ensembles)—**after** classical baselines  
5. Walk-forward / purged validation with costs and regimes  
6. Paper → live with risk controls and drift retrain  
7. Orchestration, registries, monitoring  

### Explicit failure modes

Non-stationarity · overfitting · costs/impact · data leakage · competition · black-box/compliance  

### Guardrails for this desk

- Prefer **process, risk, and execution** over flashiest models  
- LLMs are useful for research cards / orchestration—not unchecked core alpha  
- No model bypasses book / grade / RiskConfig without explicit opt-in  
- Dual-system: work = research only; home = local brokerage; no secret/position sync  

---

## Part B — Goal catalog (G0–G7)

### G0 — North star

| ID | Goal |
|----|------|
| G0.1 | Research integrity: every edge has hypothesis, data, labels, costs, validation |
| G0.2 | Capital preservation first: rails dominate model output |
| G0.3 | Dual-system safety preserved |
| G0.4 | Ship with offline score deltas vs baselines |
| G0.5 | Explainable signals for Discord / CIO |

### G1 — Data

| ID | Goal |
|----|------|
| G1.1 | Point-in-time store (as-of joins; ban leakage) |
| G1.2 | Corporate actions + survivorship / universe history |
| G1.3 | Multi-provider OHLCV/news with quality metrics |
| G1.4 | Cost/liquidity surfaces (ADV, spread, options greeks history) |
| G1.5 | Versioned session artifact schemas |
| G1.6 | Optional alt-data adapters (later) |

### G2 — Research / signals

| ID | Goal |
|----|------|
| G2.1 | Hypothesis registry (named edges + params + regime) |
| G2.2 | Versioned feature engineering module |
| G2.3 | Labeling framework (e.g. +1R before stop, net of costs) |
| G2.4 | Classical baselines must be beaten before ML ships |
| G2.5 | Optional supervised models (GBM) behind feature store |
| G2.6 | Regime detection feeding risk throttle |
| G2.7 | NLP as **features**, not trade authority |
| G2.8 | Deep RL production **deferred** until G3 mature |

### G3 — Backtest & validation (highest leverage)

| ID | Goal |
|----|------|
| G3.1 | Historical engine (real OHLCV; synthetic for unit fixtures) |
| G3.2 | Transaction costs + slippage model |
| G3.3 | Walk-forward evaluation on desk decision path |
| G3.4 | Purged / embargoed CV for ML |
| G3.5 | Multi-regime + crisis report cards |
| G3.6 | Full metrics suite (Sharpe, Sortino, Calmar, expectancy, PF, DD, turnover) |
| G3.7 | Promotion gate before “shipped default” |
| G3.8 | Live session replay from session JSON |

### G4 — Portfolio

| ID | Goal |
|----|------|
| G4.1 | Constraint-aware construction (sector/beta/cluster caps) |
| G4.2 | Dynamic sizing (vol/confidence/grade/regime) |
| G4.3 | Optional ML ranker only if it beats current ranker under G3 |
| G4.4 | Day + portfolio heat / cash controller |
| G4.5 | RL allocation sandbox only (after G3 + G4.1–4.4) |

### G5 — Execution

| ID | Goal |
|----|------|
| G5.1 | Ready-order quality + pre-trade checks |
| G5.2 | Slippage accounting in journal → feeds G3 |
| G5.3 | TWAP/VWAP-style scheduling for larger equity |
| G5.4 | Options multi-leg / partial-fill integrity |
| G5.5 | Kill switch / flatten |

### G6 — Production

| ID | Goal |
|----|------|
| G6.1 | Orchestration hardening (launchd / Task Scheduler) |
| G6.2 | Versioned config/model registry + changelog |
| G6.3 | Drift / degradation monitors |
| G6.4 | Always-on paper book parallel to live |
| G6.5 | Scheduled re-sweep; human approve promotion |
| G6.6 | Observability (fills, rejects, gate reasons) |
| G6.7 | Immutable audit trail for ENTER/REJECT |

### G7 — Desk product

| ID | Goal |
|----|------|
| G7.1 | Discord CIO loop stays excellent |
| G7.2 | Playbooks expand only with offline evidence |
| G7.3 | Discovery multi-pass **with** gates |
| G7.4 | Performance proposes params; never auto-applies without G3.7 |
| G7.5 | Provider phase mapping complete + tested |
| G7.6 | Optional literature mapping notes |

### Phasing

| Phase | Focus | Exit criteria |
|-------|--------|----------------|
| **A** | Honest rules path: historical + costs, promotion, replay | Cost-aware offline of current gates; promotion checklist |
| **B** | Feature store + classical ML rank | Walk-forward beat-or-fail baseline; paper book ≥ N weeks |
| **C** | Execution polish; optional RL sandbox | Slippage calibrated; kill switch tested |

### First work packages (Phase A)

1. Historical backtest data path (real OHLCV + costs; keep synthetic fixtures)  
2. Promotion report template (metrics, regimes, gates ON/OFF)  
3. Hypothesis registry for existing playbooks  
4. Session replay CLI  
5. Journal slippage fields  

---

## Part C — Current auto-trade stack (what exists)

End-to-end path today:

```text
Research / QT / gap  →  auto_trade_book*.json  →  consume_auto_trade_book.py
                              ↓
                    ready_orders_YYYY-MM-DD.json
                              ↓
              LIVE=1 ?  schwab-mcp place_order  :  dry-run / TOS hand entry
                              ↓
              Intraday desk (alerts / PT-SL recs)  — mostly advisory
                              ↓
              Performance / journal (local Mac)
```

| Stage | Implementation | Automation level |
|-------|----------------|------------------|
| Signal generation | Screener, strength, books, MTF, options methods, CIO, QT, gap | High (scheduled desk) |
| Eligibility | `auto_trade_eligible`, defined risk, risk package, rails | High |
| Book export | `export/auto_trade_book.py`, QT export, gap books | High |
| Consumer | `scripts/macos/consume_auto_trade_book.py` + `export/mac_execute.py` | High (windowed) |
| Live place | Single-leg debit OCC BUY_TO_OPEN; equity BUY market | **Partial** |
| Multi-leg / credit | `ready` only → human TOS | **Manual** |
| Brackets / OCO at broker | Not placed with entry | **Missing** |
| Auto exits | Intraday **recommends**; scalp bot separate; no general SELL_TO_CLOSE loop tied to books | **Partial / missing** |
| Fill confirm + state | No durable OMS position state from order id | **Missing** |
| Kill switch flatten | Risk alerts, not broker flatten-all | **Missing** |
| Paper parallel book | Dry-run default; not full paper P&amp;L twin | **Partial** |

### Live place matrix (shipped)

| Package | Auto-submit when `TRADING_AGENT_AUTO_TRADE_LIVE=1`? |
|---------|------------------------------------------------------|
| Single-leg debit (1 strike, CALL/PUT, expiration) | Yes — market BUY_TO_OPEN |
| Simple equity buy | Yes — market BUY (no bracket) |
| Multi-leg (IC, spreads, 2+ strikes) | No — ready_orders / TOS |
| Credit / short premium | No — ready_orders / TOS |
| Equity short | No |

Schwab MCP `place_order` today is **single-instrument** (one symbol, one instruction). Instructions include BUY_TO_CLOSE / SELL_TO_CLOSE / SELL_TO_OPEN, but the desk consumer does not implement a full multi-leg order graph or exit OMS.

Separate path: MCP `auto_trade_qqq` scalp bot (level rules + exits) — not the same as desk book consumer.

Fail-closed defaults remain correct: no live without env/`--live`; dual-system air gap preserved.

---

## Part D — Missing pieces for **ultimate fully auto trade**

“Ultimate” here means: **no required human for entry, risk, exit, or day halt**, with auditability and recovery. Gaps are ordered by blocking severity.

### D1 — Critical blockers (cannot claim full auto without these)

| # | Missing piece | Why it blocks | Target |
|---|---------------|---------------|--------|
| **D1.1** | **Multi-leg order builder + submit** | Desk alpha is largely defined-risk spreads/IC; live path only does single-leg debit | Schwab multi-leg order spec (or sequential legs with atomicity policy) in MCP + `mac_execute` |
| **D1.2** | **Credit / short-premium path** | Bull put / bear call / IC are core playbooks; currently TOS-only | Safe SELL_TO_OPEN + long hedge legs, buying-power checks, defined-risk validation pre-submit |
| **D1.3** | **Entry + protective exit at fill** | Entries are naked market; stop/target not at broker | Bracket / OCO / separate stop+target working orders after fill confirm |
| **D1.4** | **Auto exit engine (OMS loop)** | Intraday posts recommendations; does not systematically SELL_TO_CLOSE / BUY_TO_CLOSE | State machine: open lot → monitor → exit instructions → confirm flat |
| **D1.5** | **Fill / order lifecycle tracking** | No durable map order_id → working/filled/rejected → position | Poll orders + positions; reconcile; retry policy; never double-enter |
| **D1.6** | **Pre-trade account gates** | Size from max_risk only; weak BP / existing exposure / open-order checks | Buying power, max contracts, max open risk, symbol cluster, day loss halt before submit |
| **D1.7** | **Global kill switch → flatten** | Alerts exist; no one-button / auto flatten-all on feed loss or DD breach | Halt flag + cancel working + close all (or all auto-trade tags) |

### D2 — High priority (safe automation quality)

| # | Missing piece | Notes |
|---|---------------|--------|
| **D2.1** | Limit / mid-based options entry (not market-only) | Reduce slip; quote check max spread before cross |
| **D2.2** | Partial-fill handling | Multi-leg integrity; cancel remainder; never leave one-legged risk |
| **D2.3** | Idempotent consume | Processed fingerprints + broker client order id; restart-safe |
| **D2.4** | Intraday re-entry / discovery → live | Discovery promotes to CIO; wire eligible ENTER to consumer continuously (not only 9:25–11:00 ET window) with rate limits |
| **D2.5** | Position source of truth | Prefer Schwab `get_positions` over stale files for exit logic |
| **D2.6** | Journal from broker fills | Auto-append closed trades (setup_id, grade, slip) for Performance |
| **D2.7** | Daily loss / Kiev halt enforced at **submit** | `daily_loss_halt` exists on rails; must hard-block consumer + cancel entries |
| **D2.8** | Quote freshness / data-feed kill | No place if quotes stale or MCP down |

### D3 — Medium (institutional completeness)

| # | Missing piece | Notes |
|---|---------------|--------|
| **D3.1** | Paper trading twin | Same books → paper account or simulated fills with realistic slip |
| **D3.2** | Cost model from live slip | Calibrate G3.2 from journal (G5.2) |
| **D3.3** | Capacity / liquidity gates at submit | OI, bid-ask, ADV already partially in options methods—re-check at T0 |
| **D3.4** | Config promotion gate | No LIVE default flip without offline + paper thresholds (G3.7) |
| **D3.5** | Continuous watch consumer | Full RTH watch (not only morning window) with max orders/day |
| **D3.6** | Rollback / cancel API | Cancel working on strategy invalidate |
| **D3.7** | Multi-account / account hash selection | Explicit account for live |
| **D3.8** | Compliance audit log | Immutable JSONL of every submit/skip/exit reason (G6.7) |

### D4 — Later / optional (scale & research)

| # | Missing piece |
|---|---------------|
| **D4.1** | Smart equity execution (TWAP/VWAP) for larger size |
| **D4.2** | ML ranker for ENTER priority (Phase B only after baselines) |
| **D4.3** | RL execution sandbox |
| **D4.4** | Alt data |
| **D4.5** | Unify desk consumer with `auto_trade_qqq` scalp state (one OMS) |

### D5 — Explicit non-goals for “full auto”

| Non-goal | Reason |
|----------|--------|
| LLM free-form place without gates | Hallucination / leakage risk |
| Bypass defined-risk for speed | Capital preservation |
| Work PC places Schwab orders | Dual-system hard rule |
| Auto-promote RiskConfig from one good day | Overfit |

---

## Part E — Target fully auto architecture

```text
                    ┌─────────────────────────────┐
                    │  Research / QT / Discovery   │
                    │  (gates, books, eligibility) │
                    └──────────────┬──────────────┘
                                   │ ENTER intents (versioned)
                                   ▼
                    ┌─────────────────────────────┐
                    │  Intent bus (local books)    │
                    │  + fingerprint / idempotency │
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  Pre-trade risk service      │
                    │  BP, heat, day-loss, quotes   │
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  Execution adapter (Schwab)  │
                    │  multi-leg · credit · debit  │
                    │  limit/mid · brackets/OCO    │
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  OMS state store             │
                    │  orders · fills · lots       │
                    └──────────────┬──────────────┘
                                   ▼
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   ┌────────────────────┐                  ┌────────────────────┐
   │ Exit / manage loop │                  │ Kill switch        │
   │ PT/SL · time · roll│                  │ flatten + halt     │
   └─────────┬──────────┘                  └────────────────────┘
             ▼
   ┌────────────────────┐
   │ Journal + slip     │──► Performance ──► (proposals only)
   └────────────────────┘
```

All of this stays **Mac-local** for live; Windows continues research-only code + Discord.

---

## Part F — Suggested implementation order (auto-trade specific)

### Auto Phase 0 — Safety spine (before more LIVE volume)

1. Order/fill state store + idempotent consume (**D1.5**, **D2.3**)  
2. Pre-trade BP / heat / day-loss / quote freshness (**D1.6**, **D2.7**, **D2.8**)  
3. Kill switch halt flag (cancel + no new entries) (**D1.7** partial)  
4. Audit JSONL (**D3.8**)  

### Auto Phase 1 — Close the loop on what we already place

5. After single-leg debit / equity fill: place stop (+ target) or manage loop with SELL_TO_CLOSE (**D1.3**, **D1.4**)  
6. Broker positions as truth for open lots (**D2.5**)  
7. Journal from transactions (**D2.6**)  
8. Limit/mid entry option (**D2.1**)  

### Auto Phase 2 — Desk strategy completeness

9. Multi-leg builder (**D1.1**)  
10. Credit spreads with defined-risk checks (**D1.2**)  
11. Partial-fill / one-leg protection (**D2.2**)  
12. Flatten-all kill (**D1.7** complete)  

### Auto Phase 3 — Always-on desk

13. Full-RTH consumer + discovery ENTER rate limits (**D2.4**, **D3.5**)  
14. Paper twin (**D3.1**)  
15. Slip → cost model → promotion gate before raising LIVE risk (**D3.2**, **D3.4**)  

### Auto Phase 4 — Research upgrades (parallel track)

16. Historical cost-aware backtest + promotion (Part B Phase A)  
17. Feature store / ML rank only after baselines (Part B Phase B)  

---

## Part G — Definition of done: “fully auto trade”

All of the following must be true for a **named strategy class** (e.g. single-leg debit, then credit spreads):

1. **Entry:** eligible book row → pre-trade pass → broker submit without human, within limits  
2. **Protect:** stop (and target or manage rules) active within seconds of fill  
3. **Exit:** rules or risk breach closes via broker API; lot marked flat  
4. **Halt:** day-loss / feed-loss / kill flag stops new risk and can flatten  
5. **Audit:** every skip/submit/exit has immutable reason + ids  
6. **Reconcile:** restart mid-day does not double-enter; positions match broker  
7. **Evidence:** offline + paper promotion for that strategy class  

Until **D1.1–D1.7** are done for the strategies you actually trade, the honest status is:

> **Semi-auto:** high automation on research + single-leg debit/equity entries; multi-leg/credit and full lifecycle still require human or separate scalp tooling.

---

## Part H — Open product choices

1. First fully-auto strategy class: **single-leg debit** (shortest path) vs **credit spreads** (true desk product)?  
2. Protective exits: **broker OCO/bracket** vs **software manage loop** (poll + close)?  
3. Paper twin: Schwab paper account vs internal simulator?  
4. Unify `auto_trade_qqq` with desk OMS or keep separate?

**Default recommendation:** finish Auto Phase 0–1 for single-leg debit + equity (close the loop safely), then Auto Phase 2 multi-leg/credit for the real options book. Run research Phase A in parallel so LIVE risk is evidence-based.

---

## Implementation status (started 2026-08-01)

| Area | Status | Where |
|------|--------|--------|
| OMS state store | **Shipped** | `trading_agent/oms/state.py` |
| Audit JSONL | **Shipped** | `trading_agent/oms/audit.py` |
| Kill switch | **Shipped** | `trading_agent/oms/kill_switch.py` + `python -m trading_agent oms kill` |
| Pre-trade gates | **Shipped** | `trading_agent/oms/pretrade.py` |
| Consume → OMS | **Shipped** (default `TRADING_AGENT_OMS=1`) | `oms/pipeline.py`, `export/mac_execute.run_consume` |
| Multi-leg package in ready_orders | **Shipped** | `oms/multileg.py` (sequential live **opt-in only**) |
| Software exit manage loop | **Shipped** | `oms/exits.py` + `oms manage` |
| Journal slippage fields | **Shipped** | `journal/trades.py` |
| Hypothesis registry | **Shipped** | `research/hypotheses.py` |
| Promotion checklist | **Shipped** | `research/promotion.py` |
| Session replay | **Shipped** | `research/replay.py` |
| Backtest costs | **Shipped** | `backtest` `--slippage-bps` / `--commission` |
| True atomic multi-leg MCP | **Not yet** | needs schwab-mcp multi-leg API |
| Broker OCO brackets | **Not yet** | software stops only |
| Historical OHLCV loader | **Shipped** | `backtest/historical.py` (Schwab/yfinance; synthetic fallback) |
| Walk-forward desk BT | **Shipped** | `backtest/walk_forward.py` + embargo between train/test |
| Feature store v1 + labels | **Shipped** | `features/builder.py`, `features/labels.py` (PIT features; forward labels) |
| Linear ranker vs baseline | **Shipped** | `ml/ranker.py` — **never auto-promotes to LIVE** |
| Full PIT corporate-actions store | **Not yet** | features are bar-local only |
| GBM / deep models | **Not yet** | ridge linear only (numpy) |

### CLI

```bash
python -m trading_agent oms status
python -m trading_agent oms kill --reason "halt" --flatten
python -m trading_agent oms clear-kill
python -m trading_agent oms manage
python -m trading_agent oms consume --anytime
python -m trading_agent research hypotheses
python -m trading_agent research replay ~/.trading_agent/sessions/YYYY-MM-DD
python -m trading_agent research walk-forward --synthetic
python -m trading_agent research walk-forward --period 1y
python -m trading_agent research features
python -m trading_agent backtest --single --slippage-bps 5 --commission 1
python -m trading_agent backtest --historical --period 1y --walk-forward
```

## Changelog

| Date | Note |
|------|------|
| 2026-08-01 | Initial check-in from shared quant guide + codebase auto-trade audit |
| 2026-08-01 | OMS Phase 0–1 + multileg packages + research tools implemented |
| 2026-08-01 | Phase B start: historical OHLCV, walk-forward, features/labels, linear ranker gate |
