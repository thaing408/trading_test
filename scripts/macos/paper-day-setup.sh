#!/usr/bin/env bash
# One-time / morning setup for trading_test + IBKR paper (no CIO).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_DIR="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
ENV_FILE="${TRADING_TEST_ENV_FILE:-$STATE_DIR/trading-test.env}"
VENV="$REPO/.venv"
PY="$VENV/bin/python"

mkdir -p "$STATE_DIR/sync" "$STATE_DIR/logs" "$STATE_DIR/sessions" "$STATE_DIR/ready_orders"

if [[ ! -x "$PY" ]]; then
  echo "Creating venv at $VENV …"
  python3.11 -m venv "$VENV"
  "$VENV/bin/pip" install -U pip
  "$VENV/bin/pip" install -e "$REPO" ib_insync
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$REPO/.env.paper.example" "$ENV_FILE"
  echo "Wrote $ENV_FILE — review IBKR_READONLY and LIVE flags."
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

export TRADING_AGENT_SYNC_DIR="${TRADING_AGENT_SYNC_DIR:-$STATE_DIR/sync}"
export IBKR_PORT="${IBKR_PORT:-7497}"
export IBKR_ENABLED=1
export TRADING_AGENT_BROKER="${TRADING_AGENT_BROKER:-ibkr}"
export TRADING_AGENT_INCLUDE_CIO=0

echo "=== trading_test paper setup ==="
echo "repo=$REPO"
echo "env=$ENV_FILE"
echo "sync=$TRADING_AGENT_SYNC_DIR"
echo "broker=$TRADING_AGENT_BROKER port=$IBKR_PORT readonly=${IBKR_READONLY:-?} live=${TRADING_AGENT_AUTO_TRADE_LIVE:-0}"

echo "=== IBKR research ping ==="
IBKR_ENABLED=1 IBKR_PORT="$IBKR_PORT" IBKR_READONLY=1 \
  "$PY" "$REPO/scripts/ibkr_research_ping.py" || true

echo "=== IBKR trade socket ping ==="
"$PY" - <<'PY'
from trading_agent.oms.ibkr_broker import ping_trade_connection
import json
print(json.dumps(ping_trade_connection(), indent=2))
PY

echo "=== No-CIO config check ==="
"$PY" - <<'PY'
from trading_agent.session.config import SessionConfig
c = SessionConfig.from_env()
print(f"include_cio={c.include_cio} auto_export={c.auto_export_book_without_cio}")
assert c.include_cio is False, "CIO should be off"
print("OK no-CIO")
PY

echo "Done. Tomorrow:"
echo "  1. Start TWS paper, API port 7497, uncheck Read-Only if you will place orders"
echo "  2. bash $REPO/scripts/macos/run-paper-session.sh"
echo "  3. When ready for paper fills: TRADING_AGENT_AUTO_TRADE_LIVE=1 in env, then consumer"
