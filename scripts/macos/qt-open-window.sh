#!/bin/bash
# QT open-window (9:30–9:50 ET / 6:30–6:50 PT): run mech model → export book → consume.
# Intended for launchd at 6:30 PT weekdays; loops until window ends.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
GROK_ENV="$HOME/.grok/trading-agent.env"
LOG_DIR="$HOME/.trading_agent/logs"
mkdir -p "$LOG_DIR"

DATE_ARG=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$LOG_DIR/qt-open-window_${DATE_ARG}.log"
exec >>"$LOG" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

dow=$(date '+%u')
if [ "$dow" -ge 6 ]; then
  log "Weekend — QT open-window skip"
  exit 0
fi

if [ -f "$GROK_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$GROK_ENV"
  set +a
fi

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

export TZ=America/Los_Angeles
cd "$REPO"

log "=== QT open-window start ==="
log "python=$PYTHON repo=$REPO"

# Keep Mac awake during open window
CAFFEINATE=()
if command -v caffeinate >/dev/null 2>&1; then
  CAFFEINATE=(caffeinate -dims)
fi

# Loop ~25 minutes covering 9:30–9:50 ET (6:30–6:50 PT) plus a few minutes
END_EPOCH=$(( $(date +%s) + ${TRADING_AGENT_QT_WINDOW_SECONDS:-1500} ))
SYMBOLS="${TRADING_AGENT_QT_SYMBOLS:-QQQ SPY IWM}"
ITER=0

while [ "$(date +%s)" -lt "$END_EPOCH" ]; do
  ITER=$((ITER + 1))
  log "QT pass $ITER symbols=$SYMBOLS"
  set +e
  # shellcheck disable=SC2086
  "${CAFFEINATE[@]}" "$PYTHON" -m trading_agent qt --export $(printf -- '--symbol %s ' $SYMBOLS)
  code=$?
  set -e
  log "qt export exit=$code"

  set +e
  "$PYTHON" "$MACOS_DIR/consume_auto_trade_book.py" --anytime
  ccode=$?
  set -e
  log "consume exit=$ccode"

  # Sleep between passes (default 60s)
  sleep "${TRADING_AGENT_QT_POLL:-60}"
done

log "=== QT open-window done (passes=$ITER) ==="
exit 0
