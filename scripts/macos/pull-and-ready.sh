#!/usr/bin/env bash
# OPTIONAL manual recovery only. Normal path: launchd runs trading-agent-desk.sh
# which auto git-pulls + installs before the desk — no daily manual prepare.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
cd "$REPO"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== pull-and-ready (optional recovery) ==="
log "NOTE: Weekday launchd desk already auto-pulls at 01:55 PT — you do not need this daily."

if ! command -v git >/dev/null 2>&1; then
  log "ERROR: git not found"
  exit 1
fi

git fetch origin
git pull --ff-only origin main || {
  log "WARN: ff-only pull failed — resolve local commits, then re-run"
  exit 1
}
log "HEAD: $(git log -1 --oneline)"

PYTHON="${TRADING_AGENT_PYTHON:-python3}"
if [ -x "$REPO/.venv/bin/python" ]; then
  PYTHON="$REPO/.venv/bin/python"
fi

"$PYTHON" -m pip install -e ".[dev]" -q || "$PYTHON" -m pip install -e . -q
"$PYTHON" -c "import trading_agent; from trading_agent.methods.options_methods import OPTIONS_BASELINE_METHODS; print('ok', len(OPTIONS_BASELINE_METHODS), 'options methods')"

log "Ready. Prefer launchd com.grok.trading-agent-desk for automatic daily runs."
exit 0
