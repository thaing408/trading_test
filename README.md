# Trading Agent

Multi-phase options trading desk: market intelligence, research, CIO approval, and Discord delivery.

**Repo:** https://github.com/thaing408/trading_agent

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

**Default for new installs:** phases 1–4 only (`TRADING_AGENT_UNTIL_PHASE=preopen`) until a brokerage account is connected.

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
| `scripts/macos/install-trading-agent-launchd.sh` | Install `com.grok.trading-agent-desk` |

Logs: `~/.trading_agent/logs/`  
Session artifacts: `~/.trading_agent/sessions/{date}/`

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

- `TRADING_AGENT_UNTIL_PHASE=preopen` — stop after phase 4
- `TRADING_AGENT_PYTHON` — explicit Python path for scheduled tasks
- `TRADING_AGENT_DRY_RUN=1` / `TRADING_AGENT_NO_DISCORD=1` — no Discord posts
- `TRADING_AGENT_ENV_FILE` — alternate env path
- `TRADING_AGENT_TIMEZONE=America/Los_Angeles`
