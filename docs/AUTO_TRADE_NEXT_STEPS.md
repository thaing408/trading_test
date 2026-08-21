# Auto-trade next steps (Mac `trading_agent`)

**Last updated:** 2026-08-20

## WR desk (default ON) — fewer ENTERs, higher bar

`TRADING_AGENT_WR_DESK=1` (default). LIVE new entries require:

| Gate | Rule |
|------|------|
| Bias | **`trade` only** (`light` / `cash` → no ENTER) |
| Regime | Not chop/range/sideways |
| Tape | SPY 10d MA ≥ 20d MA **and** VIX ≤ 20 (disable tape: `TRADING_AGENT_WR_TAPE=0`) |
| Setup | Pullback family only: `fvg`, `soulz_pa` (`TRADING_AGENT_WR_METHODS`) |
| Side | No PUT / bear_breakdown |
| DTE | ≥ 3 (index 0DTE off; `TRADING_AGENT_WR_ALLOW_INDEX_0DTE=1` to restore on push tape) |
| Spread | Skip if `bid_ask_spread_pct` &gt; 8 |
| Payoff | Target **2R** vs stop |
| Time stop | Flatten debit after **60m** if still open |

Disable all of the above: `TRADING_AGENT_WR_DESK=0`.

---  
**Audience:** Mac production desk ops + continue from multi-day manage hardening.

Related:

- [`options_auto_trade.md`](options_auto_trade.md) — LIVE path, env flags, multi-method auto-export  
- [`DESK_UI_AUTO_TRADE.md`](DESK_UI_AUTO_TRADE.md) — operator UI  
- [`PACKAGING_ROADMAP.md`](PACKAGING_ROADMAP.md) — installable Operator Desk (Mac/Windows); feature constraints  
- [`quant_institution_roadmap.md`](quant_institution_roadmap.md) — long-horizon G0–G7  

Paper stack on me-ai is **`trading_test`** (separate repo); this file is **Mac production desk**.

---

## Already shipped (do not re-do)

| Item | Notes / commit area |
|------|---------------------|
| Process day bias auto-set from desk research/scanners | Avoids `process_bias_unset` |
| Protect multi-method ENTERs from empty cash/discovery overwrite | `TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK=1` (default) |
| **P1** Multi-method EXPORT → `auto_trade_book` **without CIO** | `TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT=1` (default); desk scanners write ENTERs |
| Dual-path DTE | **0DTE only SPY/QQQ/IWM**; all others **min DTE 3** (`option_dte_policy.py`) |
| Desk UI + `desk-status` CLI | Optional `[desk-ui]` extra |
| **Cash gate** | LIVE `get_account` cash_available; skip if premium doesn’t fit; reserve |
| **Journal parity** | MULTI AUTO entry/exit via `post-trade-event.sh` (same layout as SCALP, @mention) |
| **Manage v2** | Live marks; und stop/target; option ±%; **trail**; **EOD 0DTE flatten**; **min-premium wipe** |
| **Watch through manage-until** | Default **9:25–16:00 ET** (entries still soft-gated early; manage all day) |
| **Caffeinate** | `auto-trade-consumer.sh` wraps with `caffeinate -dims` (set `TRADING_AGENT_CAFFEINATE=0` to disable) |

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

## P2 — Ops reliability + execution quality

**Status (2026-08-17):** implemented on `main` — re-run install for LaunchAgent:

```bash
cd ~/trading_agent && git pull
bash scripts/macos/install-auto-trade-launchd.sh
```

### P2.1 Mac consumer watchdog — **done**

| | |
|--|--|
| **Script** | `scripts/macos/auto-trade-consumer-watchdog.sh` |
| **LaunchAgent** | `com.grok.auto-trade-consumer-watchdog` (every 15m; no-op outside Mon–Fri 06:30–11:00 PT) |
| **Behavior** | If `consume_auto_trade_book.py` not running → restart `--watch` + Discord |

### P2.2 Discord ops alerts — **done**

| | |
|--|--|
| **Module** | `trading_agent/ops/alerts.py` |
| **Triggers** | kill switch, Schwab OAuth block, process gate fail, no books / zero ENTER rows, submit summary |
| **Env** | `TRADING_AGENT_OPS_ALERTS=1` (default); channel `DISCORD_OPS_CHANNEL_ID` or `DISCORD_CHANNEL_ID` |

### P2.3 Schwab OAuth / MCP health — **done**

| | |
|--|--|
| **Module** | `trading_agent/ops/schwab_health.py` |
| **Behavior** | LIVE place skipped with `skip_reason=schwab_oauth_expired` / `schwab_no_token` when refresh expired; still writes ready_orders |
| **Env** | `TRADING_AGENT_SCHWAB_HEALTH_CHECK=1` (default) |

### P2.4 Mac awake for desk + consumer — **documented**

Install script prints awake reminder. Ensure power settings / existing awake LaunchAgents cover 01:55 + 06:25 PT.

### P2.5 Schwab option contract precheck — **done**

| | |
|--|--|
| **API** | `option_contract_precheck()` in `mac_execute.py` before `place_order` |
| **Checks** | expiration, min/max DTE, single strike, CALL/PUT, OCC length 21 |
| **Env** | `TRADING_AGENT_MIN_OPTION_DTE` (default `1`), `TRADING_AGENT_MAX_OPTION_DTE` (default `90`) |
| **Note** | Structural precheck only (no full chain quote); bad OCC still fails at MCP |

### P2.6 Book merge clarity — **done**

| | |
|--|--|
| **API** | `summarize_books()`; checklist section **Books loaded**; `book_summary` on consume result + audit `books_loaded` |
| **Discord** | Ops alert lists top book symbols when submits/fails |

### P2.7 Order caps — **documented**

Default `TRADING_AGENT_MAX_ORDERS_PER_CONSUME=3`. Rest skipped by design (`max_orders_per_consume`).

### P2.8 Multileg LIVE (opt-in only) — **unchanged default OFF**

```bash
# optional — only after single-leg path proven
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
| `TRADING_AGENT_REQUIRE_ACCOUNT_CASH` | `1` | Fail closed if LIVE balances missing |
| `TRADING_AGENT_MIN_CASH_RESERVE` | `25` | Leave unspent |
| `TRADING_AGENT_OPTION_LOSS_PCT` / `_PROFIT_PCT` | `50` / `100` | Option premium hard rails |
| `TRADING_AGENT_TRAIL_ENABLED` | `1` | Underlying trail after +0.5R |
| `TRADING_AGENT_TRAIL_BE_R` | `0.5` | R-multiple to move stop to breakeven |
| `TRADING_AGENT_TRAIL_LOCK_PCT` | `50` | Lock % of favorable excursion |
| `TRADING_AGENT_EOD_0DTE_FLATTEN` | `1` | Flatten 0DTE after cutoff |
| `TRADING_AGENT_EOD_0DTE_CUTOFF_ET` | `15:45` | ET clock for 0DTE flatten |
| `TRADING_AGENT_MIN_PREMIUM_WIPE` | `1` | Close dirt-cheap marks |
| `TRADING_AGENT_MIN_OPTION_PREMIUM` | `0.05` | Wipe floor ($/contract) |
| `TRADING_AGENT_MANAGE_UNTIL_ET` | `16:00` | Watch/manage end |
| `TRADING_AGENT_CAFFEINATE` | `1` | Prevent Mac idle sleep during watch |
| `TRADING_AGENT_JOURNAL_ALERTS` | `1` | @mention #trading-journal on entry/exit |
| `TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK` | `1` | Block empty overwrite of ENTERs |
| `TRADING_AGENT_PROCESS_GATE` | default on | Process Steps 1–3 |
| `TRADING_AGENT_MULTILEG_LIVE` | `0` | Spreads LIVE place |
| `TRADING_AGENT_MAX_ORDERS_PER_CONSUME` | `3` | Cap per consume cycle |

---

## me-ai paper twin (for comparison only)

Paper auto lives in **`trading_test`** on me-ai (`scripts/me-ai/`, watchdog, IBKR qualify). Do not mix Mac Schwab LIVE with me-ai paper client ids. Monday paper checks are separate from this Mac P0 table.
