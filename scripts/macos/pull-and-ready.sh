#!/usr/bin/env bash
# End-of-day / Discord-cued prep: pull latest research code from GitHub and smoke-test.
# Home Mac only — no work paths, no positions sync, no order placement.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
cd "$REPO"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== pull-and-ready (home Mac) ==="
log "Repo: $REPO"

if ! command -v git >/dev/null 2>&1; then
  log "ERROR: git not found"
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
log "Branch: $BRANCH"
log "Pulling origin/main (ff-only) ..."
git fetch origin
git pull --ff-only origin main || {
  log "WARN: ff-only pull failed — resolve local commits, then re-run"
  exit 1
}
log "HEAD: $(git log -1 --oneline)"

PYTHON="${TRADING_AGENT_PYTHON:-python3}"
if [ -x "$HOME/schwab-mcp-server/.venv/bin/python" ] && [ -z "${TRADING_AGENT_PYTHON:-}" ]; then
  # Prefer project venv if present
  if [ -x "$REPO/.venv/bin/python" ]; then
    PYTHON="$REPO/.venv/bin/python"
  fi
fi
if [ -x "$REPO/.venv/bin/python" ]; then
  PYTHON="$REPO/.venv/bin/python"
fi

log "Python: $PYTHON"
log "Installing package (editable) ..."
"$PYTHON" -m pip install -e ".[dev]" -q || "$PYTHON" -m pip install -e . -q

log "Smoke import ..."
"$PYTHON" -c "import trading_agent; from trading_agent.session.schedule import DISCOVERY_REFRESH_TIMES_PT; print('ok', trading_agent.__file__); print('discovery_slots_pt', DISCOVERY_REFRESH_TIMES_PT)"

log "Ready for next trading day."
log "Next: run local desk / TOS MCP with HOME env only (no work sync)."
log "Optional: python scripts/macos/consume_auto_trade_book.py  # only if you generate a LOCAL book"
exit 0
