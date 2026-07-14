# Dual-system architecture: Windows research + macOS TOS execution

## Physical setup (your machines)

| Location | Machine | Role | TOS / trading |
|----------|---------|------|----------------|
| **Work** | **Windows** | Research / methods only | **No** — ideas, gates, discovery, Discord, `auto_trade_book.json` |
| **Home** | **macOS** | Live trading desk | **Yes** — TOS / Schwab MCP, positions, brackets, journal |

Implication: research can run weekdays while you’re at work; **execution only happens at home** when the Mac is on. Sync must cross **work ↔ home** (not LAN). Prefer cloud folder or git over USB.

Do **not** require TOS MCP on Windows. All research must remain **provider-pluggable** (yfinance / FMP / optional data APIs).

## Shared contract directory

Both machines should read/write under a synced folder (iCloud / Dropbox / git-lfs / network share):

```
~/.trading_agent/
  sync/                          # optional cloud sync root
    auto_trade_book.json         # Windows → Mac: executable ideas
    positions.json               # Mac → Windows: open risk for rails/intraday
    stopouts.json                # either: cool-down book
    journal/
      trades_YYYY-MM-DD.json     # closed trades for Performance
  sessions/YYYY-MM-DD/
    daily_plan_context.json
    auto_trade_book.json         # also copied per session
```

Env (both sides):

```bash
TRADING_AGENT_SYNC_DIR=~/.trading_agent/sync   # or shared path
TRADING_AGENT_POSITIONS_FILE=$SYNC/positions.json
TRADING_AGENT_STOPOUT_FILE=$SYNC/stopouts.json
TRADING_AGENT_TRADES_FILE=$SYNC/journal/trades_today.json
```

## `auto_trade_book.json` schema (Windows writes, Mac reads)

```json
{
  "schema_version": 1,
  "generated_at": "ISO-8601",
  "source_host": "windows-research",
  "trading_date": "YYYY-MM-DD",
  "regime": "bullish|bearish|neutral",
  "stay_in_cash": false,
  "entries": [
    {
      "symbol": "NVDA",
      "action": "ENTER",
      "side": "Bullish",
      "strategy": "Long Call",
      "setup_id": "opening_range_breakout_long",
      "setup_grade": "A",
      "entry": 115.0,
      "stop": 111.0,
      "target": 123.0,
      "max_risk_dollars": 500,
      "max_risk_pct": 1.0,
      "confidence": 72,
      "technical_score": 78,
      "fundamental_score": 65,
      "quality_score": 80,
      "checklist_passed": true,
      "edge_complete": true,
      "expires_at": "ISO-8601 session close",
      "notes": "short thesis"
    }
  ],
  "exits": [],
  "watchlist": ["NVDA", "AMD"]
}
```

**Mac rules (recommended):**
1. Only `action=ENTER` with `checklist_passed` + `edge_complete` + grade A/A+ (or B if explicitly allowed).
2. Size from `max_risk_pct` / `max_risk_dollars`, never from Discord prose.
3. After fill/stop, update `positions.json` + `stopouts.json` + journal for Windows Performance.
4. Never invent entries without a book row.

**Windows rules:**
1. Never place orders.
2. Always refresh book on research + discovery.
3. Use Mac `positions.json` for rails / cool-down when sync present.

## Data flow (daily)

```
Windows 02:00–06:30 PT  → research + book export
Mac     ~01:55 PT       → positions export + full desk (or pull book)
Windows 07:00/09:30/11  → discovery → overwrite auto_trade_book.json
Mac     continuous      → PT/SL via real positions; optional book refresh pull
Both    after close     → journal merge → Performance
```

## Improving auto-trade quality (both systems)

| Layer | Owner | Method |
|-------|--------|--------|
| Technical | Windows | MTF, Murphy confluence, Nison, Bulkowski, Shannon |
| Fundamental | Windows | Quality score (growth, profitability, leverage, event risk) |
| Process | Both | Playbook checklist, edge package, rails |
| Execution | Mac only | TOS brackets, real fills, position sync |
| Learning | Windows | Backtests + journal attribution |

## Sync options (work Windows ↔ home Mac)

| Method | Fit for work/home | Notes |
|--------|-------------------|--------|
| **1. Cloud folder** (OneDrive / Dropbox / Google Drive / iCloud Drive) | **Best default** | Same relative path under `TRADING_AGENT_SYNC_DIR` on both; auto-sync after research/discovery |
| **2. Private git** (`sync/*.json` only, no secrets) | Good audit trail | Windows: commit/push book after morning research; Mac: `git pull` before open / after lunch |
| **3. Manual copy** | Fallback | Download book from work → home before open (last resort) |

**Recommended:** cloud folder named e.g. `TradingAgentSync` containing:

```
TradingAgentSync/
  auto_trade_book.json      # work → home (ENTER ideas)
  positions.json            # home → work (optional; rails/cool-down on research host)
  stopouts.json             # home → work (revenge cool-down)
  journal/
    trades_YYYY-MM-DD.json  # home → work (Performance learning)
```

### Work (Windows) env

```env
TRADING_AGENT_SYNC_DIR=C:\Users\...\OneDrive\TradingAgentSync
TRADING_AGENT_UNTIL_PHASE=cio_review
TRADING_AGENT_DISCOVERY_REFRESH=1
# No TOS; no order placement
```

### Home (macOS) env

```bash
export TRADING_AGENT_SYNC_DIR="$HOME/Library/CloudStorage/.../TradingAgentSync"
# or Dropbox/iCloud path
export TRADING_AGENT_POSITIONS_FILE="$TRADING_AGENT_SYNC_DIR/positions.json"
export TRADING_AGENT_STOPOUT_FILE="$TRADING_AGENT_SYNC_DIR/stopouts.json"
export TRADING_AGENT_TRADES_FILE="$TRADING_AGENT_SYNC_DIR/journal/trades_$(date +%Y-%m-%d).json"
```

### Daily rhythm (work/home)

| When (PT) | Work Windows | Home Mac |
|-----------|--------------|----------|
| ~01:55–06:30 | Full research (if PC awake) → writes `auto_trade_book.json` | Optional: pull + prepare TOS |
| Before open / after you get home | Discovery overwrites book if still running | **Pull sync** → `consume_auto_trade_book.py` → trade only ENTERs |
| 07:00 / 09:30 / 11:00 | Discovery refresh updates book | Re-pull if at desk; ignore if away |
| After close | — | Export positions + journal into sync folder |
| Next workday | Performance reads journal from sync | — |

**Security:** never put `DISCORD_TOKEN` / Schwab OAuth tokens in the shared sync folder. Only JSON books, positions, stopouts, journal.
