"""Methods-lab research path: multi-method + swing, no CIO capital decisions.

Used by ``trading_test`` product mode. Produces Discord text + auto_trade_book
export from method confluence (not classic risk/CIO pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class MethodsResearchResult:
    message: str
    symbols: List[str] = field(default_factory=list)
    play_symbols: List[str] = field(default_factory=list)
    multi_results: list = field(default_factory=list)
    swing_plays: int = 0
    multi_plays: int = 0
    export_paths: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    plan_context: Dict[str, Any] = field(default_factory=dict)


def _resolve_symbols(limit: int) -> List[str]:
    try:
        from trading_agent.strategy.swing_scan import resolve_swing_universe

        return resolve_swing_universe(None, limit=limit)
    except Exception:
        pass
    try:
        from trading_agent.odte.top_winners import resolve_data_driven_pool

        pool, _ = resolve_data_driven_pool(max_symbols=limit)
        if pool:
            return [str(s).upper() for s in pool[:limit]]
    except Exception:
        pass
    return ["SPY", "QQQ", "IWM", "NVDA", "AMD", "AAPL", "MSFT", "TSLA", "META", "AMZN"][:limit]


def run_methods_research(
    *,
    symbols: Optional[Sequence[str]] = None,
    limit: int = 20,
    fixture_mode: bool = False,
    export_book: bool = True,
    data_source: str = "yfinance",
) -> MethodsResearchResult:
    """Run combined multi-method + daily swing; export PLAYs when not fixture."""
    syms = [str(s).upper().strip() for s in (symbols or []) if str(s).strip()]
    if not syms:
        syms = _resolve_symbols(limit)
    syms = syms[:limit]
    out = MethodsResearchResult(message="", symbols=list(syms))

    if fixture_mode:
        out.message = (
            f"**Methods lab research (fixture)**\n"
            f"Universe: {', '.join(syms[:12])}{'…' if len(syms) > 12 else ''}\n"
            f"_Live multi-method + swing skipped in fixture mode._\n"
            f"_No CIO decision desk in trading_test._\n"
        )
        out.plan_context = {
            "product": "trading_test",
            "mode": "methods",
            "include_cio": False,
            "top_watchlist": syms,
            "stay_in_cash": True,
            "cash_reason": "fixture methods run — no live exports",
            "opportunities": [],
        }
        return out

    lines = [
        "**Methods lab research** (trading_test — multi-method, **no CIO**)",
        f"Universe: **{len(syms)}** names",
        "",
    ]

    # Multi-method router
    try:
        from trading_agent.strategy.multi_method import (
            MultiMethodConfig,
            evaluate_universe,
            format_multi_method_report,
            write_process_cards_for_plays,
        )

        mcfg = MultiMethodConfig(
            min_method_score=55.0,
            min_play_methods=2,
            bar_period="10d",
            bar_interval="15m",
            data_source=data_source,
            use_htf_bias=True,
        )
        evals = evaluate_universe(syms, cfg=mcfg)
        out.multi_results = evals
        plays = [e for e in evals if e.play and e.decision == "PLAY"]
        out.multi_plays = len(plays)
        out.play_symbols = [e.symbol for e in plays]
        lines.append(format_multi_method_report(evals, cfg=mcfg))
        try:
            write_process_cards_for_plays(evals, update_focus=True, default_size="0.5R")
        except Exception as exc:  # noqa: BLE001
            out.errors.append(f"process cards: {exc}")
        if export_book:
            try:
                from trading_agent.export.multi_method_book import export_multi_method_auto_trade

                book, paths = export_multi_method_auto_trade(
                    evals,
                    merge_desk=False,
                    stay_in_cash=False,
                )
                out.export_paths = [str(p) for p in (paths or [])]
                lines.append("")
                lines.append(
                    f"_auto_trade_book: entries={book.get('entry_count')} "
                    f"export_plays={(book.get('multi_method') or {}).get('play_count')} "
                    f"stay_in_cash={book.get('stay_in_cash')}_"
                )
            except Exception as exc:  # noqa: BLE001
                out.errors.append(f"export: {exc}")
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"multi-method: {exc}")
        lines.append(f"_Multi-method failed: {exc}_")

    # Daily swing companion
    try:
        from trading_agent.strategy.swing_scan import (
            SwingScanConfig,
            format_swing_scan_report,
            scan_swing_universe,
            write_swing_process_cards,
        )

        sc = SwingScanConfig(
            bar_period="1y",
            bar_interval="1d",
            data_source=data_source,
            min_score=58.0,
            max_symbols=len(syms),
            use_rs=True,
        )
        swings = scan_swing_universe(syms, cfg=sc)
        swing_plays = [c for c in swings if c.play]
        out.swing_plays = len(swing_plays)
        for c in swing_plays:
            if c.symbol not in out.play_symbols:
                out.play_symbols.append(c.symbol)
        lines.append("")
        lines.append(format_swing_scan_report(swings, cfg=sc))
        try:
            write_swing_process_cards(swings, update_focus=False, default_size="1R")
        except Exception as exc:  # noqa: BLE001
            out.errors.append(f"swing cards: {exc}")
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"swing: {exc}")
        lines.append(f"_Swing-scan failed: {exc}_")

    if out.errors:
        lines.append("")
        lines.append("**Errors:** " + "; ".join(out.errors[:6]))

    lines.append("")
    lines.append(
        f"**Summary:** multi PLAY={out.multi_plays} · swing PLAY={out.swing_plays} · "
        f"union watch={len(out.play_symbols)} · **CIO desk: off**"
    )
    out.message = "\n".join(lines)

    out.plan_context = {
        "product": "trading_test",
        "mode": "methods",
        "include_cio": False,
        "top_watchlist": out.play_symbols or syms[:15],
        "methods_universe": syms,
        "multi_method_plays": out.multi_plays,
        "swing_plays": out.swing_plays,
        "stay_in_cash": out.multi_plays == 0 and out.swing_plays == 0,
        "cash_reason": (
            ""
            if (out.multi_plays or out.swing_plays)
            else "No multi-method or swing PLAY names at current gates"
        ),
        "opportunities": [],
        "bias_narrative": "methods lab — multi-method confluence (no CIO)",
        "market_environment_score": 50.0,
    }
    return out
