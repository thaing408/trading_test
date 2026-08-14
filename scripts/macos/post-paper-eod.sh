#!/usr/bin/env bash
# Post end-of-day IBKR paper P/L journal (like prod trading-journal) to #ibkr-tradings.
# Requires: Gateway API up, DISCORD_TOKEN, DISCORD_IBKR_CHANNEL_ID (or paper fallback).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
ENV_FILE="${TRADING_TEST_ENV_FILE:-$STATE_DIR/trading-test.env}"

set -a
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
[[ -f "$HOME/.grok/discord.env" ]] && source "$HOME/.grok/discord.env"
[[ -f "$HOME/.trading_test/discord-paper.env" ]] && source "$HOME/.trading_test/discord-paper.env"
set +a

export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
export DISCORD_TOKEN="${DISCORD_TOKEN:-${DISCORD_BOT_TOKEN:-}}"
# #ibkr-tradings — set channel snowflake in env
export DISCORD_IBKR_CHANNEL_ID="${DISCORD_IBKR_CHANNEL_ID:-${DISCORD_IBKR_TRADINGS_CHANNEL_ID:-}}"
export DISCORD_PAPER_CHANNEL_ID="${DISCORD_PAPER_CHANNEL_ID:-1536602374502613013}"
export DISCORD_CHANNEL_ID="${DISCORD_IBKR_CHANNEL_ID:-$DISCORD_PAPER_CHANNEL_ID}"
unset DISCORD_WEBHOOK_URL || true
export TRADING_AGENT_SYNC_DIR="${TRADING_AGENT_SYNC_DIR:-$STATE_DIR/sync}"
export IBKR_ENABLED="${IBKR_ENABLED:-1}"
export IBKR_HOST="${IBKR_HOST:-127.0.0.1}"
export IBKR_PORT="${IBKR_PORT:-4002}"

PY="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/paper_eod_${DAY}.log"

{
  echo "==== EOD $(date -Is) day=$DAY ===="
  echo "IBKR channel=${DISCORD_IBKR_CHANNEL_ID:-'(fallback paper channel)'}"
  "$PY" - <<PY
from trading_agent.discord.paper_activity import (
    build_pnl_journal,
    fetch_ibkr_day_pnl,
    post_eod_summary,
    post_positions,
    ibkr_journal_channel_id,
)

day = "$DAY"
print("channel", ibkr_journal_channel_id())
pnl = fetch_ibkr_day_pnl(trading_date=day)
print("connected", pnl.get("connected"), "realized", pnl.get("realized_pnl"), "unrealized", pnl.get("unrealized_pnl"), "fills", len(pnl.get("fills") or []))
print("--- journal preview ---")
print(build_pnl_journal(trading_date=day, pnl=pnl)[:1500])
print("--- posting ---")
r1 = post_eod_summary(trading_date=day, to_ibkr_channel=True)
print("eod", r1)
r2 = post_positions(source="IBKR paper EOD")
print("positions", r2)
print("OK")
PY
} 2>&1 | tee -a "$LOG"
