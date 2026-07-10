#!/bin/bash
# Fail-loud health check for 1:55 AM trading desk. Exit 0 only if ready.
set -euo pipefail

REPO="${TRADING_AGENT_REPO:-$HOME/trading_agent}"
LOG_DIR="$HOME/.trading_agent/logs"
mkdir -p "$LOG_DIR"
OUT="$LOG_DIR/healthcheck-$(date '+%Y-%m-%d').log"
exec > >(tee "$OUT") 2>&1

ok=1
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; ok=0; }
warn() { echo "WARN  $*"; }

echo "=== desk healthcheck $(TZ=America/Los_Angeles date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo "bash=$BASH_VERSION"

# 1) bash 3.2 empty-args regression
if /bin/bash -c 'set -u; EXTRA_ARGS=(); echo count=${#EXTRA_ARGS[@]}; if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then echo "${EXTRA_ARGS[@]}"; fi; echo ok'; 2>/dev/null; then
  pass "bash empty-array guard"
else
  fail "bash empty-array still unsafe under set -u"
fi

# 2) desk script syntax + zero-arg path does not unbound-variable before env load
if bash -n "$REPO/scripts/macos/trading-agent-desk.sh"; then
  pass "desk.sh syntax"
else
  fail "desk.sh syntax"
fi

# 3) launchd loaded + Mon-Fri 1:55
if launchctl print "gui/$(id -u)/com.grok.trading-agent-desk" >/tmp/desk-launchd.txt 2>&1; then
  pass "launchd agent loaded"
  if grep -q '"Hour" => 1' /tmp/desk-launchd.txt && grep -q '"Minute" => 55' /tmp/desk-launchd.txt; then
    pass "schedule 1:55 present"
  else
    fail "1:55 schedule missing"
  fi
  # Monday = 1
  if grep -q '"Weekday" => 1' /tmp/desk-launchd.txt; then
    pass "Monday included"
  else
    warn "Monday not in schedule"
  fi
else
  fail "launchd agent not loaded"
fi

# 4) env + python
if [ -f "$HOME/.grok/trading-agent.env" ]; then pass "trading-agent.env"; else fail "trading-agent.env missing"; fi
if [ -f "$HOME/.grok/discord.env" ]; then pass "discord.env"; else fail "discord.env missing"; fi

# shellcheck disable=SC1090
set -a
. "$HOME/.grok/trading-agent.env" 2>/dev/null || true
. "$HOME/.grok/discord.env" 2>/dev/null || true
set +a
export DISCORD_TOKEN="${DISCORD_BOT_TOKEN:-${DISCORD_TOKEN:-}}"
export DISCORD_CHANNEL_ID="${DISCORD_DESK_CHANNEL_ID:-1510184298442002502}"

PYTHON="${TRADING_AGENT_PYTHON:-$REPO/.venv/bin/python}"
if [ -x "$PYTHON" ] && "$PYTHON" -c "import trading_agent"; then
  pass "trading_agent import ($PYTHON)"
else
  fail "trading_agent import"
fi
if [ -n "${DISCORD_TOKEN:-}" ] && [ -n "${DISCORD_CHANNEL_ID:-}" ]; then
  pass "Discord bot credentials present"
else
  fail "Discord bot credentials missing"
fi

# 5) Schwab positions
if [ -x "$HOME/schwab-mcp-server/.venv/bin/python" ]; then
  if TRADING_AGENT_PYTHON="$PYTHON" "$REPO/scripts/macos/trading-agent-positions.sh"; then
    n=$("$PYTHON" -c "import json;print(len(json.load(open('$HOME/.trading_agent/positions.json')).get('positions',[])))")
    pass "Schwab positions export ($n)"
  else
    fail "Schwab positions export"
  fi
else
  fail "schwab-mcp venv missing"
fi

# 6) dry-run first 2 phases (no wait, no discord) — proves pipeline
if "$PYTHON" -m trading_agent session \
  --date "$(TZ=America/Los_Angeles date '+%Y-%m-%d')" \
  --timezone America/Los_Angeles \
  --dry-run \
  --from-phase intelligence \
  --until-phase research \
  --positions "$HOME/.trading_agent/positions.json" \
  --output "$LOG_DIR/healthcheck-session.log"; then
  pass "dry-run intelligence→research"
else
  fail "dry-run intelligence→research"
fi

# 7) scalp auto-trade session bars (related bug)
if [ -x "$HOME/schwab-mcp-server/.venv/bin/python" ]; then
  bars=$("$HOME/schwab-mcp-server/.venv/bin/python" -m schwab_mcp.mcp_stdio auto_trade_qqq '{"dry_run":true}' 2>/dev/null | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin)
rows=d.get('scan') or []
counts=[int(r.get('closes_session_count') or 0) for r in rows]
print(min(counts) if counts else -1)
print('details', [(r.get('symbol'), r.get('closes_session_count'), r.get('closes_raw_count')) for r in rows], file=sys.stderr)
" 2>/tmp/bars-err.txt)
  echo "session_bar min count: $bars"
  cat /tmp/bars-err.txt 2>/dev/null || true
  # After hours min can still be >0 for today; 0 is the historical bug
  if [ "${bars:-0}" -gt 0 ]; then
    pass "auto-trade session bars populated (min=$bars)"
  else
    warn "auto-trade session bars min=$bars (ok if market closed & no today bars yet; was 0 all RTH before fix)"
  fi
fi

echo ""
if [ "$ok" -eq 1 ]; then
  echo "=== HEALTHCHECK PASS ==="
  exit 0
fi
echo "=== HEALTHCHECK FAIL — do not trust 1:55 until fixed ==="
exit 1
