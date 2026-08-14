#!/usr/bin/env bash
# Post a short message to the paper Discord channel (#ibkr-tradings).
# Usage: paper-discord-notify.sh "message text"
set -euo pipefail

MSG="${1:-}"
if [[ -z "$MSG" ]]; then
  echo "usage: $0 <message>" >&2
  exit 2
fi

STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
set -a
[[ -f "$STATE/discord-paper.env" ]] && source "$STATE/discord-paper.env"
[[ -f "$STATE/trading-test.env" ]] && source "$STATE/trading-test.env"
[[ -f "$HOME/.grok/discord.env" ]] && source "$HOME/.grok/discord.env"
[[ -f "$HOME/researcher/.env" ]] && source "$HOME/researcher/.env"
set +a

TOKEN="${DISCORD_TOKEN:-${DISCORD_BOT_TOKEN:-}}"
CH="${DISCORD_PAPER_CHANNEL_ID:-${DISCORD_IBKR_CHANNEL_ID:-1536602374502613013}}"

if [[ -z "$TOKEN" ]]; then
  echo "discord-notify: no DISCORD_TOKEN — skip" >&2
  exit 0
fi

# Escape for JSON string
json_msg=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$MSG")

code=$(curl -sS -o /tmp/paper-discord-notify.out -w "%{http_code}" \
  -H "Authorization: Bot $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"content\": ${json_msg}}" \
  "https://discord.com/api/v10/channels/${CH}/messages" || echo "000")

if [[ "$code" != "200" && "$code" != "201" ]]; then
  echo "discord-notify: HTTP $code $(head -c 200 /tmp/paper-discord-notify.out 2>/dev/null)" >&2
  exit 1
fi
echo "discord-notify: ok HTTP $code"
