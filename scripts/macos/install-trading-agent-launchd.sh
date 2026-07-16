#!/usr/bin/env bash
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
NAME="com.grok.trading-agent-desk"
DST="$HOME/Library/LaunchAgents/$NAME.plist"
GROK_DIR="$HOME/.grok"

chmod +x "$MACOS_DIR/trading-agent-desk.sh"
chmod +x "$MACOS_DIR/trading-agent-positions.sh"
chmod +x "$MACOS_DIR/trading-agent-positions.py"
chmod +x "$MACOS_DIR/run-argv.py" 2>/dev/null || true
chmod +x "$MACOS_DIR/desk-healthcheck.sh" 2>/dev/null || true

mkdir -p "$GROK_DIR/scripts" "$GROK_DIR/launchd" "$HOME/.trading_agent/logs" "$HOME/Library/LaunchAgents"

# Sync convenience copies for Grok pipeline
cp "$MACOS_DIR/trading-agent-desk.sh" "$GROK_DIR/scripts/"
cp "$MACOS_DIR/trading-agent-positions.sh" "$GROK_DIR/scripts/"
cp "$MACOS_DIR/trading-agent-positions.py" "$GROK_DIR/scripts/"
cp "$MACOS_DIR/run-argv.py" "$GROK_DIR/scripts/" 2>/dev/null || true
cp "$MACOS_DIR/desk-healthcheck.sh" "$GROK_DIR/scripts/" 2>/dev/null || true
chmod +x "$GROK_DIR/scripts/"*.sh "$GROK_DIR/scripts/"*.py 2>/dev/null || true

if [[ ! -f "$GROK_DIR/trading-agent.env" ]]; then
  sed "s|__HOME__|$HOME|g; s|\$HOME|$HOME|g" "$MACOS_DIR/trading-agent.env.example" > "$GROK_DIR/trading-agent.env"
  echo "Created $GROK_DIR/trading-agent.env from example"
fi

sed "s|__HOME__|$HOME|g" "$MACOS_DIR/com.grok.trading-agent-desk.plist" > "$GROK_DIR/launchd/$NAME.plist"
cp "$GROK_DIR/launchd/$NAME.plist" "$DST"

launchctl bootout "gui/$(id -u)/$NAME" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST"
launchctl enable "gui/$(id -u)/$NAME"

echo "✓ $NAME — weekdays 1:55 AM PT → 7-phase trading desk"
echo "Desk Discord: #daily-plays (${DISCORD_DESK_CHANNEL_ID:-1510184298442002502})"
echo "Logs: ~/.trading_agent/logs/"
echo ""
Also install QT open-window + auto-trade consumer:"
echo "  bash scripts/macos/install-auto-trade-launchd.sh"
