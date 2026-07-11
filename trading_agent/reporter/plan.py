"""Render the Daily Trading Plan with all required fields."""

from __future__ import annotations

from typing import List

from trading_agent.models import DailyTradingPlan, RejectedSetup, TradeOpportunity


def _render_opportunity(opp: TradeOpportunity) -> str:
    strikes = ", ".join(f"${s:.2f}" for s in opp.strike_prices)
    reasons = "\n".join(f"    - {r}" for r in opp.supporting_reasons)
    risks = "\n".join(f"    - {r}" for r in (opp.risks or ["Standard session risk"]))
    return f"""
### #{opp.rank} — {opp.symbol} [{getattr(opp, 'setup_grade', 'C')}] ({opp.strategy})

- **Ticker:** {opp.symbol}
- **Setup Grade:** {getattr(opp, 'setup_grade', 'C')} ({getattr(opp, 'grade_score', 0):.1f}/100) — A+/A trade first
- **Hold Style:** {getattr(opp, 'hold_style', '') or 'n/a'}
- **Direction:** {opp.direction}
- **Trade Thesis:** {opp.trade_thesis or "n/a"}
- **Entry Price:** ${opp.entry_price:.2f}
- **Strike Prices:** {strikes}
- **Expiration:** {opp.expiration}
- **Profit Target:** ${opp.profit_target:.2f}
- **Stop Loss:** ${opp.stop_loss:.2f}
- **Maximum Risk:** ${opp.maximum_risk:.2f}
- **Maximum Reward:** ${opp.maximum_reward:.2f}
- **Probability of Success:** {opp.probability_of_success:.0%}
- **Confidence Score:** {opp.confidence_score:.1f}/100
- **Trade Quality Score:** {opp.trade_quality_score:.1f}/100

**Risks:**
{risks}

**Supporting Reasons:**
{reasons}
"""


def _render_rejections(rejections: List[RejectedSetup]) -> str:
    if not rejections:
        return "\n_No setups were screened out — all candidates passed initial filters or none were evaluated._\n"
    lines = ["\n## Rejected Lower-Quality Setups\n"]
    for r in rejections:
        lines.append(f"- **{r.symbol}:** {r.reason}")
    return "\n".join(lines) + "\n"


def render_daily_plan(plan: DailyTradingPlan) -> str:
    rs = plan.research_summary
    lines = [
        f"# Daily Trading Plan — {plan.date}",
        "",
        "## Overall Market Bias",
        plan.overall_market_bias,
        "",
        "## Market Environment Score",
        f"**{plan.market_environment_score:.1f}** / 100",
        "",
        "## Overnight Global Markets",
    ]
    overnight = rs.get("overnight_summary", {})
    for key, val in overnight.items():
        lines.append(f"- **{key.title()}:** {val}")
    if rs.get("market_signals"):
        lines.append(f"- **Key signals:** {'; '.join(rs['market_signals'][:4])}")
    lines.extend(["", "## Economic Calendar Highlights", rs.get("calendar_summary", "N/A")])
    for evt in rs.get("high_impact_events", []):
        lines.append(f"- {evt}")
    lines.extend(["", "## News & Catalysts"])
    for headline in rs.get("news_highlights", []):
        lines.append(f"- {headline}")
    if rs.get("catalyst_symbols"):
        lines.append(f"- **Catalyst watch:** {', '.join(rs['catalyst_symbols'])}")
    lines.extend(
        [
            "",
            "## Top Watchlist",
            ", ".join(plan.top_watchlist) if plan.top_watchlist else "_None_",
            "",
        ]
    )

    if plan.stay_in_cash:
        lines.extend(
            [
                "## Ranked Trade Opportunities",
                "",
                "**RECOMMENDATION: STAY IN CASH**",
                "",
                plan.cash_recommendation_reason,
                "",
            ]
        )
    else:
        lines.append("## Ranked Trade Opportunities")
        lines.append("")
        for opp in plan.ranked_opportunities:
            lines.append(_render_opportunity(opp).strip())

    lines.append(_render_rejections(plan.rejection_reasons).strip())

    lines.extend(
        [
            "",
            "## Research Summary",
            f"- Market data source: {rs.get('market_source', 'N/A')}",
            f"- Calendar source: {rs.get('calendar_source', 'N/A')}",
            f"- News source: {rs.get('news_source', 'N/A')}",
            f"- Screener source: {rs.get('screener_source', 'N/A')}",
            f"- Candidates screened: {rs.get('candidates_screened', 0)}",
            f"- Qualified after risk filter: {rs.get('qualified_count', 0)}",
            f"- Calendar events reviewed: {rs.get('calendar_events', 0)}",
            f"- News items synthesized: {rs.get('news_items', 0)}",
        ]
    )
    if rs.get("candlestick_pa_note"):
        lines.append(f"- Pattern framework: {rs['candlestick_pa_note']}")
    if rs.get("pattern_signals"):
        lines.append("- Price action / candlestick signals:")
        for hit in rs["pattern_signals"][:8]:
            lines.append(f"  - {hit}")

    if plan.research_summary.get("errors"):
        lines.append("\n**Data collection notes:**")
        for err in plan.research_summary["errors"]:
            lines.append(f"- {err}")

    return "\n".join(lines) + "\n"