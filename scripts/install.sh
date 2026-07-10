#!/usr/bin/env bash
# Effortless macOS/Linux install for new users:
#   collect config -> venv + pip -> write .env -> optional launchd -> fixture dry-run
#
# Interactive:
#   bash scripts/install.sh
#
# Non-interactive:
#   bash scripts/install.sh --non-interactive --delivery-mode dry_run --skip-automation

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

NONINTERACTIVE=0
DELIVERY_MODE=""
DISCORD_TOKEN="${DISCORD_TOKEN:-}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
DISCORD_CHANNEL_ID="${DISCORD_CHANNEL_ID:-}"
UNTIL_PHASE="${TRADING_AGENT_UNTIL_PHASE:-}"
PYTHON_PATH="${TRADING_AGENT_PYTHON:-}"
PORTFOLIO_VALUE="${TRADING_AGENT_PORTFOLIO_VALUE:-100000}"
TIMEZONE="${TRADING_AGENT_TIMEZONE:-America/Los_Angeles}"
ENABLE_AUTOMATION=0
SKIP_AUTOMATION=0
SKIP_FIRST_RUN=0
SKIP_PIP=0
USE_VENV=1

usage() {
  cat <<'EOF'
Usage: bash scripts/install.sh [options]

  --non-interactive          No prompts; use flags/env defaults
  --delivery-mode MODE       dry_run | no_discord | bot | webhook
  --discord-token TOKEN
  --discord-webhook-url URL
  --discord-channel-id ID
  --until-phase PHASE        preopen (default) | full | ...
  --python PATH              Python interpreter
  --portfolio-value N
  --timezone TZ
  --enable-automation        Install launchd agent (macOS)
  --skip-automation
  --skip-first-run
  --skip-pip
  --no-venv                  Install into current Python (no .venv)
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NONINTERACTIVE=1; shift ;;
    --delivery-mode) DELIVERY_MODE="$2"; shift 2 ;;
    --discord-token) DISCORD_TOKEN="$2"; shift 2 ;;
    --discord-webhook-url) DISCORD_WEBHOOK_URL="$2"; shift 2 ;;
    --discord-channel-id) DISCORD_CHANNEL_ID="$2"; shift 2 ;;
    --until-phase) UNTIL_PHASE="$2"; shift 2 ;;
    --python) PYTHON_PATH="$2"; shift 2 ;;
    --portfolio-value) PORTFOLIO_VALUE="$2"; shift 2 ;;
    --timezone) TIMEZONE="$2"; shift 2 ;;
    --enable-automation) ENABLE_AUTOMATION=1; shift ;;
    --skip-automation) SKIP_AUTOMATION=1; shift ;;
    --skip-first-run) SKIP_FIRST_RUN=1; shift ;;
    --skip-pip) SKIP_PIP=1; shift ;;
    --no-venv) USE_VENV=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }
ok() { printf '  OK  %s\n' "$1"; }
warn() { printf '  WARN %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; }

read_default() {
  # $1 prompt $2 default
  local prompt="$1" default="${2:-}" val=""
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " val || true
  else
    read -r -p "$prompt: " val || true
  fi
  if [[ -z "${val// }" ]]; then
    printf '%s\n' "$default"
  else
    printf '%s\n' "$val"
  fi
}

read_yes_no() {
  # $1 prompt $2 default 1/0
  local prompt="$1" def="${2:-1}" raw="" hint
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    printf '%s\n' "$def"
    return
  fi
  if [[ "$def" -eq 1 ]]; then hint="Y/n"; else hint="y/N"; fi
  read -r -p "$prompt ($hint): " raw || true
  if [[ -z "${raw// }" ]]; then
    printf '%s\n' "$def"
    return
  fi
  case "$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')" in
    y|yes|1|true) printf '1\n' ;;
    *) printf '0\n' ;;
  esac
}

resolve_python() {
  local c resolved
  for c in "$PYTHON_PATH" \
           "${TRADING_AGENT_PYTHON:-}" \
           "$REPO_ROOT/.venv/bin/python" \
           "/opt/homebrew/bin/python3.12" \
           "/opt/homebrew/bin/python3.11" \
           "/opt/homebrew/bin/python3" \
           "/usr/local/bin/python3" \
           "python3" \
           "python"; do
    [[ -z "$c" ]] && continue
    resolved=""
    if [[ -x "$c" ]]; then
      resolved="$c"
    elif command -v "$c" >/dev/null 2>&1; then
      resolved="$(command -v "$c")"
    fi
    [[ -z "$resolved" ]] && continue
    # Skip Windows Store python shim (breaks real installs under Git Bash)
    case "$resolved" in
      *WindowsApps*) continue ;;
    esac
    printf '%s\n' "$resolved"
    return 0
  done
  return 1
}

echo "============================================"
echo " Trading Agent — Install Wizard"
echo " Repo: $REPO_ROOT"
echo "============================================"

step "Checking prerequisites"
if command -v git >/dev/null 2>&1; then ok "git found"; else warn "git not on PATH"; fi

BASE_PY="$(resolve_python || true)"
if [[ -z "${BASE_PY:-}" ]]; then
  fail "Python 3.10+ not found. Install Python and re-run."
  exit 1
fi
ok "Base Python: $BASE_PY ($("$BASE_PY" --version 2>&1))"

# --- venv ---
PY="$BASE_PY"
if [[ "$USE_VENV" -eq 1 ]]; then
  step "Creating / reusing .venv"
  if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
    "$BASE_PY" -m venv "$REPO_ROOT/.venv"
  fi
  PY="$REPO_ROOT/.venv/bin/python"
  ok "venv Python: $PY"
fi

# --- collect ---
step "Collecting configuration"
if [[ -z "$DELIVERY_MODE" ]]; then
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    DELIVERY_MODE="${DELIVERY_MODE:-dry_run}"
  else
    echo "Discord delivery: dry_run | no_discord | bot | webhook"
    DELIVERY_MODE="$(read_default "Choose delivery mode" "dry_run")"
  fi
fi
DELIVERY_MODE="$(printf '%s' "$DELIVERY_MODE" | tr '[:upper:]' '[:lower:]' | tr '-' '_')"

case "$DELIVERY_MODE" in
  bot)
    [[ -z "$DISCORD_TOKEN" ]] && DISCORD_TOKEN="$(read_default "DISCORD_TOKEN (bot token)" "")"
    [[ -z "$DISCORD_CHANNEL_ID" ]] && DISCORD_CHANNEL_ID="$(read_default "DISCORD_CHANNEL_ID" "1510184298442002502")"
    ;;
  webhook)
    [[ -z "$DISCORD_WEBHOOK_URL" ]] && DISCORD_WEBHOOK_URL="$(read_default "DISCORD_WEBHOOK_URL" "")"
    [[ -z "$DISCORD_CHANNEL_ID" ]] && DISCORD_CHANNEL_ID="${DISCORD_CHANNEL_ID:-1510184298442002502}"
    ;;
  *)
    [[ -z "$DISCORD_CHANNEL_ID" ]] && DISCORD_CHANNEL_ID="${DISCORD_CHANNEL_ID:-1510184298442002502}"
    ;;
esac

if [[ -z "$UNTIL_PHASE" ]]; then
  if [[ "$NONINTERACTIVE" -eq 1 ]]; then
    UNTIL_PHASE="preopen"
  else
    echo "Phase scope: preopen = prep 1-4 (recommended without brokerage); full = all 7."
    UNTIL_PHASE="$(read_default "Until-phase" "preopen")"
  fi
fi

if [[ "$SKIP_AUTOMATION" -eq 1 ]]; then
  DO_AUTO=0
elif [[ "$ENABLE_AUTOMATION" -eq 1 ]]; then
  DO_AUTO=1
elif [[ "$NONINTERACTIVE" -eq 1 ]]; then
  DO_AUTO=0
else
  DO_AUTO="$(read_yes_no "Install weekday launchd automation (macOS, 01:55 AM PT)?" 0)"
fi

DO_FIRST=1
if [[ "$SKIP_FIRST_RUN" -eq 1 ]]; then
  DO_FIRST=0
elif [[ "$NONINTERACTIVE" -eq 0 ]]; then
  DO_FIRST="$(read_yes_no "Run safe first session (fixture + dry-run, prep)?" 1)"
fi

# --- pip ---
if [[ "$SKIP_PIP" -eq 0 ]]; then
  step "Installing package (pip install -e '.[dev]')"
  "$PY" -m pip install -U pip -q
  "$PY" -m pip install -e ".[dev]" -q
  ok "trading_agent installed"
else
  warn "Skipping pip install"
fi

# --- write env ---
step "Writing environment files"
ENV_PATH="$REPO_ROOT/.env"
EXAMPLE_PATH="$REPO_ROOT/.env.example"
# --flag=value keeps empty strings from eating the next argument
WRITE_ARGS=(
  -m trading_agent.install_wizard write-env
  "--output=$ENV_PATH"
  "--delivery-mode=$DELIVERY_MODE"
  "--discord-token=$DISCORD_TOKEN"
  "--discord-webhook-url=$DISCORD_WEBHOOK_URL"
  "--discord-channel-id=$DISCORD_CHANNEL_ID"
  "--until-phase=$UNTIL_PHASE"
  "--timezone=$TIMEZONE"
  "--python-path=$PY"
  "--portfolio-value=$PORTFOLIO_VALUE"
  --strict
)
if [[ -f "$EXAMPLE_PATH" ]]; then
  WRITE_ARGS+=("--example=$EXAMPLE_PATH")
fi
"$PY" "${WRITE_ARGS[@]}"
ok "Env written: $ENV_PATH"

# Also write ~/.grok/trading-agent.env on macOS for launchd bridge compatibility
if [[ "$(uname -s)" == "Darwin" ]]; then
  mkdir -p "$HOME/.grok" "$HOME/.trading_agent/logs"
  GROK_ENV="$HOME/.grok/trading-agent.env"
  {
    echo "# Synced by scripts/install.sh"
    echo "TRADING_AGENT_PYTHON=$PY"
    echo "TRADING_AGENT_ENV_FILE=$ENV_PATH"
    echo "TRADING_AGENT_TIMEZONE=$TIMEZONE"
    if [[ "$UNTIL_PHASE" != "full" && -n "$UNTIL_PHASE" ]]; then
      echo "TRADING_AGENT_UNTIL_PHASE=$UNTIL_PHASE"
    fi
    echo "DISCORD_CHANNEL_ID=$DISCORD_CHANNEL_ID"
    if [[ -n "$DISCORD_TOKEN" ]]; then
      echo "DISCORD_TOKEN=$DISCORD_TOKEN"
      # Grok bridge often expects DISCORD_BOT_TOKEN
      echo "DISCORD_BOT_TOKEN=$DISCORD_TOKEN"
    fi
    if [[ -n "$DISCORD_WEBHOOK_URL" ]]; then
      echo "DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL"
    fi
  } > "$GROK_ENV"
  ok "Also wrote $GROK_ENV"
fi

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
source <(grep -v '^\s*#' "$ENV_PATH" | grep -v '^\s*$' | sed 's/\r$//' || true)
set +a

# --- automation ---
if [[ "$DO_AUTO" -eq 1 ]]; then
  if [[ "$(uname -s)" == "Darwin" && -x "$REPO_ROOT/scripts/macos/install-trading-agent-launchd.sh" ]]; then
    step "Installing launchd agent"
    bash "$REPO_ROOT/scripts/macos/install-trading-agent-launchd.sh" || warn "launchd install failed"
  else
    warn "Automation only auto-installs on macOS with scripts/macos/install-trading-agent-launchd.sh"
  fi
else
  warn "Automation skipped"
fi

# --- validate env via helper ---
step "Validating configuration"
if "$PY" -m trading_agent.install_wizard validate-env --env-file "$ENV_PATH"; then
  ok "Env validation READY"
  VERIFY_EXIT=0
else
  warn "Env validation reported NOT READY"
  VERIFY_EXIT=1
fi

# --- import check ---
if "$PY" -c "import trading_agent; import yfinance; import requests; import dotenv; print('import ok')"; then
  ok "Package importable"
else
  fail "Package import failed"
  exit 1
fi

# --- first run ---
FIRST_EXIT=0
if [[ "$DO_FIRST" -eq 1 ]]; then
  step "Safe first run (fixture + dry-run + prep phases)"
  DATE_ARG="$(date +%F)"
  mkdir -p "$HOME/.trading_agent/logs"
  FIRST_LOG="$HOME/.trading_agent/logs/first_run_${DATE_ARG}.log"
  set +e
  "$PY" -m trading_agent session \
    --fixture --dry-run \
    --date "$DATE_ARG" \
    --from-phase intelligence \
    --until-phase preopen \
    --output "$FIRST_LOG"
  FIRST_EXIT=$?
  set -e
  if [[ "$FIRST_EXIT" -eq 0 ]]; then
    ok "First run completed (log: $FIRST_LOG)"
  else
    fail "First run failed (exit $FIRST_EXIT). See $FIRST_LOG"
  fi
fi

echo ""
echo "============================================"
if [[ "$VERIFY_EXIT" -eq 0 && "$FIRST_EXIT" -eq 0 ]]; then
  echo " INSTALL COMPLETE — READY"
elif [[ "$VERIFY_EXIT" -eq 0 ]]; then
  echo " INSTALL COMPLETE — env READY (first run had issues)"
else
  echo " INSTALL FINISHED WITH WARNINGS"
fi
echo "============================================"
echo "Next:"
echo "  $PY -m trading_agent session --fixture --dry-run --until-phase preopen"
echo "  bash scripts/macos/install-trading-agent-launchd.sh   # macOS automation"
echo ""

if [[ "$VERIFY_EXIT" -ne 0 ]]; then exit "$VERIFY_EXIT"; fi
if [[ "$FIRST_EXIT" -ne 0 ]]; then exit "$FIRST_EXIT"; fi
exit 0
