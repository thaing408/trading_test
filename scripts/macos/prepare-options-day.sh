#!/usr/bin/env bash
# DEPRECATED as a daily chore. launchd desk auto-pulls + runs full day.
# This script only exists for one-off recovery if launchd is not installed.
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[prepare-options-day] No manual daily prepare required when launchd is installed."
echo "[prepare-options-day] Running optional recovery pull only ..."
exec bash "$MACOS_DIR/pull-and-ready.sh"
