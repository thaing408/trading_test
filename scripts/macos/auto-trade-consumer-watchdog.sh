#!/bin/bash
# P2.1 — Mac consumer watchdog.
# Restarts auto-trade consumer if not running during the manage window.
# Aligned with manage-until (default 16:00 ET ≈ 13:00 PT): trail / 0DTE flatten need
# the watch loop alive past the old 11:00 ET entry window.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
LOG_DIR="$HOME/.trading_agent/logs"
STATE_DIR="$HOME/.trading_agent"
mkdir -p "$LOG_DIR" "$STATE_DIR"
DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$LOG_DIR/auto-trade-watchdog_${DAY}.log"
ALERT_STAMP="$STATE_DIR/watchdog-last-alert.txt"
exec >>"$LOG" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export TZ="${TZ:-America/Los_Angeles}"
dow=$(date '+%u')
if [ "$dow" -ge 6 ]; then
  log "weekend skip"
  exit 0
fi

if [ -f "$HOME/.grok/trading-agent.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$HOME/.grok/trading-agent.env"
  set +a
fi
if [ -f "$HOME/.grok/discord.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$HOME/.grok/discord.env"
  set +a
fi

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3

# Watchdog active while manage window is open (PT clock derived from ET manage-until).
# Default: Mon–Fri 06:25–13:05 PT (covers 9:25 ET start → 16:00 ET manage end + buffer).
FROM_PT="${TRADING_AGENT_WATCHDOG_FROM_PT:-0625}"
UNTIL_PT="${TRADING_AGENT_WATCHDOG_UNTIL_PT:-1305}"
hm=$(date '+%H%M')
if [ "$hm" -lt "$FROM_PT" ] || [ "$hm" -gt "$UNTIL_PT" ]; then
  log "outside watchdog window hm=$hm (active ${FROM_PT}-${UNTIL_PT} PT)"
  exit 0
fi

consumer_alive() {
  pgrep -f "consume_auto_trade_book.py" >/dev/null 2>&1
}

# Rate-limit Discord: at most one DOWN/RESTARTED pair per N seconds (default 1h)
maybe_alert() {
  local msg="$1"
  local min_gap="${TRADING_AGENT_WATCHDOG_ALERT_GAP_SEC:-3600}"
  local now
  now=$(date +%s)
  local last=0
  if [ -f "$ALERT_STAMP" ]; then
    last=$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)
  fi
  if [ $((now - last)) -lt "$min_gap" ]; then
    log "alert suppressed (gap ${min_gap}s): $msg"
    return 0
  fi
  echo "$now" >"$ALERT_STAMP"
  "$PYTHON" - <<PY 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, "${REPO}")
try:
    from trading_agent.ops.alerts import post_ops_alert
    post_ops_alert("""${msg}""", title="Mac auto-trade watchdog")
except Exception as e:
    print("alert fail", e)
PY
}

if consumer_alive; then
  log "consumer OK pid=$(pgrep -f consume_auto_trade_book.py | head -1)"
  exit 0
fi

log "consumer DOWN — restarting"
maybe_alert "⚠️ **Mac consumer was DOWN** — watchdog restarting \`--watch\` (manage window through ~16:00 ET)."

export TRADING_AGENT_AUTO_TRADE_WATCH=1
nohup bash "$MACOS_DIR/auto-trade-consumer.sh" --watch >>"$LOG_DIR/auto-trade-consumer_${DAY}.log" 2>&1 &
echo $! >"$STATE_DIR/auto-trade-consumer-watchdog.pid"
sleep 3
if consumer_alive; then
  log "restart OK pid=$(pgrep -f consume_auto_trade_book.py | head -1)"
  # Only second alert if we actually alerted on DOWN (stamp freshly written)
  maybe_alert "🔴 **Mac consumer RESTARTED** by watchdog."
  exit 0
fi
log "restart FAILED"
maybe_alert "🚨 **Mac consumer restart FAILED** — check logs ~/.trading_agent/logs/"
exit 1
