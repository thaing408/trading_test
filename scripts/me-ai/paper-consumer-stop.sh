#!/usr/bin/env bash
# Stop LIVE paper consumer and any orphaned watch process (frees IBKR client ids).
set -u
STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"

if [[ -f "$STATE/paper-consumer.pid" ]]; then
  pid=$(cat "$STATE/paper-consumer.pid" 2>/dev/null || true)
  if [[ -n "${pid:-}" ]]; then
    # wrapper shell
    kill "$pid" 2>/dev/null || true
    # process group if started with job control
    kill -- -"$pid" 2>/dev/null || true
    # direct children
    for c in $(ps -o pid= --ppid "$pid" 2>/dev/null); do
      kill "$c" 2>/dev/null || true
    done
  fi
  rm -f "$STATE/paper-consumer.pid"
fi

# Reap orphans that outlived the shell wrapper (common cause of Error 326 client id in use).
# Match only the python consumer script path — not this stop script.
while read -r p cmd; do
  case "$cmd" in
    *consume_auto_trade_book.py*)
      echo "killing orphan consumer pid=$p"
      kill "$p" 2>/dev/null || true
      sleep 0.3
      kill -9 "$p" 2>/dev/null || true
      ;;
  esac
done < <(ps -eo pid=,args= 2>/dev/null || true)

sleep 1
left=$(ps -eo args= 2>/dev/null | grep -c 'consume_auto_trade_book.py' || true)
echo "consumer stop $(date -u -Is) remaining=$left"
if [[ "${left:-0}" != "0" ]]; then
  ps -eo pid,args= | grep consume_auto_trade_book | grep -v grep || true
fi
