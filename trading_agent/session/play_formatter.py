"""Concise play-oriented messages for Discord delivery."""

from __future__ import annotations

from trading_agent.cio.models import CIOReport
from trading_agent.intraday.models import IntradayReport
from trading_agent.models import DailyTradingPlan
from trading_agent.performance.models import PerformanceReport
from trading_agent.session.intelligence import IntelligenceBrief


def format_intelligence_brief(brief: IntelligenceBrief) -> str:
    """Institutional Market Intelligence brief — no trade recommendations."""
    lines = [
        f"**Market Intelligence — {brief.date}**",
        f"**Outlook:** {brief.outlook}",
        f"**Market Environment Score:** {brief.environment_score:.1f}/100",
        f"**Bias narrative:** {brief.bias}",
        "",
        "**Global markets / overnight:**",
    ]
    for key, val in brief.overnight_summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {val}")
    if brief.vix_term_note:
        lines.append(f"- VIX term: {brief.vix_term_note}")
    if brief.yield_curve_note:
        lines.append(f"- Yields: {brief.yield_curve_note}")
    if brief.market_signals:
        lines.append(f"- Signals: {'; '.join(brief.market_signals[:6])}")

    lines.extend(["", f"**Macro calendar:** {brief.calendar_summary}"])
    for evt in brief.high_impact_events[:6]:
        lines.append(f"- {evt}")

    if brief.sector_ranking:
        lines.extend(["", "**Sector ranking (strongest → weakest):**"])
        for i, row in enumerate(brief.sector_ranking, 1):
            lines.append(f"{i}. {row}")

    if brief.etf_snapshot:
        lines.extend(["", "**ETF complex:**"])
        for row in brief.etf_snapshot:
            lines.append(f"- {row}")

    if brief.breadth_notes:
        lines.extend(["", "**Market breadth / internals:**"])
        for row in brief.breadth_notes[:10]:
            lines.append(f"- {row}")

    if brief.unavailable_series:
        lines.extend(["", "**Unavailable series (honest gaps):**"])
        for key, note in list(brief.unavailable_series.items())[:8]:
            lines.append(f"- {key}: {note}")

    if brief.news_highlights:
        lines.append("")
        lines.append("**News / catalysts (verified source only):**")
        for item in brief.news_highlights[:5]:
            lines.append(f"- {item}")
    else:
        news_src = brief.metadata.get("news_source", "")
        if news_src in ("unavailable", "fixture-fallback", ""):
            lines.append("")
            lines.append(
                "**News / catalysts:** none — no verified live headlines "
                "(fixture-fallback never treated as institutional catalysts)"
            )
        elif news_src == "fixture":
            lines.append("")
            lines.append("**News / catalysts (fixture mode):**")
            # Fixture mode still surfaces highlights via synthesis when source is fixture
            if not brief.news_highlights:
                lines.append("- (fixture news present in pipeline; none ranked into brief)")

    if brief.catalyst_symbols:
        lines.append(f"**Catalyst symbols:** {', '.join(brief.catalyst_symbols)}")

    lines.extend(["", "**Conclusion (intelligence only — no trade tickets):**"])
    lines.append(f"- **Recommended market posture:** {brief.market_posture or 'n/a'}")
    if brief.top_opportunities:
        lines.append("- **Top opportunities (themes):**")
        for item in brief.top_opportunities:
            lines.append(f"  - {item}")
    if brief.major_risks:
        lines.append("- **Major risks:**")
        for item in brief.major_risks:
            lines.append(f"  - {item}")
    if brief.expected_drivers:
        lines.append("- **Today's expected market drivers:**")
        for item in brief.expected_drivers:
            lines.append(f"  - {item}")

    market_src = brief.metadata.get("market_source", "")
    cal_src = brief.metadata.get("calendar_source", "")
    if market_src or cal_src:
        lines.append("")
        lines.append(
            f"_Sources: market={market_src or 'n/a'}, "
            f"calendar={cal_src or 'n/a'}, "
            f"news={brief.metadata.get('news_source', 'n/a')}_"
        )
    lines.append("_Desk note: Market Intelligence does not recommend trades or option structures._")
    return "\n".join(lines)


# Discord length: show a capped list but always report totals.
_MAX_REJECT_REASONS_SHOWN = 8


def format_options_enter_cards(plan: DailyTradingPlan, *, limit: int = 5) -> list[str]:
    """Compact auto-trade ENTER cards for options (Discord + logs)."""
    lines: list[str] = []
    cards = [
        o
        for o in (plan.ranked_opportunities or [])
        if getattr(o, "auto_trade_eligible", False)
        and getattr(o, "checklist_passed", False)
        and getattr(o, "edge_complete", False)
        and getattr(o, "defined_risk", True)
        and float(o.entry_price or 0) > 0
        and float(o.stop_loss or 0) > 0
        and float(o.profit_target or 0) > 0
    ][:limit]
    if not cards:
        return lines
    lines.append("**Options AUTO-ENTER cards** (research host — Mac TOS executes after git pull):")
    for o in cards:
        strikes = ", ".join(f"${s:.2f}" for s in (o.strike_prices or [])[:4])
        lines.append(
            f"- **ENTER {o.symbol}** `{o.strategy}` [{o.setup_grade}] "
            f"{o.direction} | setup=`{getattr(o, 'playbook_setup_id', '') or 'n/a'}`"
        )
        lines.append(
            f"  strikes [{strikes}] exp {o.expiration} | "
            f"class={getattr(o, 'options_strategy_class', '') or 'n/a'} | "
            f"IVR {getattr(o, 'iv_rank', 0):.0f} POP {getattr(o, 'options_pop', o.probability_of_success):.0%} "
            f"Δ {getattr(o, 'options_delta', 0):.2f} DTE {getattr(o, 'expiration_days', 0)}"
        )
        lines.append(
            f"  entry ${o.entry_price:.2f} stop ${o.stop_loss:.2f} target ${o.profit_target:.2f} "
            f"max_risk ${o.maximum_risk:.2f} | conf {o.confidence_score:.0f}"
        )
    return lines


def format_research_plays(plan: DailyTradingPlan) -> str:
    text = format_premarket_plays(plan)
    text = text.replace("**Pre-Market Scout", "**Trading Research (Options)", 1)
    cards = format_options_enter_cards(plan)
    if cards:
        text = text + "\n\n" + "\n".join(cards)
    return text


def _scanned_count(plan: DailyTradingPlan) -> int:
    """Names evaluated/screened that day (from pipeline research_summary)."""
    rs = plan.research_summary or {}
    if rs.get("candidates_screened") is not None:
        try:
            return int(rs["candidates_screened"])
        except (TypeError, ValueError):
            pass
    # Fallback when summary omitted (constructed plans in tests)
    return len(plan.rejection_reasons or []) + len(plan.ranked_opportunities or [])


def _qualified_count(plan: DailyTradingPlan) -> int:
    rs = plan.research_summary or {}
    if rs.get("qualified_count") is not None:
        try:
            return int(rs["qualified_count"])
        except (TypeError, ValueError):
            pass
    return len(plan.ranked_opportunities or [])


def format_rejection_summary(
    plan: DailyTradingPlan,
    *,
    max_shown: int = _MAX_REJECT_REASONS_SHOWN,
) -> list[str]:
    """Discord-facing scan + rejection block (used for cash and non-cash paths)."""
    rejects = list(plan.rejection_reasons or [])
    total = len(rejects)
    shown = rejects[: max(0, max_shown)]
    scanned = _scanned_count(plan)
    qualified = _qualified_count(plan)
    lines = [
        f"**Scan summary:** scanned **{scanned}** | qualified **{qualified}** | "
        f"rejected **{total}** | showing **{len(shown)}** reason(s)",
    ]
    if total == 0:
        lines.append(
            "_No rejections — all screened names passed gates, or none were evaluated._"
        )
        return lines
    lines.append(f"**Rejected setups ({total} total, displaying {len(shown)}):**")
    for rejection in shown:
        reason = (rejection.reason or "").strip() or "no reason recorded"
        lines.append(f"- **{rejection.symbol}:** {reason}")
    if total > len(shown):
        lines.append(f"_…and **{total - len(shown)}** more rejection(s) not shown._")
    return lines


def format_premarket_plays(plan: DailyTradingPlan) -> str:
    scanned = _scanned_count(plan)
    cap = (plan.research_summary or {}).get("top_candidates_cap") or 5
    try:
        cap = int(cap)
    except (TypeError, ValueError):
        cap = 5
    lines = [
        f"**Pre-Market Scout — {plan.date}**",
        f"**Bias:** {plan.overall_market_bias}",
        f"**Environment:** {plan.market_environment_score:.1f}/100",
        f"**Scanned:** {scanned} name(s)",
        f"**Top 10 Watchlist:** {', '.join(plan.top_watchlist) if plan.top_watchlist else 'None'}",
        "",
    ]
    highlights = (plan.research_summary or {}).get("news_highlights", [])
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
                "",
            ]
        )
        lines.extend(format_rejection_summary(plan))
    else:
        lines.append(f"**Top {cap} trade candidates:**")
        for opp in plan.ranked_opportunities[:cap]:
            strikes = ", ".join(f"${s:.2f}" for s in opp.strike_prices)
            setup_id = getattr(opp, "playbook_setup_id", "") or "n/a"
            eligible = "YES" if getattr(opp, "auto_trade_eligible", False) else "NO"
            methods = getattr(opp, "method_tags", None) or []
            method_s = ", ".join(methods[:5]) if methods else "baseline"
            lines.extend(
                [
                    f"### #{opp.rank} {opp.symbol} [{getattr(opp, 'setup_grade', 'C')}] — "
                    f"{opp.direction} {opp.strategy}",
                    f"- **Suggested trade:** {opp.direction} | setup=`{setup_id}` | "
                    f"auto_trade={eligible}",
                    f"- Grade: {getattr(opp, 'setup_grade', 'C')} "
                    f"({getattr(opp, 'grade_score', 0):.0f}/100) | "
                    f"{getattr(opp, 'hold_style', '') or 'n/a'}",
                    f"- Entry ${opp.entry_price:.2f} | Stop ${opp.stop_loss:.2f} | "
                    f"Target ${opp.profit_target:.2f} | Max risk ${opp.maximum_risk:.2f}",
                    f"- **Options:** {getattr(opp, 'options_strategy_class', '') or 'n/a'} | "
                    f"IVR {getattr(opp, 'iv_rank', 0):.0f} | "
                    f"POP {getattr(opp, 'options_pop', opp.probability_of_success):.0%} | "
                    f"Δ {getattr(opp, 'options_delta', 0):.2f} | "
                    f"DTE {getattr(opp, 'expiration_days', 0)} | "
                    f"defined_risk={getattr(opp, 'defined_risk', True)}",
                    f"- Strikes: {strikes} | Exp: {opp.expiration}",
                    f"- Prob {opp.probability_of_success:.0%} | Conf {opp.confidence_score:.0f} | "
                    f"Quality {getattr(opp, 'combined_quality_score', opp.trade_quality_score):.0f}/100 | "
                    f"Fund {getattr(opp, 'fundamental_score', 0):.0f}",
                    f"- Methods: {method_s}",
                    f"- Checklist: {getattr(opp, 'checklist_passed', False)} | "
                    f"Edge: {getattr(opp, 'edge_complete', False)}",
                    f"- Thesis: {(opp.trade_thesis or 'n/a')[:160]}",
                    f"- Risks: {'; '.join(opp.risks[:3]) if opp.risks else 'standard'}",
                ]
            )
        methods_rs = (plan.research_summary or {}).get("web_methods") or []
        if methods_rs:
            lines.append("")
            lines.append("**Active process methods (research):**")
            for m in methods_rs[:5]:
                if isinstance(m, dict):
                    lines.append(f"- **{m.get('name', m.get('method_id'))}**: {m.get('rule', '')[:120]}")
                else:
                    lines.append(f"- {m}")
        export_info = (plan.research_summary or {}).get("auto_trade_export") or {}
        if export_info:
            lines.append("")
            lines.append(
                f"**Auto-trade book:** {export_info.get('entry_count', 0)} ENTER row(s) "
                f"(Windows suggest/export only — Mac TOS executes after git pull)"
            )
        # Approvals and rejections both visible on Discord when opportunities exist
        lines.append("")
        lines.extend(format_rejection_summary(plan))
    return "\n".join(lines)


def format_cio_plays(report: CIOReport, title: str = "CIO Decision Summary") -> str:
    p = report.portfolio
    lines = [
        f"**{title} — {report.date}**",
        f"**Market bias:** {report.context.overall_market_bias}",
        f"**Capital allocation:** {p.total_capital_recommended_pct:.0f}% deployed | "
        f"**Cash:** {p.cash_allocation_pct:.0f}%",
        f"**Overall portfolio risk:** {p.overall_portfolio_risk} | "
        f"Est. DD {p.estimated_portfolio_drawdown_pct:.1f}% | "
        f"Cap efficiency {p.capital_efficiency_score:.0f}",
        "",
    ]
    # Full research board so CIO (and Discord) can see IBKR-backed setups before decisions
    board = list(getattr(report.context, "research_board_lines", None) or [])
    sources = dict(getattr(report.context, "research_data_sources", None) or {})
    if board or sources:
        ibkr_n = sum(1 for s in sources.values() if str(s).lower() == "ibkr")
        lines.append(
            f"**Research board (CIO visibility — decide trade/no-trade; "
            f"not IBKR execution):** {len(board) or len(sources)} setup(s)"
            + (f" | **{ibkr_n}** with bars=`IBKR`" if sources else "")
        )
        note = getattr(report.context, "research_ohlcv_note", "") or ""
        if note:
            lines.append(f"_{note}_")
        for row in board[:12]:
            lines.append(f"- {row}")
        if len(board) > 12:
            lines.append(f"_…and **{len(board) - 12}** more on the research board._")
        lines.append("")
    if report.approved:
        lines.append("**Approved trades** (A+/A first, then by conviction):")
        for trade in report.approved:
            bars = getattr(trade, "market_data_source", "") or ""
            bars_bit = f" | bars=`{bars.upper()}`" if bars else ""
            lines.extend(
                [
                    f"- **#{trade.conviction_rank} {trade.ticker}** [{getattr(trade, 'setup_grade', 'C')}] — {trade.decision}: "
                    f"{trade.direction} {trade.strategy}",
                    f"  Entry ${trade.entry_price:.2f} | Size {trade.position_size_pct:.0f}% | "
                    f"Conf {trade.confidence_score:.0f} | Conviction {trade.conviction_score:.0f} | "
                    f"R:R {trade.reward_to_risk:.1f}{bars_bit}",
                    f"  Works: {(trade.why_it_works or '')[:120]}…",
                    f"  HF approve: {trade.hedge_fund_approve}",
                ]
            )
    else:
        lines.append("**Approved trades:** none")
    if report.modified:
        lines.append("")
        lines.append("**Modified trades:**")
        for trade in report.modified:
            lines.append(
                f"- **{trade.ticker}** — {trade.decision}: {trade.strategy} | "
                f"Size {trade.position_size_pct:.0f}% | Mods: {'; '.join(trade.modifications) or 'n/a'}"
            )
    if not report.approved and not report.modified:
        lines.append("**No CIO approvals today — remain in cash if uncertainty elevated.**")
    rejected = list(report.rejected or [])
    if rejected or getattr(p, "rejected_count", 0):
        total_r = len(rejected)
        shown_r = rejected[:6]
        lines.append("")
        lines.append(
            f"**Rejected trades ({total_r} total, showing {len(shown_r)}):**"
        )
        if not shown_r:
            lines.append("_No rejection detail list (count only)._")
        for item in shown_r:
            bars = getattr(item, "market_data_source", "") or ""
            bars_bit = f" | bars=`{bars}`" if bars else ""
            lines.append(f"- {item.ticker} — {item.decision}: {item.explanation}{bars_bit}")
        if total_r > len(shown_r):
            lines.append(f"_…and **{total_r - len(shown_r)}** more rejection(s) not shown._")
    if p.sector_allocation:
        lines.append("")
        lines.append(
            "**Portfolio allocation:** "
            + ", ".join(f"{k} {v:.0f}%" for k, v in p.sector_allocation.items())
        )
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
        for note in report.governance_notes[:4]:
            lines.append(f"- {note}")
    return "\n".join(lines)


def format_performance_plays(report: PerformanceReport) -> str:
    m = report.metrics
    meta = report.metadata or {}
    source = meta.get("trades_source", "unknown")
    is_fixture = bool(meta.get("trades_is_fixture"))
    if is_fixture:
        source_note = " ⚠️ **demo fixture — not live P/L**"
    elif m.trade_count == 0:
        source_note = " (empty journal — no closed trades loaded)"
    else:
        source_note = " (live journal)"
    lines = [
        f"**Performance Review — {report.date}**",
        f"**Data source:** `{source}`{source_note}",
        f"**Session P/L:** ${m.total_profit_loss:+.2f} | Win rate: {m.win_rate:.0%} "
        f"({m.winner_count}W/{m.loser_count}L) | trades={m.trade_count}",
        f"**Profit factor:** {m.profit_factor:.2f} | Expectancy: ${m.expectancy:.2f}/trade",
        "",
    ]
    if m.trade_count == 0 and not is_fixture:
        lines.append(
            "_No closed trades loaded — P/L and lessons are empty on purpose "
            "(set TRADING_AGENT_TRADES_FILE for real journal data)._"
        )
        lines.append("")
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


# Actions that do not warrant a fresh Discord ping by themselves
_IDLE_ACTIONS = frozenset({"Hold", "Take No Action"})

_ACTION_SHORT = {
    "Take Partial Profit": "Partial",
    "Move Stop Loss": "Move SL",
    "Scale In": "Scale-in",
    "Scale Out": "Scale-out",
    "Take No Action": "No action",
}


def summarize_intraday_actions(report: IntradayReport) -> str:
    """Short human summary for titles: 'Exit×5 · Partial×4' or 'Watchlist'."""
    from collections import Counter

    counts = Counter(rec.action for rec in report.recommendations)
    if counts:
        bits: list[str] = []
        # Prefer risk-first order
        preferred = (
            "Exit",
            "Take Partial Profit",
            "Move Stop Loss",
            "Scale Out",
            "Hedge",
            "Adjust",
            "Roll",
            "Scale In",
            "Enter",
            "Hold",
            "Take No Action",
        )
        seen: set[str] = set()
        ordered: list[str] = []
        for name in preferred:
            if name in counts:
                ordered.append(name)
                seen.add(name)
        for name in sorted(counts.keys()):
            if name not in seen:
                ordered.append(name)
        for action in ordered:
            n = counts[action]
            if action in _IDLE_ACTIONS and len(counts) > 1:
                continue  # don't clutter title with Hold×N when real actions exist
            short = _ACTION_SHORT.get(action, action)
            bits.append(f"{short}×{n}" if n > 1 else short)
        if bits:
            return " · ".join(bits[:6])

    severities = {(a.severity or "").lower() for a in report.notifications}
    if "critical" in severities:
        return "Critical alerts"
    if "high" in severities:
        return "High alerts"
    if report.notifications:
        return "Alerts"
    if report.session.regime_shift:
        return "Regime shift"
    if report.no_open_positions:
        return "Watchlist"
    return "Status"


def intraday_cycle_fingerprint(report: IntradayReport) -> str:
    """Stable signature of *actionable* content — used to suppress repeat Discord posts."""
    parts: list[str] = []
    for rec in sorted(report.recommendations, key=lambda r: r.symbol):
        # Skip pure holds so price-only churn doesn't re-ping; keep non-idle
        if rec.action in _IDLE_ACTIONS:
            continue
        parts.append(f"{rec.symbol}:{rec.action}")
    for alert in report.notifications:
        sev = (alert.severity or "").lower()
        if sev in {"critical", "high"}:
            parts.append(f"A:{alert.symbol}:{alert.alert_type}:{sev}")
    if report.session.regime_shift:
        parts.append(f"R:{report.session.regime_description}")
    if not parts and report.no_open_positions:
        # Flat book: one fingerprint for "watching" — suppress repeat scout spam
        parts.append("flat")
    elif not parts:
        parts.append("idle")
    return "|".join(parts)


def should_post_intraday_discord(
    report: IntradayReport,
    *,
    cycle: int,
    previous_fingerprint: str | None,
) -> tuple[bool, str]:
    """Post cycle 1 always; later only when the action/alert fingerprint changes."""
    fp = intraday_cycle_fingerprint(report)
    if cycle <= 1:
        return True, fp
    if previous_fingerprint is None:
        return True, fp
    if fp != previous_fingerprint:
        return True, fp
    return False, fp


def format_intraday_discord_title(report: IntradayReport, cycle: int) -> str:
    """Discord post title — action summary, not bare 'cycle N'."""
    summary = summarize_intraday_actions(report)
    # Compact clock from report timestamp when present
    ts = (report.timestamp or "").strip()
    clock = ""
    if ts:
        # Accept '2026-07-16 13:30 UTC' or ISO-ish
        for token in reversed(ts.replace("T", " ").split()):
            if ":" in token and token[0].isdigit():
                clock = token[:5]
                break
    if clock:
        return f"Trading Desk · {summary} · {clock}"
    return f"Trading Desk · {summary}"


def format_intraday_plays(report: IntradayReport, cycle: int) -> str:
    summary = summarize_intraday_actions(report)
    lines = [
        f"**Trading Desk · {summary}** (check #{cycle} · {report.timestamp})",
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
        # Surface non-idle first so pings stay scannable
        active = [r for r in report.recommendations if r.action not in _IDLE_ACTIONS]
        idle = [r for r in report.recommendations if r.action in _IDLE_ACTIONS]
        lines.append("**Position actions:**")
        for rec in active + idle:
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