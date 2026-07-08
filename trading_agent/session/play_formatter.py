"""Concise play-oriented messages for Discord delivery."""

from __future__ import annotations

from trading_agent.cio.models import CIOReport
from trading_agent.intraday.models import IntradayReport
from trading_agent.models import DailyTradingPlan


def format_premarket_plays(plan: DailyTradingPlan) -> str:
    lines = [
        f"**Pre-Market Scout — {plan.date}**",
        f"**Bias:** {plan.overall_market_bias}",
        f"**Environment:** {plan.market_environment_score:.1f}/100",
        f"**Watchlist:** {', '.join(plan.top_watchlist) if plan.top_watchlist else 'None'}",
        "",
    ]
    highlights = plan.research_summary.get("news_highlights", [])
    if highlights:
        lines.append("**Catalysts:**")
        for item in highlights[:5]:
            lines.append(f"- {item}")
        lines.append("")

    if plan.stay_in_cash:
        lines.extend(
            [
                "**RECOMMENDATION: STAY IN CASH**",
                plan.cash_recommendation_reason or "No setups passed risk standards.",
            ]
        )
        if plan.rejection_reasons:
            lines.append("")
            lines.append("**Screened / rejected:**")
            for rejection in plan.rejection_reasons[:6]:
                lines.append(f"- {rejection.symbol}: {rejection.reason}")
    else:
        lines.append("**Ranked plays:**")
        for opp in plan.ranked_opportunities:
            rr = opp.maximum_reward / opp.maximum_risk if opp.maximum_risk else 0.0
            lines.extend(
                [
                    f"### {opp.symbol} — {opp.strategy}",
                    f"- Entry: ${opp.entry_price:.2f} | Stop: ${opp.stop_loss:.2f} | Target: ${opp.profit_target:.2f}",
                    f"- Risk/Reward: {rr:.1f}:1 | Prob: {opp.probability_of_success:.0%} | Conf: {opp.confidence_score:.0f}/100",
                ]
            )
    return "\n".join(lines)


def format_cio_plays(report: CIOReport) -> str:
    lines = [
        f"**CIO Decision Summary — {report.date}**",
        f"**Market bias:** {report.context.overall_market_bias}",
        f"**Capital deployed:** {report.portfolio.total_capital_recommended_pct:.0f}% | "
        f"Cash: {report.portfolio.cash_allocation_pct:.0f}%",
        "",
    ]
    if report.approved:
        lines.append("**Approved plays:**")
        for trade in report.approved:
            lines.extend(
                [
                    f"- **{trade.ticker}** — {trade.decision}: {trade.strategy}",
                    f"  Entry ${trade.entry_price:.2f} | Size {trade.position_size_pct:.0f}% | Conf {trade.confidence_score:.0f}",
                ]
            )
    else:
        lines.append("**No CIO approvals today.**")
    if report.rejected:
        lines.append("")
        lines.append("**Rejected / delayed:**")
        for item in report.rejected[:5]:
            lines.append(f"- {item.ticker} — {item.decision}: {item.explanation}")
    return "\n".join(lines)


def _watchlist_action(symbol: str, trend: str, price: float, vwap: float) -> str:
    above_vwap = price > vwap
    if trend == "uptrend" and above_vwap:
        return "Enter / Watch Long"
    if trend == "downtrend":
        return "Avoid / Exit bias"
    if trend == "uptrend":
        return "Watch — pullback to VWAP"
    return "Watch"


def build_watchlist_plays(report: IntradayReport) -> list[str]:
    plays: list[str] = []
    watchlist = report.plan_context.get("top_watchlist", [])
    for symbol in watchlist:
        data = report.session_snapshot.symbols.get(symbol)
        if not data:
            continue
        action = _watchlist_action(symbol, data.trend, data.price, data.vwap)
        plays.append(
            f"**{symbol}** — {action} | ${data.price:.2f} ({data.change_pct:+.1f}%) "
            f"| trend {data.trend} | VWAP ${data.vwap:.2f}"
        )
    return plays


def format_intraday_plays(report: IntradayReport, cycle: int) -> str:
    lines = [
        f"**Intraday Update — cycle {cycle}** ({report.timestamp})",
        f"**Regime:** {report.session.regime_description}",
        f"**Session score:** {report.session.session_score:.1f}/100 | Risk: {report.session.risk_environment}",
        "",
    ]
    if report.notifications:
        lines.append("**Alerts:**")
        for alert in report.notifications[:6]:
            lines.append(
                f"- [{alert.severity.upper()}] **{alert.symbol}** ({alert.alert_type}): {alert.recommended_response}"
            )
        lines.append("")

    if report.recommendations:
        lines.append("**Position actions:**")
        for rec in report.recommendations:
            lines.append(
                f"- **{rec.symbol}** — **{rec.action}**: {rec.why_recommended}"
            )
    elif report.no_open_positions:
        watch_plays = build_watchlist_plays(report)
        if watch_plays:
            lines.append("**Watchlist scout:**")
            lines.extend(watch_plays)
        else:
            lines.append("_No open positions — monitoring watchlist; no actionable entries yet._")
            for obs in report.session.observations[:5]:
                lines.append(f"- {obs}")

    return "\n".join(lines)