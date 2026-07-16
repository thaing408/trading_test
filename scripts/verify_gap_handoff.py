"""Verify researcher gap book is loaded and applied to auto-trade decisions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure package import when run from scripts/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trading_agent.export.auto_trade_book import build_auto_trade_book
from trading_agent.export.gap_book import (
    apply_gap_boost_to_opportunity_fields,
    continuation_symbols,
    gap_book_paths,
    load_gap_book,
)
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)


def _tech(sym: str) -> TechnicalAnalysis:
    return TechnicalAnalysis(
        symbol=sym,
        trend="uptrend",
        rsi=58,
        macd_signal="bullish",
        adx=28,
        atr=2.0,
        bollinger_position="upper",
        support=90,
        resistance=100,
        relative_strength=5,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=72,
        breakout_state="breakout",
        momentum="bullish",
    )


def _opt(sym: str) -> OptionsMetrics:
    return OptionsMetrics(
        symbol=sym,
        implied_volatility=30,
        iv_rank=45,
        iv_percentile=45,
        expected_move_pct=3,
        delta=0.4,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=80,
        probability_of_profit=0.55,
    )


def _opp(sym: str, *, grade: str = "A", eligible: bool = True) -> TradeOpportunity:
    return TradeOpportunity(
        rank=1,
        symbol=sym,
        strategy="Bull Put Credit Spread",
        entry_price=100,
        strike_prices=[97, 92],
        expiration="2026-08-15",
        profit_target=108,
        stop_loss=95,
        maximum_risk=150,
        maximum_reward=300,
        probability_of_success=0.55,
        confidence_score=75,
        supporting_reasons=["verify"],
        technical=_tech(sym),
        options=_opt(sym),
        direction="Bullish",
        setup_grade=grade,
        grade_score=80,
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=eligible,
        fundamental_score=60,
        combined_quality_score=70,
        defined_risk=True,
        method_tags=[],
        stop_basis="lfd",
        target_basis="measured_move",
        geometry_source="hybrid",
        lfd_level=95,
        breakout_level=99,
    )


def main() -> int:
    print("=== Gap book search paths ===")
    for p in gap_book_paths():
        print(f"  {p}  exists={p.is_file()}")

    book = load_gap_book()
    if not book:
        print("FAIL: no gap_screener_book.json found — researcher has not written a book yet")
        return 2

    cont = sorted(continuation_symbols(book))
    print(f"\n=== Loaded book as_of={book.get('as_of')} ===")
    print(f"continuation symbols ({len(cont)}): {cont}")
    print(f"candidates: {len(book.get('candidates') or [])}")

    print("\n=== Per-symbol gap decision (boost layer) ===")
    for sym in cont[:20]:
        tags, elig, note = apply_gap_boost_to_opportunity_fields(
            symbol=sym,
            method_tags=["checklist_edge"],
            auto_trade_eligible=True,
            book=book,
        )
        print(f"  {sym}: TRADE_BIAS=continuation tags={tags}")
        print(f"         {note}")

    # Build a synthetic plan mixing continuation + non-gap names
    cont_sym = cont[0] if cont else "IBM"
    opps = [
        _opp(cont_sym, grade="A", eligible=True),
        _opp("MSFT", grade="A", eligible=True),  # likely not in gap continuation
    ]
    plan = DailyTradingPlan(
        date="2026-07-16",
        overall_market_bias="Bullish",
        market_environment_score=70,
        top_watchlist=[cont_sym, "MSFT"],
        ranked_opportunities=opps,
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    built = build_auto_trade_book(
        plan,
        min_grade="B",
        min_fundamental_score=0,
        min_quality_score=0,
    )
    print("\n=== Synthetic auto_trade_book (prove handoff tagging) ===")
    print(f"entry_count={built.get('entry_count')} stay_in_cash={built.get('stay_in_cash')}")
    for e in built.get("entries") or []:
        print(
            f"  ENTER {e.get('symbol')} gap_continuation={e.get('gap_continuation')} "
            f"tags={e.get('method_tags')} boost={e.get('priority_boost')}"
        )
        if e.get("gap_screener"):
            print(f"         gap_screener: {e.get('gap_screener')}")
    print(f"rejected_sample: {(built.get('rejected_incomplete') or [])[:8]}")

    # Live desk book
    atb = Path.home() / ".trading_agent" / "sync" / "auto_trade_book.json"
    print("\n=== Live desk auto_trade_book.json ===")
    if not atb.is_file():
        print("  missing")
        return 0
    live = json.loads(atb.read_text(encoding="utf-8"))
    print(
        f"  generated_at={live.get('generated_at')} entries={live.get('entry_count')} "
        f"stay_in_cash={live.get('stay_in_cash')}"
    )
    gap_hits = 0
    for e in live.get("entries") or []:
        tags = e.get("method_tags") or []
        if e.get("gap_continuation") or "gap_continuation_4d" in tags or e.get("gap_screener"):
            gap_hits += 1
            print(f"  HIT {e.get('symbol')} tags={tags} note={e.get('gap_screener')}")
    if gap_hits == 0:
        print(
            "  No gap tags on live ENTER rows. "
            "Either stay-in-cash (0 entries) or book was written before gap handoff / no overlap."
        )
        print(f"  gap book as_of={book.get('as_of')} vs auto_trade generated_at={live.get('generated_at')}")
        print(f"  watchlist sample: {(live.get('watchlist') or [])[:10]}")
        # Overlap watchlist with continuation?
        watch = {str(s).upper() for s in (live.get("watchlist") or [])}
        overlap = watch & set(cont)
        print(f"  watchlist ∩ continuation = {sorted(overlap) or '∅'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
