"""Promotion gate checklist before shipping RiskConfig / LIVE defaults (G3.7)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PromotionChecklist:
    """Evidence required to promote a config/strategy to shipped or LIVE."""

    name: str
    offline_trades: int = 0
    offline_expectancy: float = 0.0
    offline_win_rate: float = 0.0
    offline_max_dd: float = 0.0
    offline_profit_factor: float = 0.0
    gates_on_ablation_done: bool = False
    multi_regime_done: bool = False
    costs_modeled: bool = False
    paper_days: int = 0
    paper_trades: int = 0
    paper_expectancy: float = 0.0
    human_reviewed: bool = False
    notes: str = ""
    # thresholds (overridable)
    min_offline_trades: int = 20
    min_offline_expectancy: float = 0.0
    min_offline_win_rate: float = 0.45
    max_offline_dd: float = 25_000.0
    min_paper_days: int = 10
    min_paper_trades: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PromotionResult:
    approved: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checklist: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_promotion(check: PromotionChecklist) -> PromotionResult:
    failures: List[str] = []
    warnings: List[str] = []

    if check.offline_trades < check.min_offline_trades:
        failures.append(
            f"offline_trades {check.offline_trades} < min {check.min_offline_trades}"
        )
    if check.offline_expectancy < check.min_offline_expectancy:
        failures.append(
            f"offline_expectancy {check.offline_expectancy:.2f} < min {check.min_offline_expectancy:.2f}"
        )
    if check.offline_win_rate < check.min_offline_win_rate:
        failures.append(
            f"offline_win_rate {check.offline_win_rate:.2%} < min {check.min_offline_win_rate:.2%}"
        )
    if check.offline_max_dd > check.max_offline_dd:
        failures.append(
            f"offline_max_dd {check.offline_max_dd:.0f} > max {check.max_offline_dd:.0f}"
        )
    if not check.gates_on_ablation_done:
        failures.append("gates_on_ablation_done required")
    if not check.multi_regime_done:
        failures.append("multi_regime_done required")
    if not check.costs_modeled:
        warnings.append("costs_modeled false — promotion weak without slippage/commissions")
    if check.paper_days < check.min_paper_days:
        failures.append(f"paper_days {check.paper_days} < min {check.min_paper_days}")
    if check.paper_trades < check.min_paper_trades:
        failures.append(f"paper_trades {check.paper_trades} < min {check.min_paper_trades}")
    if check.paper_expectancy < 0:
        warnings.append("paper_expectancy negative")
    if not check.human_reviewed:
        failures.append("human_reviewed required")

    return PromotionResult(
        approved=len(failures) == 0,
        failures=failures,
        warnings=warnings,
        checklist=check.to_dict(),
    )


def format_promotion_report(result: PromotionResult) -> str:
    lines = [
        f"# Promotion: {result.checklist.get('name', '')}",
        f"**Approved:** {result.approved}",
        "",
        "## Failures",
    ]
    if result.failures:
        lines.extend(f"- {f}" for f in result.failures)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Warnings")
    if result.warnings:
        lines.extend(f"- {w}" for w in result.warnings)
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Checklist snapshot")
    for k, v in sorted((result.checklist or {}).items()):
        lines.append(f"- `{k}`: {v}")
    return "\n".join(lines) + "\n"
