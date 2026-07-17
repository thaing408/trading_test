"""Raschke-style first-30m open drive + previous-day low/high over-under.

Rules (America/New_York RTH):
- Window: 09:30–10:00 ET (first 30 minutes).
- Up bar: close > open; down bar: close < open.
- 3 consecutive up bars in the first-30m sequence → bullish *day bias candidate*.
- PDL (prior session low) is the main over/under: bias holds while last >= PDL;
  last < PDL invalidates the bullish open-drive bias.
- Symmetric optional: 3 consecutive down + PDH (last <= PDH holds bearish).

Fail-closed: incomplete first-30m bars or missing PDL/PDH never invent a bias.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
FIRST_30_END = time(10, 0)


@dataclass
class DayBiasResult:
    """Objective open-drive / day-bias package for tags and gates."""

    bias: str = "neutral"  # bullish | bearish | neutral | invalid
    consecutive_up: int = 0  # max run of up bars in first 30m
    consecutive_down: int = 0
    three_up_open: bool = False
    three_down_open: bool = False
    pdl: Optional[float] = None
    pdh: Optional[float] = None
    last: Optional[float] = None
    above_pdl: Optional[bool] = None
    below_pdh: Optional[bool] = None
    session: str = ""
    prior_session: str = ""
    first_30_bar_count: int = 0
    valid: bool = False
    tags: List[str] = field(default_factory=list)
    note: str = ""
    source: str = "raschke_first30_pdl"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _to_et(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc).astimezone(ET)
    return ts.astimezone(ET)


def _session_date(ts: datetime) -> date:
    return _to_et(ts).date()


def prior_session_hl(
    timestamps: Sequence[datetime],
    highs: Sequence[float],
    lows: Sequence[float],
    session: date,
) -> Tuple[Optional[float], Optional[float], Optional[date]]:
    """Prior weekday session high/low strictly before ``session``."""
    by_day: Dict[date, List[Tuple[float, float]]] = {}
    for ts, h, l in zip(timestamps, highs, lows):
        d = _session_date(ts)
        if d.weekday() >= 5:
            continue
        by_day.setdefault(d, []).append((float(h), float(l)))
    prior_days = sorted(d for d in by_day if d < session)
    if not prior_days:
        return None, None, None
    pd = prior_days[-1]
    rows = by_day[pd]
    return max(r[0] for r in rows), min(r[1] for r in rows), pd


def first_30m_indices(
    timestamps: Sequence[datetime],
    session: date,
) -> List[int]:
    """Bar indices fully inside 09:30–10:00 ET on ``session`` (weekday)."""
    if session.weekday() >= 5:
        return []
    out: List[int] = []
    for i, ts in enumerate(timestamps):
        t = _to_et(ts)
        if t.date() != session:
            continue
        tm = t.time()
        if RTH_OPEN <= tm < FIRST_30_END:
            out.append(i)
    return out


def max_consecutive_direction(
    opens: Sequence[float],
    closes: Sequence[float],
    indices: Sequence[int],
    *,
    up: bool,
) -> int:
    """Longest consecutive up (close>open) or down (close<open) run along indices."""
    best = 0
    run = 0
    for i in indices:
        o = float(opens[i])
        c = float(closes[i])
        hit = (c > o) if up else (c < o)
        if hit:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def evaluate_day_bias(
    timestamps: Sequence[datetime],
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    session: Optional[date] = None,
    last: Optional[float] = None,
    min_consecutive: int = 3,
    pdl: Optional[float] = None,
    pdh: Optional[float] = None,
) -> DayBiasResult:
    """Evaluate first-30m 3-up/3-down open drive vs PDL/PDH.

    Fail-closed: returns ``valid=False``, ``bias=neutral`` when first-30m
    bars are missing or PDL is required but unavailable for a 3-up candidate.
    """
    n = len(timestamps)
    if not (n == len(opens) == len(highs) == len(lows) == len(closes) and n > 0):
        return DayBiasResult(valid=False, note="empty_or_mismatched_ohlc")

    if session is None:
        # Prefer most recent RTH session present in the series
        days = sorted({_session_date(ts) for ts in timestamps if _session_date(ts).weekday() < 5})
        if not days:
            return DayBiasResult(valid=False, note="no_weekday_session")
        session = days[-1]

    idx = first_30m_indices(timestamps, session)
    up_run = max_consecutive_direction(opens, closes, idx, up=True)
    down_run = max_consecutive_direction(opens, closes, idx, up=False)
    three_up = up_run >= min_consecutive
    three_down = down_run >= min_consecutive

    computed_pdh, computed_pdl, prior = prior_session_hl(timestamps, highs, lows, session)
    use_pdl = float(pdl) if pdl is not None else computed_pdl
    use_pdh = float(pdh) if pdh is not None else computed_pdh

    last_px = float(last) if last is not None else float(closes[-1])
    above_pdl: Optional[bool] = None
    below_pdh: Optional[bool] = None
    if use_pdl is not None:
        above_pdl = last_px >= float(use_pdl)
    if use_pdh is not None:
        below_pdh = last_px <= float(use_pdh)

    tags: List[str] = []
    bias = "neutral"
    note_parts: List[str] = []
    valid = len(idx) > 0

    if not valid:
        return DayBiasResult(
            bias="neutral",
            consecutive_up=up_run,
            consecutive_down=down_run,
            three_up_open=False,
            three_down_open=False,
            pdl=use_pdl,
            pdh=use_pdh,
            last=last_px,
            above_pdl=above_pdl,
            below_pdh=below_pdh,
            session=session.isoformat(),
            prior_session=prior.isoformat() if prior else "",
            first_30_bar_count=0,
            valid=False,
            tags=[],
            note="incomplete_first_30m_bars",
        )

    if three_up:
        tags.append("open_drive_3up")
        if use_pdl is None:
            # Fail-closed: do not claim bullish day bias without PDL over/under
            bias = "neutral"
            note_parts.append("3up_open_but_missing_pdl")
            valid = False
        elif above_pdl:
            bias = "bullish"
            tags.append("day_bias_bullish")
            tags.append("pdl_hold")
            note_parts.append(
                f"3 consecutive up bars in first 30m; PDL {use_pdl:.2f} hold (last {last_px:.2f})"
            )
        else:
            bias = "invalid"
            tags.append("day_bias_invalid_pdl_break")
            note_parts.append(
                f"3-up open invalidated: last {last_px:.2f} < PDL {use_pdl:.2f}"
            )
    elif three_down:
        tags.append("open_drive_3down")
        if use_pdh is None:
            bias = "neutral"
            note_parts.append("3down_open_but_missing_pdh")
            valid = False
        elif below_pdh:
            bias = "bearish"
            tags.append("day_bias_bearish")
            tags.append("pdh_hold")
            note_parts.append(
                f"3 consecutive down bars in first 30m; PDH {use_pdh:.2f} hold (last {last_px:.2f})"
            )
        else:
            bias = "invalid"
            tags.append("day_bias_invalid_pdh_break")
            note_parts.append(
                f"3-down open invalidated: last {last_px:.2f} > PDH {use_pdh:.2f}"
            )
    else:
        note_parts.append(
            f"no_open_drive (up_run={up_run} down_run={down_run} need>={min_consecutive})"
        )

    return DayBiasResult(
        bias=bias,
        consecutive_up=up_run,
        consecutive_down=down_run,
        three_up_open=three_up,
        three_down_open=three_down,
        pdl=use_pdl,
        pdh=use_pdh,
        last=last_px,
        above_pdl=above_pdl,
        below_pdh=below_pdh,
        session=session.isoformat(),
        prior_session=prior.isoformat() if prior else "",
        first_30_bar_count=len(idx),
        valid=valid,
        tags=tags,
        note="; ".join(note_parts),
    )


def apply_day_bias_tags(
    method_tags: Optional[Sequence[str]],
    result: DayBiasResult,
    *,
    direction: str = "",
) -> Tuple[List[str], str, float]:
    """Merge day-bias tags into method tags; return (tags, note, priority_boost).

    Soft boost only when bias aligns with direction (or direction empty).
    """
    tags = list(method_tags or [])
    boost = 0.0
    for t in result.tags:
        if t not in tags:
            tags.append(t)
    note = result.note
    d = (direction or "").lower()
    if result.bias == "bullish" and result.valid:
        if not d or d in ("bullish", "long", "call", "neutral"):
            boost = 8.0
            if "open_drive_day_bias" not in tags:
                tags.append("open_drive_day_bias")
    elif result.bias == "bearish" and result.valid:
        if not d or d in ("bearish", "short", "put", "neutral"):
            boost = 8.0
            if "open_drive_day_bias" not in tags:
                tags.append("open_drive_day_bias")
    return tags, note, boost


def day_bias_from_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    session: Optional[date] = None,
    last: Optional[float] = None,
    min_consecutive: int = 3,
) -> DayBiasResult:
    """Convenience: rows with keys ts/open/high/low/close (ts datetime or iso str)."""
    timestamps: List[datetime] = []
    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    for r in rows:
        ts = r.get("ts") or r.get("timestamp") or r.get("datetime")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if not isinstance(ts, datetime):
            continue
        timestamps.append(ts)
        opens.append(float(r["open"]))
        highs.append(float(r["high"]))
        lows.append(float(r["low"]))
        closes.append(float(r["close"]))
    return evaluate_day_bias(
        timestamps,
        opens,
        highs,
        lows,
        closes,
        session=session,
        last=last,
        min_consecutive=min_consecutive,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """One-shot fixture demo for verification / CLI."""
    import argparse
    from datetime import timedelta

    parser = argparse.ArgumentParser(description="Raschke first-30m day bias")
    parser.add_argument("--json", action="store_true", help="Print full JSON result")
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Synthetic: prior day + session with 3 up bars in first 30m, last above PDL
    session = date(2026, 7, 17)
    prior = date(2026, 7, 16)
    base = datetime(2026, 7, 16, 9, 30, tzinfo=ET)
    rows: List[Dict[str, Any]] = []
    # Prior day bars (PDL=100)
    for i in range(6):
        rows.append(
            {
                "ts": base + timedelta(minutes=5 * i),
                "open": 101.0 + i * 0.1,
                "high": 102.0,
                "low": 100.0,
                "close": 101.2 + i * 0.1,
            }
        )
    # Session open: 3 green bars then continuation
    s0 = datetime(2026, 7, 17, 9, 30, tzinfo=ET)
    for i, (o, c) in enumerate([(100.5, 101.0), (101.0, 101.6), (101.6, 102.2), (102.2, 102.5)]):
        rows.append(
            {
                "ts": s0 + timedelta(minutes=5 * i),
                "open": o,
                "high": c + 0.1,
                "low": o - 0.1,
                "close": c,
            }
        )
    result = day_bias_from_rows(rows, session=session, last=102.5)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"bias={result.bias} consecutive_up={result.consecutive_up} "
            f"pdl={result.pdl} last={result.last} valid={result.valid} tags={result.tags}"
        )
        print(f"note={result.note}")
    return 0 if result.bias == "bullish" and result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
