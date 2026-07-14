"""Douglas: predefined edge package — direction, stop, target, size/risk — fail closed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional


@dataclass(frozen=True)
class EdgePackage:
    direction: str
    entry_price: float
    stop_loss: float
    profit_target: float
    maximum_risk: float
    maximum_reward: float = 0.0
    size_units: float = 1.0
    risk_reward: float = 0.0

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "profit_target": self.profit_target,
            "maximum_risk": self.maximum_risk,
            "maximum_reward": self.maximum_reward,
            "size_units": self.size_units,
            "risk_reward": self.risk_reward,
        }


@dataclass
class EdgeValidation:
    ok: bool
    package: Optional[EdgePackage]
    missing: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok and self.package:
            return (
                f"Edge OK: {self.package.direction} stop={self.package.stop_loss} "
                f"target={self.package.profit_target} risk={self.package.maximum_risk} "
                f"R:R={self.package.risk_reward:.2f}"
            )
        return "Edge incomplete: " + "; ".join(self.missing or self.reasons)


def _f(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def validate_edge_package(
    *,
    direction: str | None = None,
    entry_price: float | None = None,
    stop_loss: float | None = None,
    profit_target: float | None = None,
    maximum_risk: float | None = None,
    maximum_reward: float | None = None,
    size_units: float | None = None,
    min_risk_reward: float = 0.0,
    payload: Mapping[str, Any] | None = None,
) -> EdgeValidation:
    """Fail closed if direction, stop, target, or risk/size missing or incoherent.

    Size must not be inferred from 'feeling' — only explicit maximum_risk / size_units.
    """
    data = dict(payload or {})
    direction = direction if direction is not None else data.get("direction")
    entry_price = entry_price if entry_price is not None else data.get("entry_price")
    stop_loss = stop_loss if stop_loss is not None else data.get("stop_loss")
    profit_target = profit_target if profit_target is not None else data.get("profit_target")
    maximum_risk = maximum_risk if maximum_risk is not None else data.get("maximum_risk")
    maximum_reward = maximum_reward if maximum_reward is not None else data.get("maximum_reward")
    size_units = size_units if size_units is not None else data.get("size_units", data.get("quantity"))

    missing: List[str] = []
    reasons: List[str] = []

    d = str(direction or "").strip()
    if not d or d.lower() in ("none", "null", "unknown"):
        missing.append("direction")
    elif d.lower() not in ("bullish", "bearish", "neutral", "long", "short"):
        # Allow free-form but require non-empty
        pass

    entry = _f(entry_price)
    stop = _f(stop_loss)
    target = _f(profit_target)
    risk = _f(maximum_risk)
    reward = _f(maximum_reward)
    size = _f(size_units, 1.0)

    if entry <= 0:
        missing.append("entry_price")
    if stop <= 0:
        missing.append("stop_loss")
    if target <= 0:
        missing.append("profit_target")
    if risk <= 0 and size <= 0:
        missing.append("maximum_risk_or_size")
    if risk <= 0 and size > 0:
        # Size alone without risk dollars still incomplete for Douglas package
        missing.append("maximum_risk")

    if entry > 0 and stop > 0 and target > 0:
        if d.lower() in ("bullish", "long"):
            if not (stop < entry < target or (stop < entry and target > entry)):
                if stop >= entry:
                    reasons.append("Bullish stop must be below entry")
                if target <= entry:
                    reasons.append("Bullish target must be above entry")
        elif d.lower() in ("bearish", "short"):
            if stop <= entry:
                reasons.append("Bearish stop must be above entry")
            if target >= entry:
                reasons.append("Bearish target must be below entry")
        if stop == target:
            reasons.append("Stop and target cannot be equal")

    rr = 0.0
    if risk > 0 and reward > 0:
        rr = reward / risk
    elif entry > 0 and stop > 0 and target > 0:
        risk_pts = abs(entry - stop)
        reward_pts = abs(target - entry)
        if risk_pts > 0:
            rr = reward_pts / risk_pts
            if risk <= 0:
                risk = risk_pts  # geometric proxy only if max risk missing was already flagged
    if min_risk_reward > 0 and rr + 1e-9 < min_risk_reward:
        reasons.append(f"R:R {rr:.2f} below minimum {min_risk_reward}")

    # Reject expansion-from-feeling: explicit negative flags in payload
    if data.get("feeling_size_boost") or data.get("discretionary_size_up"):
        reasons.append("Size may not expand from feeling fields — fixed inputs only")
        missing.append("fixed_size_only")

    if missing or reasons:
        return EdgeValidation(ok=False, package=None, missing=missing, reasons=reasons)

    # Ensure risk is positive for package
    if risk <= 0:
        return EdgeValidation(
            ok=False,
            package=None,
            missing=["maximum_risk"],
            reasons=reasons,
        )

    pkg = EdgePackage(
        direction=d,
        entry_price=entry,
        stop_loss=stop,
        profit_target=target,
        maximum_risk=risk,
        maximum_reward=reward if reward > 0 else abs(target - entry),
        size_units=size if size > 0 else 1.0,
        risk_reward=round(rr, 4),
    )
    return EdgeValidation(ok=True, package=pkg, missing=[], reasons=[])


def edge_from_opportunity_fields(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    profit_target: float,
    maximum_risk: float,
    maximum_reward: float = 0.0,
    size_units: float = 1.0,
    min_risk_reward: float = 0.0,
) -> EdgeValidation:
    return validate_edge_package(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        profit_target=profit_target,
        maximum_risk=maximum_risk,
        maximum_reward=maximum_reward,
        size_units=size_units,
        min_risk_reward=min_risk_reward,
    )
