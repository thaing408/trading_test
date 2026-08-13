#!/usr/bin/env bash
# Consume auto_trade_book → ready_orders; submit to IBKR paper when LIVE=1.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
ENV_FILE="${TRADING_TEST_ENV_FILE:-$STATE_DIR/trading-test.env}"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
if [[ -f "$HOME/.grok/discord.env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.grok/discord.env"
fi
set +a

export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
export TRADING_AGENT_BROKER=ibkr
export IBKR_PORT="${IBKR_PORT:-4002}"
export IBKR_HOST="${IBKR_HOST:-127.0.0.1}"
export IBKR_READONLY="${IBKR_READONLY:-0}"
export TRADING_AGENT_SYNC_DIR="${TRADING_AGENT_SYNC_DIR:-$STATE_DIR/sync}"
export TRADING_AGENT_AUTO_TRADE_ANYTIME="${TRADING_AGENT_AUTO_TRADE_ANYTIME:-1}"
export DISCORD_PAPER_CHANNEL_ID="${DISCORD_PAPER_CHANNEL_ID:-1536602374502613013}"
export DISCORD_CHANNEL_ID="$DISCORD_PAPER_CHANNEL_ID"
export DISCORD_TOKEN="${DISCORD_TOKEN:-${DISCORD_BOT_TOKEN:-}}"
unset DISCORD_WEBHOOK_URL || true

PY="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$STATE_DIR/logs/paper_consumer_${DAY}.log"
mkdir -p "$STATE_DIR/logs"

LIVE_FLAG=()
if [[ "${TRADING_AGENT_AUTO_TRADE_LIVE:-0}" == "1" ]]; then
  LIVE_FLAG=(--live)
  echo "WARNING: LIVE paper orders enabled" | tee -a "$LOG"
fi

ANY_FLAG=()
if [[ "${TRADING_AGENT_AUTO_TRADE_ANYTIME:-0}" == "1" ]]; then
  ANY_FLAG=(--anytime)
fi

exec "$PY" "$REPO/scripts/macos/consume_auto_trade_book.py" \
  --watch \
  --poll-seconds 60 \
  "${LIVE_FLAG[@]}" \
  "${ANY_FLAG[@]}" \
  2>&1 | tee -a "$LOG"
