#!/usr/bin/env bash
# Install Mon–Fri 6:35 AM PT morning check (adds Monday, excludes Saturday).
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
NAME="com.grok.morning-check"
DST="$HOME/Library/LaunchAgents/$NAME.plist"
GROK_DIR="$HOME/.grok"

chmod +x "$MACOS_DIR/morning-check-635.sh"
mkdir -p "$GROK_DIR/scripts" "$GROK_DIR/launchd" "$GROK_DIR/logs" "$HOME/Library/LaunchAgents"

cp "$MACOS_DIR/morning-check-635.sh" "$GROK_DIR/scripts/"
chmod +x "$GROK_DIR/scripts/morning-check-635.sh"

sed "s|__HOME__|$HOME|g" "$MACOS_DIR/com.grok.morning-check.plist" > "$GROK_DIR/launchd/$NAME.plist"
cp "$GROK_DIR/launchd/$NAME.plist" "$DST"

launchctl bootout "gui/$(id -u)/$NAME" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST"
launchctl enable "gui/$(id -u)/$NAME"

echo "✓ $NAME — Mon–Fri 6:35 AM PT → #scalp-pulse"
echo "Log: ~/.grok/logs/morning-check-635.log"
