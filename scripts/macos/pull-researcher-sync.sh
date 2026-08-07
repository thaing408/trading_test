#!/usr/bin/env bash
# Pull researcher handoff books from production host (10.0.0.52) onto this Mac.
# trading_agent only reads local ~/.trading_agent/sync/ — never the remote path.
set -euo pipefail

HOST="${RESEARCHER_HOST:-10.0.0.52}"
USER="${RESEARCHER_SSH_USER:-ubuntu}"
REMOTE_SYNC="${RESEARCHER_REMOTE_SYNC:-.trading_agent/sync}"
LOCAL_SYNC="${TRADING_AGENT_SYNC_DIR:-$HOME/.trading_agent/sync}"
LOG_DIR="${HOME}/.trading_agent/logs"
mkdir -p "$LOCAL_SYNC" "$LOCAL_SYNC/archive" "$LOG_DIR"
LOG="$LOG_DIR/pull-researcher-sync.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Optional env overlay
if [ -f "$HOME/.grok/trading-agent.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$HOME/.grok/trading-agent.env"
  set +a
  HOST="${RESEARCHER_HOST:-$HOST}"
  USER="${RESEARCHER_SSH_USER:-$USER}"
fi

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)
SCP=(scp -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)

if ! "${SSH[@]}" "${USER}@${HOST}" "echo ok" >/dev/null 2>&1; then
  log "ERROR: cannot SSH ${USER}@${HOST} (BatchMode). Fix key auth."
  exit 1
fi

# Files researcher writes for desk / CIO soft inputs
FILES=(
  gap_screener_book.json
  watchlist_playlist.json
)

pulled=0
for f in "${FILES[@]}"; do
  # Resolve absolute path on remote (HOME-relative REMOTE_SYNC)
  rpath=$("${SSH[@]}" "${USER}@${HOST}" "test -f \"\$HOME/${REMOTE_SYNC}/${f}\" && echo \"\$HOME/${REMOTE_SYNC}/${f}\"" 2>/dev/null || true)
  if [ -z "$rpath" ]; then
    log "skip $f (not on remote)"
    continue
  fi
  if "${SCP[@]}" "${USER}@${HOST}:${rpath}" "$LOCAL_SYNC/${f}.tmp" 2>>"$LOG"; then
    if [ -f "$LOCAL_SYNC/$f" ]; then
      cp "$LOCAL_SYNC/$f" "$LOCAL_SYNC/archive/${f%.json}_$(date '+%Y%m%d_%H%M%S').json" 2>/dev/null || true
    fi
    mv "$LOCAL_SYNC/${f}.tmp" "$LOCAL_SYNC/$f"
    log "pulled $f → $LOCAL_SYNC/$f"
    pulled=$((pulled + 1))
  else
    log "WARN: scp failed for $f"
    rm -f "$LOCAL_SYNC/${f}.tmp"
  fi
done

# Also pull dated watchlist if present (best-effort)
if "${SSH[@]}" "${USER}@${HOST}" "ls \$HOME/.trading_agent/watchlist/*.json >/dev/null 2>&1"; then
  mkdir -p "$HOME/.trading_agent/watchlist"
  rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=8" \
    "${USER}@${HOST}:.trading_agent/watchlist/" \
    "$HOME/.trading_agent/watchlist/" 2>>"$LOG" || true
  log "rsync watchlist/ done"
fi

log "done pulled=$pulled host=$HOST"
exit 0
