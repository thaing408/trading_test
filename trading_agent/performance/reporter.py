"""Render Daily Performance Report."""

from __future__ import annotations

from trading_agent.performance.models import CompletedTrade, PerformanceReport


def _render_trade(t: CompletedTrade) -> str:
    return f"""
### {t.symbol} — {t.strategy}

| Field | Value |
|-------|-------|
| Entry / Exit | ${t.entry:.2f} → ${t.exit:.2f} |
| Profit/Loss | ${t.profit_loss:+.2f} |
| Holding Time | {t.holding_time_minutes} min |
| Technical Setup | {t.technical_setup} |
| News Catalyst | {t.news_catalyst} |
| Market Conditions | {t.market_conditions} |
| Volatility Environment | {t.volatility_environment} |
| Risk-to-Reward | {t.risk_reward_ratio:.2f} |
| Probability of Success | {t.probability_of_success:.0%} |
| Confidence Score | {t.confidence_score:.1f}/100 |
| Position Size | {t.position_size} |
| Max Drawdown | ${t.max_drawdown:.2f} |
| MFE / MAE | ${t.max_favorable_excursion:.2f} / ${t.max_adverse_excursion:.2f} |
| Sector / Regime | {t.sector or 'N/A'} / {t.market_regime or 'N/A'} |
"""


def render_performance_report(report: PerformanceReport) -> str:
    m = report.metrics
    p = report.patterns
    r = report.refinement

    lines = [
        f"# Daily Performance Report — {report.date}",
        "",
        "## Daily Performance Metrics",
        f"- **Total P/L:** ${m.total_profit_loss:+.2f}",
        f"- **Win Rate:** {m.win_rate:.1%} ({m.winner_count}W / {m.loser_count}L / {m.trade_count} trades)",
        f"- **Average Winner:** ${m.average_winner:.2f}",
        f"- **Average Loser:** ${m.average_loser:.2f}",
        f"- **Profit Factor:** {m.profit_factor:.2f}",
        f"- **Expectancy:** ${m.expectancy:.2f} per trade",
        f"- **Largest Winner:** ${m.largest_winner:.2f}",
        f"- **Largest Loser:** ${m.largest_loser:.2f}",
        "",
        "### Strategy Performance",
    ]
    for strat, pl in sorted(m.strategy_performance.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {strat}: ${pl:+.2f}")

    lines.extend(["", "### Sector Performance"])
    for sec, pl in sorted(m.sector_performance.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {sec}: ${pl:+.2f}")

    lines.extend(["", "### Market Regime Performance"])
    for reg, pl in sorted(m.regime_performance.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {reg}: ${pl:+.2f}")

    lines.extend(["", "## Recurring Patterns"])
    lines.append(f"- **Best strategies:** {', '.join(p.best_strategies) or 'N/A'}")
    lines.append(f"- **Weakest strategies:** {', '.join(p.weakest_strategies) or 'N/A'}")
    lines.append(f"- **Losing trade causes:** {', '.join(p.losing_trade_causes) or 'N/A'}")
    lines.append(f"- **Profitable conditions:** {', '.join(p.profitable_conditions) or 'N/A'}")
    if p.time_of_day_performance:
        lines.append("- **Time-of-day performance:**")
        for bucket, pl in p.time_of_day_performance.items():
            lines.append(f"  - {bucket}: ${pl:+.2f}")
    lines.append(f"- **Top indicator combos:** {', '.join(p.top_indicator_combos) or 'N/A'}")
    lines.append(f"- **Top news catalysts:** {', '.join(p.top_news_catalysts) or 'N/A'}")

    lines.extend(["", "## Confidence Refinement (Historical)"])
    if r.strategy_adjustments:
        lines.append("- Strategy adjustments:")
        for k, v in r.strategy_adjustments.items():
            lines.append(f"  - {k}: {v:+.1f} pts")
    if r.sector_adjustments:
        lines.append("- Sector adjustments:")
        for k, v in r.sector_adjustments.items():
            lines.append(f"  - {k}: {v:+.1f} pts")
    if r.regime_adjustments:
        lines.append("- Regime adjustments:")
        for k, v in r.regime_adjustments.items():
            lines.append(f"  - {k}: {v:+.1f} pts")
    for note in r.notes:
        lines.append(f"- {note}")

    lines.extend(["", "## Summary of All Trades"])
    if not report.trades:
        lines.append("_No completed trades for this session._")
    else:
        for t in report.trades:
            lines.append(_render_trade(t).strip())

    lines.extend(["", "## Key Lessons Learned"])
    for item in report.lessons_learned:
        lines.append(f"- {item}")

    lines.extend(["", "## Mistakes to Avoid"])
    for item in report.mistakes_to_avoid:
        lines.append(f"- {item}")

    lines.extend(["", "## Areas for Improvement"])
    for item in report.areas_for_improvement:
        lines.append(f"- {item}")

    lines.extend(["", "## Successful Habits to Reinforce"])
    for item in report.successful_habits:
        lines.append(f"- {item}")

    lines.extend(["", "## Recommended Adjustments for Tomorrow"])
    for item in report.tomorrow_adjustments:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"