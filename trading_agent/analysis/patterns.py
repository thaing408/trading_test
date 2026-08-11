"""Candlestick + institutional price-action detectors (pure OHLCV, no I/O).

Institutional patterns are robust proxies of the PenguinBTC / ReadTheMarket
"Institutional Price Action - Cheat Sheet" families (stop hunt / liquidity grab,
fakeout / failed breakout, QML-style retest, RS/support-resistance flip).

Candles: hammer/pin, shooting star, bullish/bearish engulfing, doji.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class PatternSignal:
    """Named pattern with decision-facing metadata."""

    name: str
    family: str  # candlestick | institutional_pa | chart_pattern
    bias: str  # bullish | bearish | neutral
    confidence: float  # 0-100
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatternReport:
    signals: List[PatternSignal] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return [s.name for s in self.signals]

    @property
    def bullish(self) -> List[PatternSignal]:
        return [s for s in self.signals if s.bias == "bullish"]

    @property
    def bearish(self) -> List[PatternSignal]:
        return [s for s in self.signals if s.bias == "bearish"]

    def summary(self) -> str:
        if not self.signals:
            return "none"
        return "; ".join(f"{s.name}({s.bias})" for s in self.signals)

    def to_dict(self) -> Dict[str, Any]:
        return {"signals": [s.to_dict() for s in self.signals], "summary": self.summary()}


# --- bar helpers -----------------------------------------------------------------


def _body(o: float, c: float) -> float:
    return abs(float(c) - float(o))


def _range(h: float, l: float) -> float:
    return max(1e-9, float(h) - float(l))


def _upper_wick(o: float, h: float, c: float) -> float:
    return float(h) - max(float(o), float(c))


def _lower_wick(o: float, l: float, c: float) -> float:
    return min(float(o), float(c)) - float(l)


def _is_bull(o: float, c: float) -> bool:
    return float(c) > float(o)


def _is_bear(o: float, c: float) -> bool:
    return float(c) < float(o)


def _opens_from_closes(
    opens: Sequence[float] | None,
    closes: Sequence[float],
) -> List[float]:
    """Synthesize opens from prior close when open series missing."""
    if opens and len(opens) == len(closes):
        return [float(x) for x in opens]
    if not closes:
        return []
    out = [float(closes[0])]
    for i in range(1, len(closes)):
        out.append(float(closes[i - 1]))
    return out


# --- candlesticks -----------------------------------------------------------------


def detect_doji(
    o: float, h: float, l: float, c: float, body_frac: float = 0.1
) -> PatternSignal | None:
    rng = _range(h, l)
    if _body(o, c) / rng <= body_frac and rng > 0:
        return PatternSignal(
            name="doji",
            family="candlestick",
            bias="neutral",
            confidence=60.0,
            note="Indecision: small body vs range — wait for confirmation",
        )
    return None


def detect_hammer(
    o: float, h: float, l: float, c: float
) -> PatternSignal | None:
    """Bullish pin / hammer: long lower wick, small body near highs."""
    rng = _range(h, l)
    body = _body(o, c)
    lower = _lower_wick(o, l, c)
    upper = _upper_wick(o, h, c)
    if rng <= 0:
        return None
    if lower >= body * 2.0 and lower >= rng * 0.55 and upper <= body * 1.1:
        return PatternSignal(
            name="hammer",
            family="candlestick",
            bias="bullish",
            confidence=72.0,
            note="Bullish pin / hammer — demand rejection of lows",
        )
    return None


def detect_shooting_star(
    o: float, h: float, l: float, c: float
) -> PatternSignal | None:
    """Bearish pin / shooting star: long upper wick, small body near lows."""
    rng = _range(h, l)
    body = _body(o, c)
    lower = _lower_wick(o, l, c)
    upper = _upper_wick(o, h, c)
    if rng <= 0:
        return None
    if upper >= body * 2.0 and upper >= rng * 0.55 and lower <= max(body * 1.5, rng * 0.15):
        return PatternSignal(
            name="shooting_star",
            family="candlestick",
            bias="bearish",
            confidence=72.0,
            note="Bearish pin / shooting star — supply rejection of highs",
        )
    return None


def detect_bullish_engulfing(
    o1: float, c1: float, o2: float, c2: float
) -> PatternSignal | None:
    if _is_bear(o1, c1) and _is_bull(o2, c2):
        if float(c2) >= float(o1) and float(o2) <= float(c1):
            return PatternSignal(
                name="bullish_engulfing",
                family="candlestick",
                bias="bullish",
                confidence=75.0,
                note="Bullish engulfing — buyers overtook prior bear body",
            )
    return None


def detect_bearish_engulfing(
    o1: float, c1: float, o2: float, c2: float
) -> PatternSignal | None:
    if _is_bull(o1, c1) and _is_bear(o2, c2):
        if float(c2) <= float(o1) and float(o2) >= float(c1):
            return PatternSignal(
                name="bearish_engulfing",
                family="candlestick",
                bias="bearish",
                confidence=75.0,
                note="Bearish engulfing — sellers overtook prior bull body",
            )
    return None


def detect_candlestick_patterns(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[PatternSignal]:
    """Detect candlesticks on the last 1–2 bars."""
    n = min(len(opens), len(highs), len(lows), len(closes))
    if n < 1:
        return []
    signals: List[PatternSignal] = []
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    for det in (
        detect_doji(o, h, l, c),
        detect_hammer(o, h, l, c),
        detect_shooting_star(o, h, l, c),
    ):
        if det:
            signals.append(det)
    if n >= 2:
        o1, c1 = opens[-2], closes[-2]
        o2, c2 = opens[-1], closes[-1]
        for det in (
            detect_bullish_engulfing(o1, c1, o2, c2),
            detect_bearish_engulfing(o1, c1, o2, c2),
        ):
            if det:
                signals.append(det)
    # Prefer decisive patterns over doji when both fire
    names = {s.name for s in signals}
    if "doji" in names and len(names) > 1:
        signals = [s for s in signals if s.name != "doji"]
    return signals


# --- institutional price action proxies ------------------------------------------


def detect_stop_hunt(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 10,
) -> List[PatternSignal]:
    """Liquidity grab / stop hunt: sweep beyond recent extremes then reclaim."""
    n = min(len(highs), len(lows), len(closes))
    if n < lookback + 1:
        return []
    window_h = list(highs[-(lookback + 1) : -1])
    window_l = list(lows[-(lookback + 1) : -1])
    if not window_h or not window_l:
        return []
    prior_high = max(window_h)
    prior_low = min(window_l)
    last_h, last_l, last_c = float(highs[-1]), float(lows[-1]), float(closes[-1])
    out: List[PatternSignal] = []
    # Demand stop hunt: pierce below prior lows, close back above
    if last_l < prior_low and last_c > prior_low:
        out.append(
            PatternSignal(
                name="stop_hunt_demand",
                family="institutional_pa",
                bias="bullish",
                confidence=70.0,
                note="Stop hunt / liquidity grab below demand — sweep then reclaim",
            )
        )
    # Supply stop hunt: pierce above prior highs, close back below
    if last_h > prior_high and last_c < prior_high:
        out.append(
            PatternSignal(
                name="stop_hunt_supply",
                family="institutional_pa",
                bias="bearish",
                confidence=70.0,
                note="Stop hunt / liquidity grab above supply — sweep then reclaim",
            )
        )
    return out


def detect_fakeout(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 12,
) -> List[PatternSignal]:
    """Failed breakout / fakeout: break range then reverse and close inside/through."""
    n = min(len(highs), len(lows), len(closes))
    if n < lookback + 2:
        return []
    # Range from bars before the break attempt (exclude last 2)
    base_h = list(highs[-(lookback + 2) : -2])
    base_l = list(lows[-(lookback + 2) : -2])
    if len(base_h) < 3:
        return []
    range_high = max(base_h)
    range_low = min(base_l)
    prev_h, prev_l, prev_c = float(highs[-2]), float(lows[-2]), float(closes[-2])
    last_c = float(closes[-1])
    out: List[PatternSignal] = []
    # Bullish fakeout of lows: prior bar broke down, last bar closes back above range low
    if prev_l < range_low and prev_c < range_low and last_c > range_low:
        out.append(
            PatternSignal(
                name="fakeout_failed_breakdown",
                family="institutional_pa",
                bias="bullish",
                confidence=68.0,
                note="Fakeout / failed breakdown — trap below range then reverse up",
            )
        )
    # Bearish fakeout of highs
    if prev_h > range_high and prev_c > range_high and last_c < range_high:
        out.append(
            PatternSignal(
                name="fakeout_failed_breakout",
                family="institutional_pa",
                bias="bearish",
                confidence=68.0,
                note="Fakeout / failed breakout — trap above range then reverse down",
            )
        )
    return out


def detect_rs_flip(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 20,
) -> List[PatternSignal]:
    """Support/resistance flip: prior resistance retested as support (or inverse)."""
    n = min(len(highs), len(lows), len(closes))
    if n < lookback:
        return []
    mid = n // 2
    early_high = max(highs[:mid]) if mid >= 3 else max(highs[: max(3, n // 3)])
    late = list(zip(highs[-5:], lows[-5:], closes[-5:]))
    if not late:
        return []
    last_l = float(lows[-1])
    last_c = float(closes[-1])
    last_h = float(highs[-1])
    # Bullish RS flip: price traded above early high, retested near it from above, held
    traded_above = any(float(c) > early_high for c in closes[mid:])
    retest_zone = early_high * 0.985 <= last_l <= early_high * 1.015
    if traded_above and retest_zone and last_c >= early_high * 0.995:
        return [
            PatternSignal(
                name="rs_flip_support",
                family="institutional_pa",
                bias="bullish",
                confidence=65.0,
                note="RS flip: prior resistance retested as support",
            )
        ]
    early_low = min(lows[:mid]) if mid >= 3 else min(lows[: max(3, n // 3)])
    traded_below = any(float(c) < early_low for c in closes[mid:])
    retest_res = early_low * 0.985 <= last_h <= early_low * 1.015
    if traded_below and retest_res and last_c <= early_low * 1.005:
        return [
            PatternSignal(
                name="rs_flip_resistance",
                family="institutional_pa",
                bias="bearish",
                confidence=65.0,
                note="RS flip: prior support retested as resistance",
            )
        ]
    return []


def detect_qml_retest(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[PatternSignal]:
    """Quasimodo-style proxy: HH → LL (QML) → reclaim / retest of left shoulder zone.

    Compact structural proxy of cheat-sheet QML Quick/Late Retest — not full schematic.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < 12:
        return []
    h = [float(x) for x in highs]
    l = [float(x) for x in lows]
    c = [float(x) for x in closes]
    # Find swing high (HH) in middle third, then a lower low after it
    i0, i1 = n // 3, (2 * n) // 3
    if i1 <= i0 + 2:
        return []
    hh_idx = i0 + max(range(i1 - i0), key=lambda k: h[i0 + k])
    after = list(range(hh_idx + 1, n - 1))
    if len(after) < 3:
        return []
    ll_idx = min(after, key=lambda i: l[i])
    if l[ll_idx] >= min(l[max(0, hh_idx - 5) : hh_idx + 1]):
        # Not a clear LL below prior structure
        if l[ll_idx] >= l[hh_idx]:
            return []
    # Left shoulder approx: high before HH
    left = h[max(0, hh_idx - 6) : hh_idx]
    if not left:
        return []
    qml_level = max(left)  # simplified QML / left structure
    # Retest: after LL, price returns toward QML and holds (bullish reclaim)
    if ll_idx >= n - 2:
        return []
    post = c[ll_idx + 1 :]
    if not post:
        return []
    reclaimed = any(px >= qml_level * 0.998 for px in post)
    last = c[-1]
    near_qml = abs(last - qml_level) / max(qml_level, 1e-9) <= 0.025
    if reclaimed and last > l[ll_idx] and (near_qml or last > qml_level * 0.99):
        return [
            PatternSignal(
                name="qml_retest",
                family="institutional_pa",
                bias="bullish",
                confidence=62.0,
                note="QML-style retest proxy: HH→LL liquidity then reclaim of structure",
            )
        ]
    # Bearish inverse QML proxy
    ll_pre = i0 + min(range(i1 - i0), key=lambda k: l[i0 + k])
    after_ll = list(range(ll_pre + 1, n - 1))
    if len(after_ll) >= 3:
        hh2 = max(after_ll, key=lambda i: h[i])
        right_low = min(l[max(0, ll_pre - 6) : ll_pre] or [l[ll_pre]])
        if h[hh2] > max(h[max(0, ll_pre - 5) : ll_pre + 1]) and c[-1] < right_low * 1.01:
            if any(px <= right_low * 1.002 for px in c[hh2:]):
                return [
                    PatternSignal(
                        name="qml_retest_bearish",
                        family="institutional_pa",
                        bias="bearish",
                        confidence=60.0,
                        note="Bearish QML-style proxy: LL→HH then reject structure",
                    )
                ]
    return []


def detect_institutional_pa(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[PatternSignal]:
    signals: List[PatternSignal] = []
    signals.extend(detect_stop_hunt(highs, lows, closes))
    signals.extend(detect_fakeout(highs, lows, closes))
    signals.extend(detect_rs_flip(highs, lows, closes))
    signals.extend(detect_qml_retest(highs, lows, closes))
    # Dedupe by name (keep highest confidence)
    best: Dict[str, PatternSignal] = {}
    for s in signals:
        prev = best.get(s.name)
        if prev is None or s.confidence > prev.confidence:
            best[s.name] = s
    return list(best.values())


def detect_classical_chart_patterns(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[PatternSignal]:
    """Bridge classical geometry detectors into PatternSignal for TA books."""
    try:
        from trading_agent.pa.chart_patterns import detect_all_chart_patterns
    except Exception:
        return []
    out: List[PatternSignal] = []
    for p in detect_all_chart_patterns(highs, lows, closes):
        # Prefer confirmed; still surface approaching so Bulkowski gates can see them
        conf = float(p.confidence)
        if p.status != "confirmed":
            conf = max(40.0, conf - 12.0)
        out.append(
            PatternSignal(
                name=p.name,
                family="chart_pattern",
                bias=p.bias,
                confidence=conf,
                note="; ".join(p.notes) if p.notes else p.status,
            )
        )
    return out


def detect_all_patterns(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float] | None = None,
    opens: Sequence[float] | None = None,
) -> PatternReport:
    """Full pattern report from OHLCV (opens optional — synthesized if absent)."""
    if not closes or not highs or not lows:
        return PatternReport()
    o = _opens_from_closes(opens, closes)
    candles = detect_candlestick_patterns(o, highs, lows, closes)
    pa = detect_institutional_pa(highs, lows, closes)
    classical = detect_classical_chart_patterns(highs, lows, closes)
    return PatternReport(signals=candles + pa + classical)


def pattern_score_adjustment(report: PatternReport) -> float:
    """Bounded score delta for technical_score (approx ±8)."""
    if not report.signals:
        return 0.0
    delta = 0.0
    for s in report.signals:
        weight = (s.confidence / 100.0) * 3.5
        if s.bias == "bullish":
            delta += weight
        elif s.bias == "bearish":
            delta -= weight
    return max(-8.0, min(8.0, delta))


def patterns_for_decision(report: PatternReport) -> Dict[str, Any]:
    """Compact dict for research_summary / MI metadata."""
    return {
        "candles": [s.name for s in report.signals if s.family == "candlestick"],
        "institutional_pa": [s.name for s in report.signals if s.family == "institutional_pa"],
        "summary": report.summary(),
        "bias_net": (
            "bullish"
            if len(report.bullish) > len(report.bearish)
            else "bearish"
            if len(report.bearish) > len(report.bullish)
            else "neutral"
        ),
    }


# Named families for docs / verification dumps
CHEATSHEET_PATTERN_NAMES = (
    "stop_hunt_demand",
    "stop_hunt_supply",
    "fakeout_failed_breakout",
    "fakeout_failed_breakdown",
    "qml_retest",
    "qml_retest_bearish",
    "rs_flip_support",
    "rs_flip_resistance",
)
CANDLESTICK_PATTERN_NAMES = (
    "hammer",
    "shooting_star",
    "bullish_engulfing",
    "bearish_engulfing",
    "doji",
)
