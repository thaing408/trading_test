"""Immediate notification trigger detection."""

from __future__ import annotations

from typing import List

from trading_agent.analysis.lfd_breakout import BreakoutType, classify_breakout_path
from trading_agent.intraday.config import IntradayRiskConfig
from trading_agent.intraday.models import Alert, OpenPosition, SessionSnapshot, SessionSynthesis

THESIS_INVALID_KEYWORDS = (
    "downgrade", "miss", "cuts guidance", "lawsuit", "investigation",
    "recall", "fraud", "bankruptcy", "warning",
)


def _structure_levels(position: OpenPosition) -> dict:
    """Read optional LFD / structure fields from position (plan handoff)."""
    return {
        "lfd_level": float(getattr(position, "lfd_level", 0) or 0),
        "breakout_level": float(getattr(position, "breakout_level", 0) or 0),
        "negation_level": float(getattr(position, "negation_level", 0) or 0),
        "measured_target": float(getattr(position, "measured_target", 0) or 0),
        "direction": str(getattr(position, "direction", "") or ""),
    }


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

    instr = (getattr(position, "instrument_type", None) or "equity").lower()
    is_option = instr == "option" or "option" in (position.strategy or "").lower()
    # Options: always use premium mark on the lot (never underlying equity print).
    sym_data = None if is_option else snapshot.symbols.get(position.symbol)
    if not is_option and sym_data is None and getattr(position, "underlying", None):
        sym_data = snapshot.symbols.get(position.underlying)
    if is_option:
        price = position.current_price or position.entry_price
    else:
        price = sym_data.price if sym_data else position.current_price or position.entry_price
    # Missing quotes (price<=0) used to force stop-loss on junk/None rows.
    has_price = price is not None and price > 0
    unit = "prem" if is_option else "px"
    mark_src = getattr(position, "mark_source", "") or ("premium" if is_option else "quote")

    if has_price and position.stop_loss > 0 and price <= position.stop_loss * (
        1 + risk_config.stop_loss_tolerance_pct / 100
    ):
        alerts.append(
            Alert(
                alert_type="stop_loss_triggered",
                symbol=position.symbol,
                message=(
                    f"{unit} ${price:.2f} ≤ stop ${position.stop_loss:.2f}"
                    f" (entry ${position.entry_price:.2f}, src={mark_src}"
                    f"{', OPTION' if is_option else ''})"
                ),
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
                message=(
                    f"{unit} ${price:.2f} ≥ target ${position.profit_target:.2f}"
                    f" (entry ${position.entry_price:.2f}, src={mark_src}"
                    f"{', OPTION' if is_option else ''})"
                ),
                recommended_response="Take Partial Profit or Exit per plan",
                severity="high",
            )
        )

    # Brandt LFD / TechCharts Type 1–4 path alerts (structure, not fixed %)
    # Skip for option premium lots — structure levels are underlying-based.
    if has_price and not is_option:
        levels = _structure_levels(position)
        lfd = levels["lfd_level"]
        brk = levels["breakout_level"]
        neg = levels["negation_level"]
        # Infer direction from stop geometry when missing
        direction = levels["direction"]
        if not direction:
            if position.stop_loss and position.stop_loss < position.entry_price:
                direction = "bullish"
            elif position.stop_loss and position.stop_loss > position.entry_price:
                direction = "bearish"
        # Proxy structure from stop/target when plan did not carry LFD fields
        if lfd <= 0 and position.stop_loss > 0:
            lfd = float(position.stop_loss)
        if brk <= 0 and position.entry_price > 0:
            brk = float(position.entry_price)
        if neg <= 0 and position.stop_loss > 0:
            # Negation slightly beyond stop (pattern fail beyond LFD stop)
            if direction in ("bullish", "long", "Bullish"):
                neg = min(float(position.stop_loss) * 0.995, float(position.stop_loss) - 0.01)
            else:
                neg = max(float(position.stop_loss) * 1.005, float(position.stop_loss) + 0.01)
        if lfd > 0 and brk > 0 and neg > 0 and direction:
            session_high = getattr(sym_data, "resistance", None) if sym_data else None
            session_low = getattr(sym_data, "support", None) if sym_data else None
            # Prefer price as both extremes when S/R are far from tape
            hi = float(price)
            lo = float(price)
            if sym_data:
                # Use change to infer session extremes loosely
                chg = abs(float(getattr(sym_data, "change_pct", 0) or 0)) / 100.0
                if chg > 0:
                    hi = max(price, position.entry_price * (1 + chg))
                    lo = min(price, position.entry_price * (1 - chg))
            path = classify_breakout_path(
                direction=direction,
                entry_price=float(position.entry_price),
                breakout_level=float(brk),
                lfd_level=float(lfd),
                negation_level=float(neg),
                current_price=float(price),
                session_high=hi,
                session_low=lo,
                measured_target=float(levels["measured_target"] or position.profit_target or 0),
            )
            # Persist live type on position when attribute exists
            try:
                position.breakout_type = path.breakout_type.value  # type: ignore[attr-defined]
            except Exception:
                pass
            if path.breakout_type == BreakoutType.TYPE_4_FAILED:
                alerts.append(
                    Alert(
                        alert_type="pattern_negation_broken",
                        symbol=position.symbol,
                        message=path.message,
                        recommended_response=path.recommended_action,
                        severity="critical",
                    )
                )
            elif path.breakout_type == BreakoutType.TYPE_3_DEEP_RETEST:
                alerts.append(
                    Alert(
                        alert_type="lfd_broken_type3",
                        symbol=position.symbol,
                        message=path.message,
                        recommended_response=path.recommended_action,
                        severity="high",
                    )
                )
            elif path.breakout_type == BreakoutType.TYPE_2_STANDARD_RETEST:
                alerts.append(
                    Alert(
                        alert_type="breakout_retest_type2",
                        symbol=position.symbol,
                        message=path.message,
                        recommended_response=path.recommended_action,
                        severity="medium",
                    )
                )
            # Type 1: informational only when extended into target zone
            elif path.breakout_type == BreakoutType.TYPE_1_MOMENTUM and position.profit_target > 0:
                if direction in ("bullish", "long", "Bullish") and price >= position.profit_target * 0.98:
                    alerts.append(
                        Alert(
                            alert_type="momentum_type1_near_target",
                            symbol=position.symbol,
                            message=path.message + f" — near structure target ${position.profit_target:.2f}",
                            recommended_response=path.recommended_action,
                            severity="medium",
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