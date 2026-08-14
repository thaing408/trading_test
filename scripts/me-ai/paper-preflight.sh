#!/usr/bin/env bash
# me-ai paper preflight: Gateway :4002 + research ping + positions seed + Discord.
#
# Modes:
#   full   (default) — wake stack, verify API, seed positions, Discord OK/FAIL
#   wake   — only ensure Xvfb/x11vnc/Gateway process (early morning, before login)
#   quiet  — full checks, no Discord success (still Discord on FAIL)
#
# Env:
#   PAPER_PREFLIGHT_MODE=full|wake|quiet
#   PAPER_PREFLIGHT_NOTIFY=1|0   (default 1 for full)
#   PAPER_PREFLIGHT_RETRIES=6
#   PAPER_PREFLIGHT_SLEEP=15
set -euo pipefail

STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
LOG_DIR="$STATE/logs"
mkdir -p "$LOG_DIR"
DAY=$(TZ=America/Los_Angeles date +%Y-%m-%d)
LOG="$LOG_DIR/preflight_${DAY}.log"
MODE="${PAPER_PREFLIGHT_MODE:-full}"
NOTIFY="${PAPER_PREFLIGHT_NOTIFY:-1}"
RETRIES="${PAPER_PREFLIGHT_RETRIES:-6}"
SLEEP_S="${PAPER_PREFLIGHT_SLEEP:-15}"

NOTIFY_BIN="$HOME/bin/paper-discord-notify.sh"
if [[ ! -x "$NOTIFY_BIN" ]]; then
  NOTIFY_BIN="$(cd "$(dirname "$0")" && pwd)/paper-discord-notify.sh"
fi

notify() {
  local msg="$1"
  if [[ "$NOTIFY" != "1" ]]; then
    echo "notify skipped: $msg"
    return 0
  fi
  if [[ -x "$NOTIFY_BIN" ]]; then
    bash "$NOTIFY_BIN" "$msg" || echo "notify failed (non-fatal)"
  else
    echo "notify binary missing: $NOTIFY_BIN"
  fi
}

# Always log to file; also print to stdout when interactive
exec >>"$LOG" 2>&1
echo "==== preflight mode=$MODE $(date -u -Is) utc / $(TZ=America/Los_Angeles date -Is) pt ===="

port_up() {
  ss -lntp 2>/dev/null | grep -q ":4002" || \
    netstat -lntp 2>/dev/null | grep -q ":4002"
}

ensure_display() {
  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    echo "Starting Xvfb :99 1400x900..."
    nohup Xvfb :99 -screen 0 1400x900x24 -ac -nolisten tcp >/tmp/Xvfb-99.log 2>&1 &
    sleep 1
  else
    echo "Xvfb already running"
  fi
  if ! pgrep -x x11vnc >/dev/null 2>&1; then
    echo "Starting x11vnc :99 -> localhost:5900..."
    nohup x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw -noxdamage \
      >/tmp/x11vnc-99.log 2>&1 &
    sleep 1
  else
    echo "x11vnc already running"
  fi
}

ensure_gateway() {
  if port_up; then
    echo "4002 already listening"
    return 0
  fi
  echo "4002 down — starting IB Gateway on DISPLAY=:99"
  if [[ -x "$HOME/bin/start-ibgateway-display99.sh" ]]; then
    bash "$HOME/bin/start-ibgateway-display99.sh" || true
  else
    export DISPLAY=:99
    ensure_display
    cd "${IBGATEWAY_HOME:-$HOME/ibgateway}"
    nohup ./ibgateway >>"$HOME/ibgateway/logs/gateway-display99.log" 2>&1 &
  fi
  # Gateway often needs login before 4002 opens
  local i
  for i in $(seq 1 "$RETRIES"); do
    if port_up; then
      echo "4002 up after try $i"
      return 0
    fi
    echo "waiting for 4002 ($i/$RETRIES) sleep ${SLEEP_S}s..."
    sleep "$SLEEP_S"
  done
  return 1
}

# --- wake mode: start stack only (early cron) ---
if [[ "$MODE" == "wake" ]]; then
  ensure_display
  ensure_gateway || true
  if port_up; then
    echo "wake OK — 4002 up"
    # Only ping Discord if it was down earlier today? Keep quiet on success for wake.
    # Notify only if still down after wake (user must VNC login).
    :
  else
    echo "wake: Gateway started but 4002 still down — need paper VNC login"
    notify "⚠️ **me-ai paper wake** · Gateway process started but **:4002 not open** yet.
Re-login **paper** via TigerVNC (ssh tunnel → \`127.0.0.1:5901\`) before desk.
\`ssh -N -L 5901:127.0.0.1:5900 ubuntu@10.0.0.52\`"
  fi
  echo "wake done"
  exit 0
fi

# --- full / quiet ---
ensure_display
if ! ensure_gateway; then
  echo "FATAL: 4002 not listening after retries"
  notify "🚨 **me-ai paper preflight FAIL** · Gateway **:4002 down**
Desk/consumer will not run until paper login.
1. \`ssh -N -L 5901:127.0.0.1:5900 ubuntu@10.0.0.52\`
2. TigerVNC → \`127.0.0.1:5901\`
3. Log into **IB Gateway paper** (API 4002, not read-only)"
  exit 1
fi

cd "$HOME/trading_test"
set -a
[[ -f "$STATE/trading-test.env" ]] && source "$STATE/trading-test.env"
[[ -f "$STATE/discord-paper.env" ]] && source "$STATE/discord-paper.env"
set +a

# Research ping
PING_JSON=""
if ! PING_JSON=$(.venv/bin/python scripts/ibkr_research_ping.py --json 2>&1); then
  echo "FATAL: research ping failed: $PING_JSON"
  notify "🚨 **me-ai paper preflight FAIL** · :4002 open but **API ping failed**
\`\`\`
$(echo "$PING_JSON" | head -c 400)
\`\`\`
Check Gateway login / API client permissions."
  exit 1
fi
echo "$PING_JSON"

# Seed positions so desk never FileNotFoundError
POS_FILE="${TRADING_AGENT_POSITIONS_FILE:-$STATE/positions.json}"
export TRADING_AGENT_POSITIONS_FILE="$POS_FILE"
export TRADING_AGENT_STATE_DIR="$STATE"
export IBKR_ENABLED="${IBKR_ENABLED:-1}"
export TRADING_AGENT_BROKER="${TRADING_AGENT_BROKER:-ibkr}"
POS_N="?"
POS_SYMS="—"
if POS_OUT=$(.venv/bin/python - <<'PY'
import os
from trading_agent.intraday.plan_loader import load_positions, _maybe_seed_ibkr_positions_file
path = os.environ.get("TRADING_AGENT_POSITIONS_FILE", "")
_maybe_seed_ibkr_positions_file(path)
pos = load_positions(path, False, refresh=False)
syms = ",".join(p.symbol for p in pos[:8]) or "—"
print(f"{len(pos)}|{syms}")
PY
); then
  POS_N="${POS_OUT%%|*}"
  POS_SYMS="${POS_OUT#*|}"
  echo "positions loaded: n=$POS_N syms=$POS_SYMS"
else
  echo "positions seed warning (non-fatal)"
fi

# Parse ping for last_close if present
LAST=$(echo "$PING_JSON" | .venv/bin/python -c 'import sys,json
try:
 d=json.load(sys.stdin); print(d.get("last_close") or d.get("connected") or "?")
except Exception:
 print("?")' 2>/dev/null || echo "?")

echo "preflight OK mode=$MODE pos=$POS_N last=$LAST"

if [[ "$MODE" == "quiet" ]]; then
  exit 0
fi

notify "✅ **me-ai paper preflight OK** · $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M %Z')
• Gateway **:4002** up · API connected
• Research ping last≈\`${LAST}\`
• Open positions: **${POS_N}** (\`${POS_SYMS}\`)
• Next: desk ~01:55 PT · LIVE consumer ~06:20 PT
• VNC if needed: tunnel \`5901→5900\` then TigerVNC"

exit 0
