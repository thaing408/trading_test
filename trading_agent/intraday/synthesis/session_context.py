"""Synthesize intraday session observations into actionable context."""

from __future__ import annotations

from trading_agent.intraday.models import SessionSnapshot, SessionSynthesis


def synthesize_session(snapshot: SessionSnapshot) -> SessionSynthesis:
    observations: list[str] = []
    regime_shift = (
        snapshot.prior_regime != snapshot.market_regime
        and snapshot.prior_regime in ("bullish", "bearish")
        and snapshot.market_regime in ("bullish", "bearish")
        and snapshot.prior_regime != snapshot.market_regime
    )

    observations.append(
        f"Market regime: {snapshot.prior_regime} → {snapshot.market_regime}"
        + (" (SHIFT DETECTED)" if regime_shift else "")
    )
    observations.append(
        f"VIX change {snapshot.vix_change_pct:+.1f}%; "
        f"breadth {snapshot.breadth_advancers} adv / {snapshot.breadth_decliners} dec "
        f"(ratio {snapshot.breadth_ratio:.2f})"
    )
    if snapshot.sector_leaders:
        observations.append(f"Sector strength: {', '.join(snapshot.sector_leaders)}")
    if snapshot.sector_laggards:
        observations.append(f"Sector weakness: {', '.join(snapshot.sector_laggards)}")

    for sym, data in snapshot.symbols.items():
        vwap_side = "above" if data.price > data.vwap else "below" if data.price < data.vwap else "at"
        observations.append(
            f"{sym}: ${data.price:.2f} ({data.change_pct:+.1f}%), "
            f"VWAP {vwap_side} (${data.vwap:.2f}), vol {data.relative_volume:.1f}x, "
            f"trend {data.trend}, momentum {data.momentum}, "
            f"IV {data.iv:.1f}% ({data.iv_change_pct:+.1f}%), OI chg {data.oi_change_pct:+.1f}%, "
            f"Greeks Δ={data.delta:.3f} Γ={data.gamma:.3f} Θ={data.theta:.3f} ν={data.vega:.3f}, "
            f"flow {data.options_flow_bias}, S/R ${data.support:.2f}/${data.resistance:.2f}"
        )

    for headline in snapshot.breaking_news[:3]:
        observations.append(f"News: {headline}")
    for ann in snapshot.economic_announcements[:2]:
        observations.append(f"Announcement: {ann}")

    score = 50.0
    if snapshot.market_regime == "bullish":
        score += 15
    elif snapshot.market_regime == "bearish":
        score -= 15
    score += (snapshot.breadth_ratio - 0.5) * 20
    score -= max(0, snapshot.vix_change_pct) * 0.5
    score = max(0.0, min(100.0, score))

    risk_env = "elevated" if regime_shift or snapshot.vix_change_pct > 5 else "normal"
    if snapshot.market_regime == "bearish":
        risk_env = "elevated"

    regime_desc = (
        f"Session regime is {snapshot.market_regime}"
        + (f" (shifted from {snapshot.prior_regime})" if regime_shift else "")
    )

    return SessionSynthesis(
        regime_shift=regime_shift,
        regime_description=regime_desc,
        observations=observations,
        risk_environment=risk_env,
        session_score=round(score, 1),
    )