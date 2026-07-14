#!/usr/bin/env bash
# Home Mac: pull latest research code from GitHub, then print options ENTER checklist.
# Fully separated from work — no shared positions/journal with Windows.
# Does NOT place TOS orders; use with local Schwab/TOS MCP after review.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$MACOS_DIR/../.." && pwd)"
cd "$REPO"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== prepare-options-day (home Mac) ==="

if [ -x "$MACOS_DIR/pull-and-ready.sh" ]; then
  bash "$MACOS_DIR/pull-and-ready.sh"
else
  git pull --ff-only origin main || true
fi

PYTHON="${TRADING_AGENT_PYTHON:-python3}"
if [ -x "$REPO/.venv/bin/python" ]; then
  PYTHON="$REPO/.venv/bin/python"
fi

log "Options ENTER checklist from local auto_trade_book (if any) ..."
# Prefer session book generated on THIS machine after a local research dry-run;
# work Discord is the brief — book file is optional/local only.
BOOK="${1:-}"
if [ -z "$BOOK" ]; then
  if [ -n "${TRADING_AGENT_SYNC_DIR:-}" ] && [ -f "$TRADING_AGENT_SYNC_DIR/auto_trade_book.json" ]; then
    BOOK="$TRADING_AGENT_SYNC_DIR/auto_trade_book.json"
  elif [ -f "$HOME/.trading_agent/sync/auto_trade_book.json" ]; then
    BOOK="$HOME/.trading_agent/sync/auto_trade_book.json"
  else
    TODAY=$(date '+%Y-%m-%d')
    if [ -f "$HOME/.trading_agent/sessions/$TODAY/auto_trade_book.json" ]; then
      BOOK="$HOME/.trading_agent/sessions/$TODAY/auto_trade_book.json"
    fi
  fi
fi

if [ -n "${BOOK:-}" ] && [ -f "$BOOK" ]; then
  "$PYTHON" "$MACOS_DIR/consume_auto_trade_book.py" "$BOOK"
else
  log "No local auto_trade_book.json found."
  log "Use Discord research posts for ideas, or run local:"
  log "  $PYTHON -m trading_agent premarket --fixture   # dry structure"
  log "  Then trade defined-risk ENTERs in TOS with your own size rules."
fi

log "TOS checklist:"
log "  1) Confirm IV rank / DTE / liquidity on chain match Discord card"
log "  2) Defined-risk only (spreads/condors/long options)"
log "  3) Bracket: stop + target from card; size by max_risk_dollars"
log "  4) No short premium into earnings without plan"
log "  5) After fills: keep positions/journal LOCAL on Mac"
log "Done."
exit 0
