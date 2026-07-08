"""Render the Daily Trading Plan with all required fields."""

from __future__ import annotations

from typing import List

from trading_agent.models import DailyTradingPlan, RejectedSetup, TradeOpportunity


def _render_opportunity(opp: TradeOpportunity) -> str:
    strikes = ", ".join(f"${s:.2f}" for s in opp.strike_prices)
    reasons = "\n".join(f"    - {r}" for r in opp.supporting_reasons)
    return f"""
### #{opp.rank} — {opp.symbol} ({opp.strategy})

- **Entry Price:** ${opp.entry_price:.2f}
- **Strike Prices:** {strikes}
- **Expiration:** {opp.expiration}
- **Profit Target:** ${opp.profit_target:.2f}
- **Stop Loss:** ${opp.stop_loss:.2f}
- **Maximum Risk:** ${opp.maximum_risk:.2f}
- **Maximum Reward:** ${opp.maximum_reward:.2f}
- **Probability of Success:** {opp.probability_of_success:.0%}
- **Confidence Score:** {opp.confidence_score:.1f}/100

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
    lines = [
        f"# Daily Trading Plan — {plan.date}",
        "",
        "## Overall Market Bias",
        plan.overall_market_bias,
        "",
        "## Market Environment Score",
        f"**{plan.market_environment_score:.1f}** / 100",
        "",
        "## Top Watchlist",
        ", ".join(plan.top_watchlist) if plan.top_watchlist else "_None_",
        "",
    ]

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
            f"- Market data source: {plan.research_summary.get('market_source', 'N/A')}",
            f"- Calendar source: {plan.research_summary.get('calendar_source', 'N/A')}",
            f"- News source: {plan.research_summary.get('news_source', 'N/A')}",
            f"- Screener source: {plan.research_summary.get('screener_source', 'N/A')}",
            f"- Candidates screened: {plan.research_summary.get('candidates_screened', 0)}",
            f"- Qualified after risk filter: {plan.research_summary.get('qualified_count', 0)}",
        ]
    )

    if plan.research_summary.get("errors"):
        lines.append("\n**Data collection notes:**")
        for err in plan.research_summary["errors"]:
            lines.append(f"- {err}")

    return "\n".join(lines) + "\n"