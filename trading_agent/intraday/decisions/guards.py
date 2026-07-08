"""Disciplined management guards."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_agent.intraday.models import OpenPosition


def days_to_expiration(expiration: str, reference: datetime | None = None) -> int:
    ref = reference or datetime.now(timezone.utc)
    exp = datetime.strptime(expiration, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (exp.date() - ref.date()).days


def check_averaging_down(position: OpenPosition, current_price: float) -> bool:
    """Return True if averaging down is permitted for this position."""
    if position.allows_averaging_down:
        return True
    if current_price < position.entry_price:
        return False
    return True


def compute_trailing_stop(
    position: OpenPosition,
    current_price: float,
    activation_pct: float,
) -> float | None:
    """Compute trailing stop when position is in profit beyond activation threshold."""
    gain_pct = (current_price - position.entry_price) / position.entry_price * 100
    if gain_pct < activation_pct:
        return None
    trail = current_price * (1 - position.trailing_stop_pct / 100)
    return round(max(trail, position.stop_loss), 2)