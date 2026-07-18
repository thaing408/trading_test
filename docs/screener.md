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

## Strength floors (ADR / 52w / EMA)
Default profile is **softened** so large-caps in quieter regimes are not mass-rejected:

| Gate | Soft default | Strict Komar (`TRADING_AGENT_STRENGTH_PROFILE=strict`) |
|------|--------------|--------------------------------------------------------|
| ADR% | ≥ **2.5** | ≥ **4.5** |
| 52w above low | ≥ **35%** | ≥ **70%** |
| EMA | above **EMA8** only | above **EMA8 and EMA21** |

```bash
# Classic Best Winners floors
set TRADING_AGENT_STRENGTH_PROFILE=strict

# Or numeric overrides
set TRADING_AGENT_MIN_ADR_PCT=3.0
set TRADING_AGENT_MIN_PCT_ABOVE_52W_LOW=50
set TRADING_AGENT_STRENGTH_EMA_MODE=both
```

## Liquid mid-price trade path (optional)

Default trade floor is still **`min_price = $20`**. Liquid names like **LCID** (~$5–$15 with huge ADV) fail that floor even when strength passes.

Enable an **exception path** (not a global price cut):

```bash
set TRADING_AGENT_LIQUID_MID_PRICE=1
# or
set TRADING_AGENT_RISK_PROFILE=liquid_mid
```

When enabled, a name with price in **[`liquid_mid_min_price`, `min_price`)** may pass risk only if:

| Floor | Default |
|-------|---------|
| Min price | **$5** |
| ADV | **≥ 5M** (stricter than standard 2M) |
| Dollar volume (price × ADV) | **≥ $30M** |
| Market cap | **≥ $1B** |
| RVOL | **≥ 1.5** |

Illiquid sub-$20 names still fail. Override knobs:

```bash
set TRADING_AGENT_MIN_PRICE=20
set TRADING_AGENT_LIQUID_MID_MIN_PRICE=5
set TRADING_AGENT_LIQUID_MID_MIN_ADV=5000000
set TRADING_AGENT_LIQUID_MID_MIN_DOLLAR_VOL=30000000
```

Scan band also drops to the liquid mid min when the exception is on so names can enter the screener.

## Discovery vs CIO (mid-session)
- Morning CIO (≈06:00 PT) is the **initial capital plan**.
- Discovery slots (07:00 / 09:30 / 11:00 PT) rescreen watchlist — **not** full CIO every 15m cycle.
- If discovery produces **tradeable ranked setups** after a cash/empty morning, CIO is **promoted once** that day (mid-session capital re-eval). Watchlist rotation alone is never approval.

## Parallel fetch
`ScreenerConfig.fetch_workers` (default 6) for live Yahoo multi-symbol scan.

## Pulse market scan (macOS scalp pulse)

`python -m trading_agent.export.market_scan` ranks the **same screener universe**
by day % change (gainers/losers). `~/.grok/scripts/scalp-market-pulse.py` calls
this first so Discord pulse is code-universe driven, not a fixed AAPL/AMZN/QQQ/SPY loop.

```bash
# Full expanded universe top 8
python -m trading_agent.export.market_scan --top 8

# Cap symbols for speed
TRADING_AGENT_SCAN_MAX_SYMBOLS=40 python -m trading_agent.export.market_scan --json
```

Level proximity spam on pulse is separate (`SCALP_LEVEL_ALERTS=breaks|off`).

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
