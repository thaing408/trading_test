# Screener: scan wide, trade tight

## Design
- **Scan tier** (`ScreenerConfig`): large liquid universe + soft floors → more candidates
- **Trade tier** (`RiskConfig` + book gates): still institutional / A-tier / playbook quality

## Defaults
| | Scan | Trade (`RiskConfig`) |
|--|------|----------------------|
| Universe | ~90 expanded liquid names | same names that survive scan |
| ADV | 1M (hard drop ~15% of floor) | 2M |
| RVOL | 1.2 (soft; not hard-dropped) | 2.0 |
| Market cap | $1B soft | $2B |
| Watchlist | top **20** | — |
| Strength | **soft** (fail still analyzed) | book/risk still apply for entries |

## Expand / override universe
```bash
# Comma list
set TRADING_AGENT_SYMBOLS=AAPL,MSFT,NVDA,AMD,TSLA

# Or file (one symbol per line or CSV)
set TRADING_AGENT_SYMBOLS_FILE=%USERPROFILE%\.trading_agent\symbols.txt

# Soften scan further
set TRADING_AGENT_SCAN_MIN_RVOL=1.0
set TRADING_AGENT_SCAN_MIN_ADV=500000
set TRADING_AGENT_SCAN_MAX_SYMBOLS=50

# Strength: soft | hard | off
set TRADING_AGENT_STRENGTH_MODE=soft
```

## Strength modes
- **soft** (default): strength fail is noted; name still analyzed for risk/watchlist
- **hard**: legacy — strength fail drops from research entirely
- **off**: skip strength gates

## Parallel fetch
`ScreenerConfig.fetch_workers` (default 6) for live Yahoo multi-symbol scan.

## Intraday discovery refresh (Pacific Time)

Morning research/CIO still builds the day plan once. During RTH the desk also runs
**light discovery** (rescreen + re-rank, update `daily_plan_context.json`) at:

| PT | ET | Role |
|----|-----|------|
| **07:00** | 10:00 | Post-open range set |
| **09:30** | 12:30 | Midday rotation |
| **11:00** | 14:00 | Afternoon check before 13:00 PT close |

- Not a full CIO rebuild every 15m — only these slots (or catch-up if late).
- Disable: `TRADING_AGENT_DISCOVERY_REFRESH=0`
- Module: `trading_agent.session.discovery`
