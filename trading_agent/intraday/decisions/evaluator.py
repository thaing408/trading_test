"""Per-position action evaluator."""

from __future__ import annotations

from trading_agent.intraday.config import IntradayRiskConfig
from trading_agent.intraday.decisions.alerts import detect_alerts
from trading_agent.intraday.decisions.guards import (
    check_averaging_down,
    compute_trailing_stop,
    days_to_expiration,
)
from trading_agent.intraday.models import (
    OpenPosition,
    PositionRecommendation,
    SessionSnapshot,
    SessionSynthesis,
    SymbolSessionData,
)


def critical_alerts_pending(alerts: list) -> bool:
    return any(a.severity == "critical" for a in alerts)


def _update_scores(
    position: OpenPosition,
    sym_data: SymbolSessionData | None,
    synthesis: SessionSynthesis,
    alerts_count: int,
) -> tuple[float, float]:
    prob = position.original_probability
    conf = position.original_confidence

    if sym_data:
        if sym_data.trend == "uptrend" and sym_data.price > sym_data.vwap:
            prob += 0.05
            conf += 5
        elif sym_data.trend == "downtrend" and sym_data.price < sym_data.vwap:
            prob -= 0.08
            conf -= 10
        if sym_data.momentum == "decelerating":
            prob -= 0.03
            conf -= 5

    if synthesis.regime_shift:
        conf -= 12
        prob -= 0.06
    if synthesis.risk_environment == "elevated":
        conf -= 5

    conf -= alerts_count * 8
    prob -= alerts_count * 0.05

    return round(max(0.05, min(0.95, prob)), 2), round(max(0.0, min(100.0, conf)), 1)


def evaluate_position(
    position: OpenPosition,
    snapshot: SessionSnapshot,
    synthesis: SessionSynthesis,
    risk_config: IntradayRiskConfig,
    better_opportunity_symbol: str | None = None,
) -> PositionRecommendation:
    sym_data = snapshot.symbols.get(position.symbol)
    price = sym_data.price if sym_data else position.current_price or position.entry_price
    alerts = detect_alerts(position, snapshot, synthesis, risk_config, better_opportunity_symbol)
    prob, conf = _update_scores(position, sym_data, synthesis, len(alerts))

    what_changed_parts = []
    if sym_data:
        what_changed_parts.append(
            f"Price ${price:.2f} ({sym_data.change_pct:+.1f}%), VWAP ${sym_data.vwap:.2f}, "
            f"trend {sym_data.trend}, momentum {sym_data.momentum}"
        )
    if synthesis.regime_shift:
        what_changed_parts.append(synthesis.regime_description)
    for a in alerts:
        what_changed_parts.append(a.message)

    what_changed = "; ".join(what_changed_parts) if what_changed_parts else "No material session changes"

    if position.pending_entry and sym_data:
        if (
            sym_data.trend == "uptrend"
            and sym_data.price >= sym_data.vwap
            and not critical_alerts_pending(alerts)
            and conf >= position.original_confidence
        ):
            return PositionRecommendation(
                symbol=position.symbol,
                action="Enter",
                what_changed=what_changed,
                why_recommended="Planned entry conditions met: price above VWAP with confirming uptrend",
                risk_if_no_action="Miss planned entry at favorable intraday level",
                updated_probability=prob,
                updated_confidence=conf,
                alerts=alerts,
            )
        return PositionRecommendation(
            symbol=position.symbol,
            action="Take No Action",
            what_changed=what_changed,
            why_recommended="Pending entry — conditions not yet confirmed for execution",
            risk_if_no_action="Low — wait for entry trigger alignment",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    critical = [a for a in alerts if a.severity == "critical"]
    if any(a.alert_type == "stop_loss_triggered" for a in alerts):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Exit",
            what_changed=what_changed,
            why_recommended="Stop-loss triggered; capital preservation requires immediate exit",
            risk_if_no_action="Further downside with no predefined risk boundary",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if any(a.alert_type == "thesis_invalidated" for a in alerts):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Exit",
            what_changed=what_changed,
            why_recommended="Original trade thesis invalidated by breaking news",
            risk_if_no_action="Position may deteriorate as catalyst reverses original edge",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if any(a.alert_type == "risk_limit_breach" for a in critical):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Exit",
            what_changed=what_changed,
            why_recommended="Risk exceeds acceptable per-position loss limit",
            risk_if_no_action="Portfolio risk cap breach and larger drawdown",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if any(a.alert_type == "profit_target_reached" for a in alerts):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Take Partial Profit",
            what_changed=what_changed,
            why_recommended="Profit target reached; lock gains per plan discipline",
            risk_if_no_action="Give-back risk if momentum reverses at resistance",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    trailing = compute_trailing_stop(position, price, risk_config.trailing_stop_activation_pct)
    if trailing and trailing > position.stop_loss:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Move Stop Loss",
            what_changed=what_changed,
            why_recommended=f"Position in profit; raise stop to ${trailing:.2f} trailing level",
            risk_if_no_action="Unprotected gains may erode on reversal",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if any(a.alert_type == "regime_shift" for a in alerts):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Hedge",
            what_changed=what_changed,
            why_recommended="Market regime shift threatens directional exposure",
            risk_if_no_action="Directional loss if regime move continues against position",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if any(a.alert_type == "better_opportunity" for a in alerts):
        return PositionRecommendation(
            symbol=position.symbol,
            action="Scale Out",
            what_changed=what_changed,
            why_recommended="Better risk/reward available elsewhere; redeploy capital",
            risk_if_no_action="Opportunity cost and suboptimal capital allocation",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if sym_data and sym_data.trend == "uptrend" and sym_data.momentum == "accelerating":
        if price < position.entry_price and not check_averaging_down(position, price):
            return PositionRecommendation(
                symbol=position.symbol,
                action="Hold",
                what_changed=what_changed,
                why_recommended="Losing position; averaging down not permitted by strategy rules",
                risk_if_no_action="Adding size would increase loss exposure against discipline rules",
                updated_probability=prob,
                updated_confidence=conf,
                alerts=alerts,
            )
        if price > position.entry_price and conf > position.original_confidence:
            return PositionRecommendation(
                symbol=position.symbol,
                action="Scale In",
                what_changed=what_changed,
                why_recommended="Trend accelerating with improved confidence above entry",
                risk_if_no_action="Missed participation in confirmed momentum move",
                updated_probability=prob,
                updated_confidence=conf,
                alerts=alerts,
            )

    if sym_data and sym_data.trend == "downtrend" and price > position.entry_price:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Scale Out",
            what_changed=what_changed,
            why_recommended="Trend weakening while still in profit; reduce exposure",
            risk_if_no_action="Profit erosion if downtrend accelerates",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if sym_data and abs(sym_data.iv_change_pct) > 5:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Adjust",
            what_changed=what_changed,
            why_recommended=f"IV moved {sym_data.iv_change_pct:+.1f}%; adjust strikes or size",
            risk_if_no_action="Greeks drift may distort intended risk/reward profile",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    dte = days_to_expiration(position.expiration)
    if dte <= risk_config.roll_days_threshold and dte >= 0 and sym_data:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Roll",
            what_changed=what_changed + f"; {dte} day(s) to expiration ({position.expiration})",
            why_recommended=f"Options expire in {dte} days; roll to next cycle to preserve thesis",
            risk_if_no_action="Theta decay and gamma risk accelerate into expiration",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if sym_data:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Hold",
            what_changed=what_changed,
            why_recommended="Conditions stable; position within plan parameters",
            risk_if_no_action="Minimal — monitor for trigger events",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    if not sym_data and not alerts:
        return PositionRecommendation(
            symbol=position.symbol,
            action="Take No Action",
            what_changed=what_changed,
            why_recommended="Insufficient session data change; maintain current position state",
            risk_if_no_action="Low — continue monitoring next cycle",
            updated_probability=prob,
            updated_confidence=conf,
            alerts=alerts,
        )

    return PositionRecommendation(
        symbol=position.symbol,
        action="Hold",
        what_changed=what_changed,
        why_recommended="No trigger events; maintain position per original plan",
        risk_if_no_action="Standard market risk; alerts will fire on trigger breach",
        updated_probability=prob,
        updated_confidence=conf,
        alerts=alerts,
    )