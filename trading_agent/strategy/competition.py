"""Multi-sleeve competition: all methods score each ticker; best sleeve wins.

Previously ``select_strategy`` returned a single rule-based pick. Now each
qualified name is evaluated by several sleeves; the highest viable score
becomes the trade shape (still subject to books/CIO/rails afterward).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis
from trading_agent.strategy.selector import StrategySelection, select_strategy


@dataclass
class SleeveScore:
    """One method's view of a ticker."""

    sleeve_id: str
    sleeve_name: str
    viable: bool
    score: float  # 0–100 competition score
    strategy: Optional[StrategySelection] = None
    setup_id: str = ""
    notes: str = ""
    # Optional geometry overrides (else ranker uses grade geometry from strategy)
    entry_price: float = 0.0
    stop_loss: float = 0.0
    profit_target: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sleeve_id": self.sleeve_id,
            "sleeve_name": self.sleeve_name,
            "viable": self.viable,
            "score": round(self.score, 2),
            "setup_id": self.setup_id,
            "strategy": self.strategy.name if self.strategy else "",
            "direction": self.strategy.direction if self.strategy else "",
            "notes": self.notes,
        }


@dataclass
class CompetitionResult:
    """Winner + full scoreboard for one ticker."""

    symbol: str
    winner: Optional[SleeveScore]
    scoreboard: List[SleeveScore] = field(default_factory=list)

    def scoreboard_summary(self, top_n: int = 5) -> str:
        parts = []
        for s in self.scoreboard[:top_n]:
            mark = "WIN" if self.winner and s.sleeve_id == self.winner.sleeve_id else "—"
            parts.append(
                f"{mark} {s.sleeve_id}={s.score:.0f}"
                f"{'' if s.viable else '(out)'}"
            )
        return "; ".join(parts)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _base_strategy(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    price: float,
) -> StrategySelection:
    return select_strategy(technical, options, price)


def _strategy_variants(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    price: float,
) -> List[Tuple[str, StrategySelection, str]]:
    """Named strategy sleeves derived from market state (compete head-to-head)."""
    variants: List[Tuple[str, StrategySelection, str]] = []
    primary = _base_strategy(technical, options, price)
    variants.append(("desk_primary", primary, "selector_primary"))

    iv_high = options.iv_rank >= 55
    iv_low = options.iv_rank <= 40
    bullish = technical.trend == "uptrend"
    bearish = technical.trend == "downtrend"
    aligned = (technical.timeframe_alignment or "").lower()

    # Premium / credit family
    if iv_high:
        variants.append(
            (
                "premium_iron_condor",
                StrategySelection(
                    name="Iron Condor",
                    strike_prices=[
                        round(price * 0.94, 2),
                        round(price * 0.97, 2),
                        round(price * 1.03, 2),
                        round(price * 1.06, 2),
                    ],
                    expiration_days=30,
                    bias="neutral",
                    direction="Neutral",
                ),
                "options_credit_iron_condor",
            )
        )
        if bullish:
            variants.append(
                (
                    "premium_bull_put",
                    StrategySelection(
                        name="Bull Put Credit Spread",
                        strike_prices=[round(price * 0.97, 2), round(price * 0.92, 2)],
                        expiration_days=30,
                        bias="bullish",
                        direction="Bullish",
                    ),
                    "options_credit_bull_put",
                )
            )
            variants.append(
                (
                    "premium_covered_call",
                    StrategySelection(
                        name="Covered Call",
                        strike_prices=[round(price * 1.05, 2)],
                        expiration_days=30,
                        bias="bullish",
                        direction="Bullish",
                    ),
                    "options_credit_covered_call",
                )
            )
        if bearish:
            variants.append(
                (
                    "premium_bear_call",
                    StrategySelection(
                        name="Bear Call Credit Spread",
                        strike_prices=[round(price * 1.03, 2), round(price * 1.08, 2)],
                        expiration_days=30,
                        bias="bearish",
                        direction="Bearish",
                    ),
                    "options_credit_bear_call",
                )
            )

    # Debit / directional family
    if iv_low or bullish:
        variants.append(
            (
                "debit_call_spread",
                StrategySelection(
                    name="Debit Spread",
                    strike_prices=[round(price, 2), round(price * 1.05, 2)],
                    expiration_days=45,
                    bias="bullish",
                    direction="Bullish",
                ),
                "options_debit_call_spread",
            )
        )
    if iv_low or bearish:
        variants.append(
            (
                "debit_put_spread",
                StrategySelection(
                    name="Debit Spread",
                    strike_prices=[round(price, 2), round(price * 0.95, 2)],
                    expiration_days=45,
                    bias="bearish",
                    direction="Bearish",
                ),
                "options_debit_put_spread",
            )
        )

    # Breakout / pullback directional long option
    if bullish and "aligned" in aligned:
        variants.append(
            (
                "momentum_long_call",
                StrategySelection(
                    name="Long Call",
                    strike_prices=[round(price, 2)],
                    expiration_days=21,
                    bias="bullish",
                    direction="Bullish",
                ),
                "momentum_breakout",
            )
        )
    if bearish and "aligned" in aligned:
        variants.append(
            (
                "momentum_long_put",
                StrategySelection(
                    name="Long Put",
                    strike_prices=[round(price, 2)],
                    expiration_days=21,
                    bias="bearish",
                    direction="Bearish",
                ),
                "momentum_breakdown",
            )
        )

    # de-dupe by (name, direction, setup)
    seen = set()
    out: List[Tuple[str, StrategySelection, str]] = []
    for sid, st, setup in variants:
        key = (st.name, st.direction, setup)
        if key in seen:
            continue
        seen.add(key)
        out.append((sid, st, setup))
    return out


def _score_desk_options(
    sleeve_id: str,
    strategy: StrategySelection,
    setup_id: str,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
) -> SleeveScore:
    """Score classic options structure against tape + IV."""
    score = 40.0
    notes = []
    bullish = technical.trend == "uptrend"
    bearish = technical.trend == "downtrend"
    iv = float(options.iv_rank or 0)
    pop = float(options.probability_of_profit or 0)

    # Direction fit
    if strategy.direction == "Bullish" and bullish:
        score += 15
        notes.append("dir=bull fit")
    elif strategy.direction == "Bearish" and bearish:
        score += 15
        notes.append("dir=bear fit")
    elif strategy.direction == "Neutral" and not bullish and not bearish:
        score += 12
        notes.append("dir=neutral fit")
    elif strategy.direction == "Neutral" and (bullish or bearish):
        score -= 8
        notes.append("neutral vs trend")
    else:
        score -= 12
        notes.append("dir mismatch")

    # IV fit for premium vs debit
    name = strategy.name.lower()
    is_credit = any(x in name for x in ("condor", "credit", "covered call", "cash secured"))
    is_debit = any(x in name for x in ("debit", "long call", "long put"))
    if is_credit and iv >= 55:
        score += 18
        notes.append("IV rich→credit")
    elif is_credit and iv < 40:
        score -= 15
        notes.append("IV poor for credit")
    if is_debit and iv <= 40:
        score += 15
        notes.append("IV lean→debit")
    elif is_debit and iv >= 65:
        score -= 10
        notes.append("IV rich hurts debit")

    # POP / liquidity
    score += _clamp(pop * 20, 0, 15)
    score += _clamp((options.liquidity_score or 50) / 10.0, 0, 10)
    score += _clamp((technical.score or 50) / 10.0 - 3, -5, 12)

    # MTF
    align = (technical.timeframe_alignment or "").lower()
    if "aligned" in align and strategy.direction != "Neutral":
        score += 8
        notes.append("MTF aligned")
    if align == "conflicting":
        score -= 10
        notes.append("MTF conflict")

    # RVOL
    rvol = float(candidate.relative_volume or 1.0)
    if rvol >= 1.5:
        score += 5

    viable = score >= 45
    return SleeveScore(
        sleeve_id=sleeve_id,
        sleeve_name=f"Options:{strategy.name}",
        viable=viable,
        score=_clamp(score),
        strategy=strategy,
        setup_id=setup_id,
        notes="; ".join(notes)[:200],
    )


def _score_gap_sleeve(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    price: float,
) -> SleeveScore:
    """Gap continuation sleeve — competes when gap + volume present."""
    gap = abs(float(candidate.gap_pct or 0))
    rvol = float(candidate.relative_volume or 0)
    score = 20.0
    notes = []
    viable = False
    strategy = None
    setup_id = "gap_continuation"

    if gap >= 1.0 and rvol >= 1.3:
        viable = True
        score = 50 + min(25, gap * 3) + min(15, (rvol - 1) * 10)
        if float(candidate.gap_pct or 0) > 0 and technical.trend != "downtrend":
            strategy = StrategySelection(
                name="Debit Spread",
                strike_prices=[round(price, 2), round(price * 1.04, 2)],
                expiration_days=14,
                bias="bullish",
                direction="Bullish",
            )
            notes.append(f"gap_up {gap:.1f}% rvol={rvol:.1f}")
            score += 5 if technical.trend == "uptrend" else 0
        elif float(candidate.gap_pct or 0) < 0 and technical.trend != "uptrend":
            strategy = StrategySelection(
                name="Debit Spread",
                strike_prices=[round(price, 2), round(price * 0.96, 2)],
                expiration_days=14,
                bias="bearish",
                direction="Bearish",
            )
            notes.append(f"gap_down {gap:.1f}% rvol={rvol:.1f}")
        else:
            viable = False
            score = 30
            notes.append("gap vs trend conflict")
    else:
        notes.append("no material gap/rvol")

    # Optional soft boost if gap book would tag
    try:
        from trading_agent.export.gap_book import apply_gap_boost_to_opportunity_fields

        tags, _, note = apply_gap_boost_to_opportunity_fields(
            symbol=candidate.symbol,
            method_tags=[],
            auto_trade_eligible=True,
        )
        if "gap_continuation_4d" in tags:
            viable = True
            score = max(score, 72.0)
            notes.append(note or "gap_4d")
            if strategy is None and technical.trend == "uptrend":
                strategy = StrategySelection(
                    name="Debit Spread",
                    strike_prices=[round(price, 2), round(price * 1.04, 2)],
                    expiration_days=14,
                    bias="bullish",
                    direction="Bullish",
                )
    except Exception:
        pass

    if strategy is None:
        strategy = _base_strategy(technical, options, price)
        if not viable:
            score = min(score, 40)

    return SleeveScore(
        sleeve_id="gap_continuation",
        sleeve_name="Gap continuation",
        viable=viable and strategy is not None,
        score=_clamp(score),
        strategy=strategy,
        setup_id=setup_id,
        notes="; ".join(notes)[:200],
    )


def _score_momentum_rs(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    price: float,
) -> SleeveScore:
    """Relative strength / momentum sleeve."""
    score = 35.0
    notes = []
    rs = float(getattr(candidate, "relative_strength", 0) or 0)
    # institutional_score often proxies quality/RS in screener
    inst = float(candidate.institutional_score or 50)
    rvol = float(candidate.relative_volume or 1)
    bullish = technical.trend == "uptrend"
    bearish = technical.trend == "downtrend"
    align = (technical.timeframe_alignment or "").lower()

    score += _clamp((inst - 50) / 2.5, -10, 20)
    if rvol >= 1.5:
        score += 8
    if "aligned_bullish" in align and bullish:
        score += 15
        notes.append("aligned bull RS")
    elif "aligned_bearish" in align and bearish:
        score += 12
        notes.append("aligned bear RS")
    if bullish:
        score += 8
    if technical.breakout_state in ("breakout", "breakdown"):
        score += 10
        notes.append(f"breakout_state={technical.breakout_state}")

    viable = score >= 55 and (bullish or bearish)
    if bullish:
        strategy = StrategySelection(
            name="Long Call" if options.iv_rank <= 50 else "Debit Spread",
            strike_prices=[round(price, 2)]
            if options.iv_rank <= 50
            else [round(price, 2), round(price * 1.05, 2)],
            expiration_days=30,
            bias="bullish",
            direction="Bullish",
        )
        setup_id = "momentum_rs_long"
    elif bearish:
        strategy = StrategySelection(
            name="Long Put" if options.iv_rank <= 50 else "Debit Spread",
            strike_prices=[round(price, 2)]
            if options.iv_rank <= 50
            else [round(price, 2), round(price * 0.95, 2)],
            expiration_days=30,
            bias="bearish",
            direction="Bearish",
        )
        setup_id = "momentum_rs_short"
    else:
        strategy = _base_strategy(technical, options, price)
        setup_id = "momentum_rs_flat"
        viable = False
        notes.append("no directional trend")

    return SleeveScore(
        sleeve_id="momentum_rs",
        sleeve_name="Momentum / RS",
        viable=viable,
        score=_clamp(score),
        strategy=strategy,
        setup_id=setup_id,
        notes="; ".join(notes)[:200],
    )


def _score_orb_vwap_proxy(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    price: float,
) -> SleeveScore:
    """Daily proxy for ORB+VWAP (true OR needs 15m; use range + MA as stand-in)."""
    score = 30.0
    notes = ["daily_proxy"]
    support = float(technical.support or 0)
    resistance = float(technical.resistance or 0)
    bullish = technical.trend == "uptrend"
    # Treat breakout above resistance with trend as ORB-long proxy
    near_break = resistance > 0 and price >= resistance * 0.995
    near_fail = support > 0 and price <= support * 1.005
    ma_ok = technical.ma_alignment in ("bullish", "aligned", "up") or bullish

    if near_break and bullish and ma_ok:
        score = 68
        notes.append("break resistance + trend")
        strategy = StrategySelection(
            name="Debit Spread",
            strike_prices=[round(price, 2), round(price * 1.03, 2)],
            expiration_days=10,
            bias="bullish",
            direction="Bullish",
        )
        viable = True
        setup_id = "orb_vwap_long_proxy"
    elif near_fail and technical.trend == "downtrend":
        score = 62
        notes.append("lose support + downtrend")
        strategy = StrategySelection(
            name="Debit Spread",
            strike_prices=[round(price, 2), round(price * 0.97, 2)],
            expiration_days=10,
            bias="bearish",
            direction="Bearish",
        )
        viable = True
        setup_id = "orb_vwap_short_proxy"
    else:
        strategy = _base_strategy(technical, options, price)
        viable = False
        setup_id = "orb_vwap_none"
        notes.append("no ORB proxy trigger")

    if float(candidate.relative_volume or 0) >= 1.5 and viable:
        score += 8

    return SleeveScore(
        sleeve_id="orb_vwap",
        sleeve_name="ORB+VWAP proxy",
        viable=viable,
        score=_clamp(score),
        strategy=strategy,
        setup_id=setup_id,
        notes="; ".join(notes)[:200],
    )


def _score_mean_reversion(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    price: float,
) -> SleeveScore:
    """RSI/mean-reversion sleeve when extended against longer trend."""
    score = 25.0
    notes = []
    mom = (technical.momentum or "").lower()
    rsi_proxy = 50.0
    # technical may expose rsi
    rsi = float(getattr(technical, "rsi", 0) or 0)
    if rsi:
        rsi_proxy = rsi
    elif "overbought" in mom:
        rsi_proxy = 72
    elif "oversold" in mom:
        rsi_proxy = 28

    viable = False
    strategy = _base_strategy(technical, options, price)
    setup_id = "mean_reversion"

    if rsi_proxy >= 70 and technical.trend != "uptrend":
        viable = True
        score = 58 + min(15, rsi_proxy - 70)
        strategy = StrategySelection(
            name="Bear Call Credit Spread" if options.iv_rank >= 45 else "Debit Spread",
            strike_prices=[round(price * 1.02, 2), round(price * 1.06, 2)],
            expiration_days=21,
            bias="bearish",
            direction="Bearish",
        )
        notes.append(f"overbought rsi~{rsi_proxy:.0f}")
        setup_id = "mean_reversion_fade_high"
    elif rsi_proxy <= 30 and technical.trend != "downtrend":
        viable = True
        score = 58 + min(15, 30 - rsi_proxy)
        strategy = StrategySelection(
            name="Bull Put Credit Spread" if options.iv_rank >= 45 else "Debit Spread",
            strike_prices=[round(price * 0.98, 2), round(price * 0.94, 2)],
            expiration_days=21,
            bias="bullish",
            direction="Bullish",
        )
        notes.append(f"oversold rsi~{rsi_proxy:.0f}")
        setup_id = "mean_reversion_fade_low"
    else:
        notes.append("not extended")

    return SleeveScore(
        sleeve_id="mean_reversion",
        sleeve_name="Mean reversion",
        viable=viable,
        score=_clamp(score),
        strategy=strategy,
        setup_id=setup_id,
        notes="; ".join(notes)[:200],
    )


def compete_sleeves(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    *,
    min_score: float = 45.0,
) -> CompetitionResult:
    """Run all sleeves; return winner (highest viable score) + full scoreboard."""
    price = float(candidate.price or 0) or 1.0
    board: List[SleeveScore] = []

    # 1) All options strategy variants
    for sleeve_id, strategy, setup_id in _strategy_variants(technical, options, price):
        board.append(
            _score_desk_options(
                sleeve_id, strategy, setup_id, technical, options, candidate
            )
        )

    # 2) Structural / factor sleeves
    board.append(_score_gap_sleeve(technical, options, candidate, price))
    board.append(_score_momentum_rs(technical, options, candidate, price))
    board.append(_score_orb_vwap_proxy(technical, options, candidate, price))
    board.append(_score_mean_reversion(technical, options, candidate, price))

    board.sort(key=lambda s: (s.viable, s.score), reverse=True)

    winner = None
    for s in board:
        if s.viable and s.score >= min_score and s.strategy is not None:
            winner = s
            break
    # Fallback: best score even if slightly below min (still rank for research)
    if winner is None and board:
        best = board[0]
        if best.strategy is not None and best.score >= min_score - 10:
            winner = best
            winner.notes = (winner.notes + "; soft_winner").strip("; ")

    return CompetitionResult(symbol=candidate.symbol, winner=winner, scoreboard=board)


def select_strategy_competitive(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
) -> Tuple[StrategySelection, str, CompetitionResult]:
    """Drop-in enrichment: strategy + setup_id + competition metadata."""
    result = compete_sleeves(candidate, technical, options)
    if result.winner and result.winner.strategy:
        return result.winner.strategy, result.winner.setup_id, result
    # Ultimate fallback
    st = select_strategy(technical, options, float(candidate.price or 1))
    return st, "desk_fallback", result
