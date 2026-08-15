#!/usr/bin/env bash
# Mon–Fri RTH watchdog: ensure LIVE paper consumer is running after 06:25 PT.
# Posts Discord if it had to restart or if Gateway/API is down.
set -euo pipefail

export TZ="${TZ:-America/Los_Angeles}"
# Only weekdays
dow=$(date +%u)  # 1=Mon … 7=Sun
if [[ "$dow" -gt 5 ]]; then
  exit 0
fi
# PT clock: run checks 06:30–13:15 only
hm=$(date +%H%M)
if [[ "$hm" -lt 0630 || "$hm" -gt 1315 ]]; then
  exit 0
fi

STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
LOG_DIR="$STATE/logs"
mkdir -p "$LOG_DIR"
DAY=$(date +%Y-%m-%d)
LOG="$LOG_DIR/paper_watchdog_${DAY}.log"
exec >>"$LOG" 2>&1
echo "==== watchdog $(date -u -Is) utc / $(date -Is) pt ===="

NOTIFY="$HOME/bin/paper-discord-notify.sh"
notify() {
  [[ -x "$NOTIFY" ]] && bash "$NOTIFY" "$1" || true
}

# Consumer alive?
alive=0
if [[ -f "$STATE/paper-consumer.pid" ]]; then
  pid=$(cat "$STATE/paper-consumer.pid" 2>/dev/null || true)
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    alive=1
  fi
fi
if [[ "$alive" != "1" ]]; then
  # orphan python?
  if ps -eo args= 2>/dev/null | grep -q 'consume_auto_trade_book.py'; then
    alive=1
    echo "consumer python alive (no pid file)"
  fi
fi

if [[ "$alive" == "1" ]]; then
  echo "consumer OK"
  exit 0
fi

echo "consumer DOWN — restarting"
notify "⚠️ **me-ai paper watchdog** · LIVE consumer was **down** at $(date '+%H:%M %Z') — restarting…"
export TRADING_AGENT_AUTO_TRADE_LIVE=1
export TRADING_AGENT_AUTO_TRADE_ANYTIME=1
export PAPER_PREFLIGHT_NOTIFY=1
if bash "$HOME/bin/paper-consumer-start.sh"; then
  notify "🔴 **me-ai paper watchdog** · consumer **restarted** (LIVE) at $(date '+%H:%M %Z')"
  echo "restart OK"
  exit 0
fi
notify "🚨 **me-ai paper watchdog** · consumer restart **FAILED** — check Gateway :4002 / VNC / client ids"
echo "restart FAILED"
exit 1
