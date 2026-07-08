# Trading Agent

Multi-phase options trading desk: market intelligence, research, CIO approval, and Discord delivery.

**Repo:** https://github.com/thaing408/trading_agent

## Quick start (new machine / new agent)

```powershell
git clone https://github.com/thaing408/trading_agent.git
cd trading_agent

# 1. Install
python -m pip install -e ".[dev]"

# 2. Configure
copy .env.example .env
# Edit .env: set DISCORD_CHANNEL_ID (and DISCORD_TOKEN if not using researcher .env)

# 3. Verify
powershell -ExecutionPolicy Bypass -File scripts\verify_environment.ps1

# 4. Test (fixture, no Discord)
python -m trading_agent session --fixture --dry-run --date 2026-07-09 --until-phase preopen

# 5. Automate weekdays 01:55 AM Pacific
powershell -ExecutionPolicy Bypass -File scripts\setup_desk_automation.ps1
```

## Discord setup

The agent posts to Discord via **bot channel** (preferred) or webhook.

| Variable | Required | Source |
|----------|----------|--------|
| `DISCORD_TOKEN` | Yes (bot mode) | `C:\Personal\Scripts\researcher\.env` or local `.env` |
| `DISCORD_CHANNEL_ID` | Yes | `.env` (default: `#daily-plays`) |
| `DISCORD_WEBHOOK_URL` | Optional | Overrides bot if set |

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

**Current mode:** phases 1-4 only (`TRADING_AGENT_UNTIL_PHASE=preopen`) until brokerage is connected.

## Commands

```powershell
# Full desk day (waits for schedule, posts to Discord)
python -m trading_agent session --date 2026-07-09

# First 4 phases only (evaluation mode)
python -m trading_agent session --date 2026-07-09 --until-phase preopen

# Individual phases
python -m trading_agent premarket
python -m trading_agent cio --fixture
python -m trading_agent intraday --fixture
python -m trading_agent performance --fixture
```

## Automation

| Script | Purpose |
|--------|---------|
| `scripts/start_desk_session.ps1` | Git pull, install, run session |
| `scripts/register_desk_task.ps1` | Register Windows Task Scheduler job |
| `scripts/setup_desk_automation.ps1` | One-shot setup |
| `scripts/verify_environment.ps1` | Readiness check |

**Scheduled task:** `TradingAgentDeskSession` — Mon-Fri 01:55 AM Pacific.

Logs: `%USERPROFILE%\.trading_agent\logs\`

Session artifacts: `%USERPROFILE%\.trading_agent\sessions\{date}\`

## Tests

```powershell
python -m pytest -q
```

## Environment variables

See `.env.example` for all options. Key vars:

- `TRADING_AGENT_UNTIL_PHASE=preopen` — stop after phase 4
- `TRADING_AGENT_PYTHON` — explicit Python path for scheduled tasks
- `TRADING_AGENT_ENV_FILE` — alternate .env path