"""Investopedia top technical-analysis books → auto-trade mechanisms.

Source (updated list of 7 classics):
https://www.investopedia.com/articles/personal-finance/090916/top-5-books-learn-technical-analysis.asp

Overlap with existing modules is intentional (thin wrappers + confluence):
  - O'Neil → also smb_books.oneil_can_slim_proxy
  - Shannon → discipline/mtf_gate.py
  - Candles → analysis/patterns.py (Nison gate uses those fields)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Sequence


INVESTOPEDIA_TA_BOOKS: tuple[dict[str, str], ...] = (
    {
        "rank": "1",
        "title": "Getting Started in Technical Analysis",
        "author": "Jack Schwager",
        "mechanism": "schwager_plan_entry_exit",
        "principle": "Defined entry, exit, stop, and system rules before risk",
    },
    {
        "rank": "2",
        "title": "Technical Analysis Explained",
        "author": "Martin Pring",
        "mechanism": "pring_trend_volume",
        "principle": "Trend + volume confirmation; market mechanics before signals",
    },
    {
        "rank": "3",
        "title": "Technical Analysis of the Financial Markets",
        "author": "John Murphy",
        "mechanism": "murphy_indicator_confluence",
        "principle": "Multi-indicator confluence (MA/MACD/RSI) with trend",
    },
    {
        "rank": "4",
        "title": "How to Make Money in Stocks",
        "author": "William O'Neil",
        "mechanism": "oneil_can_slim_proxy",
        "principle": "Participation (RVOL) + structure (see smb_books)",
    },
    {
        "rank": "5",
        "title": "Japanese Candlestick Charting Techniques",
        "author": "Steve Nison",
        "mechanism": "nison_candle_alignment",
        "principle": "Candles must not strongly oppose trade direction",
    },
    {
        "rank": "6",
        "title": "Encyclopedia of Chart Patterns",
        "author": "Thomas Bulkowski",
        "mechanism": "bulkowski_pattern_bias",
        "principle": "Avoid trading against high-reliability opposing PA patterns",
    },
    {
        "rank": "7",
        "title": "Technical Analysis Using Multiple Timeframes",
        "author": "Brian Shannon",
        "mechanism": "shannon_mtf_gate",
        "principle": "HTF bias alignment (discipline/mtf_gate.py)",
    },
)


# Nison / Bulkowski-style opposing pattern tokens (lowercase substrings)
_BEARISH_CANDLES = (
    "shooting_star",
    "bearish_engulfing",
    "evening_star",
    "hanging_man",
    "dark_cloud",
    "bearish",
)
_BULLISH_CANDLES = (
    "hammer",
    "bullish_engulfing",
    "morning_star",
    "piercing",
    "bullish",
)
# Higher-reliability classical / failure patterns (Bulkowski-style hard blocks).
# Liquidity-grab labels (stop_hunt_*) are context-dependent — not auto hard-blocks.
_STRONG_BEAR_PA = (
    "failed_breakout",
    "head_and_shoulders",
    "double_top",
    "descending_triangle",
    "bear_flag",
    "rs_flip_resistance",
    "evening_star",
)
_STRONG_BULL_PA = (
    "double_bottom",
    "inverse_head",  # matches inverse_head_and_shoulders
    "ascending_triangle",
    "bull_flag",
    "rs_flip_support",
    "morning_star",
    "failed_breakdown",
)


@dataclass
class TaGateResult:
    ok: bool
    book: str
    mechanism: str
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return f"{self.book}: OK"
        return f"{self.book}: BLOCK — " + "; ".join(self.reasons)


@dataclass
class TaBooksResult:
    ok: bool
    results: List[TaGateResult] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "Investopedia TA book gates: all passed"
        return "Investopedia TA book gates blocked: " + "; ".join(self.blocked_by)


def _f(ctx: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(ctx.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _s(ctx: Mapping[str, Any], key: str, default: str = "") -> str:
    return str(ctx.get(key, default) or default).lower().strip()


def _listish(ctx: Mapping[str, Any], key: str) -> List[str]:
    raw = ctx.get(key) or []
    if isinstance(raw, str):
        return [raw.lower()]
    return [str(x).lower() for x in raw]


# --- 1 Schwager: plan / entry / exit ---


def schwager_plan_entry_exit(ctx: Mapping[str, Any]) -> TaGateResult:
    """Getting Started in TA: system needs entry, stop, target before risk."""
    reasons: List[str] = []
    entry = _f(ctx, "entry_price", _f(ctx, "price"))
    stop = _f(ctx, "stop_loss")
    target = _f(ctx, "profit_target")
    if entry <= 0:
        reasons.append("Schwager: entry price missing")
    if stop <= 0:
        reasons.append("Schwager: stop/exit risk level missing")
    if target <= 0:
        reasons.append("Schwager: profit target / exit plan missing")
    if entry > 0 and stop > 0 and abs(entry - stop) / entry < 0.001:
        reasons.append("Schwager: stop too tight vs entry (not a real plan)")
    return TaGateResult(
        ok=len(reasons) == 0,
        book="Getting Started in TA (Schwager)",
        mechanism="schwager_plan_entry_exit",
        reasons=reasons,
    )


# --- 2 Pring: trend + volume ---


def pring_trend_volume(ctx: Mapping[str, Any], *, min_rvol: float = 1.2) -> TaGateResult:
    """Technical Analysis Explained: price trend confirmed by volume/participation."""
    reasons: List[str] = []
    direction = _s(ctx, "direction")
    trend = _s(ctx, "trend")
    rvol = _f(ctx, "relative_volume", _f(ctx, "rvol"))
    ma = _s(ctx, "ma_alignment")

    if direction in ("bullish", "long"):
        if trend in ("downtrend", "bearish"):
            reasons.append("Pring: long without bullish trend structure")
        if ma == "bearish":
            reasons.append("Pring: long against bearish MA stack")
    if direction in ("bearish", "short"):
        if trend in ("uptrend", "bullish"):
            reasons.append("Pring: short without bearish trend structure")
        if ma == "bullish":
            reasons.append("Pring: short against bullish MA stack")
    if rvol < min_rvol:
        reasons.append(f"Pring: volume not confirming (RVOL {rvol:.2f}x < {min_rvol}x)")
    return TaGateResult(
        ok=len(reasons) == 0,
        book="Technical Analysis Explained (Pring)",
        mechanism="pring_trend_volume",
        reasons=reasons,
    )


# --- 3 Murphy: indicator confluence ---


def murphy_indicator_confluence(
    ctx: Mapping[str, Any],
    *,
    min_aligned: int = 2,
) -> TaGateResult:
    """Murphy: at least N of MA / MACD / RSI / momentum agree with direction."""
    reasons: List[str] = []
    direction = _s(ctx, "direction")
    if direction not in ("bullish", "long", "bearish", "short"):
        return TaGateResult(
            ok=True,
            book="TA of the Financial Markets (Murphy)",
            mechanism="murphy_indicator_confluence",
            reasons=["Murphy: neutral direction — confluence N/A"],
        )

    bullish_votes = 0
    bearish_votes = 0

    ma = _s(ctx, "ma_alignment")
    if ma == "bullish":
        bullish_votes += 1
    elif ma == "bearish":
        bearish_votes += 1

    macd = _s(ctx, "macd_signal")
    if macd == "bullish":
        bullish_votes += 1
    elif macd == "bearish":
        bearish_votes += 1

    rsi = _f(ctx, "rsi", 50.0)
    if rsi >= 55:
        bullish_votes += 1
    elif rsi <= 45:
        bearish_votes += 1

    mom = _s(ctx, "momentum")
    if mom == "bullish":
        bullish_votes += 1
    elif mom == "bearish":
        bearish_votes += 1

    if direction in ("bullish", "long"):
        if bullish_votes < min_aligned:
            reasons.append(
                f"Murphy: bullish confluence {bullish_votes}/{min_aligned} "
                f"(MA/MACD/RSI/momentum)"
            )
        if bearish_votes >= 3 and bullish_votes < 2:
            reasons.append("Murphy: majority indicators bearish vs long")
    else:
        if bearish_votes < min_aligned:
            reasons.append(
                f"Murphy: bearish confluence {bearish_votes}/{min_aligned} "
                f"(MA/MACD/RSI/momentum)"
            )
        if bullish_votes >= 3 and bearish_votes < 2:
            reasons.append("Murphy: majority indicators bullish vs short")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="TA of the Financial Markets (Murphy)",
        mechanism="murphy_indicator_confluence",
        reasons=reasons,
    )


# --- 5 Nison: candle alignment ---


def nison_candle_alignment(ctx: Mapping[str, Any]) -> TaGateResult:
    """Candles should not strongly oppose the trade direction."""
    reasons: List[str] = []
    direction = _s(ctx, "direction")
    candles = _listish(ctx, "candle_patterns") + _listish(ctx, "candles")
    summary = _s(ctx, "pattern_summary")
    blob = " ".join(candles + [summary])

    if direction in ("bullish", "long"):
        hits = [t for t in _BEARISH_CANDLES if t in blob and "bullish" not in t]
        # allow "bearish" only as token in mixed strings carefully
        strong = [
            t
            for t in ("shooting_star", "bearish_engulfing", "evening_star", "hanging_man")
            if t in blob
        ]
        if strong:
            reasons.append(f"Nison: bearish candle(s) oppose long: {', '.join(strong)}")
    if direction in ("bearish", "short"):
        strong = [
            t
            for t in ("hammer", "bullish_engulfing", "morning_star", "piercing")
            if t in blob
        ]
        if strong:
            reasons.append(f"Nison: bullish candle(s) oppose short: {', '.join(strong)}")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Japanese Candlestick Charting (Nison)",
        mechanism="nison_candle_alignment",
        reasons=reasons,
    )


# --- 6 Bulkowski: pattern reliability bias ---


def bulkowski_pattern_bias(ctx: Mapping[str, Any]) -> TaGateResult:
    """Block trading against high-reliability opposing chart/PA patterns."""
    reasons: List[str] = []
    direction = _s(ctx, "direction")
    pa = _listish(ctx, "pa_signals") + _listish(ctx, "candle_patterns")
    summary = _s(ctx, "pattern_summary")
    blob = " ".join(pa + [summary])

    if direction in ("bullish", "long"):
        hits = [t for t in _STRONG_BEAR_PA if t in blob]
        if hits:
            reasons.append(
                f"Bulkowski: high-reliability bearish pattern vs long: {', '.join(hits)}"
            )
    if direction in ("bearish", "short"):
        hits = [t for t in _STRONG_BULL_PA if t in blob]
        if hits:
            reasons.append(
                f"Bulkowski: high-reliability bullish pattern vs short: {', '.join(hits)}"
            )

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Encyclopedia of Chart Patterns (Bulkowski)",
        mechanism="bulkowski_pattern_bias",
        reasons=reasons,
    )


def apply_investopedia_ta_gates(
    ctx: Mapping[str, Any],
    *,
    min_rvol: float = 1.2,
    min_confluence: int = 2,
    enabled: bool = True,
) -> TaBooksResult:
    """Run Investopedia TA-book gates (Shannon/O'Neil already elsewhere when full desk runs)."""
    if not enabled:
        return TaBooksResult(ok=True, results=[], blocked_by=[])

    results = [
        schwager_plan_entry_exit(ctx),
        pring_trend_volume(ctx, min_rvol=min_rvol),
        murphy_indicator_confluence(ctx, min_aligned=min_confluence),
        nison_candle_alignment(ctx),
        bulkowski_pattern_bias(ctx),
    ]
    blocked = [r.summary for r in results if not r.ok]
    return TaBooksResult(ok=len(blocked) == 0, results=results, blocked_by=blocked)
