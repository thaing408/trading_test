"""Save CIO approval inputs after the research phase."""

from __future__ import annotations

from pathlib import Path

from trading_agent.models import DailyTradingPlan


def save_cio_approval_snapshot(session_dir: Path, plan: DailyTradingPlan, fixture_mode: bool) -> Path:
    from trading_agent.cio.loader import build_cio_approval_inputs
    from dataclasses import asdict
    import json

    candidates, context = build_cio_approval_inputs(plan, fixture_mode)
    session_dir.mkdir(parents=True, exist_ok=True)
    out = session_dir / "cio_inputs.json"
    payload = {
        "candidates": [asdict(c) for c in candidates],
        "context": asdict(context),
    }
    with out.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return out