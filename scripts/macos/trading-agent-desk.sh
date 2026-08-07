#!/bin/bash
# macOS trading desk: positions export + 7-phase session for launchd @ 1:55 AM PT
#
# CRITICAL: launchd uses /bin/bash (macOS 3.2). Under `set -u`, expanding an
# empty array ("${arr[@]}") throws "unbound variable" and kills the job.
# Never expand empty arrays. Prefer "$@" (special-cased) or a NUL argv file.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
GROK_ENV="$HOME/.grok/trading-agent.env"
DISCORD_ENV="$HOME/.grok/discord.env"
LOG_DIR="$HOME/.trading_agent/logs"
STATE_DIR="$HOME/.trading_agent"
PID_FILE="$STATE_DIR/desk.pid"
HEARTBEAT_FILE="$STATE_DIR/desk_heartbeat.txt"
ARGC=$#

mkdir -p "$LOG_DIR" "$STATE_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Return 0 if any CLI arg equals $1. Usage: cli_has --fixture "$@"
cli_has() {
  local target="$1"
  shift || true
  local a
  for a in "$@"; do
    if [ "$a" = "$target" ]; then
      return 0
    fi
  done
  return 1
}

# --- weekend guard (date +%u: 6=Sat 7=Sun) ---
dow=$(date '+%u')
if [ "$dow" -ge 6 ]; then
  if [ "$ARGC" -eq 0 ] || ! cli_has "--fixture" "$@"; then
    log "Weekend — desk session not started."
    exit 0
  fi
fi

DATE_ARG=$(date '+%Y-%m-%d')
STARTUP_LOG="$LOG_DIR/desk_startup_${DATE_ARG}.log"
SESSION_LOG="$LOG_DIR/desk_${DATE_ARG}.log"
FAIL_LOG="$LOG_DIR/desk_fail_${DATE_ARG}.log"
ARGV_FILE="$STATE_DIR/desk_argv_${DATE_ARG}.nul"
RUNNER="$MACOS_DIR/run-argv.py"

exec > >(tee -a "$STARTUP_LOG") 2>&1

log "=== Trading desk startup (macOS) ==="
log "bash=$BASH_VERSION host=$(hostname) pid=$$"
log "Repo: $REPO"
log "Args($ARGC): $*"

# Pull researcher books (gap + playlist) from production host before desk
PULL_SCRIPT="$MACOS_DIR/pull-researcher-sync.sh"
if [ -x "$PULL_SCRIPT" ]; then
  log "Pulling researcher sync from ${RESEARCHER_HOST:-10.0.0.52}…"
  bash "$PULL_SCRIPT" || log "WARN: researcher pull failed (desk continues with local books)"
else
  log "WARN: missing $PULL_SCRIPT"
fi

# --- load env ---
if [ -f "$GROK_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$GROK_ENV"
  set +a
  log "Loaded $GROK_ENV"
else
  log "WARN: missing $GROK_ENV"
fi
if [ -f "$DISCORD_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$DISCORD_ENV"
  set +a
  export DISCORD_TOKEN="${DISCORD_BOT_TOKEN:-${DISCORD_TOKEN:-}}"
  export DISCORD_CHANNEL_ID="${DISCORD_DESK_CHANNEL_ID:-1510184298442002502}"
  unset DISCORD_WEBHOOK_URL || true
  log "Discord desk channel: $DISCORD_CHANNEL_ID (bot mode)"
else
  log "WARN: missing $DISCORD_ENV"
fi

export TRADING_AGENT_ENV_FILE="$GROK_ENV"
export TRADING_AGENT_SESSION_LOG="$SESSION_LOG"

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
log "Python: $PYTHON"

alert_fail() {
  local msg="$1"
  log "FAIL: $msg"
  echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $msg" >>"$FAIL_LOG"
  if [ -n "${DISCORD_TOKEN:-}" ] && [ -n "${DISCORD_CHANNEL_ID:-}" ] && [ -x "$PYTHON" ]; then
    MSG="$msg" "$PYTHON" - <<'PY' 2>/dev/null || true
import json, os, urllib.request
token = os.environ.get("DISCORD_TOKEN", "")
chan = os.environ.get("DISCORD_CHANNEL_ID", "")
msg = os.environ.get("MSG", "desk failed")[:1500]
body = json.dumps({
    "content": f"🚨 **Desk launch FAILED**\n```\n{msg}\n```\nCheck `~/.trading_agent/logs/`"
}).encode()
req = urllib.request.Request(
    f"https://discord.com/api/v10/channels/{chan}/messages",
    data=body,
    headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
    method="POST",
)
try:
    urllib.request.urlopen(req, timeout=15)
except Exception as exc:
    print("alert post failed:", exc)
PY
  fi
}

# --- preflight ---
if [ ! -x "$PYTHON" ]; then
  alert_fail "Python not executable: $PYTHON"
  exit 1
fi
if [ -z "${DISCORD_TOKEN:-}" ] || [ -z "${DISCORD_CHANNEL_ID:-}" ]; then
  alert_fail "Discord not configured (need DISCORD_TOKEN + DISCORD_CHANNEL_ID)"
  exit 1
fi
if [ ! -x "$HOME/schwab-mcp-server/.venv/bin/python" ]; then
  log "WARN: schwab-mcp venv missing — positions export may fail"
fi

cd "$REPO"

# --- auto pull latest research code (no manual daily prepare) ---
# Work Windows pushes methods; home Mac launchd pulls here before the desk runs.
log "Auto-updating from origin/main (non-fatal; replaces manual pull-and-ready) ..."
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git status --porcelain -- scripts/macos/trading-agent-desk.sh 2>/dev/null | grep -q .; then
    log "Local changes in trading-agent-desk.sh — skipping git pull for safety"
  else
    git fetch origin 2>&1 || log "git fetch skipped or failed"
    if git pull --ff-only origin main 2>&1; then
      log "Pulled origin/main → HEAD $(git log -1 --oneline 2>/dev/null || echo unknown)"
    else
      log "git pull --ff-only failed (continuing with local tree)"
    fi
  fi
else
  log "Not a git repo — skip pull"
fi

# --- deps: non-fatal ---
log "Installing package dependencies (non-fatal) ..."
if ! "$PYTHON" -m pip install -q -e ".[dev]"; then
  log "WARN: pip install failed — continuing with existing install"
fi
if ! "$PYTHON" -c "import trading_agent; from trading_agent.methods.options_methods import evaluate_options_methods; from trading_agent.export.auto_trade_book import build_auto_trade_book"; then
  alert_fail "trading_agent / options modules not importable after pip"
  exit 1
fi
log "trading_agent import OK (options auto-trade modules ready)"

# --- positions ---
POSITIONS_FILE="${TRADING_AGENT_POSITIONS_FILE:-$HOME/.trading_agent/positions.json}"
if [ "$ARGC" -gt 0 ] && cli_has "--fixture" "$@"; then
  log "Fixture mode — skipping live Schwab positions export"
else
  if "$MACOS_DIR/trading-agent-positions.sh"; then
    log "Positions exported to $POSITIONS_FILE"
  else
    log "WARN: positions export failed — session continues without --positions"
    POSITIONS_FILE=""
  fi
fi

# --- build argv as NUL-separated file (no bash arrays) ---
: >"$ARGV_FILE"
add_arg() {
  printf '%s\0' "$1" >>"$ARGV_FILE"
}

add_arg "$PYTHON"
add_arg "-m"
add_arg "trading_agent"
add_arg "session"
add_arg "--date"
add_arg "$DATE_ARG"
add_arg "--timezone"
add_arg "${TRADING_AGENT_TIMEZONE:-America/Los_Angeles}"
add_arg "--output"
add_arg "$SESSION_LOG"

if [ -n "${POSITIONS_FILE}" ] && [ -f "${POSITIONS_FILE}" ]; then
  add_arg "--positions"
  add_arg "$POSITIONS_FILE"
fi

# Full day by default (intraday + discovery). Override only if explicitly set.
UNTIL_PHASE="${TRADING_AGENT_UNTIL_PHASE:-cio_review}"
if [ "$UNTIL_PHASE" = "full" ] || [ "$UNTIL_PHASE" = "all" ]; then
  UNTIL_PHASE="cio_review"
fi
add_arg "--until-phase"
add_arg "$UNTIL_PHASE"
if [ "$UNTIL_PHASE" = "cio_review" ]; then
  log "Running FULL DAY desk (until cio_review) — no manual prepare step"
else
  log "Phase cap: $UNTIL_PHASE"
fi

if [ "$ARGC" -gt 0 ]; then
  for a in "$@"; do
    add_arg "$a"
  done
fi

# Ensure runner exists
if [ ! -f "$RUNNER" ]; then
  cat >"$RUNNER" <<'RUNNER'
#!/usr/bin/env python3
"""Exec NUL-separated argv file — avoids bash 3.2 empty-array + set -u crash."""
import os
import sys

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run-argv.py <nul-separated-argv-file>")
    raw = open(sys.argv[1], "rb").read().split(b"\0")
    args = [p.decode() for p in raw if p]
    if not args:
        raise SystemExit("empty argv")
    os.execvp(args[0], args)

if __name__ == "__main__":
    main()
RUNNER
  chmod +x "$RUNNER"
fi

DISPLAY_CMD=$("$PYTHON" -c "
import sys
raw=open(sys.argv[1],'rb').read().split(b'\\0')
print(' '.join(p.decode() for p in raw if p))
" "$ARGV_FILE")
log "Starting: $DISPLAY_CMD"

echo $$ >"$PID_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S %Z') starting desk" >"$HEARTBEAT_FILE"

cleanup() {
  rm -f "$PID_FILE"
}
trap cleanup EXIT

set +e
if command -v caffeinate >/dev/null 2>&1; then
  # -d display -i idle -m disk -s system (AC); keeps desk alive through waits
  caffeinate -dims "$PYTHON" "$RUNNER" "$ARGV_FILE"
  code=$?
else
  "$PYTHON" "$RUNNER" "$ARGV_FILE"
  code=$?
fi
set -e

echo "$(date '+%Y-%m-%d %H:%M:%S %Z') exited code=$code" >>"$HEARTBEAT_FILE"
log "Desk session exited with code $code"

if [ "$code" -ne 0 ]; then
  alert_fail "Desk session exited with code $code — see $SESSION_LOG"
fi

exit "$code"
