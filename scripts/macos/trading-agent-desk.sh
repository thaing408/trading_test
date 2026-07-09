#!/usr/bin/env bash
# macOS trading desk: git pull, install, Schwab positions, run 7-phase session
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
GROK_ENV="$HOME/.grok/trading-agent.env"
DISCORD_ENV="$HOME/.grok/discord.env"
LOG_DIR="$HOME/.trading_agent/logs"

EXTRA_ARGS=("$@")

has_extra_arg() {
  local target="$1"
  for arg in "${EXTRA_ARGS[@]}"; do
    [[ "$arg" == "$target" ]] && return 0
  done
  return 1
}

mkdir -p "$LOG_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

dow=$(date '+%u')
if [[ "$dow" -ge 6 ]] && ! has_extra_arg "--fixture"; then
  log "Weekend — desk session not started."
  exit 0
fi

DATE_ARG=$(date '+%Y-%m-%d')
STARTUP_LOG="$LOG_DIR/desk_startup_${DATE_ARG}.log"
SESSION_LOG="$LOG_DIR/desk_${DATE_ARG}.log"

exec > >(tee -a "$STARTUP_LOG") 2>&1

log "=== Trading desk startup (macOS) ==="
log "Repo: $REPO"

if [[ -f "$GROK_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$GROK_ENV"
  set +a
  log "Loaded $GROK_ENV"
fi
if [[ -f "$DISCORD_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$DISCORD_ENV"
  set +a
  export DISCORD_TOKEN="${DISCORD_BOT_TOKEN:-${DISCORD_TOKEN:-}}"
  export DISCORD_CHANNEL_ID="${DISCORD_DESK_CHANNEL_ID:-1510184298442002502}"
  unset DISCORD_WEBHOOK_URL
  log "Discord desk channel: $DISCORD_CHANNEL_ID (bot mode)"
fi

export TRADING_AGENT_ENV_FILE="$GROK_ENV"
export TRADING_AGENT_SESSION_LOG="$SESSION_LOG"

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
log "Python: $PYTHON"

cd "$REPO"
log "Pulling latest from origin/main ..."
git pull origin main 2>&1 || log "git pull skipped or failed (continuing)"

log "Installing package dependencies ..."
"$PYTHON" -m pip install -q -e ".[dev]"

if has_extra_arg "--fixture"; then
  log "Fixture mode — skipping live Schwab positions export"
else
  if "$MACOS_DIR/trading-agent-positions.sh"; then
    log "Positions exported to ${TRADING_AGENT_POSITIONS_FILE:-$HOME/.trading_agent/positions.json}"
  else
    log "WARN: positions export failed — session continues without --positions"
    unset TRADING_AGENT_POSITIONS_FILE
  fi
fi

SESSION_CMD=(
  "$PYTHON" -m trading_agent session
  --date "$DATE_ARG"
  --timezone "${TRADING_AGENT_TIMEZONE:-America/Los_Angeles}"
  --output "$SESSION_LOG"
)

if [[ -n "${TRADING_AGENT_POSITIONS_FILE:-}" && -f "${TRADING_AGENT_POSITIONS_FILE}" ]]; then
  SESSION_CMD+=(--positions "$TRADING_AGENT_POSITIONS_FILE")
fi

if [[ -n "${TRADING_AGENT_UNTIL_PHASE:-}" ]]; then
  SESSION_CMD+=(--until-phase "$TRADING_AGENT_UNTIL_PHASE")
  log "Phase cap: $TRADING_AGENT_UNTIL_PHASE"
else
  log "Running full 7-phase desk day"
fi

SESSION_CMD+=("${EXTRA_ARGS[@]}")

log "Starting: ${SESSION_CMD[*]}"
# Prevent idle sleep for the full desk day (~02:00–13:30 PT)
if command -v caffeinate >/dev/null; then
  caffeinate -i "${SESSION_CMD[@]}"
else
  "${SESSION_CMD[@]}"
fi
code=$?
log "Desk session exited with code $code"
exit "$code"