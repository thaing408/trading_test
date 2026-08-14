#!/usr/bin/env bash
# Start LIVE paper auto-trade consumer (after preflight). Discord notice on start.
set -euo pipefail
STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
LOG_DIR="$STATE/logs"
mkdir -p "$LOG_DIR"
DAY=$(TZ=America/Los_Angeles date +%Y-%m-%d)
LOG="$LOG_DIR/paper_consumer_launch_${DAY}.log"

if [[ -f "$STATE/paper-consumer.pid" ]] && kill -0 "$(cat "$STATE/paper-consumer.pid")" 2>/dev/null; then
  echo "consumer already running pid $(cat "$STATE/paper-consumer.pid")" | tee -a "$LOG"
  exit 0
fi

export PAPER_PREFLIGHT_MODE=full
export PAPER_PREFLIGHT_NOTIFY=0   # avoid double OK; we post LIVE notice below
bash "$HOME/bin/paper-preflight.sh" || {
  echo "preflight failed" | tee -a "$LOG"
  bash "$HOME/bin/paper-discord-notify.sh" "🚨 **me-ai paper consumer NOT started** · preflight failed (see Gateway :4002 / VNC)" || true
  exit 1
}

export TRADING_AGENT_AUTO_TRADE_LIVE=1
export TRADING_AGENT_AUTO_TRADE_ANYTIME=1
nohup bash "$HOME/trading_test/scripts/macos/run-paper-consumer.sh" >>"$LOG" 2>&1 &
echo $! > "$STATE/paper-consumer.pid"
PID=$(cat "$STATE/paper-consumer.pid")
echo "consumer LIVE anytime pid $PID" | tee -a "$LOG"

bash "$HOME/bin/paper-discord-notify.sh" "🔴 **me-ai paper LIVE consumer STARTED** · $(TZ=America/Los_Angeles date '+%H:%M %Z')
• pid \`${PID}\` · poll 60s · options-only paper **DUQ181571**
• book: \`~/.trading_test/sync/auto_trade_book.json\`
• stop ~13:20 PT (\`paper-consumer-stop\`)" || true
