# Auto-trade next steps (Mac `trading_agent`)

**Last updated:** 2026-08-15  
**Audience:** continue Monday after multi-method no-CIO export (P1) and process-bias / book-protect land on `main`.

Related:

- [`options_auto_trade.md`](options_auto_trade.md) — LIVE path, env flags, multi-method auto-export  
- [`DESK_UI_AUTO_TRADE.md`](DESK_UI_AUTO_TRADE.md) — operator UI  
- [`quant_institution_roadmap.md`](quant_institution_roadmap.md) — long-horizon G0–G7  

Paper stack on me-ai is **`trading_test`** (separate repo); this file is **Mac production desk**.

---

## Already shipped (do not re-do)

| Item | Notes / commit area |
|------|---------------------|
| Process day bias auto-set from desk research/scanners | Avoids `process_bias_unset` |
| Protect multi-method ENTERs from empty cash/discovery overwrite | `TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK=1` (default) |
| **P1** Multi-method EXPORT → `auto_trade_book` **without CIO** | `TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT=1` (default); desk scanners write ENTERs |
| Desk UI + `desk-status` CLI | Optional `[desk-ui]` extra |

```bash
cd ~/trading_agent && git pull   # expect 8b9bb48+ (or later)
```

---

## P0 — Monday proof (ops checklist, no new code)

Run after RTH open path; fix from logs before building P2.

### Before open (once)

```bash
cd ~/trading_agent && git pull && git log -1 --oneline
# LIVE should already be on if you place orders:
grep TRADING_AGENT_AUTO_TRADE_LIVE ~/.grok/trading-agent.env
```

### After desk ~01:55–05:30 PT

| Check | Command / path | Pass if |
|-------|----------------|---------|
| Bias set | `cat ~/.trading_agent/process/$(TZ=America/Los_Angeles date +%Y-%m-%d).json` | `"bias"` is `trade` / `light` / `cash` (not empty) |
| Book has ENTERs | `~/.trading_agent/sync/auto_trade_book.json` | `entry_count > 0` **or** intentional cash |
| Multi-method export note | desk log / Discord scanners | text like `auto_trade_book (multi-method, no CIO required): N ENTER` |

```bash
DAY=$(TZ=America/Los_Angeles date +%Y-%m-%d)
python3 -c "
import json
from pathlib import Path
b=json.loads(Path.home().joinpath('.trading_agent/sync/auto_trade_book.json').read_text())
print('entries', b.get('entry_count'), 'cash', b.get('stay_in_cash'), 'policy', b.get('export_policy'))
print('syms', [e.get('symbol') for e in (b.get('entries') or [])[:12]])
p=Path.home()/'.trading_agent'/'process'/'$DAY.json'
print('process', p.read_text()[:400] if p.exists() else 'MISSING')
"
```

### After consumer ~06:25 PT

| Check | Path | Pass if |
|-------|------|---------|
| Consumer log | `~/.trading_agent/logs/auto-trade-consumer_$DAY.log` | not only `NO ORDERS — empty books`; gate not stuck on `process_bias_unset` |
| Ready orders | `~/.trading_agent/ready_orders/ready_orders_$DAY.json` | `order_count` / skips with reasons / submitted |

```bash
DAY=$(TZ=America/Los_Angeles date +%Y-%m-%d)
tail -80 ~/.trading_agent/logs/auto-trade-consumer_${DAY}.log
python3 -c "
import json
from pathlib import Path
p=Path.home()/'.trading_agent'/'ready_orders'/f'ready_orders_{Path.home()}'
" 2>/dev/null
ls -la ~/.trading_agent/ready_orders/ready_orders_${DAY}.json
python3 -c "
import json
from pathlib import Path
import os
day=os.popen('TZ=America/Los_Angeles date +%Y-%m-%d').read().strip()
p=Path.home()/'.trading_agent'/'ready_orders'/f'ready_orders_{day}.json'
d=json.loads(p.read_text()) if p.exists() else {}
print('orders', d.get('order_count'), 'skipped', d.get('skipped_count'), 'live', d.get('live'))
for o in (d.get('orders') or [])[:8]:
    print(' ', o.get('symbol'), o.get('status'), o.get('skip_reason') or (o.get('broker_response') or {}).get('status'))
"
```

**If P0 fails:** capture log snippets; do not enable multileg LIVE until book + consumer path is green.

---

## P2 — Ops reliability + execution quality (next code)

Implement after Monday proof (or if P0 shows consumer dies / silent MCP fail).

### P2.1 Mac consumer watchdog

| | |
|--|--|
| **Gap** | Paper (`trading_test` me-ai) has `paper-consumer-watchdog`; Mac LaunchAgent only starts ~06:25 — if it fails, no auto restart |
| **Done means** | LaunchAgent or cron-like interval Mon–Fri ~06:30–13:00 PT: if consumer not running and book has ENTERs (or always in window), restart + log |
| **Ref** | `trading_test/scripts/me-ai/paper-consumer-watchdog.sh` |

### P2.2 Discord ops alerts at open

| | |
|--|--|
| **Gap** | Failures stay in local logs only |
| **Done means** | Post to desk/auto-trade Discord channel when any of: consumer start fail, `process_bias_unset`, `entry_count=0` at 06:30 with scanners that claimed EXPORT, Schwab MCP / OAuth error, kill switch on |
| **Keep short** | One message with reason + path to log |

### P2.3 Schwab OAuth / MCP health

| | |
|--|--|
| **Gap** | `LIVE=1` does nothing useful if token expired |
| **Done means** | Morning check (existing `com.grok.morning-check` / schwab remind) explicitly fails consumer preflight; Discord if refresh needed before 06:25 |

### P2.4 Mac awake for desk + consumer

| | |
|--|--|
| **Gap** | Sleeping Mac skips 01:55 / 06:25 |
| **Done means** | Confirm awake agents / power settings; document “desk host must be awake” in install script output |

### P2.5 Schwab option contract qualify

| | |
|--|--|
| **Gap** | Paper IBKR now qualifies contracts + min DTE; Schwab place path can still submit bad OCC / DTE / liquidity |
| **Done means** | Pre-place: resolve option symbol, reject if missing, enforce min DTE/OI/spread; surface `skip_reason` on ready_orders |

### P2.6 Book merge clarity

| | |
|--|--|
| **Gap** | Consumer merges desk + QT + gap + session; Discord PLAY ≠ winning book |
| **Done means** | Consumer log + optional Discord line: which book path produced ENTERs / stay_in_cash; desk-ui Overview shows source |

### P2.7 Order caps (document / tune, not always “fix”)

| | |
|--|--|
| **Default** | `TRADING_AGENT_MAX_ORDERS_PER_CONSUME=3` |
| **Done means** | Ops knows rest are skipped by design; optional env bump only after risk review |

### P2.8 Multileg LIVE (opt-in only)

| | |
|--|--|
| **Gap** | Spreads/IC not auto-placed unless `TRADING_AGENT_MULTILEG_LIVE=1` |
| **Done means** | Only enable after single-leg path proven; sequential wing-first + reverse on fail understood |
| **Do not** | Turn on by default in code |

```bash
# optional — after P0 green and you accept multi-leg risk
# echo 'TRADING_AGENT_MULTILEG_LIVE=1' >> ~/.grok/trading-agent.env
```

---

## P3 — Longer-term (roadmap-aligned)

Track against [`quant_institution_roadmap.md`](quant_institution_roadmap.md). Prefer Phase A before new alpha.

### P3.1 Backtest & promotion (Phase A)

- Historical path with costs/slippage for multi-method + auto_trade export gate  
- Promotion checklist before shipping method/default changes  
- Session replay from session JSON  

### P3.2 Journal & execution feedback

- Slippage fields on fills → feed backtest  
- Manage/exit reasons consistently on Discord + desk-ui (human-readable, not only lot hashes)  

### P3.3 Portfolio / risk

- Sector / cluster / beta caps beyond simple OMS open-lot limits  
- Day heat / cash controller tied to process bias  

### P3.4 Production hardening

- Always-on **paper parallel** book on Mac (or keep me-ai `trading_test` as the paper twin — document which is source of truth)  
- Drift / degrade monitors (edge decay, reject rate spike)  
- Kill-switch drill runbook (quarterly)  
- Immutable audit trail already partial under OMS — ensure ENTER/REJECT/skip always audited  

### P3.5 Desk product

- CIO Discord loop stays decision-quality even when multi-method auto-exports  
- Discovery multi-pass without wiping protected ENTERs (already partial via protect flag)  
- Performance proposes params; never auto-applies without promotion gate  

---

## Suggested Monday agenda

1. **P0 proof** (table above) — 15–30 min after open  
2. If consumer died or MCP quiet → start **P2.1 + P2.2 + P2.3**  
3. If orders cancel / bad OCC → **P2.5**  
4. If single-leg path green for a week → consider **P2.8** multileg  
5. Park **P3** until promotion/backtest slice is scheduled  

---

## Env quick reference (Mac)

| Variable | Typical | Role |
|----------|---------|------|
| `TRADING_AGENT_AUTO_TRADE_LIVE` | `1` | Allow place via Schwab MCP |
| `TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT` | `1` | Multi-method ENTERs without CIO |
| `TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK` | `1` | Block empty overwrite of ENTERs |
| `TRADING_AGENT_PROCESS_GATE` | default on | Process Steps 1–3 |
| `TRADING_AGENT_MULTILEG_LIVE` | `0` | Spreads LIVE place |
| `TRADING_AGENT_MAX_ORDERS_PER_CONSUME` | `3` | Cap per consume cycle |

---

## me-ai paper twin (for comparison only)

Paper auto lives in **`trading_test`** on me-ai (`scripts/me-ai/`, watchdog, IBKR qualify). Do not mix Mac Schwab LIVE with me-ai paper client ids. Monday paper checks are separate from this Mac P0 table.
