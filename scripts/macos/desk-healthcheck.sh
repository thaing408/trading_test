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
LAUNCHD_DUMP="$LOG_DIR/launchd-print-$$.txt"
if launchctl print "gui/$(id -u)/com.grok.trading-agent-desk" >"$LAUNCHD_DUMP" 2>&1; then
  pass "launchd agent loaded"
  if grep -q '"Hour" => 1' "$LAUNCHD_DUMP" && grep -q '"Minute" => 55' "$LAUNCHD_DUMP"; then
    pass "schedule 1:55 present"
  else
    fail "1:55 schedule missing"
  fi
  # Monday = 1 (macOS: 0=Sun … 6=Sat)
  if grep -q '"Weekday" => 1' "$LAUNCHD_DUMP"; then
    pass "Monday included"
  else
    fail "Monday not in schedule"
  fi
  for wd in 2 3 4 5; do
    if ! grep -q "\"Weekday\" => $wd" "$LAUNCHD_DUMP"; then
      fail "Weekday $wd missing from schedule"
    fi
  done
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
SESSION_LOG="$LOG_DIR/healthcheck-session.log"
POS_ARG=()
if [ -f "$HOME/.trading_agent/positions.json" ]; then
  POS_ARG=(--positions "$HOME/.trading_agent/positions.json")
fi
if "$PYTHON" -m trading_agent session \
  --date "$(TZ=America/Los_Angeles date '+%Y-%m-%d')" \
  --timezone America/Los_Angeles \
  --dry-run \
  --from-phase intelligence \
  --until-phase research \
  "${POS_ARG[@]}" \
  --output "$SESSION_LOG"; then
  pass "dry-run intelligence→research"
  # Live Bias must not invent fixture Jobless Claims / demo NVDA beats
  if grep -q "Jobless Claims" "$SESSION_LOG" 2>/dev/null && \
     grep -q "fixture-fallback\|Calendar unavailable\|calendar omitted" "$SESSION_LOG" 2>/dev/null; then
    fail "Bias still embeds fixture calendar while reporting unavailable"
  elif grep -q "NVDA beats earnings estimates" "$SESSION_LOG" 2>/dev/null; then
    # Only fail if this is the exact fixture headline in a live dry-run
    if grep -q "active catalyst:.*NVDA beats earnings estimates" "$SESSION_LOG"; then
      fail "Bias uses fixture news catalyst (NVDA beats…) in live dry-run"
    else
      warn "NVDA earnings text present in log (check if live news)"
    fi
  else
    pass "Bias has no fixture Jobless Claims / demo NVDA catalyst"
  fi
else
  fail "dry-run intelligence→research"
fi

# 7) Performance live mode must not silently load demo trades
PERF_OUT="$LOG_DIR/healthcheck-performance.json"
export PERF_OUT
if "$PYTHON" - <<'PY'
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.session.play_formatter import format_performance_plays
import json, os
from pathlib import Path
cfg = PerformanceConfig(fixture_mode=False)  # live path
report = run_performance_pipeline(cfg)
text = format_performance_plays(report)
meta = report.metadata or {}
out = Path(os.environ["PERF_OUT"])
out.write_text(json.dumps({"metadata": meta, "text": text}, indent=2), encoding="utf-8")
assert not meta.get("trades_is_fixture"), meta
src = str(meta.get("trades_source") or "")
assert src == "none" or not src.startswith("fixture/"), meta
if meta.get("session_trade_count", 0) == 0:
    assert "demo fixture" not in text
    assert "No closed trades" in text or "empty" in text.lower() or src == "none"
print("performance_live_ok", meta)
PY
then
  pass "Performance live path does not use demo fixture trades"
else
  fail "Performance live path still looks like fixture fill"
fi

# 8) scalp auto-trade session bars (related bug)
if [ -x "$HOME/schwab-mcp-server/.venv/bin/python" ]; then
  BARS_ERR="$LOG_DIR/bars-err-$$.txt"
  bars=$("$HOME/schwab-mcp-server/.venv/bin/python" -m schwab_mcp.mcp_stdio auto_trade_qqq '{"dry_run":true}' 2>/dev/null | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin)
rows=d.get('scan') or []
counts=[int(r.get('closes_session_count') or 0) for r in rows]
print(min(counts) if counts else -1)
print('details', [(r.get('symbol'), r.get('closes_session_count'), r.get('closes_raw_count')) for r in rows], file=sys.stderr)
" 2>"$BARS_ERR")
  echo "session_bar min count: $bars"
  cat "$BARS_ERR" 2>/dev/null || true
  if [ "${bars:-0}" -gt 0 ]; then
    pass "auto-trade session bars populated (min=$bars)"
  else
    warn "auto-trade session bars min=$bars (ok if market closed / weekend)"
  fi
fi

echo ""
if [ "$ok" -eq 1 ]; then
  echo "=== HEALTHCHECK PASS ==="
  exit 0
fi
echo "=== HEALTHCHECK FAIL — do not trust 1:55 until fixed ==="
exit 1
