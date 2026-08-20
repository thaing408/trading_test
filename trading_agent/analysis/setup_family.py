"""EP vs breakout setup family (Qullamaggie / Muninn dial split).

Episodic pivots (gap + catalyst / gap-continuation) vs clean breakouts.
Default: **tag only**. ``TRADING_AGENT_EP_SLOW=1`` applies soft 0.5× size on EP
(prefer slower confirmation — do not change OR window live).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence

FAMILY_EP = "ep"
FAMILY_BREAKOUT = "breakout"

_CATALYST_RE = re.compile(
    r"\b(earnings?|eps|guidance|upgrade|downgrade|contract|acquisition|"
    r"buyout|fda|pdufa|offering|secondary|ipo|merger|m&a|catalyst|"
    r"gap[\s_-]?up|gap[\s_-]?down|unfilled\s+gap)\b",
    re.I,
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def ep_slow_enabled() -> bool:
    return _env_bool("TRADING_AGENT_EP_SLOW", False)


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts)


def classify_setup_family(
    *,
    method_tags: Optional[Sequence[str]] = None,
    notes: str = "",
    thesis: str = "",
    catalyst: str = "",
    catalyst_type: str = "",
    gap_note: str = "",
    gap_continuation: bool = False,
) -> str:
    """Return ``ep`` or ``breakout``.

    EP if:
      - gap_continuation / gap_continuation_4d tag, or
      - named catalyst (earnings / contract / upgrade / …), or
      - gap language in notes/thesis/gap_note with catalyst-ish wording
    """
    tags = [str(t).lower() for t in (method_tags or []) if t]
    if gap_continuation or any("gap_continuation" in t for t in tags):
        return FAMILY_EP
    if any(t in ("ep", "episodic_pivot", "gap_ep") for t in tags):
        return FAMILY_EP

    cat = _blob(catalyst, catalyst_type, gap_note)
    if _CATALYST_RE.search(cat):
        return FAMILY_EP

    text = _blob(notes, thesis, gap_note, " ".join(tags))
    if "gap_continuation" in text.lower():
        return FAMILY_EP
    # Gap + catalyst-ish together
    if re.search(r"\bgap\b", text, re.I) and _CATALYST_RE.search(text):
        return FAMILY_EP
    return FAMILY_BREAKOUT


def family_note(family: str) -> str:
    if family == FAMILY_EP:
        return "setup_family=ep (gap/catalyst — prefer slower confirmation)"
    return "setup_family=breakout"


def apply_setup_family_to_entry(
    row: Dict[str, Any],
    *,
    family: Optional[str] = None,
    apply_ep_slow: Optional[bool] = None,
) -> Dict[str, Any]:
    """Stamp setup_family; optional EP size cut when EP_SLOW flag on."""
    if family is None:
        family = classify_setup_family(
            method_tags=row.get("method_tags") or [],
            notes=str(row.get("notes") or ""),
            thesis=str(row.get("thesis") or ""),
            catalyst=str(row.get("primary_catalyst") or row.get("catalyst") or ""),
            catalyst_type=str(row.get("catalyst_type") or ""),
            gap_note=str(row.get("gap_screener") or row.get("gap_note") or ""),
            gap_continuation=bool(row.get("gap_continuation")),
        )
    row["setup_family"] = family
    row["setup_family_note"] = family_note(family)

    do_slow = ep_slow_enabled() if apply_ep_slow is None else bool(apply_ep_slow)
    if do_slow and family == FAMILY_EP:
        try:
            risk = float(row.get("max_risk_dollars") or 0)
            if risk > 0:
                row["max_risk_dollars"] = round(risk * 0.5, 2)
        except (TypeError, ValueError):
            pass
        try:
            qty = int(row.get("quantity") or 1)
            if qty > 1:
                row["quantity"] = max(1, int(qty * 0.5))
        except (TypeError, ValueError):
            pass
        notes = str(row.get("notes") or "")
        row["notes"] = (notes + "; ep_slow_size×0.5").strip("; ")[:240]
        row["ep_slow_applied"] = True
    return row


def discord_family_line(row: Dict[str, Any]) -> str:
    fam = str(row.get("setup_family") or "").strip()
    if not fam:
        return ""
    return family_note(fam)
