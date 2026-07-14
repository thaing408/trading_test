"""Immediate notification trigger detection."""

from __future__ import annotations

from typing import List

from trading_agent.intraday.config import IntradayRiskConfig
from trading_agent.intraday.models import Alert, OpenPosition, SessionSnapshot, SessionSynthesis

THESIS_INVALID_KEYWORDS = (
    "downgrade", "miss", "cuts guidance", "lawsuit", "investigation",
    "recall", "fraud", "bankruptcy", "warning",
)


def detect_alerts(
    position: OpenPosition,
    snapshot: SessionSnapshot,
    synthesis: SessionSynthesis,
    risk_config: IntradayRiskConfig,
    better_opportunity_symbol: str | None = None,
) -> List[Alert]:
    alerts: List[Alert] = []
    # Flat / closed lots should never reach here; load_positions filters qty<=0.
    if int(getattr(position, "quantity", 0) or 0) <= 0:
        return alerts

    sym_data = snapshot.symbols.get(position.symbol)
    price = sym_data.price if sym_data else position.current_price or position.entry_price
    # Missing quotes (price<=0) used to force stop-loss on junk/None rows.
    has_price = price is not None and price > 0

    if has_price and position.stop_loss > 0 and price <= position.stop_loss * (
        1 + risk_config.stop_loss_tolerance_pct / 100
    ):
        alerts.append(
            Alert(
                alert_type="stop_loss_triggered",
                symbol=position.symbol,
                message=f"Price ${price:.2f} at/below stop ${position.stop_loss:.2f}",
                recommended_response="Exit position immediately to limit loss",
                severity="critical",
            )
        )

    if has_price and position.profit_target > 0 and price >= position.profit_target * (
        1 - risk_config.profit_target_tolerance_pct / 100
    ):
        alerts.append(
            Alert(
                alert_type="profit_target_reached",
                symbol=position.symbol,
                message=f"Price ${price:.2f} at/above target ${position.profit_target:.2f}",
                recommended_response="Take Partial Profit or Exit per plan",
                severity="high",
            )
        )

    for headline in snapshot.breaking_news:
        if position.symbol in headline.upper() or position.symbol in headline:
            lower = headline.lower()
            if any(k in lower for k in THESIS_INVALID_KEYWORDS):
                alerts.append(
                    Alert(
                        alert_type="thesis_invalidated",
                        symbol=position.symbol,
                        message=f"Breaking news invalidates thesis: {headline}",
                        recommended_response="Exit or Hedge; do not add to position",
                        severity="critical",
                    )
                )

    if synthesis.regime_shift:
        alerts.append(
            Alert(
                alert_type="regime_shift",
                symbol=position.symbol,
                message=(
                    f"Market shifted {snapshot.prior_regime} → {snapshot.market_regime}"
                ),
                recommended_response="Re-evaluate position; consider Hedge or Scale Out",
                severity="high",
            )
        )

    loss_pct = 0.0
    if has_price and position.entry_price:
        loss_pct = (position.entry_price - price) / position.entry_price * 100
    if loss_pct > risk_config.max_loss_per_position_pct:
        alerts.append(
            Alert(
                alert_type="risk_limit_breach",
                symbol=position.symbol,
                message=f"Unrealized loss {loss_pct:.1f}% exceeds limit {risk_config.max_loss_per_position_pct}%",
                recommended_response="Exit to protect capital",
                severity="critical",
            )
        )

    if better_opportunity_symbol and better_opportunity_symbol != position.symbol:
        alerts.append(
            Alert(
                alert_type="better_opportunity",
                symbol=position.symbol,
                message=f"Higher-conviction opportunity in {better_opportunity_symbol}",
                recommended_response="Consider Scale Out or Exit to redeploy capital",
                severity="medium",
            )
        )

    return alerts