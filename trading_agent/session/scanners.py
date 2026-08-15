"""Desk scanner pack: swing-scan (+ optional multi-method) at research / evening.

Called from session orchestrator:
  - RESEARCH phase (05:00 PT) — once with the research watchlist
  - EVENING_SCAN phase (18:00 ET / ~15:00 PT) — post-close daily re-rank
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class DeskScannerResult:
    slot: str  # research | evening
    swing_text: str = ""
    multi_text: str = ""
    swing_plays: int = 0
    multi_plays: int = 0
    multi_export_entries: int = 0
    multi_export_paths: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    discord_posted: bool = False
    errors: List[str] = field(default_factory=list)

    def combined_message(self) -> str:
        parts = [
            f"**Desk scanners — {self.slot}**",
            f"Universe: {len(self.symbols)} name(s)",
            "",
        ]
        if self.swing_text:
            parts.append(self.swing_text.strip())
            parts.append("")
        if self.multi_text:
            parts.append(self.multi_text.strip())
            parts.append("")
        if self.multi_export_entries:
            parts.append(
                f"_auto_trade_book (multi-method, no CIO required): "
                f"**{self.multi_export_entries}** ENTER row(s)_"
            )
            parts.append("")
        if self.errors:
            parts.append("**Errors:** " + "; ".join(self.errors[:4]))
        return "\n".join(parts).strip() + "\n"


def multi_method_auto_export_enabled() -> bool:
    """When true, export-eligible multi-method PLAYs write auto_trade_book without CIO."""
    return os.getenv("TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def symbols_from_plan_context(
    plan_context: Optional[dict],
    *,
    limit: int = 20,
    fallback: Optional[Sequence[str]] = None,
) -> List[str]:
    """Prefer watchlist / ranked names from research plan context."""
    out: List[str] = []
    ctx = plan_context or {}
    for key in ("top_watchlist", "watchlist", "focus_list", "ranked_symbols"):
        raw = ctx.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        for item in raw:
            if isinstance(item, dict):
                sym = str(item.get("symbol") or item.get("ticker") or "").upper().strip()
            else:
                sym = str(item).upper().strip()
            if sym and sym not in out:
                out.append(sym)
            if len(out) >= limit:
                return out
    # opportunities-style lists
    for key in ("opportunities", "approved_trades", "top_candidates"):
        raw = ctx.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                sym = str(item.get("symbol") or item.get("ticker") or "").upper().strip()
            else:
                sym = str(item).upper().strip()
            if sym and sym not in out:
                out.append(sym)
            if len(out) >= limit:
                return out
    if out:
        return out[:limit]
    if fallback:
        return [str(s).upper() for s in fallback if str(s).strip()][:limit]
    return ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "AMD", "TSLA", "META", "AMZN"][:limit]


def run_desk_scanners(
    *,
    slot: str,
    symbols: Optional[Sequence[str]] = None,
    plan_context: Optional[dict] = None,
    fixture_mode: bool = False,
    post_discord: bool = True,
    limit: int = 20,
    run_multi_method: bool = True,
    min_swing_score: float = 58.0,
    data_source: str = "yfinance",
) -> DeskScannerResult:
    """Run swing-scan and optional multi-method on a shared symbol list."""
    syms = list(symbols) if symbols else symbols_from_plan_context(plan_context, limit=limit)
    if limit > 0:
        syms = syms[:limit]
    result = DeskScannerResult(slot=slot, symbols=list(syms))

    if fixture_mode:
        result.swing_text = (
            f"_Fixture mode: swing-scan skipped ({slot}; would scan "
            f"{', '.join(syms[:8])}{'…' if len(syms) > 8 else ''})_"
        )
        if run_multi_method:
            result.multi_text = f"_Fixture mode: multi-method skipped ({slot})_"
        return result

    # --- Swing (daily) ---
    try:
        from trading_agent.strategy.swing_scan import (
            SwingScanConfig,
            format_swing_scan_discord,
            format_swing_scan_report,
            post_swing_scan_to_discord,
            scan_swing_universe,
            write_swing_process_cards,
        )

        sc = SwingScanConfig(
            bar_period="1y",
            bar_interval="1d",
            data_source=data_source,
            min_score=min_swing_score,
            max_symbols=max(len(syms), 1),
            use_rs=True,
        )
        candidates = scan_swing_universe(syms, cfg=sc)
        plays = [c for c in candidates if c.play]
        result.swing_plays = len(plays)
        # Discord body is compact; keep full report for session log
        result.swing_text = format_swing_scan_report(candidates, cfg=sc)
        try:
            write_swing_process_cards(candidates, update_focus=(slot == "research"), default_size="1R")
        except Exception as card_exc:  # noqa: BLE001
            result.errors.append(f"swing cards: {card_exc}")
        if post_discord:
            posted = post_swing_scan_to_discord(candidates, cfg=sc)
            if posted.get("ok"):
                result.discord_posted = True
            else:
                result.errors.append(f"swing discord: {posted.get('error', 'fail')}")
            # Prefer compact body in combined Discord deliverable
            result.swing_text = format_swing_scan_discord(candidates, cfg=sc)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"swing-scan: {exc}")
        result.swing_text = f"_Swing-scan failed: {exc}_"

    # --- Multi-method (existing router scanners on same names) ---
    if run_multi_method:
        try:
            from trading_agent.strategy.multi_method import (
                MultiMethodConfig,
                evaluate_universe,
                format_multi_method_report,
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
            plays_m = [e for e in evals if e.play]
            result.multi_plays = len(plays_m)
            result.multi_text = format_multi_method_report(evals, cfg=mcfg)

            # P1: multi-method EXPORT → auto_trade_book without CIO approval.
            # Research/CIO capital-preservation stay_in_cash no longer blocks this path.
            # Consumer still applies process gate, OMS limits, and LIVE flags.
            if multi_method_auto_export_enabled() and evals:
                try:
                    from trading_agent.export.multi_method_book import (
                        export_multi_method_auto_trade,
                    )
                    from trading_agent.session.context import default_session_dir
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    pt = ZoneInfo("America/Los_Angeles")
                    session_dir = default_session_dir(datetime.now(pt).date())
                    book, paths = export_multi_method_auto_trade(
                        evals,
                        merge_desk=True,
                        session_dir=session_dir,
                        # Explicit False: do not suppress ENTERs because process
                        # bias is cash from an empty research pass.
                        stay_in_cash=False,
                    )
                    result.multi_export_entries = int(
                        book.get("entry_count") or len(book.get("entries") or [])
                    )
                    result.multi_export_paths = [str(p) for p in (paths or [])]
                    if result.multi_export_entries > 0:
                        try:
                            from trading_agent.runbook.process import (
                                sync_process_bias_from_desk,
                            )

                            sync_process_bias_from_desk(
                                stay_in_cash=False,
                                market_regime="multi-method auto-export",
                                ranked_count=result.multi_export_entries,
                                multi_method_entries=result.multi_export_entries,
                                focus_symbols=[
                                    str(e.get("symbol") or "")
                                    for e in (book.get("entries") or [])
                                    if isinstance(e, dict)
                                ],
                                reason=f"desk scanners multi-method export ({slot})",
                                force=True,
                            )
                        except Exception as bias_exc:  # noqa: BLE001
                            result.errors.append(f"bias after mm export: {bias_exc}")
                except Exception as exp_exc:  # noqa: BLE001
                    result.errors.append(f"multi-method export: {exp_exc}")
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"multi-method: {exc}")
            result.multi_text = f"_Multi-method failed: {exc}_"

    return result
