#!/usr/bin/env bash
# Pull researcher handoff books from production host onto this Mac.
# Host is resolved under DHCP: hostname / cache file / env — not a fixed IP only.
#
# Only runs inside the trading window (default: weekdays 5:35–12:55 America/Los_Angeles).
# Override: TRADING_AGENT_PULL_ANYTIME=1
set -euo pipefail

USER="${RESEARCHER_SSH_USER:-ubuntu}"
REMOTE_SYNC="${RESEARCHER_REMOTE_SYNC:-.trading_agent/sync}"
LOCAL_SYNC="${TRADING_AGENT_SYNC_DIR:-$HOME/.trading_agent/sync}"
LOG_DIR="${HOME}/.trading_agent/logs"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$LOCAL_SYNC" "$LOCAL_SYNC/archive" "$LOG_DIR" "$HOME/.grok"
LOG="$LOG_DIR/pull-researcher-sync.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

if [ -f "$HOME/.grok/trading-agent.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$HOME/.grok/trading-agent.env"
  set +a
  USER="${RESEARCHER_SSH_USER:-$USER}"
fi

# --- Trading window only (no overnight / weekend pulls) ---
if [ "${TRADING_AGENT_PULL_ANYTIME:-0}" != "1" ]; then
  OPEN_REASON=$(
    PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}" \
      "${TRADING_AGENT_PYTHON:-python3}" - <<'PY' 2>/dev/null || true
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from trading_agent.session.schedule import is_market_open_day  # type: ignore
except Exception:
    is_market_open_day = None
try:
    # Prefer scalp bot window (5:35–12:55 PT weekdays, holidays excluded)
    from schwab_mcp.qqq_strategy import is_trading_window  # type: ignore
    open_, reason = is_trading_window()
    print("1" if open_ else "0")
    print(reason)
except Exception:
    # Fallback without schwab_mcp: Mon–Fri 05:35–12:55 PT
    PT = ZoneInfo("America/Los_Angeles")
    now = datetime.now(PT)
    if now.weekday() >= 5:
        print("0")
        print("weekend — skip pull")
    else:
        t = now.time()
        from datetime import time as dtime
        if dtime(5, 35) <= t <= dtime(12, 55):
            print("1")
            print("trading window open (fallback PT 5:35–12:55)")
        else:
            print("0")
            print(f"outside trading window ({now.strftime('%H:%M %Z')})")
PY
  )
  OPEN=$(printf '%s\n' "$OPEN_REASON" | sed -n '1p')
  REASON=$(printf '%s\n' "$OPEN_REASON" | sed -n '2p')
  if [ "$OPEN" != "1" ]; then
    log "skip pull — ${REASON:-outside trading window}"
    exit 0
  fi
fi

# Resolve host (Python helper handles DHCP: me-ai.local, cache, env, fallback)
HOST=""
HOW=""
if command -v python3 >/dev/null 2>&1; then
  RESOLVE=$(
    cd "$REPO" 2>/dev/null || cd "$HOME/trading_agent" 2>/dev/null || true
    PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY' 2>/dev/null || true
import os, sys
sys.path.insert(0, os.environ.get("REPO", os.path.expanduser("~/trading_agent")))
try:
    from trading_agent.export.researcher_host import resolve_researcher_host
    h, how = resolve_researcher_host()
    print(h)
    print(how)
except Exception as e:
    print("")
    print(str(e))
PY
  )
  # pass REPO into env for the heredoc path
fi

# Simpler resolve call
resolve_out=$(
  PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" REPO="$REPO" python3 -c "
from trading_agent.export.researcher_host import resolve_researcher_host_safe
h, how = resolve_researcher_host_safe()
print(h or '')
print(how)
" 2>/dev/null || echo $'\nresolve failed'
)
HOST=$(printf '%s\n' "$resolve_out" | sed -n '1p')
HOW=$(printf '%s\n' "$resolve_out" | sed -n '2p')

if [ -z "$HOST" ]; then
  log "ERROR: cannot resolve researcher host ($HOW)"
  log "Set RESEARCHER_HOST, RESEARCHER_HOSTNAME=me-ai.local, or ~/.grok/researcher_host"
  exit 1
fi
log "host=$HOST ($HOW) user=$USER"

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)
SCP=(scp -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)

if ! "${SSH[@]}" "${USER}@${HOST}" "echo ok" >/dev/null 2>&1; then
  log "ERROR: SSH ${USER}@${HOST} failed (key auth?)"
  exit 1
fi

# Cache successful host (also done in Python; reinforce shell path)
echo "host=${HOST}" >"$HOME/.grok/researcher_host"

FILES=(
  gap_screener_book.json
  watchlist_playlist.json
)

pulled=0
for f in "${FILES[@]}"; do
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

if "${SSH[@]}" "${USER}@${HOST}" "ls \$HOME/.trading_agent/watchlist/*.json >/dev/null 2>&1"; then
  mkdir -p "$HOME/.trading_agent/watchlist"
  rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new" \
    "${USER}@${HOST}:.trading_agent/watchlist/" \
    "$HOME/.trading_agent/watchlist/" 2>>"$LOG" || true
  log "rsync watchlist/ done"
fi

log "done pulled=$pulled host=$HOST"
exit 0
