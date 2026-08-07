# Options auto-trade research (Windows) → execute (Mac)

**Roadmap / full-auto gaps:** see [`docs/quant_institution_roadmap.md`](quant_institution_roadmap.md) (institutional goals + missing pieces for ultimate fully auto trade).

## Goal
Windows builds **defined-risk options** suggestions with IV/POP/DTE/liquidity gates and posts them to Discord.  
Mac pulls **code only** from git, then trades in **local TOS** using Discord cards + optional local book file.

No work↔home file share of positions or journals.

## Windows research output
Discord **Trading Research (Options)** includes:
- Strategy + direction + setup id  
- Entry / stop / target / max risk  
- **IVR, POP, delta, DTE, strikes, defined_risk**  
- **Options AUTO-ENTER cards** for auto_trade_eligible rows  

Local files (on the machine that ran research):
- `~/.trading_agent/sessions/YYYY-MM-DD/auto_trade_book.json`
- optional `~/.trading_agent/sync/auto_trade_book.json` (local only)

## Options playbooks
| setup_id | Typical strategies |
|----------|-------------------|
| `options_credit_bull_put` | Bull Put Credit Spread |
| `options_credit_bear_call` | Bear Call Credit Spread |
| `options_credit_iron_condor` | Iron Condor |
| `options_debit_call_spread` | Debit call spreads |
| `options_debit_put_spread` | Debit put / long put |

Plus equity-style pullback/ORB plays that can map into long options.

## Options gates
See `methods/options_methods.py`: IV regime match, defined risk, OI/spread, credit POP, debit R:R, DTE 5–60, earnings short-premium block.

## Mac — auto launch + auto trade

Install once (home Mac):
```bash
# desk + QT open-window + book consumer LaunchAgents
bash scripts/macos/install-auto-trade-launchd.sh
```

| Job | Schedule (PT) | Role |
|-----|---------------|------|
| `com.grok.trading-agent-desk` | Mon–Fri **01:55** | git pull, positions, full desk → local `auto_trade_book.json` |
| `com.grok.auto-trade-consumer` | Mon–Fri **06:25** | Poll local books → `ready_orders_*.json` |
| `com.grok.qt-open-window` | Mon–Fri **06:30** | QT PO3/CISD open window (9:30–9:50 ET) + consume |

### Consumer behavior

```bash
# Manual (dry-run checklist + ready orders)
python scripts/macos/consume_auto_trade_book.py --anytime

# Live Schwab MCP submit (only if you accept risk)
# echo 'TRADING_AGENT_AUTO_TRADE_LIVE=1' >> ~/.grok/trading-agent.env
python scripts/macos/consume_auto_trade_book.py --live --anytime
```

- **Fail-closed default:** no broker calls unless `TRADING_AGENT_AUTO_TRADE_LIVE=1` or `--live`
- Writes `~/.trading_agent/ready_orders/ready_orders_YYYY-MM-DD.json` for TOS hand entry when MCP cannot place multi-leg packages
- Discovers **local** books only: `~/.trading_agent/sync/`, session dir, `~/.grok/state/` (not work paths)

### Researcher host handoff (production Ubuntu → Mac)

Production **researcher** runs on the LAN box (hostname **`me-ai`**, mDNS **`me-ai.local`** — IP may change under DHCP).

Mac **pull** resolves host in order:

1. `RESEARCHER_HOST` env  
2. `~/.grok/researcher_host` (auto-updated on successful pull)  
3. `RESEARCHER_HOSTNAME` / **`me-ai.local`**  
4. `RESEARCHER_HOST_FALLBACK` (default `10.0.0.52`, last resort)

Agent: `com.grok.pull-researcher-sync` every **15m** + desk startup.

| Book | CIO / desk effect |
|------|-------------------|
| Gap book | On **CIO board** as decision candidates (continuation); soft pipeline tag |
| Playlist | On **CIO board** + screener universe; confidence boost if already Phase-1 |
| Both | Full CIO gates still apply — **not auto-approve** |

Disable:

- `TRADING_AGENT_RESEARCHER_CIO=0` — stop CIO board merge  
- `TRADING_AGENT_PLAYLIST_MERGE=0` — stop screener universe merge

### Live place paths (schwab-mcp `place_order`)

| Package | Auto-submit when LIVE=1? | Behavior |
|---------|--------------------------|----------|
| **Single-leg debit** (long call / long put, 1 strike) | **Yes** | OCC + `BUY_TO_OPEN` market via `place_order` |
| **Simple equity buy** | **Yes** | `BUY` equity market via `place_order` |
| **Multi-leg** (IC, spreads, 2+ strikes) | **Opt-in LIVE** | Package always in `ready_orders`. LIVE wing-first sequential when `TRADING_AGENT_MULTILEG_LIVE=1` (or `ALLOW_SEQUENTIAL_MULTILEG=1`); **reverse opened legs** if a later leg fails |
| **Credit / short premium** (2+ strikes) | **Same as multi-leg** | Wings bought first; naked single-leg credit still **never** auto |

### OMS (default on)

Consumer routes through `trading_agent.oms` when `TRADING_AGENT_OMS=1` (default):

- Pre-trade: kill switch, day-loss, max open lots/risk, max per consume  
- Audit JSONL under `~/.trading_agent/oms/audit/`  
- Lot state `~/.trading_agent/oms/state.json`  
- Manage loop: software stop/target + kill flatten (`python -m trading_agent oms manage`)  

| Env | Role |
|-----|------|
| `TRADING_AGENT_OMS` | `0` = legacy consume only |
| `TRADING_AGENT_KILL_SWITCH` / `oms kill` | Block new entries |
| `TRADING_AGENT_MAX_OPEN_LOTS` | Default 5 |
| `TRADING_AGENT_MAX_OPEN_RISK` | Default 1500 |
| `TRADING_AGENT_MAX_DAY_LOSS` | Default 500 |
| `TRADING_AGENT_MULTILEG_LIVE` | Enable multi-leg LIVE (wing-first + reverse on fail; default **off**) |
| `TRADING_AGENT_ALLOW_SEQUENTIAL_MULTILEG` | Alias for multi-leg LIVE (default off) |
| `TRADING_AGENT_OMS_MANAGE` | Run exit loop after consume (default on) |

### Execution truth CLI

```bash
python -m trading_agent oms reconcile          # match lots ↔ Schwab positions
python -m trading_agent oms manage --live      # stops/targets + kill flatten
python -m trading_agent oms flatten --live --kill   # close OMS lots + broker sweep + kill
```

Separate from this consumer: launchd **`auto_trade_qqq`** still runs the scalp level bot (CALL/PUT rules + reject/break-hold exits).

You do **not** run `pull-and-ready` or `prepare-options-day` every day.  
Those scripts are **optional recovery** only if launchd is missing.

## Journal (Mac local)
Append closed trades with setup_id / grade for local Performance:
`TRADING_AGENT_TRADES_FILE` or default journal path used if the file exists.
