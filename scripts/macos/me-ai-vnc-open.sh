#!/usr/bin/env bash
# One-click: ensure me-ai VNC SSH tunnel is up, then open TigerVNC to 127.0.0.1:5901.
# You only enter IB Gateway paper credentials in the viewer.
#
# Usage:
#   bash scripts/macos/me-ai-vnc-open.sh
#   # or after install:
#   me-ai-vnc          # if linked to ~/bin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUNNEL="$SCRIPT_DIR/me-ai-vnc-tunnel.sh"
LOCAL_PORT="${ME_AI_VNC_LOCAL_PORT:-5901}"
VIEWER="${ME_AI_VNCVIEWER:-/Applications/TigerVNC.app/Contents/MacOS/vncviewer}"

if [[ ! -x "$TUNNEL" ]]; then
  chmod +x "$TUNNEL" 2>/dev/null || true
fi

echo "Ensuring SSH tunnel 127.0.0.1:${LOCAL_PORT} → me-ai:5900 …"
if ! bash "$TUNNEL" --once; then
  echo "Tunnel failed. Check: ssh ubuntu@me-ai.local  (passwordless key) and me-ai x11vnc."
  bash "$TUNNEL" --status || true
  exit 1
fi

bash "$TUNNEL" --status || true

TARGET="127.0.0.1::${LOCAL_PORT}"
echo "Opening TigerVNC → ${TARGET}"
echo "Log in to IB Gateway **Paper** (API 4002). Leave Gateway running after login."

if [[ -x "$VIEWER" ]]; then
  # TigerVNC: host::port form
  exec "$VIEWER" "$TARGET"
fi

if [[ -d /Applications/TigerVNC.app ]]; then
  open -a TigerVNC --args "$TARGET"
  exit 0
fi

echo "TigerVNC not found at $VIEWER"
echo "Install TigerVNC or set ME_AI_VNCVIEWER=/path/to/vncviewer"
echo "Manual: open TigerVNC → VNC server: 127.0.0.1::${LOCAL_PORT}"
exit 1
