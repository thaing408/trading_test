# Repo split: trading_test vs trading_agent

Two **separate GitHub repositories** after the fork:

| Repo | Path (typical) | Role |
|------|----------------|------|
| **trading_test** | `C:\Personal\Grok\trading_test` | Multi-method **lab** — combined scanners, **no CIO decision desk** |
| **trading_agent** | `C:\Personal\Grok\trading_agent` | **Live** CIO trading desk — scanned lists for capital decisions |

## Remotes

| Clone | Origin |
|-------|--------|
| trading_test | `https://github.com/thaing408/trading_test.git` |
| trading_agent | `https://github.com/thaing408/trading_agent.git` |

Do **not** push methods-lab defaults to `trading_agent` main without an explicit merge PR.

## trading_test (this repo)

- Product marker: `trading_agent/product.py` → `PRODUCT_ID=trading_test`
- Default: `product_mode=methods`, `include_cio=False`
- Research phase: multi-method + swing (`session/methods_research.py`) → Discord + `auto_trade_book`
- CIO approval / review: **skipped** (stub messages only)
- Discovery: no CIO promotion

```bash
python -m trading_agent session --fixture --dry-run --until-phase preopen
python -m trading_agent research multi-method QQQ,NVDA --limit 12
python -m trading_agent research swing-scan --limit 20
```

Env overrides:

| Env | Effect |
|-----|--------|
| `TRADING_AGENT_PRODUCT_MODE=desk` | Force classic pipeline + CIO (rare) |
| `TRADING_AGENT_INCLUDE_CIO=1` | Re-enable CIO phases |
| `TRADING_TEST_SCAN_LIMIT=20` | Methods universe size |

## trading_agent (live)

- Full desk: MI → research pipeline → **CIO** → preopen → intraday → performance → CIO review
- Posts **scanned / watchlist / board** for human + CIO decisions
- Mac executes from local books after git pull of **trading_agent** (not this lab)

## Round-trip policy (from trading_agent OMS)

- **Max 2 closed round-trips per symbol per day** (`TRADING_AGENT_MAX_ROUND_TRIPS_PER_SYMBOL=2`)
- **Not a global day halt** — other tickers may still enter (`TRADING_AGENT_MAX_ROUND_TRIPS_PER_DAY=0`)
- Multi-method historical BT: `--max-per-symbol 2 --max-per-day 20` plus optional `--export-quality` / `--swing-weight`

## Shared scanned lists

Both products read/write the **same local artifact** so they look at one universe:

| File | Path |
|------|------|
| Canonical | `~/.trading_agent/sync/scanned_list.json` |
| Compat | `~/.trading_agent/sync/auto_trade_scan_symbols.json` |

Module: `trading_agent/export/scanned_list.py` (identical in both repos).

| Writer | When |
|--------|------|
| **trading_test** methods research | After multi-method + swing |
| **Either** auto_trade_book export | On book write |
| **trading_agent** desk research | After pipeline (full screener universe + watchlist) |

| Reader | Use |
|--------|-----|
| `resolve_screener_symbols()` | Prefers shared universe after env/file |
| multi-method / swing | Prefer shared list when no CLI symbols |
| CIO desk process | Watchlist / focus from book + scanned_list |

Override: `TRADING_AGENT_SYMBOLS` / `TRADING_AGENT_SYMBOLS_FILE` win.  
Ignore shared: `TRADING_AGENT_IGNORE_SCANNED_LIST=1`.  
On dual machines without shared disk, copy `scanned_list.json` via your sync path or re-run the same symbols env on both.

## What not to confuse

- Methods PLAY in trading_test ≠ live CIO approval on trading_agent
- Windows scheduled desk should keep pointing at **trading_agent**
- Methods automation (Linux/Mac) should run **trading_test** or `research multi-method` / `swing-scan`
