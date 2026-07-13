"""Text reports for backtest periods and config comparisons."""

from __future__ import annotations

from trading_agent.backtest.engine import score_period
from trading_agent.backtest.models import BacktestPeriodResult, SweepResult


def render_period_report(result: BacktestPeriodResult) -> str:
    lines = [
        f"# Backtest Period — {result.config_name}",
        "",
        "## Assumptions",
    ]
    for a in result.assumptions:
        lines.append(f"- {a}")
    lines.extend(
        [
            "",
            "## Config",
            f"- min_confidence_score: {result.config.min_confidence_score}",
            f"- min_setup_grade: {result.config.min_setup_grade}",
            f"- prefer_a_tier_only: {result.config.prefer_a_tier_only}",
            f"- min_technical_score: {result.config.min_technical_score}",
            f"- cio_min_confidence: {result.config.cio_min_confidence}",
            f"- hold_bars: {result.config.hold_bars}",
            f"- max_trades_per_day: {result.config.max_trades_per_day}",
            "",
            "## Period metrics",
            f"- **Total P/L:** ${result.total_pnl:+,.2f}",
            f"- **Expectancy:** ${result.expectancy:+,.2f} / trade",
            f"- **Win rate:** {result.win_rate:.1%} ({result.winner_count}W / {result.loser_count}L)",
            f"- **Trade count:** {result.trade_count}",
            f"- **Profit factor:** {result.profit_factor:.2f}",
            f"- **Max drawdown:** ${result.max_drawdown:,.2f}",
            f"- **Avg cash %:** {result.avg_cash_pct:.1f}%",
            f"- **Days simulated:** {result.metadata.get('days_simulated', len(result.days))}",
            f"- **Symbols:** {result.metadata.get('symbols', '')}",
            f"- **Score:** {score_period(result):.2f}",
            "",
            "## Sample trades",
        ]
    )
    for t in result.trades[:12]:
        lines.append(
            f"- {t.symbol} {t.strategy} [{t.grade or 'n/a'}] "
            f"entry={t.entry_price:.2f} exit={t.exit_price:.2f} "
            f"({t.exit_reason}) P/L=${t.profit_loss:+.2f}"
        )
    if not result.trades:
        lines.append("- _No trades generated under this config._")
    return "\n".join(lines) + "\n"


def render_comparison(sweep: SweepResult) -> str:
    lines = [
        "# Backtest config comparison",
        "",
        f"**Objective:** {sweep.objective}",
        f"**Best config:** **{sweep.best_name}**",
        "",
        "## Ranking",
    ]
    by_name = {r.config_name: r for r in sweep.results}
    for i, name in enumerate(sweep.ranking, 1):
        r = by_name[name]
        lines.append(
            f"{i}. **{name}** — score {score_period(r):.2f} | "
            f"P/L ${r.total_pnl:+,.2f} | exp ${r.expectancy:+.2f} | "
            f"WR {r.win_rate:.0%} | n={r.trade_count} | DD ${r.max_drawdown:,.2f} | "
            f"cash {r.avg_cash_pct:.0f}%"
        )
    lines.append("")
    for r in sweep.results:
        lines.append(render_period_report(r))
        lines.append("---")
    return "\n".join(lines) + "\n"
