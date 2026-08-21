"""Books compete for ticker — score & rank mode.

Default production path stays ``book_gates_mode=hard`` (AND gates).
Set ``TRADING_AGENT_BOOK_GATES_MODE=score`` to award points per book mechanism
(deduped), hard-DQ only safety vetoes, and rank by ``compete_score``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# Mechanisms that remain hard vetoes even in score mode (safety / plan integrity).
SAFETY_MECHANISMS = frozenset(
    {
        "schwager_plan_entry_exit",  # no entry/stop/target plan
        "livermore_tape_and_cut",  # average-down / cut discipline when flagged hard
        "wizards_risk_cap",
        "kiev_commitment",  # daily loss / freelanced
        "system2_and_observer",  # tilt / revenge
        "bulkowski_pattern_bias",  # opposing high-reliability PA
        "shannon_mtf_gate",
        "grimes_systematic_edge",  # oversize / no edge when hard-fail
    }
)

PASS_POINTS = 1.0
INACTIVE_POINTS = 0.0
FAIL_POINTS = 0.0


def book_gates_mode() -> str:
    """Return ``hard`` (default) or ``score``."""
    raw = os.getenv("TRADING_AGENT_BOOK_GATES_MODE", "hard").strip().lower()
    if raw in ("score", "compete", "points", "rank"):
        return "score"
    return "hard"


def _gate_points(ok: bool, reasons: Sequence[str]) -> float:
    if not ok:
        return FAIL_POINTS
    blob = " ".join(str(r) for r in reasons).lower()
    if "inactive" in blob or "soft" in blob or "skip" in blob:
        return INACTIVE_POINTS
    return PASS_POINTS


def iter_gate_results(bundle: Any) -> List[Any]:
    """Normalize SMB / TA / classic result objects to a list of gate rows."""
    if bundle is None:
        return []
    results = getattr(bundle, "results", None)
    if isinstance(results, list):
        return list(results)
    return []


def is_safety_block(results: Iterable[Any]) -> bool:
    """True if any failed gate is in the safety mechanism set."""
    for r in results:
        if getattr(r, "ok", True):
            continue
        mech = str(getattr(r, "mechanism", "") or "")
        if mech in SAFETY_MECHANISMS:
            return True
        # Also treat explicit kill/cash/halt wording as safety
        reasons = " ".join(str(x) for x in (getattr(r, "reasons", None) or [])).lower()
        if any(
            k in reasons
            for k in ("kill switch", "daily loss", "average down", "revenge", "no stop")
        ):
            return True
    return False


def score_gate_results(results: Iterable[Any]) -> Tuple[float, Dict[str, float]]:
    """Sum points with per-mechanism dedupe (max wins)."""
    by_mech: Dict[str, float] = {}
    for r in results:
        mech = str(getattr(r, "mechanism", "") or "unknown")
        pts = _gate_points(
            bool(getattr(r, "ok", False)),
            list(getattr(r, "reasons", None) or []),
        )
        by_mech[mech] = max(by_mech.get(mech, 0.0), pts)
    return round(sum(by_mech.values()), 2), by_mech


def compute_compete_score(
    *,
    setup_core: float,
    book_points: float,
    method_boost: float = 0.0,
    priority_boost: float = 0.0,
) -> float:
    """Unified compete score for ranking / merge."""
    try:
        core = float(setup_core or 0)
    except (TypeError, ValueError):
        core = 0.0
    return round(core + float(book_points or 0) + float(method_boost or 0) + float(priority_boost or 0), 2)


def should_hard_reject_books(*, mode: str, bundle_ok: bool, results: Sequence[Any]) -> bool:
    """Decide whether book gate failure removes the candidate."""
    if bundle_ok:
        return False
    if mode != "score":
        return True
    return is_safety_block(results)


def annotate_entry_compete(row: Mapping[str, Any] | Dict[str, Any]) -> Dict[str, Any]:
    """Ensure dict ENTER rows have a compete_score for merge ranking."""
    out = dict(row)
    if out.get("compete_score") is not None:
        try:
            float(out["compete_score"])
            return out
        except (TypeError, ValueError):
            pass
    core = (
        out.get("combined_quality_score")
        or out.get("quality_score")
        or out.get("grade_score")
        or out.get("technical_score")
        or 0
    )
    boost = float(out.get("priority_boost") or 0)
    tags = out.get("method_tags") or []
    method_boost = min(10.0, 2.0 * len(tags)) if isinstance(tags, list) else 0.0
    book_pts = float(out.get("book_points") or 0)
    out["compete_score"] = compute_compete_score(
        setup_core=float(core or 0),
        book_points=book_pts,
        method_boost=method_boost,
        priority_boost=boost,
    )
    return out


def prefer_entry_by_compete(
    a: Dict[str, Any], b: Dict[str, Any]
) -> Dict[str, Any]:
    """Return the higher-compete_score entry; merge method_tags from both."""
    aa = annotate_entry_compete(a)
    bb = annotate_entry_compete(b)
    winner, loser = (aa, bb) if float(aa["compete_score"]) >= float(bb["compete_score"]) else (bb, aa)
    tags = list(winner.get("method_tags") or [])
    for t in loser.get("method_tags") or []:
        if t not in tags:
            tags.append(t)
    winner["method_tags"] = tags
    winner["compete_merged"] = True
    winner["compete_loser_score"] = float(loser.get("compete_score") or 0)
    return winner
