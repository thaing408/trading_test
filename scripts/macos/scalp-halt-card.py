#!/usr/bin/env python3
"""Mac helper: record Pulse closes + print/post the named halt card.

Install (after git pull of trading_agent)::

    python3 -m trading_agent research scalp-halt --card

From ~/.grok/scripts/scalp-market-pulse.py on each closed scalp::

    from trading_agent.scalp.pulse_halt import (
        format_session_halt_card,
        maybe_post_session_halt,
        record_pulse_close,
        sleeve_halted,
    )
    led = record_pulse_close(symbol, side=side, pnl=pnl, setup=setup, reason=reason)
    if sleeve_halted(led):
        maybe_post_session_halt(led)   # names NVDA PUT / AMD CALL — not blank trips=2
"""

from __future__ import annotations

import sys

from trading_agent.scalp.pulse_halt import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
