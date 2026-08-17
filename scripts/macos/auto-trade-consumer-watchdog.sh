#!/bin/bash
# P2.1 — Mac consumer watchdog (Mon–Fri ~06:30–11:00 PT window).
# Restarts auto-trade consumer if not running; Discord alert on restart/fail.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
LOG_DIR="$HOME/.trading_agent/logs"
mkdir -p "$LOG_DIR"
DAY=$(TZ=America/Los_Angeles date '+%Y-%m-%d')
LOG="$LOG_DIR/auto-trade-watchdog_${DAY}.log"
exec >>"$LOG" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

export TZ="${TZ:-America/Los_Angeles}"
dow=$(date '+%u')
if [ "$dow" -ge 6 ]; then
  log "weekend skip"
  exit 0
fi
hm=$(date '+%H%M')
# Active after consumer start through ~11:00 PT (consumer window is ET 9:25–11:00 ≈ PT 6:25–8:00,
# but QT/open can extend; allow 06:30–11:00 PT checks)
if [ "$hm" -lt 0630 ] || [ "$hm" -gt 1100 ]; then
  log "outside watchdog window hm=$hm"
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

consumer_alive() {
  pgrep -f "consume_auto_trade_book.py" >/dev/null 2>&1
}

if consumer_alive; then
  log "consumer OK"
  exit 0
fi

log "consumer DOWN — restarting"
# Discord alert via python (fail-open)
"$PYTHON" - <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "trading_agent"))
try:
    from trading_agent.ops.alerts import post_ops_alert
    post_ops_alert(
        "⚠️ **Mac consumer was DOWN** — watchdog restarting `--watch`.",
        title="Mac auto-trade watchdog",
    )
except Exception as e:
    print("alert fail", e)
PY

export TRADING_AGENT_AUTO_TRADE_WATCH=1
nohup bash "$MACOS_DIR/auto-trade-consumer.sh" --watch >>"$LOG" 2>&1 &
echo $! >"$HOME/.trading_agent/auto-trade-consumer-watchdog.pid"
sleep 2
if consumer_alive; then
  log "restart OK pid=$(pgrep -f consume_auto_trade_book.py | head -1)"
  "$PYTHON" - <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "trading_agent"))
try:
    from trading_agent.ops.alerts import post_ops_alert
    post_ops_alert("🔴 **Mac consumer RESTARTED** by watchdog.", title="Mac auto-trade watchdog")
except Exception:
    pass
PY
  exit 0
fi
log "restart FAILED"
"$PYTHON" - <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "trading_agent"))
try:
    from trading_agent.ops.alerts import post_ops_alert
    post_ops_alert(
        "🚨 **Mac consumer restart FAILED** — check logs ~/.trading_agent/logs/",
        title="Mac auto-trade watchdog",
    )
except Exception:
    pass
PY
exit 1
