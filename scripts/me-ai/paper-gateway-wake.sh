#!/usr/bin/env bash
# Early Gateway wake (before full preflight). Cron ~01:20 PT Mon–Fri.
set -euo pipefail
export PAPER_PREFLIGHT_MODE=wake
export PAPER_PREFLIGHT_NOTIFY=1
export PAPER_PREFLIGHT_RETRIES="${PAPER_PREFLIGHT_RETRIES:-4}"
export PAPER_PREFLIGHT_SLEEP="${PAPER_PREFLIGHT_SLEEP:-12}"
exec bash "${HOME}/bin/paper-preflight.sh"
