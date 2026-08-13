#!/usr/bin/env bash
# Post end-of-day paper summary + positions to Discord paper channel.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
ENV_FILE="${TRADING_TEST_ENV_FILE:-$STATE_DIR/trading-test.env}"

set -a
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
[[ -f "$HOME/.grok/discord.env" ]] && source "$HOME/.grok/discord.env"
set +a

export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
export DISCORD_PAPER_CHANNEL_ID="${DISCORD_PAPER_CHANNEL_ID:-1536602374502613013}"
export DISCORD_CHANNEL_ID="$DISCORD_PAPER_CHANNEL_ID"
export DISCORD_TOKEN="${DISCORD_TOKEN:-${DISCORD_BOT_TOKEN:-}}"
unset DISCORD_WEBHOOK_URL || true
export TRADING_AGENT_SYNC_DIR="${TRADING_AGENT_SYNC_DIR:-$STATE_DIR/sync}"
export IBKR_PORT="${IBKR_PORT:-7497}"
export IBKR_ENABLED=1

PY="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')

exec "$PY" - <<PY
from trading_agent.discord.paper_activity import post_eod_summary, post_positions, post_activity
day = "$DAY"
print("Posting EOD to paper channel…")
r1 = post_eod_summary(trading_date=day)
r2 = post_positions(source="IBKR paper EOD")
print("eod", r1)
print("positions", r2)
post_activity("_Manual EOD post complete._", title="EOD done")
print("OK")
PY
