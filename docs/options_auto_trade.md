# Options auto-trade research (Windows) → execute (Mac)

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

You do **not** run `pull-and-ready` or `prepare-options-day` every day.  
Those scripts are **optional recovery** only if launchd is missing.

## Journal (Mac local)
Append closed trades with setup_id / grade for local Performance:
`TRADING_AGENT_TRADES_FILE` or default journal path used if the file exists.
