#!/usr/bin/env bash
# Install Mac auto-launch + auto-trade LaunchAgents:
#   com.grok.trading-agent-desk   (01:55 PT — already via install-trading-agent-launchd.sh)
#   com.grok.qt-open-window       (06:30 PT — QT 9:30 ET window)
#   com.grok.auto-trade-consumer  (06:25 PT — book → ready orders / optional live)
set -euo pipefail

MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
GROK_DIR="$HOME/.grok"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"

chmod +x "$MACOS_DIR/trading-agent-desk.sh" 2>/dev/null || true
chmod +x "$MACOS_DIR/trading-agent-positions.sh" 2>/dev/null || true
chmod +x "$MACOS_DIR/trading-agent-positions.py" 2>/dev/null || true
chmod +x "$MACOS_DIR/run-argv.py" 2>/dev/null || true
chmod +x "$MACOS_DIR/consume_auto_trade_book.py"
chmod +x "$MACOS_DIR/auto-trade-consumer.sh"
chmod +x "$MACOS_DIR/qt-open-window.sh"
chmod +x "$MACOS_DIR/desk-healthcheck.sh" 2>/dev/null || true
chmod +x "$MACOS_DIR/install-trading-agent-launchd.sh" 2>/dev/null || true

mkdir -p "$GROK_DIR/scripts" "$GROK_DIR/launchd" "$HOME/.trading_agent/logs" \
  "$HOME/.trading_agent/ready_orders" "$HOME/.trading_agent/sync" "$HOME/Library/LaunchAgents"

# Convenience copies
for f in \
  trading-agent-desk.sh \
  trading-agent-positions.sh \
  trading-agent-positions.py \
  run-argv.py \
  consume_auto_trade_book.py \
  auto-trade-consumer.sh \
  qt-open-window.sh \
  desk-healthcheck.sh
do
  if [[ -f "$MACOS_DIR/$f" ]]; then
    cp "$MACOS_DIR/$f" "$GROK_DIR/scripts/"
  fi
done
chmod +x "$GROK_DIR/scripts/"*.sh "$GROK_DIR/scripts/"*.py 2>/dev/null || true

if [[ ! -f "$GROK_DIR/trading-agent.env" ]]; then
  sed "s|__HOME__|$HOME|g; s|\$HOME|$HOME|g" "$MACOS_DIR/trading-agent.env.example" > "$GROK_DIR/trading-agent.env"
  echo "Created $GROK_DIR/trading-agent.env from example"
fi

install_plist() {
  local name="$1"
  local src="$MACOS_DIR/$name.plist"
  local dst="$HOME/Library/LaunchAgents/$name.plist"
  if [[ ! -f "$src" ]]; then
    echo "WARN: missing $src"
    return 1
  fi
  sed "s|__HOME__|$HOME|g" "$src" > "$GROK_DIR/launchd/$name.plist"
  cp "$GROK_DIR/launchd/$name.plist" "$dst"
  launchctl bootout "$DOMAIN/$name" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$dst"
  launchctl enable "$DOMAIN/$name"
  echo "✓ $name loaded"
}

# Desk (full day) if installer present
if [[ -x "$MACOS_DIR/install-trading-agent-launchd.sh" ]]; then
  bash "$MACOS_DIR/install-trading-agent-launchd.sh" || true
fi

install_plist "com.grok.qt-open-window"
install_plist "com.grok.auto-trade-consumer"

echo ""
echo "Mac auto-launch + auto-trade installed:"
echo "  com.grok.trading-agent-desk   → Mon–Fri 01:55 PT (full desk + local book export)"
echo "  com.grok.auto-trade-consumer  → Mon–Fri 06:25 PT (watch books → ready_orders)"
echo "  com.grok.qt-open-window       → Mon–Fri 06:30 PT (QT 9:30–9:50 ET + consume)"
echo ""
echo "Live order placement is OFF by default (fail-closed)."
echo "To enable Schwab MCP live submits on this Mac only:"
echo "  echo 'TRADING_AGENT_AUTO_TRADE_LIVE=1' >> ~/.grok/trading-agent.env"
echo ""
echo "Logs: ~/.trading_agent/logs/"
echo "Ready orders: ~/.trading_agent/ready_orders/"
echo "Manual: python scripts/macos/consume_auto_trade_book.py --anytime"
