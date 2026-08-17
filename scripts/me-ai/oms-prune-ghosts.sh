#!/usr/bin/env bash
# Close OMS ghost lots not present in IBKR portfolio (paper me-ai).
set -euo pipefail
STATE="${TRADING_TEST_STATE_DIR:-$HOME/.trading_test}"
REPO="${TRADING_TEST_REPO:-$HOME/trading_test}"
set -a
[[ -f "$STATE/trading-test.env" ]] && source "$STATE/trading-test.env"
set +a
export TRADING_AGENT_OMS_DIR="${TRADING_AGENT_OMS_DIR:-$STATE/oms}"
export PYTHONPATH="${REPO}${PYTHONPATH:+:$PYTHONPATH}"
cd "$REPO"
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from trading_agent.oms.state import OmsStore
from trading_agent.oms.lifecycle import prune_ghost_lots_ibkr

# Prefer paper state dir
oms_dir = Path(os.environ.get("TRADING_AGENT_OMS_DIR") or Path.home() / ".trading_test" / "oms")
store = OmsStore(root=oms_dir)
print("oms_dir", store.root)
print("open_before", store.open_count(), [l.symbol for l in store.open_lots()])
res = prune_ghost_lots_ibkr(store)
print("prune", json.dumps(res, indent=2))
print("open_after", store.open_count(), [l.symbol for l in store.open_lots()])

# Also clean legacy ~/.trading_agent/oms if present and different
legacy = Path.home() / ".trading_agent" / "oms"
if legacy.resolve() != oms_dir.resolve() and (legacy / "state.json").is_file():
    leg = OmsStore(root=legacy)
    print("legacy open_before", leg.open_count())
    r2 = prune_ghost_lots_ibkr(leg)
    print("legacy prune", r2)
    print("legacy open_after", leg.open_count())
PY
