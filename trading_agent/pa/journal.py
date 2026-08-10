"""PA journal field helpers for process / trade review."""

from __future__ import annotations

from typing import Any, Dict, Optional

from trading_agent.pa.fvg import FairValueGap
from trading_agent.pa.structure import StructureState


def pa_journal_fields(
    *,
    structure: Optional[StructureState] = None,
    level_type: str = "",
    reaction: str = "",  # rejection | acceptance | none
    fvg: Optional[FairValueGap] = None,
    setup_tags: Optional[list] = None,
    htf_direction: str = "",
) -> Dict[str, Any]:
    """Standard fields for Step 5 review / process notes."""
    out: Dict[str, Any] = {
        "structure_trend": structure.trend if structure else "",
        "structure_bos": structure.last_bos if structure else "",
        "structure_choch": structure.last_choch if structure else "",
        "level_type": level_type,
        "reaction": reaction,
        "htf_direction": htf_direction,
        "setup_tags": list(setup_tags or []),
        "fvg_side": "",
        "fvg_fill_pct": None,
        "ifvg": False,
    }
    if fvg:
        out["fvg_side"] = fvg.side
        out["fvg_fill_pct"] = round(fvg.fill_pct, 1)
        out["ifvg"] = bool(fvg.inverted)
        out["fvg_size_pct"] = round(fvg.size_pct, 3)
    return out


def format_pa_journal_line(fields: Dict[str, Any]) -> str:
    parts = [
        f"trend={fields.get('structure_trend') or '?'}",
        f"htf={fields.get('htf_direction') or '?'}",
        f"level={fields.get('level_type') or '?'}",
        f"rx={fields.get('reaction') or '?'}",
    ]
    if fields.get("fvg_side"):
        parts.append(
            f"fvg={fields['fvg_side']} fill={fields.get('fvg_fill_pct')} ifvg={fields.get('ifvg')}"
        )
    tags = fields.get("setup_tags") or []
    if tags:
        parts.append("tags=" + "+".join(str(t) for t in tags[:6]))
    return "PA[" + " | ".join(parts) + "]"
