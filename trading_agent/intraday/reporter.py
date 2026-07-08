"""Render Intraday Position Management Report."""

from __future__ import annotations

from trading_agent.intraday.models import IntradayReport, PositionRecommendation


def _render_recommendation(rec: PositionRecommendation) -> str:
    alert_lines = ""
    if rec.alerts:
        alert_lines = "\n**Alerts:**\n" + "\n".join(
            f"  - [{a.alert_type}] {a.message} → {a.recommended_response}" for a in rec.alerts
        )
    return f"""
### {rec.symbol} — **{rec.action}**

- **What Changed:** {rec.what_changed}
- **Why Recommended:** {rec.why_recommended}
- **Risk If No Action:** {rec.risk_if_no_action}
- **Updated Probability of Success:** {rec.updated_probability:.0%}
- **Updated Confidence Score:** {rec.updated_confidence:.1f}/100{alert_lines}
"""


def render_intraday_report(report: IntradayReport) -> str:
    lines = [
        f"# Intraday Position Management Report — {report.timestamp}",
        "",
        f"**Monitoring cycle:** {report.cycle_count}",
        "",
        "## Session Observations",
        report.session.regime_description,
        f"**Risk environment:** {report.session.risk_environment}",
        f"**Session score:** {report.session.session_score:.1f}/100",
        "",
    ]
    for obs in report.session.observations:
        lines.append(f"- {obs}")

    lines.extend(["", "## Risk Limit Evaluation"])
    if report.risk_evaluation.within_limits:
        lines.append("All positions within predefined risk limits.")
    else:
        lines.append("**RISK LIMIT BREACHES:**")
        for b in report.risk_evaluation.breaches:
            lines.append(f"- {b}")

    if report.notifications:
        lines.extend(["", "## Immediate Notifications"])
        for n in report.notifications:
            lines.append(
                f"- **[{n.severity.upper()}] {n.alert_type}** ({n.symbol}): {n.message} "
                f"→ {n.recommended_response}"
            )

    lines.extend(["", "## Position Recommendations"])
    if report.no_open_positions:
        lines.append("_No open positions. Session monitoring active; awaiting entries from Daily Trading Plan._")
    else:
        for rec in report.recommendations:
            lines.append(_render_recommendation(rec).strip())

    lines.extend(
        [
            "",
            "## Plan Context",
            f"- Market bias: {report.plan_context.get('overall_market_bias', 'N/A')}",
            f"- Environment score: {report.plan_context.get('market_environment_score', 'N/A')}",
            f"- Data source: {report.session_snapshot.source}",
        ]
    )
    if report.session_snapshot.errors:
        lines.append("\n**Data notes:**")
        for err in report.session_snapshot.errors:
            lines.append(f"- {err}")

    return "\n".join(lines) + "\n"