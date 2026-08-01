"""Named edge / hypothesis registry for desk playbooks (G2.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    name: str
    setup_ids: tuple[str, ...]
    edge_type: str  # momentum | mean_reversion | premium | breakout | gap | regime
    horizon: str
    expected_regimes: tuple[str, ...]
    requires_defined_risk: bool = True
    notes: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["setup_ids"] = list(self.setup_ids)
        d["expected_regimes"] = list(self.expected_regimes)
        return d


HYPOTHESIS_REGISTRY: Dict[str, Hypothesis] = {
    "options_credit_bull_put": Hypothesis(
        hypothesis_id="options_credit_bull_put",
        name="Bull put credit spread",
        setup_ids=("options_credit_bull_put",),
        edge_type="premium",
        horizon="days_to_weeks",
        expected_regimes=("bull", "chop"),
        notes="Defined-risk short put vertical; IV/POP gates in options_methods",
    ),
    "options_credit_bear_call": Hypothesis(
        hypothesis_id="options_credit_bear_call",
        name="Bear call credit spread",
        setup_ids=("options_credit_bear_call",),
        edge_type="premium",
        horizon="days_to_weeks",
        expected_regimes=("bear", "chop"),
    ),
    "options_credit_iron_condor": Hypothesis(
        hypothesis_id="options_credit_iron_condor",
        name="Iron condor",
        setup_ids=("options_credit_iron_condor",),
        edge_type="premium",
        horizon="days_to_weeks",
        expected_regimes=("chop",),
    ),
    "options_debit_call_spread": Hypothesis(
        hypothesis_id="options_debit_call_spread",
        name="Debit call spread",
        setup_ids=("options_debit_call_spread",),
        edge_type="momentum",
        horizon="days",
        expected_regimes=("bull",),
    ),
    "options_debit_put_spread": Hypothesis(
        hypothesis_id="options_debit_put_spread",
        name="Debit put spread",
        setup_ids=("options_debit_put_spread",),
        edge_type="momentum",
        horizon="days",
        expected_regimes=("bear",),
    ),
    "gap_continuation": Hypothesis(
        hypothesis_id="gap_continuation",
        name="Gap continuation",
        setup_ids=("gap_continuation", "gap_watch"),
        edge_type="gap",
        horizon="intraday",
        expected_regimes=("bull", "bear"),
        notes="Gap book → auto_trade when risk package complete",
    ),
    "lfd_breakout": Hypothesis(
        hypothesis_id="lfd_breakout",
        name="Last Friday day breakout",
        setup_ids=("lfd_breakout",),
        edge_type="breakout",
        horizon="swing",
        expected_regimes=("bull",),
    ),
    "qt_open_window": Hypothesis(
        hypothesis_id="qt_open_window",
        name="QT PO3/CISD open window",
        setup_ids=("qt_open_window", "qt_po3"),
        edge_type="breakout",
        horizon="intraday",
        expected_regimes=("bull", "bear", "chop"),
        notes="9:30–9:50 ET mechanical model",
    ),
    "odte_scalp": Hypothesis(
        hypothesis_id="odte_scalp",
        name="0DTE / short-dated option scalp",
        setup_ids=("odte", "auto_trade_qqq"),
        edge_type="momentum",
        horizon="intraday",
        expected_regimes=("bull", "bear"),
        requires_defined_risk=False,
        notes="Separate MCP scalp path; high turnover",
    ),
    "strength_relative": Hypothesis(
        hypothesis_id="strength_relative",
        name="Relative strength screener",
        setup_ids=("strength", "rs_leader"),
        edge_type="momentum",
        horizon="swing",
        expected_regimes=("bull",),
    ),
}


def list_hypotheses() -> List[Dict[str, Any]]:
    return [h.to_dict() for h in HYPOTHESIS_REGISTRY.values()]


def get_hypothesis(hypothesis_id: str) -> Optional[Hypothesis]:
    return HYPOTHESIS_REGISTRY.get(hypothesis_id)


def hypothesis_for_setup(setup_id: str) -> Optional[Hypothesis]:
    sid = (setup_id or "").strip().lower()
    for h in HYPOTHESIS_REGISTRY.values():
        if sid in {s.lower() for s in h.setup_ids}:
            return h
        if sid == h.hypothesis_id.lower():
            return h
    return None
