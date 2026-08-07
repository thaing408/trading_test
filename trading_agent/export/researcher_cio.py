"""Feed researcher lists into CIO decision inputs.

Sources (local books, typically pulled from production host):
- watchlist_playlist.json  → hard gates playlist (human + desk)
- gap_screener_book.json    → continuation bias names

Rules:
- Every symbol from those lists is present on the CIO board for evaluation.
- Existing Phase-1 ranked opps get researcher tags + confidence boost.
- Names missing from Phase-1 are appended as researcher-origin candidates
  (still subject to full CIO gates — not auto-approve).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from trading_agent.cio.models import PhaseContext, TradeCandidate
from trading_agent.export.gap_book import continuation_symbols, load_gap_book, gap_meta_for_symbol
from trading_agent.export.playlist_book import load_playlist_book, playlist_candidate_symbols


def researcher_cio_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_RESEARCHER_CIO", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _playlist_rows() -> List[Dict[str, Any]]:
    book = load_playlist_book()
    rows: List[Dict[str, Any]] = []
    for row in book.get("candidates") or []:
        if isinstance(row, dict) and row.get("symbol"):
            rows.append(row)
        elif isinstance(row, str) and row.strip():
            rows.append({"symbol": row.strip().upper()})
    return rows


def _sector(symbol: str) -> str:
    from trading_agent.cio.loader import _SECTOR_BY_SYMBOL

    return _SECTOR_BY_SYMBOL.get(symbol.upper(), "Unknown")


def _candidate_from_playlist(row: Dict[str, Any], rank: int) -> TradeCandidate:
    symbol = str(row.get("symbol") or "").upper().strip()
    m = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    price = float(m.get("price") or row.get("price") or 100.0)
    score = float(row.get("score") or 60.0)
    conf = max(45.0, min(78.0, 50.0 + score * 0.25))
    # Directional bias from RS if present
    rs = float(m.get("rs_20") or 1.0)
    direction = "Bullish" if rs >= 1.0 else "Bearish"
    strategy = "Debit Call Spread" if direction == "Bullish" else "Debit Put Spread"
    stop = price * (0.97 if direction == "Bullish" else 1.03)
    target = price * (1.04 if direction == "Bullish" else 0.96)
    risk = abs(price - stop) * 100  # notional-ish placeholder
    reward = abs(target - price) * 100
    return TradeCandidate(
        symbol=symbol,
        direction=direction,
        strategy=strategy,
        entry_price=round(price, 2),
        strike_prices=[round(price, 2), round(price * (1.05 if direction == "Bullish" else 0.95), 2)],
        expiration="~14-30 DTE",
        profit_target=round(target, 2),
        stop_loss=round(stop, 2),
        maximum_risk=max(risk, 50.0),
        maximum_reward=max(reward, 80.0),
        probability_of_success=0.48,
        confidence_score=conf,
        primary_catalyst="researcher momentum playlist",
        catalyst_type="sector_momentum",
        technical_summary=(
            f"Researcher playlist pass score={score:.0f} RS={rs:.2f} "
            f"ADR={m.get('adr_pct', 'n/a')} vol={m.get('vol_ratio', 'n/a')}×"
        ),
        technical_confirmations=[
            "researcher:playlist",
            "gates:momentum_playlist",
            f"rs_20:{rs:.2f}",
        ],
        options_summary="Subject to live chain at execution; playlist pre-screened weekly opts",
        open_interest=2000,
        daily_options_volume=2000,
        bid_ask_spread_pct=3.0,
        iv_rank=40.0,
        expected_move_pct=float(m.get("adr_pct") or 3.0),
        probability_of_profit=0.48,
        liquidity_score=55.0,
        sector=_sector(symbol),
        correlation_group=_sector(symbol),
        phase1_rank=rank,
        setup_grade="B",
        grade_score=score,
        hold_style="swing",
        market_data_source="researcher_playlist",
    )


def _candidate_from_gap(symbol: str, meta: Dict[str, Any], rank: int) -> TradeCandidate:
    bias = str(meta.get("continuation_bias") or "none").lower()
    direction = "Bullish" if bias == "long" else "Bearish" if bias == "short" else "Neutral"
    price = float(meta.get("last_price") or 100.0)
    gap_pct = float(meta.get("gap_pct") or 0.0)
    conf = max(48.0, min(72.0, 50.0 + abs(gap_pct)))
    strategy = (
        "Debit Call Spread"
        if direction == "Bullish"
        else "Debit Put Spread"
        if direction == "Bearish"
        else "Iron Condor"
    )
    stop = price * (0.96 if direction == "Bullish" else 1.04 if direction == "Bearish" else 0.97)
    target = price * (1.05 if direction == "Bullish" else 0.95 if direction == "Bearish" else 1.02)
    return TradeCandidate(
        symbol=symbol,
        direction=direction if direction != "Neutral" else "Bullish",
        strategy=strategy,
        entry_price=round(price, 2),
        strike_prices=[round(price, 2), round(price * 1.04, 2)],
        expiration="~14-30 DTE",
        profit_target=round(target, 2),
        stop_loss=round(stop, 2),
        maximum_risk=max(abs(price - stop) * 100, 50.0),
        maximum_reward=max(abs(target - price) * 100, 80.0),
        probability_of_success=0.47,
        confidence_score=conf,
        primary_catalyst=f"gap continuation {meta.get('direction')} {gap_pct}%",
        catalyst_type="technical_breakout",
        technical_summary=str(meta.get("notes") or f"Gap screener continuation {bias}"),
        technical_confirmations=[
            "researcher:gap_book",
            "gap_continuation_4d",
            f"gap_state:{meta.get('state')}",
            f"bias:{bias}",
        ],
        options_summary="Gap handoff — verify chain liquidity at CIO sizing",
        open_interest=2000,
        daily_options_volume=2000,
        bid_ask_spread_pct=3.0,
        iv_rank=45.0,
        expected_move_pct=max(abs(gap_pct), 2.5),
        probability_of_profit=0.47,
        liquidity_score=55.0,
        sector=_sector(symbol),
        correlation_group=_sector(symbol),
        phase1_rank=rank,
        setup_grade="B",
        grade_score=float(meta.get("rank_score") or conf),
        hold_style="swing",
        market_data_source="researcher_gap",
    )


def collect_researcher_cio_candidates(
    *,
    start_rank: int = 100,
) -> Tuple[List[TradeCandidate], Dict[str, str]]:
    """Build CIO candidates from local researcher books + provenance map."""
    if not researcher_cio_enabled():
        return [], {}

    out: List[TradeCandidate] = []
    provenance: Dict[str, str] = {}
    rank = start_rank
    seen: Set[str] = set()

    for row in _playlist_rows():
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(_candidate_from_playlist(row, rank))
        provenance[sym] = "playlist"
        rank += 1

    gap_book = load_gap_book()
    for sym in sorted(continuation_symbols(gap_book)):
        if sym in seen:
            # already playlist — keep playlist provenance, still mark gap
            provenance[sym] = provenance.get(sym, "playlist") + "+gap"
            continue
        meta = gap_meta_for_symbol(sym, gap_book) or {}
        if str(meta.get("state") or "") != "continuation":
            continue
        seen.add(sym)
        out.append(_candidate_from_gap(sym, meta, rank))
        provenance[sym] = "gap_continuation"
        rank += 1

    return out, provenance


def merge_researcher_into_cio_candidates(
    candidates: List[TradeCandidate],
    context: Optional[PhaseContext] = None,
) -> Tuple[List[TradeCandidate], PhaseContext | None, Dict[str, Any]]:
    """Ensure researcher list is on the CIO board; tag + boost existing names."""
    meta: Dict[str, Any] = {
        "enabled": researcher_cio_enabled(),
        "playlist_symbols": playlist_candidate_symbols(),
        "gap_continuation": sorted(continuation_symbols()),
        "appended": [],
        "boosted": [],
    }
    if not researcher_cio_enabled():
        return candidates, context, meta

    research_cands, provenance = collect_researcher_cio_candidates(
        start_rank=max((c.phase1_rank for c in candidates), default=0) + 100
    )
    by_sym = {c.symbol.upper(): c for c in candidates}
    boost = float(os.getenv("TRADING_AGENT_RESEARCHER_CIO_BOOST", "8") or 8)

    for rc in research_cands:
        sym = rc.symbol.upper()
        if sym in by_sym:
            c = by_sym[sym]
            for tag in rc.technical_confirmations:
                if tag not in c.technical_confirmations:
                    c.technical_confirmations.append(tag)
            # provenance catalyst note (do not wipe stronger catalyst)
            if "researcher" not in (c.primary_catalyst or "").lower():
                c.primary_catalyst = f"{c.primary_catalyst}; researcher:{provenance.get(sym, 'list')}"
            if not c.catalyst_type or c.catalyst_type == "technical":
                # keep valid institutional catalyst types
                if "playlist" in provenance.get(sym, ""):
                    c.catalyst_type = "sector_momentum"
                elif "gap" in provenance.get(sym, ""):
                    c.catalyst_type = "technical_breakout"
            c.confidence_score = min(100.0, float(c.confidence_score or 0) + boost)
            if not c.market_data_source or c.market_data_source == "unknown":
                c.market_data_source = rc.market_data_source
            meta["boosted"].append(sym)
        else:
            candidates.append(rc)
            by_sym[sym] = rc
            meta["appended"].append(sym)

    if context is not None:
        # Extend research board so CIO report shows researcher origin
        lines = list(context.research_board_lines or [])
        sources = dict(context.research_data_sources or {})
        for sym, prov in provenance.items():
            sources[sym] = sources.get(sym) or f"researcher:{prov}"
        if meta["appended"] or meta["boosted"]:
            lines.insert(
                0,
                "_Researcher feed (playlist + gap continuation) merged into CIO board — "
                "full gates still apply; not auto-approve._",
            )
            if meta["appended"]:
                lines.append(
                    f"**Researcher appended:** {', '.join(meta['appended'][:20])}"
                )
            if meta["boosted"]:
                lines.append(
                    f"**Researcher boost (already in Phase-1):** {', '.join(meta['boosted'][:20])}"
                )
        context.research_board_lines = lines
        context.research_data_sources = sources
        note = (context.research_ohlcv_note or "").strip()
        add = (
            " Researcher lists (playlist/gap) are decision inputs via local sync books "
            "pulled from production host."
        )
        if "Researcher lists" not in note:
            context.research_ohlcv_note = (note + add).strip()

    meta["provenance"] = provenance
    return candidates, context, meta
