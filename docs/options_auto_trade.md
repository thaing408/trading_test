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

## Mac daily prep
```bash
cd ~/trading_agent   # your clone
./scripts/macos/prepare-options-day.sh
# or after Discord PULL_LATEST:
./scripts/macos/pull-and-ready.sh
```

Then in TOS: only defined-risk structures; size by max risk; no short premium into earnings without a plan.

## Journal (Mac local)
Append closed trades with setup_id / grade for local Performance:
`TRADING_AGENT_TRADES_FILE` or default journal path used if the file exists.
