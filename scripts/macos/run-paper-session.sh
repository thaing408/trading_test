#!/usr/bin/env bash
# Run no-CIO desk session for trading_test (IBKR paper data + optional paper orders).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
ENV_FILE="${TRADING_TEST_ENV_FILE:-$STATE_DIR/trading-test.env}"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — run paper-day-setup.sh first"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
# Bot token from production discord env (channel overridden below)
if [[ -f "$HOME/.grok/discord.env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.grok/discord.env"
fi
set +a

export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
export TRADING_AGENT_INCLUDE_CIO=0
export TRADING_AGENT_NO_CIO=1
export TRADING_AGENT_AUTO_EXPORT_WITHOUT_CIO=1
export TRADING_AGENT_BROKER="${TRADING_AGENT_BROKER:-ibkr}"
export IBKR_PORT="${IBKR_PORT:-4002}"
export TRADING_AGENT_SYNC_DIR="${TRADING_AGENT_SYNC_DIR:-$STATE_DIR/sync}"
export TRADING_AGENT_POSITIONS_FILE="${TRADING_AGENT_POSITIONS_FILE:-$STATE_DIR/positions.json}"

# Paper journal Discord channel (all activities)
export DISCORD_PAPER_CHANNEL_ID="${DISCORD_PAPER_CHANNEL_ID:-1536602374502613013}"
export DISCORD_CHANNEL_ID="$DISCORD_PAPER_CHANNEL_ID"
export DISCORD_DESK_CHANNEL_ID="$DISCORD_PAPER_CHANNEL_ID"
export DISCORD_TOKEN="${DISCORD_TOKEN:-${DISCORD_BOT_TOKEN:-}}"
unset DISCORD_WEBHOOK_URL || true

DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$LOG_DIR/paper_session_${DAY}.log"
PY="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] paper session start day=$DAY broker=$TRADING_AGENT_BROKER" | tee -a "$LOG"

# Optional: skip schedule wait for smoke (set PAPER_NO_WAIT=1)
if [[ "${PAPER_NO_WAIT:-0}" == "1" ]]; then
  export PAPER_NO_WAIT=1
  export TRADING_AGENT_WAIT_FOR_SCHEDULE=0
fi

exec "$PY" -m trading_agent session \
  --date "$DAY" \
  --timezone America/Los_Angeles \
  --output "$LOG" \
  --positions "$TRADING_AGENT_POSITIONS_FILE" \
  --no-cio \
  2>&1 | tee -a "$LOG"
