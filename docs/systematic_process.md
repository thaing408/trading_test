# Systematic trading process (desk runbook)

Based on Julian Komar’s video  
[How to Become a Systematic Stock Trader: My Complete 5-Step Trading Process](https://www.youtube.com/watch?v=vwveCYGwM8c)  
(~45 min; also shared via [X](https://x.com/BlogJulianKomar/status/2085728431791083749)).

**Thesis:** You usually need a **repeatable process**, not another strategy. Judgment works **inside structure**.

---

## North star

| Chaotic | Systematic |
|---------|------------|
| Many stocks, endless info | Ranked focus list; say no often |
| Strategy-hopping when hard | One strategy, improved over time |
| Discretion under pressure | Written rules consulted under stress |
| Plan during RTH | Prepare before open; RTH = execute only |
| Memory as journal | Document **decisions**, not only P/L |

**Weekly metrics:** win rate · avg winner · avg loser · risk/trade · setup quality · market regime · **rule violations** · emotional decisions.

**Time goal:** once filters are stable, aim for a focused daily loop (~30 minutes of deliberate work is the aspirational benchmark from the video).

---

## Five steps (every step needs written rules)

Weakness in one step damages the next.

### 1. Read the market
- Define a regime model → **trade | light | cash**.
- Only trade when the environment matches where your edge works.
- **Deliverable:** one-liner — `Regime=… → Bias=…` + reason.

### 2. Select the right stocks
- Fixed selection criteria + screener/ranker (same every day).
- Small ranked focus list; reject almost everything.
- **Don’t** buy from social feeds or invent names after the open.
- **Deliverable:** ranked list (e.g. top 5–15) with pass notes.

### 3. Prepare every trade
- Before the open: entry trigger · stop · size/risk · exit plan · invalidation.
- Cash-bias day → empty action list.
- **Deliverable:** trade cards (symbol · trigger · stop · size · exit · why).

### 4. Execute clear rules
- During RTH: **execution only** (buy/sell/manage per plan).
- No re-screening, re-research, or redesign mid-session.
- Log rule breaks immediately for review.
- **Deliverable:** fills/management that match prep cards.

### 5. Review and improve
- Journal: charts, setup grade, regime, emotions, **rule violations**.
- Weekly: find patterns; every rule must answer *why does this exist?*
- Expect months for habit change (often ~3 months first progress).
- **Deliverable:** weekly notes + 0–3 process tweaks.

---

## Daily cadence

| When | Steps | Actions |
|------|-------|---------|
| Pre-market | 1 → 2 → 3 | Regime → ranked list → trade cards |
| Open → close | 4 | Execute / manage only |
| After close | 5 (light) | Log trades, violations, emotions |
| End of week | 5 (deep) | Metrics table + one process tweak |

### Weekly checklist
- [ ] Regime model clear (trade / light / cash)?
- [ ] Selection criteria unchanged and evidence-based?
- [ ] Prep cards complete before open?
- [ ] Execution compliance (count rule violations)?
- [ ] Journal complete for all trades?

---

## Decide in advance

1. What matters (criteria)  
2. What qualifies (pass/fail)  
3. How much you risk  
4. When you act  
5. When you exit  
6. How you learn  

---

## Map to this repo (`trading_test`)

| Step | Agent / desk concept |
|------|----------------------|
| 1 Read market | Day bias, regime, `stay_in_cash` / environment score |
| 2 Select stocks | Screener, researcher books, ranked opportunities, top-winners pool |
| 3 Prepare | `auto_trade_book`, ready orders, trade cards |
| 4 Execute | OMS consume + manage (fail-closed unless live) |
| 5 Review | Performance pipeline, journal, manage/audit logs |

Automation must **encode** these steps—not invent discretion after the open.

### Process runbook CLI (implemented)

State: `~/.trading_agent/process/YYYY-MM-DD.json`  
(or `TRADING_AGENT_PROCESS_DIR`)

```text
# Score all 5 steps + probe desk books / OMS / journal
python -m trading_agent process status

# Step 1 — regime
python -m trading_agent process regime --bias trade --regime "bull trend" --reason "SPY > 21 EMA"

# Step 2 — focus list
python -m trading_agent process focus NVDA,AMD,META,PLTR

# Step 3 — trade card
python -m trading_agent process card --symbol NVDA \
  --trigger "10:00 VWAP reclaim" --stop "OR low" --size "0.5R" --exit "trail + time 11:30"

# Step 4 — log a rule break
python -m trading_agent process violation "resized without rule after open"

# Step 5 — review note
python -m trading_agent process note "Two trades; one FOMO entry — flag violation"

python -m trading_agent process init   # create empty day file
```

### OMS pretrade process gate (implemented)

New entries via OMS consume are **fail-closed** unless Steps 1–3 pass.

| Condition | Reason code |
|-----------|-------------|
| Bias not set | `process_bias_unset` |
| Bias = cash | `process_cash_bias` |
| Step 1 score low | `process_step1_incomplete:…` |
| Step 2 score low | `process_step2_incomplete:…` |
| Step 3 score low | `process_step3_incomplete:…` |

**Env**

| Env | Default | Meaning |
|-----|---------|---------|
| `TRADING_AGENT_PROCESS_GATE` | `1` (on) | Enable process gate in pretrade |
| `TRADING_AGENT_PROCESS_MIN_STEP` | `50` | Min score for steps 1–3 |
| `TRADING_AGENT_PROCESS_REQUIRE_BIAS` | `1` | Require trade\|light\|cash |
| `TRADING_AGENT_PROCESS_BLOCK_CASH` | `1` | Block entries when bias=cash |
| `TRADING_AGENT_PROCESS_PROBE` | `1` | Include desk books in scoring |

Disable gate (legacy heat-only pretrade):

```text
set TRADING_AGENT_PROCESS_GATE=0
```

Blocked orders are audited as `order_pretrade_block` with `process_gate` detail; `oms status` / consume start snapshot includes `process_gate`.

### Suggested desk commands (existing phases)
```text
# Step 1–3 style research / prep (Windows research host)
python -m trading_agent premarket
python -m trading_agent cio

# Step 2 / experimental playbook (paper)
python -m trading_agent odte --mode top-winners

# Step 4 manage (only when intentionally live)
python -m trading_agent oms manage

# Step 5
python -m trading_agent performance
```

---

## 30-day adoption

| Week | Focus |
|------|--------|
| 1 | Write regime rules + selection checklist; journal template |
| 2 | Forced prep cards; RTH = execute only |
| 3 | Count rule violations; cut one discretionary habit |
| 4 | Simplify rules; lock one exit method (e.g. trail) |

**Process done when:** you can state tomorrow’s routine in under a minute; every trade has a pre-open card; every close is journaled; weekly metrics include violations and regime.

---

## Out of scope

- Guaranteed profits  
- Replacing your edge—only organizing how you run it  
- Live auto-trade unless you explicitly enable it  
