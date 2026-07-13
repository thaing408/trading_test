#!/usr/bin/env bash
# Mon–Fri 6:35 AM PT — live scalp check → #scalp-pulse
set -euo pipefail

LOG="$HOME/.grok/logs/morning-check-635.log"
mkdir -p "$(dirname "$LOG")"

{
  echo "=== $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M %Z') morning check ==="
  "$HOME/.grok/scripts/scalp-market-pulse.sh" --force --force-brief 2>&1
  echo ""
} >>"$LOG" 2>&1

tail -3 "$LOG"
