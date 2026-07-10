"""Render CIO Executive Decision Report."""

from __future__ import annotations

from trading_agent.cio.models import ApprovedTrade, CIOReport, RejectedDecision


def _render_approved(t: ApprovedTrade) -> str:
    strikes = ", ".join(f"${s:.2f}" for s in t.strike_prices)
    mods = ""
    if t.modifications:
        mods = "\n**Modifications:** " + "; ".join(t.modifications)
    risks = "\n".join(f"  - {r}" for r in t.key_risks)
    return f"""
### #{t.conviction_rank} {t.ticker} — **{t.decision}** (conviction {t.conviction_score:.0f})

| Field | Value |
|-------|-------|
| Direction | {t.direction} |
| Strategy | {t.strategy} |
| Entry Price | ${t.entry_price:.2f} |
| Strike Prices | {strikes} |
| Expiration | {t.expiration_date} |
| Position Size | {t.position_size_pct:.1f}% of portfolio |
| Dollar Allocation | ${t.dollar_allocation:,.2f} |
| Maximum Risk | ${t.maximum_risk:.2f} |
| Maximum Reward | ${t.maximum_reward:.2f} |
| Reward-to-Risk | {t.reward_to_risk:.1f}:1 |
| Profit Target(s) | {", ".join(f"${p:.2f}" for p in t.profit_targets)} |
| Stop Loss | ${t.stop_loss:.2f} |
| Exit Criteria | {t.exit_criteria} |
| Est. Holding Period | {t.estimated_holding_period} |
| Probability of Success | {t.probability_of_success:.0%} |
| Confidence Score | {t.confidence_score:.1f}/100 |
| Capital Efficiency | {t.capital_efficiency:.0f}/100 |
| Est. Trade Drawdown | {t.estimated_drawdown_pct:.2f}% portfolio |
| Risk Rating | {t.risk_rating} |
| Primary Catalyst | {t.primary_catalyst} |
| Technical Summary | {t.technical_summary} |
| Options Summary | {t.options_summary} |
| Correlation Group | {t.correlation_group or t.sector} |

**Why should this trade work?**  
{t.why_it_works}

**Why could this trade fail?**  
{t.why_it_fails}

**What event would invalidate this thesis?**  
{t.thesis_invalidation}

**Would a professional hedge fund approve this trade?**  
{t.hedge_fund_approve}

**Key Risks:**
{risks}

**Contingency Plan:** {t.contingency_plan}

**Decision Rationale:** {t.decision_explanation}{mods}
"""


def _render_rejected(r: RejectedDecision) -> str:
    ch = "; ".join(r.challenges[:4]) if r.challenges else ""
    lines = [
        f"- **{r.ticker} — {r.decision}:** {r.explanation}",
    ]
    if ch:
        lines.append(f"  - Challenges: {ch}")
    if r.why_it_fails:
        lines.append(f"  - Why it fails: {r.why_it_fails}")
    if r.thesis_invalidation:
        lines.append(f"  - Invalidation: {r.thesis_invalidation}")
    lines.append(f"  - Hedge fund approve: {r.hedge_fund_approve}")
    return "\n".join(lines)


def render_cio_report(report: CIOReport) -> str:
    p = report.portfolio
    lines = [
        f"# CIO Executive Decision Report — {report.date}",
        "",
        "## Daily Portfolio Summary",
        f"- **Overall Market Bias:** {p.overall_market_bias}",
        f"- **Market Environment Score:** {p.market_environment_score:.1f}/100",
        f"- **Capital Allocation (deployed):** {p.total_capital_recommended_pct:.1f}%",
        f"- **Cash Allocation:** {p.cash_allocation_pct:.1f}%",
        f"- **Approved Trades:** {p.approved_count}",
        f"- **Modified Trades:** {p.modified_count}",
        f"- **Rejected / Delayed:** {p.rejected_count}",
        f"- **Average Probability of Success:** {p.average_probability:.0%}",
        f"- **Average Confidence Score:** {p.average_confidence:.1f}/100",
        f"- **Portfolio Risk Rating:** {p.portfolio_risk_rating}",
        f"- **Overall Portfolio Risk:** {p.overall_portfolio_risk}",
        f"- **Est. Portfolio Drawdown:** {p.estimated_portfolio_drawdown_pct:.2f}%",
        f"- **Capital Efficiency (book):** {p.capital_efficiency_score:.1f}/100",
        f"- **Max Sector Concentration:** {p.max_sector_concentration_pct:.1f}%",
        f"- **Max Strategy Concentration:** {p.max_strategy_concentration_pct:.1f}%",
        f"- **Correlation:** {p.correlation_note}",
        "",
        "### Portfolio Allocation (by sector)",
    ]
    for sec, pct in p.sector_allocation.items():
        lines.append(f"- {sec}: {pct:.1f}%")
    if not p.sector_allocation:
        lines.append("- _None — cash position_")

    lines.extend(["", "### Strategy Allocation"])
    for strat, pct in p.strategy_allocation.items():
        lines.append(f"- {strat}: {pct:.1f}%")
    if not p.strategy_allocation:
        lines.append("- _None_")

    if p.cash_allocation_pct >= 50:
        lines.extend(
            [
                "",
                "> **CIO Guidance:** Elevated cash allocation. "
                "Capital preservation priority — market conditions do not justify full deployment.",
            ]
        )

    lines.extend(["", "## Governance Notes"])
    for note in report.governance_notes:
        lines.append(f"- {note}")

    lines.extend(["", "## Approved Trades"])
    if not report.approved:
        lines.append("_No unmodified approvals for capital deployment today._")
    else:
        for t in report.approved:
            lines.append(_render_approved(t).strip())

    lines.extend(["", "## Modified Trades"])
    if not report.modified:
        lines.append("_No modified approvals._")
    else:
        for t in report.modified:
            lines.append(_render_approved(t).strip())

    lines.extend(["", "## Rejected Trades"])
    if not report.rejected:
        lines.append("_No rejections._")
    else:
        for r in report.rejected:
            lines.append(_render_rejected(r))

    # Back-compat section title used by older tests
    lines.extend(["", "## Rejected / Delayed / Watchlist"])
    if not report.rejected:
        lines.append("_No rejections._")
    else:
        for r in report.rejected:
            ch = "; ".join(r.challenges[:3]) if r.challenges else ""
            lines.append(f"- **{r.ticker} — {r.decision}:** {r.explanation}")
            if ch:
                lines.append(f"  - Challenges: {ch}")

    lines.extend(["", "## Cross-Phase Context"])
    ctx = report.context
    if ctx.intraday_flags:
        lines.append("- **Phase 2 intraday flags:**")
        for sym, act in ctx.intraday_flags.items():
            lines.append(f"  - {sym}: {act}")
    if ctx.strategy_refinement:
        lines.append("- **Phase 3 confidence refinements:**")
        for k, v in ctx.strategy_refinement.items():
            lines.append(f"  - {k}: {v:+.1f} pts")
    if ctx.performance_notes:
        lines.append("- **Phase 3 lessons applied:**")
        for n in ctx.performance_notes[:3]:
            lines.append(f"  - {n}")

    return "\n".join(lines) + "\n"
