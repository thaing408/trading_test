"""Read firm sleeve day artifacts (sessions/{date}/firm/)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_firm_view(*, trading_date: str, state: Path | None = None) -> Dict[str, Any]:
    root = Path(state) if state else Path.home() / ".trading_agent"
    firm_dir = root / "sessions" / trading_date / "firm"
    out: Dict[str, Any] = {
        "enabled_artifacts": firm_dir.is_dir(),
        "path": str(firm_dir),
        "symbols": [],
        "cards": [],
        "index": None,
        "eval": None,
    }
    if not firm_dir.is_dir():
        return out

    idx = firm_dir / "index.json"
    if idx.is_file():
        try:
            out["index"] = json.loads(idx.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    ev = firm_dir / "eval_report.json"
    if ev.is_file():
        try:
            out["eval"] = json.loads(ev.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    cards: List[Dict[str, Any]] = []
    for d in sorted(p for p in firm_dir.iterdir() if p.is_dir()):
        card_p = d / "firm_card.json"
        trader_p = d / "trader_proposal.json"
        risk_p = d / "risk_adjustment.json"
        mgr_p = d / "manager_decision.json"
        debate_p = d / "debate_verdict.json"
        row: Dict[str, Any] = {"symbol": d.name}
        for label, path in (
            ("card", card_p),
            ("trader", trader_p),
            ("risk", risk_p),
            ("manager", mgr_p),
            ("debate", debate_p),
        ):
            if path.is_file():
                try:
                    row[label] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    row[label] = {"error": "parse"}
        cards.append(row)
        out["symbols"].append(d.name)
    out["cards"] = cards
    return out
