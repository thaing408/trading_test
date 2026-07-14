# Dual-system architecture: Windows research + macOS TOS execution

## Roles

| System | Role | Has TOS / Schwab MCP? | Primary job |
|--------|------|------------------------|-------------|
| **Windows** (this machine) | Research / methods lab | **No** | Screener, TA/fundamentals, book gates, discovery, Discord research, backtests, export trade book |
| **macOS** | Live trading desk | **Yes** (TOS / Schwab MCP) | Positions export, order path, PT/SL against real book, consume research book |

Do **not** require TOS MCP on Windows. All research must remain **provider-pluggable** (yfinance / FMP / Schwab OHLCV when available).

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

## Sync options

1. **iCloud/Dropbox** folder = `TRADING_AGENT_SYNC_DIR` on both  
2. **git private** push of `sync/*.json` (no secrets) from Windows after research; Mac pull before open  
3. **scp/rsync** cron after discovery  

Prefer (1) or (3) for low latency; git is fine for plan audit trail.
