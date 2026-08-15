#!/usr/bin/env bash
# Keep an SSH local-forward alive: Mac 127.0.0.1:5901 → me-ai 127.0.0.1:5900 (x11vnc).
# Used so TigerVNC can connect to 127.0.0.1:5901 without a manual ssh -L each morning.
#
# Usage:
#   bash me-ai-vnc-tunnel.sh              # foreground (launchd / terminal)
#   bash me-ai-vnc-tunnel.sh --once       # start tunnel in background if down, then exit 0
#   bash me-ai-vnc-tunnel.sh --status     # print tunnel / remote VNC status
#   bash me-ai-vnc-tunnel.sh --stop       # kill local tunnel
#
# Env:
#   ME_AI_SSH_USER   default ubuntu
#   ME_AI_HOST       override host (else ~/.grok/researcher_host, me-ai.local, 10.0.0.52)
#   ME_AI_VNC_LOCAL_PORT   default 5901
#   ME_AI_VNC_REMOTE_PORT  default 5900
set -euo pipefail

USER_NAME="${ME_AI_SSH_USER:-ubuntu}"
LOCAL_PORT="${ME_AI_VNC_LOCAL_PORT:-5901}"
REMOTE_PORT="${ME_AI_VNC_REMOTE_PORT:-5900}"
PID_FILE="${ME_AI_VNC_TUNNEL_PID:-$HOME/.trading_test/me-ai-vnc-tunnel.pid}"
LOG_DIR="${ME_AI_VNC_LOG_DIR:-$HOME/.trading_test/logs}"
mkdir -p "$(dirname "$PID_FILE")" "$LOG_DIR"
LOG="$LOG_DIR/me-ai-vnc-tunnel.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

resolve_host() {
  if [[ -n "${ME_AI_HOST:-}" ]]; then
    echo "$ME_AI_HOST"
    return
  fi
  if [[ -f "$HOME/.grok/researcher_host" ]]; then
    local h
    # file may be bare IP/hostname or "host=10.0.0.52"
    h=$(head -1 "$HOME/.grok/researcher_host" | tr -d '[:space:]' || true)
    if [[ "$h" == host=* ]]; then
      h="${h#host=}"
    fi
    if [[ -n "$h" ]]; then
      echo "$h"
      return
    fi
  fi
  # Prefer mDNS, then last-known LAN IP
  if ping -c 1 -t 1 me-ai.local >/dev/null 2>&1; then
    echo "me-ai.local"
    return
  fi
  echo "${ME_AI_HOST_FALLBACK:-10.0.0.52}"
}

tunnel_listening() {
  # macOS: lsof or nc
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  nc -z 127.0.0.1 "$LOCAL_PORT" >/dev/null 2>&1
}

stop_tunnel() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.5
      kill -9 "$pid" 2>/dev/null || true
      log "stopped tunnel pid=$pid"
    fi
    rm -f "$PID_FILE"
  fi
  # orphan ssh -L on our port
  if command -v lsof >/dev/null 2>&1; then
    local p
    for p in $(lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN -t 2>/dev/null || true); do
      kill "$p" 2>/dev/null || true
    done
  fi
}

ensure_remote_vnc() {
  local host="$1"
  # Best-effort: start Xvfb/x11vnc/Gateway stack if 5900 not up (needs passwordless SSH)
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    "${USER_NAME}@${host}" \
    'bash -s' <<'REMOTE' >/dev/null 2>&1 || true
set +e
if ! ss -lntp 2>/dev/null | grep -q ":5900"; then
  if [ -x "$HOME/bin/start-x11vnc-99.sh" ]; then
    nohup bash "$HOME/bin/start-x11vnc-99.sh" >/tmp/x11vnc-start.log 2>&1 &
  fi
  if [ -x "$HOME/bin/start-ibgateway-display99.sh" ]; then
    bash "$HOME/bin/start-ibgateway-display99.sh" >/tmp/gw-start.log 2>&1 || true
  fi
  # minimal fallback
  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    nohup Xvfb :99 -screen 0 1400x900x24 -ac -nolisten tcp >/tmp/Xvfb-99.log 2>&1 &
    sleep 1
  fi
  if ! pgrep -x x11vnc >/dev/null 2>&1; then
    nohup x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw -noxdamage \
      >/tmp/x11vnc-99.log 2>&1 &
  fi
fi
REMOTE
}

start_tunnel_bg() {
  local host="$1"
  if tunnel_listening; then
    log "tunnel already listening on 127.0.0.1:${LOCAL_PORT}"
    return 0
  fi
  ensure_remote_vnc "$host"
  # -N no remote command; -f background after auth; ExitOnForwardFailure so we don't fake success
  ssh -f -N \
    -o BatchMode=yes \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
    "${USER_NAME}@${host}" \
    >>"$LOG" 2>&1 || {
      log "ERROR: failed to open tunnel to ${USER_NAME}@${host}"
      return 1
    }
  sleep 0.8
  # record ssh pid listening on port
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 >"$PID_FILE" || true
  fi
  if tunnel_listening; then
    log "tunnel OK 127.0.0.1:${LOCAL_PORT} → ${host}:127.0.0.1:${REMOTE_PORT} pid=$(cat "$PID_FILE" 2>/dev/null || echo '?')"
    return 0
  fi
  log "ERROR: tunnel not listening after ssh -f"
  return 1
}

run_foreground_loop() {
  # For launchd KeepAlive: block on ssh -N; reconnect forever.
  log "foreground tunnel loop user=$USER_NAME local=$LOCAL_PORT"
  while true; do
    local host
    host=$(resolve_host)
    log "connecting tunnel → ${USER_NAME}@${host} (remote :${REMOTE_PORT})"
    stop_tunnel || true
    ensure_remote_vnc "$host"
    # blocking ssh (no -f) — exit means drop; sleep then retry
    ssh -N \
      -o BatchMode=yes \
      -o ConnectTimeout=15 \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -o StrictHostKeyChecking=accept-new \
      -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
      "${USER_NAME}@${host}" \
      >>"$LOG" 2>&1 || log "ssh exited ($?)"
    sleep 5
  done
}

cmd="${1:-}"
case "$cmd" in
  --stop)
    stop_tunnel
    echo "stopped"
    ;;
  --status)
    host=$(resolve_host)
    echo "host=$host user=$USER_NAME"
    if tunnel_listening; then
      echo "local_tunnel=UP 127.0.0.1:${LOCAL_PORT}"
    else
      echo "local_tunnel=DOWN"
    fi
    ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
      "${USER_NAME}@${host}" \
      'echo -n remote_5900=; ss -lntp 2>/dev/null | grep -q ":5900" && echo UP || echo DOWN; echo -n java=; pgrep -x java >/dev/null && echo UP || echo DOWN; echo -n port_4002=; ss -lntp 2>/dev/null | grep -q ":4002" && echo UP || echo DOWN' \
      2>/dev/null || echo "remote=SSH_FAIL"
    ;;
  --once)
    host=$(resolve_host)
    start_tunnel_bg "$host"
    ;;
  ""|--loop|foreground)
    run_foreground_loop
    ;;
  *)
    echo "usage: $0 [--once|--status|--stop|--loop]"
    exit 2
    ;;
esac
