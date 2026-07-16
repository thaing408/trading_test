#!/bin/bash
# macOS auto-trade book consumer (launchd-friendly).
# Polls local books → ready_orders; live only if TRADING_AGENT_AUTO_TRADE_LIVE=1.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
GROK_ENV="$HOME/.grok/trading-agent.env"
DISCORD_ENV="$HOME/.grok/discord.env"
LOG_DIR="$HOME/.trading_agent/logs"
mkdir -p "$LOG_DIR"

DATE_ARG=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$LOG_DIR/auto-trade-consumer_${DATE_ARG}.log"
exec >>"$LOG" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Weekend guard
dow=$(date '+%u')
if [ "$dow" -ge 6 ]; then
  log "Weekend — auto-trade consumer skip"
  exit 0
fi

if [ -f "$GROK_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$GROK_ENV"
  set +a
fi
if [ -f "$DISCORD_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$DISCORD_ENV"
  set +a
fi

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

export TRADING_AGENT_ENV_FILE="${TRADING_AGENT_ENV_FILE:-$GROK_ENV}"
POLL="${TRADING_AGENT_AUTO_TRADE_POLL:-60}"
# Consumer window loop: stay up through 9:25–11:00 ET when started from open-window job
WATCH="${1:-}"

log "=== auto-trade consumer start ==="
log "python=$PYTHON live=${TRADING_AGENT_AUTO_TRADE_LIVE:-0} poll=$POLL"

cd "$REPO"
# Watch stays inside 9:25–11:00 ET (exits when window ends). One-shot uses --anytime for manual runs.
if [ "$WATCH" = "--watch" ] || [ "${TRADING_AGENT_AUTO_TRADE_WATCH:-0}" = "1" ]; then
  exec "$PYTHON" "$MACOS_DIR/consume_auto_trade_book.py" --watch --poll-seconds "$POLL"
else
  exec "$PYTHON" "$MACOS_DIR/consume_auto_trade_book.py" --anytime
fi
