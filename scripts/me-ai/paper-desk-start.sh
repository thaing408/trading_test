#!/usr/bin/env bash
# Start no-CIO paper desk session after preflight.
set -euo pipefail
STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
LOG_DIR="$STATE/logs"
mkdir -p "$LOG_DIR"
DAY=$(TZ=America/Los_Angeles date +%Y-%m-%d)
LOG="$LOG_DIR/paper_desk_launch_${DAY}.log"

if [[ -f "$STATE/paper-desk.pid" ]] && kill -0 "$(cat "$STATE/paper-desk.pid")" 2>/dev/null; then
  echo "desk already running" | tee -a "$LOG"
  exit 0
fi

export PAPER_PREFLIGHT_MODE=full
# Preflight already Discord-OK at 01:50; desk run uses quiet to reduce noise
export PAPER_PREFLIGHT_NOTIFY="${PAPER_DESK_PREFLIGHT_NOTIFY:-0}"
bash "$HOME/bin/paper-preflight.sh" || {
  echo "preflight failed" | tee -a "$LOG"
  bash "$HOME/bin/paper-discord-notify.sh" "🚨 **me-ai paper desk NOT started** · preflight failed" || true
  exit 1
}

export TRADING_AGENT_PYTHON="$HOME/trading_test/.venv/bin/python"
export PAPER_NO_WAIT="${PAPER_NO_WAIT:-0}"
nohup bash "$HOME/trading_test/scripts/macos/run-paper-session.sh" >>"$LOG" 2>&1 &
echo $! > "$STATE/paper-desk.pid"
PID=$(cat "$STATE/paper-desk.pid")
echo "desk started pid $PID log=$LOG" | tee -a "$LOG"

bash "$HOME/bin/paper-discord-notify.sh" "📘 **me-ai paper desk started** · $(TZ=America/Los_Angeles date '+%H:%M %Z')
• pid \`${PID}\` · no-CIO research → auto_trade_book
• LIVE consumer still at **06:20 PT**" || true
