# trading_test

**Paper-trading fork** of the trading desk — **IBKR paper**, **no CIO**, isolated from production Schwab desk.

| | Production | This repo |
|--|------------|-----------|
| Repo | [`trading_agent`](https://github.com/thaing408/trading_agent) | **[`trading_test`](https://github.com/thaing408/trading_test)** |
| Broker | Schwab (Mac) | IBKR paper (me-ai / Linux) |
| CIO | On by default | Off (`TRADING_AGENT_INCLUDE_CIO=0`) |
| State | `~/.trading_agent` | `~/.trading_test` |

See [`PAPER_NO_CIO.md`](PAPER_NO_CIO.md) and [`docs/ibkr_gateway_paper_linux.md`](docs/ibkr_gateway_paper_linux.md).

```bash
git clone https://github.com/thaing408/trading_test.git
cd trading_test
python3 -m venv .venv && .venv/bin/pip install -e . ib_insync
cp .env.paper.example ~/.trading_test/trading-test.env   # edit ports / account
```

Optional: track prod as `upstream` for cherry-picks only — do **not** push this repo to `trading_agent`.

---

# Trading Agent (upstream lineage)

Multi-phase options trading desk: market intelligence, research, CIO approval, and Discord delivery.

**Prod repo:** https://github.com/thaing408/trading_agent

## Quick start (new machine / new user)

### Windows (this machine)

```powershell
git clone https://github.com/thaing408/trading_agent.git
cd trading_agent
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

The Windows installer (`scripts\install.ps1`) prompts for everything needed (Discord bot/webhook **or** safe dry-run), installs the package, writes `.env`, verifies readiness, optionally registers weekday automation + wake timers, and runs a fixture dry-run of prep phases. Re-running reuses existing `.env` values as defaults.

Non-interactive (CI / scripted):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -NonInteractive -DeliveryMode dry_run -SkipAutomation
```

After install (Windows):

```powershell
# Safe prep session (no Discord posts if dry-run)
python -m trading_agent session --fixture --dry-run --until-phase preopen

# Readiness check
powershell -ExecutionPolicy Bypass -File scripts\verify_environment.ps1
```

### macOS

macOS install / launchd / Schwab bridge scripts live under `scripts/install.sh` and `scripts/macos/` and are maintained on the Mac side. See those scripts or the macOS notes below after a Mac push.

## Discord setup

The agent posts via **bot channel** (preferred) or **webhook**. The install wizard collects one of:

| Mode | What you provide |
|------|------------------|
| `dry_run` / `no_discord` | Nothing — local runs only, no posts |
| `bot` | `DISCORD_TOKEN` + `DISCORD_CHANNEL_ID` |
| `webhook` | `DISCORD_WEBHOOK_URL` |

| Variable | Required | Notes |
|----------|----------|--------|
| `DISCORD_TOKEN` | Bot mode | From Discord Developer Portal |
| `DISCORD_CHANNEL_ID` | Bot mode | Default example: `#daily-plays` |
| `DISCORD_WEBHOOK_URL` | Webhook mode | Overrides bot if set |

You do **not** need any author-specific path (e.g. a personal `researcher\.env`); put secrets in the repo `.env` created by the installer.

## Desk schedule (Pacific Time)

| Time | Phase | CLI phase id |
|------|-------|--------------|
| 02:00 | Market Intelligence | `intelligence` |
| 05:00 | Trading Research | `research` |
| 06:00 | CIO Final Approval | `cio_approval` |
| 06:25 | Pre-Open Check | `preopen` |
| 06:30-13:00 | Trading Desk (intraday) | `intraday` |
| 13:15 | Performance Review | `performance` |
| 13:30 | CIO Daily Review | `cio_review` |
| 15:00 PT / **18:00 ET** | Evening scanners (swing + multi-method) | `evening_scan` |

**Default for scheduled desk:** full day (`TRADING_AGENT_UNTIL_PHASE=evening_scan`) — morning prep, **research-time scanners**, intraday PT/SL + discovery refreshes (07:00 / 09:30 / 11:00 PT), close reviews, then **6 PM ET** evening scanners. Use `preopen` for prep-only; use `cio_review` to stop before 6 PM ET.

**Swing / multi-method schedule:** runs **once at research** (with the research universe) and again at **`evening_scan` (18:00 ET)**. Disable with `TRADING_AGENT_DESK_SCANNERS=0` or `TRADING_AGENT_EVENING_SCAN=0`.

**macOS Grok + Schwab pipeline (optional):** full 7 phases via `scripts/macos/` after install.

## Commands

```powershell
# Full desk day (waits for schedule, posts to Discord if configured)
python -m trading_agent session --date 2026-07-10

# First 4 phases only (evaluation / prep mode)
python -m trading_agent session --date 2026-07-10 --until-phase preopen

# Individual phases
python -m trading_agent premarket
python -m trading_agent cio --fixture
python -m trading_agent intraday --fixture
python -m trading_agent performance --fixture
```

## Dual system (Windows @ work + macOS @ home) — fully separated

| Where | Machine | Role |
|-------|---------|------|
| **Work** | **Windows** | Research only — methods, screener, gates, discovery, Discord (**no TOS**, no home data) |
| **Home** | **macOS** | Live trading — TOS / Schwab MCP only (**no work files**) |

**Bridge = git + optional Discord cue only.** No shared positions/journals/secrets.

1. Work: improve code → **`git push`** to `main`  
2. Home Mac **launchd** (01:55 PT): auto-pull + full desk — **no manual daily prepare**  
3. Home Mac **QT + auto-trade** (06:25/06:30 PT): open-window model + book consumer → ready orders  
4. Optional Discord `PULL_LATEST` only if you need an ad-hoc pull before next launchd  

See **`docs/dual_system.md`**, **`docs/options_auto_trade.md`**, and **`docs/quant_institution_roadmap.md`** (future goals + fully auto-trade gaps).

## Automation

### Windows

| Script | Purpose |
|--------|---------|
| `scripts/install.ps1` | **Primary** new-user install + optional automation |
| `scripts/start_desk_session.ps1` | Git pull, install, run session |
| `scripts/register_desk_task.ps1` | Register wake + desk Task Scheduler jobs |
| `scripts/setup_desk_automation.ps1` | One-shot wake + task registration |
| `scripts/enable_pc_wake.ps1` | Enable OS wake timers |
| `scripts/verify_environment.ps1` | Readiness check |

**Scheduled tasks:** `TradingAgentDeskWake` (01:50 AM) + `TradingAgentDeskSession` (01:55 AM) Mon–Fri Pacific. Prefer **Sleep/Hibernate** overnight (not full Shutdown).

### macOS

| Script | Purpose |
|--------|---------|
| `scripts/install.sh` | **Primary** new-user install + optional launchd |
| `scripts/macos/trading-agent-desk.sh` | Git pull, install, optional Schwab positions, session |
| `scripts/macos/install-trading-agent-launchd.sh` | Install `com.grok.trading-agent-desk` (Mon–Fri 1:55 AM PT) |
| `scripts/macos/install-auto-trade-launchd.sh` | Desk + QT open-window + auto-trade consumer LaunchAgents |
| `scripts/macos/qt-open-window.sh` | 9:30–9:50 ET QT mech model → `qt_auto_trade_book.json` |
| `scripts/macos/consume_auto_trade_book.py` | Local books → ready orders (fail-closed; optional live MCP) |
| `scripts/macos/install-morning-check-launchd.sh` | Install `com.grok.morning-check` (Mon–Fri 6:35 AM PT; no Saturday) |

Logs: `~/.trading_agent/logs/`  
Session artifacts: `~/.trading_agent/sessions/{date}/`  
Ready orders: `~/.trading_agent/ready_orders/`

## Market data & brokerage providers

The desk uses a **pluggable multi-provider layer** (`trading_agent/providers/`) mapped to the seven phases.

| Default | Role |
|---------|------|
| **yfinance** | Primary free quotes / OHLCV / news |
| **Finnhub, Alpha Vantage, Twelve Data, Tiingo, Marketstack** | Env-gated secondary HTTP market data / news |
| **Alpaca, Tradier** | Optional brokerage positions (fail-closed if keys missing) |
| **IBKR TWS** | **Research OHLCV** when `IBKR_ENABLED=1` (read-only history; no order placement). Live trading stays Schwab. |

See **[docs/provider_phase_mapping.md](docs/provider_phase_mapping.md)** for the full OBJECTIVE source → phase table.

Useful env vars: `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `TIINGO_API_KEY`, `TWELVE_DATA_API_KEY`, `MARKETSTACK_API_KEY`, `ALPACA_API_KEY` + `ALPACA_SECRET_KEY`, `TRADIER_ACCESS_TOKEN` + `TRADIER_ACCOUNT_ID`, `TRADING_AGENT_QUOTE_PROVIDERS`, `TRADING_AGENT_NEWS_PROVIDERS`.

Live path **never** silent-fills fixture headlines when keys are missing (`source=unavailable`).

## Backtest (offline research + CIO)

```powershell
# Compare risk/grade configs on fixture OHLCV (no API keys)
python -m trading_agent backtest

# Baseline only
python -m trading_agent backtest --single
```

Findings and shipped knobs: [docs/backtest_findings.md](docs/backtest_findings.md).

## Tests

```powershell
python -m pytest -q
```

Install wizard unit tests:

```powershell
python -m pytest tests/test_install_wizard.py -q
```

## Environment variables

See `.env.example`. Key vars (written by the installer):

- `TRADING_AGENT_UNTIL_PHASE=evening_scan` — full day (default); `cio_review` = stop before 6pm ET; `preopen` = stop after phase 4
- `TRADING_AGENT_DESK_SCANNERS=1` — swing + multi-method at research + evening
- `TRADING_AGENT_DISCOVERY_REFRESH=1` — light rescreens at 07:00 / 09:30 / 11:00 PT
- `TRADING_AGENT_PYTHON` — explicit Python path for scheduled tasks
- `TRADING_AGENT_DRY_RUN=1` / `TRADING_AGENT_NO_DISCORD=1` — no Discord posts
- `TRADING_AGENT_ENV_FILE` — alternate env path
- `TRADING_AGENT_TIMEZONE=America/Los_Angeles`
- `TRADING_AGENT_MARKET_DATA=auto|ibkr|schwab|yfinance` — OHLCV for TR strength/technicals (default **auto**: IBKR if `IBKR_ENABLED`, else Schwab `~/.schwab-mcp/token.json`, else yfinance)
- `IBKR_ENABLED=1` — research-only IBKR historical bars via TWS/Gateway (`pip install ib_insync`; ports: TWS live **7496** / paper 7497, Gateway 4001/4002). Optional: `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_READONLY=1`
- `SCHWAB_TOKEN_PATH` — override Schwab OAuth token path
- Ping: `IBKR_ENABLED=1 python scripts/ibkr_research_ping.py` (and `--via-provider` for full chain)
- `TRADING_AGENT_INTRADAY_INTERVAL` — baseline desk cycle minutes when **flat** (default **15**)
- `TRADING_AGENT_INTRADAY_IN_POSITION_INTERVAL` — PT/SL re-check minutes while **open positions** exist (default **3**, must be &lt; baseline)

### Breakout vs mean reversion (QQQ playbooks)

```bash
# Mean reversion (default): Shen 0DTE / multi-DTE RSI fades at levels
python -m trading_agent odte --style mean_reversion --backtest --period 10d --source schwab

# Breakout / 888 TI: simple visual decision card (LONG · SHORT · WAIT)
python -m trading_agent odte --style breakout --symbol QQQ
python -m trading_agent odte --mode breakout --symbol SPY

# Breakout backtest (OR continuation, 15m HTF)
python -m trading_agent odte --style breakout --backtest --period 10d --source schwab
python -m trading_agent odte --mode breakout   # same path
```
