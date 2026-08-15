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

# If Gateway is not running, start it on DISPLAY=:99 (login UI for VNC)
HOST_LINE=$(bash "$TUNNEL" --status 2>/dev/null | head -1 || true)
echo "$HOST_LINE"
if echo "$(bash "$TUNNEL" --status 2>/dev/null)" | grep -q 'java=DOWN'; then
  echo "IB Gateway not running on me-ai — starting on DISPLAY=:99 …"
  # resolve host the same way as tunnel script
  ME_HOST="${ME_AI_HOST:-}"
  if [[ -z "$ME_HOST" && -f "$HOME/.grok/researcher_host" ]]; then
    ME_HOST=$(head -1 "$HOME/.grok/researcher_host" | tr -d '[:space:]')
    [[ "$ME_HOST" == host=* ]] && ME_HOST="${ME_HOST#host=}"
  fi
  ME_HOST="${ME_HOST:-10.0.0.52}"
  ssh -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new \
    "ubuntu@${ME_HOST}" 'bash ~/bin/start-ibgateway-display99.sh' || true
  sleep 8
fi

bash "$TUNNEL" --status || true
echo ""
echo "Note: 'SetDesktopSize failed' from TigerVNC is usually harmless with x11vnc."
echo "If the window is black, wait ~10s for Gateway, or File→Refresh / reconnect."
echo ""

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
