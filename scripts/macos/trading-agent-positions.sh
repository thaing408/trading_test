#!/usr/bin/env bash
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${TRADING_AGENT_POSITIONS_FILE:-$HOME/.trading_agent/positions.json}"
PYTHON="${TRADING_AGENT_PYTHON:-$HOME/trading_agent/.venv/bin/python}"

mkdir -p "$(dirname "$OUT")"
"$PYTHON" "$MACOS_DIR/trading-agent-positions.py" "$OUT"