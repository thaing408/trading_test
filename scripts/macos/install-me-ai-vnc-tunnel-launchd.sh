#!/usr/bin/env bash
# Install always-on SSH VNC tunnel to me-ai + convenience openers for TigerVNC.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
MACOS="$REPO/scripts/macos"
HOME_DIR="${HOME}"
LAUNCH_AGENTS="$HOME_DIR/Library/LaunchAgents"
LABEL="com.grok.me-ai-vnc-tunnel"
PLIST_SRC="$MACOS/com.grok.me-ai-vnc-tunnel.plist"
PLIST_DST="$LAUNCH_AGENTS/${LABEL}.plist"
BIN="$HOME_DIR/bin"
DOMAIN="gui/$(id -u)"

mkdir -p "$LAUNCH_AGENTS" "$BIN" "$HOME_DIR/.trading_test/logs"
chmod +x "$MACOS/me-ai-vnc-tunnel.sh" "$MACOS/me-ai-vnc-open.sh"

# Materialize plist with absolute paths
sed -e "s|__REPO__|${REPO}|g" -e "s|__HOME__|${HOME_DIR}|g" \
  "$PLIST_SRC" >"$PLIST_DST"

# Symlinks for quick CLI
ln -sfn "$MACOS/me-ai-vnc-tunnel.sh" "$BIN/me-ai-vnc-tunnel"
ln -sfn "$MACOS/me-ai-vnc-open.sh" "$BIN/me-ai-vnc"
ln -sfn "$MACOS/me-ai-vnc-open.sh" "$BIN/me-ai-tigervnc"

# Reload launchd
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || launchctl start "$LABEL" 2>/dev/null || true

sleep 1
echo "Installed $LABEL"
echo "  plist: $PLIST_DST"
echo "  tunnel: 127.0.0.1:5901 → me-ai:5900 (kept alive)"
echo "  CLI:    me-ai-vnc          # open TigerVNC (ensure tunnel + viewer)"
echo "          me-ai-vnc-tunnel --status"
echo "          me-ai-vnc-tunnel --stop"
echo ""
echo "Prereq: passwordless SSH  ubuntu@me-ai.local  (or ME_AI_HOST / ~/.grok/researcher_host)"
echo "Then: me-ai-vnc   → only log into IB Gateway paper in the window."
bash "$MACOS/me-ai-vnc-tunnel.sh" --status || true
