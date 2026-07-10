"""Concise play-oriented messages for Discord delivery."""

from __future__ import annotations

from trading_agent.cio.models import CIOReport
from trading_agent.intraday.models import IntradayReport
from trading_agent.models import DailyTradingPlan
from trading_agent.performance.models import PerformanceReport
from trading_agent.session.intelligence import IntelligenceBrief


def format_intelligence_brief(brief: IntelligenceBrief) -> str:
    lines = [
        f"**Market Intelligence — {brief.date}**",
        f"**Bias:** {brief.bias}",
        f"**Environment:** {brief.environment_score:.1f}/100",
        "",
        "**Overnight snapshot:**",
    ]
    for key, val in brief.overnight_summary.items():
        lines.append(f"- {key.title()}: {val}")
    if brief.market_signals:
        lines.append(f"- Signals: {'; '.join(brief.market_signals[:4])}")
    lines.extend(["", f"**Calendar:** {brief.calendar_summary}"])
    for evt in brief.high_impact_events[:4]:
        lines.append(f"- {evt}")
    if brief.news_highlights:
        lines.append("")
        lines.append("**Catalysts (live headlines):**")
        for item in brief.news_highlights[:5]:
            lines.append(f"- {item}")
    else:
        news_src = brief.metadata.get("news_source", "")
        if news_src == "unavailable":
            lines.append("")
            lines.append("**Catalysts:** none — live news feed returned no verified headlines")
    if brief.catalyst_symbols:
        lines.append(f"**Watch:** {', '.join(brief.catalyst_symbols)}")
    market_src = brief.metadata.get("market_source", "")
    cal_src = brief.metadata.get("calendar_source", "")
    if market_src or cal_src:
        lines.append("")
        lines.append(
            f"_Sources: market={market_src or 'n/a'}, calendar={cal_src or 'n/a'}, news={brief.metadata.get('news_source', 'n/a')}_"
        )
    return "\n".join(lines)


def format_research_plays(plan: DailyTradingPlan) -> str:
    text = format_premarket_plays(plan)
    return text.replace("**Pre-Market Scout", "**Trading Research", 1)


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


def format_cio_plays(report: CIOReport, title: str = "CIO Decision Summary") -> str:
    lines = [
        f"**{title} — {report.date}**",
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


def format_cio_review(report: CIOReport) -> str:
    lines = [
        format_cio_plays(report, title="CIO Daily Review"),
    ]
    if report.context.performance_notes:
        lines.append("")
        lines.append("**Performance lessons applied:**")
        for note in report.context.performance_notes[:5]:
            lines.append(f"- {note}")
    if report.governance_notes:
        lines.append("")
        lines.append("**Governance:**")
        for note in report.governance_notes[:3]:
            lines.append(f"- {note}")
    return "\n".join(lines)


def format_performance_plays(report: PerformanceReport) -> str:
    m = report.metrics
    lines = [
        f"**Performance Review — {report.date}**",
        f"**Session P/L:** ${m.total_profit_loss:+.2f} | Win rate: {m.win_rate:.0%} "
        f"({m.winner_count}W/{m.loser_count}L)",
        f"**Profit factor:** {m.profit_factor:.2f} | Expectancy: ${m.expectancy:.2f}/trade",
        "",
    ]
    if m.strategy_performance:
        lines.append("**Strategy P/L:**")
        for strategy, pnl in sorted(m.strategy_performance.items(), key=lambda x: -x[1])[:4]:
            lines.append(f"- {strategy}: ${pnl:+.2f}")
    if report.lessons_learned:
        lines.append("")
        lines.append("**Lessons:**")
        for lesson in report.lessons_learned[:4]:
            lines.append(f"- {lesson}")
    if report.tomorrow_adjustments:
        lines.append("")
        lines.append("**Tomorrow adjustments:**")
        for adj in report.tomorrow_adjustments[:4]:
            lines.append(f"- {adj}")
    return "\n".join(lines)


def format_preopen_check(plan_context: dict, report: IntradayReport | None = None) -> str:
    lines = [
        f"**Pre-Open Check — {plan_context.get('date', 'today')}**",
        f"**Bias:** {plan_context.get('overall_market_bias', 'N/A')}",
        f"**Environment:** {plan_context.get('market_environment_score', 'N/A')}/100",
        f"**Watchlist:** {', '.join(plan_context.get('top_watchlist', [])) or 'None'}",
        "",
    ]
    if plan_context.get("stay_in_cash"):
        lines.append("**Status:** STAY IN CASH — no approved entries at open")
    elif plan_context.get("ranked_opportunities"):
        lines.append("**Approved research plays:**")
        for opp in plan_context["ranked_opportunities"][:5]:
            lines.append(
                f"- **{opp['symbol']}** {opp['strategy']} @ ${opp['entry_price']:.2f} "
                f"(conf {opp['confidence_score']:.0f})"
            )
    if report:
        if report.recommendations:
            lines.append("")
            lines.append("**Position readiness:**")
            for rec in report.recommendations:
                lines.append(f"- **{rec.symbol}** — {rec.action}")
        elif report.no_open_positions:
            watch = build_watchlist_plays(report)
            if watch:
                lines.append("")
                lines.append("**Watchlist readiness:**")
                lines.extend(watch[:6])
    lines.append("")
    lines.append("_Pre-open check complete — desk monitoring begins at 06:30 PT._")
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
        f"**Trading Desk — cycle {cycle}** ({report.timestamp})",
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
            lines.append(f"- **{rec.symbol}** — **{rec.action}**: {rec.why_recommended}")
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