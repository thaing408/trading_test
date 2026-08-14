#!/usr/bin/env bash
# Install me-ai paper auto scripts into ~/bin and update crontab.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO/scripts/me-ai"
BIN="$HOME/bin"
mkdir -p "$BIN" "$HOME/.trading_test/logs"

for f in \
  paper-discord-notify.sh \
  paper-preflight.sh \
  paper-gateway-wake.sh \
  paper-desk-start.sh \
  paper-consumer-start.sh
do
  install -m 0755 "$SRC/$f" "$BIN/$f"
  echo "installed $BIN/$f"
done

# Keep existing eod/stop if already present; refresh if we ship them later
if [[ -f "$SRC/paper-eod.sh" ]]; then
  install -m 0755 "$SRC/paper-eod.sh" "$BIN/paper-eod.sh"
fi
if [[ -f "$SRC/paper-consumer-stop.sh" ]]; then
  install -m 0755 "$SRC/paper-consumer-stop.sh" "$BIN/paper-consumer-stop.sh"
fi

CRON_TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'paper-preflight\|paper-desk-start\|paper-consumer-start\|paper-eod\|paper-consumer-stop\|paper-gateway-wake' >"$CRON_TMP" || true

cat >>"$CRON_TMP" <<'EOF'
# me-ai paper auto — host is UTC; PT = America/Los_Angeles (PDT UTC-7 / PST UTC-8)
# PT 01:20 wake | 01:50 preflight+Discord | 01:55 desk | 06:20 LIVE consumer | 13:15 EOD | 13:20 stop
# UTC (PDT): 08:20 / 08:50 / 08:55 / 13:20 / 20:15 / 20:20
20 8 * * 1-5 /home/ubuntu/bin/paper-gateway-wake.sh
50 8 * * 1-5 /home/ubuntu/bin/paper-preflight.sh
55 8 * * 1-5 /home/ubuntu/bin/paper-desk-start.sh
20 13 * * 1-5 /home/ubuntu/bin/paper-consumer-start.sh
15 20 * * 1-5 /home/ubuntu/bin/paper-eod.sh
20 20 * * 1-5 /home/ubuntu/bin/paper-consumer-stop.sh
EOF

crontab "$CRON_TMP"
rm -f "$CRON_TMP"
echo "crontab installed:"
crontab -l | grep -E 'paper-'
echo "done"
