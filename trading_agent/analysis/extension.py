"""ADR extension-from-low/high dials (Qullamaggie / Muninn).

Measures how much of the average daily range is already used at entry:

  longs:  adr_used = (entry - session_low) / ADR
  shorts: adr_used = (session_high - entry) / ADR

ADR = mean(high - low) over lookback (default 20), in **price dollars**.

Default: **tag only**. Set TRADING_AGENT_ADR_EXTENSION=1 to apply soft size cuts
(0.5×) for lt_025 and gt_100 — never hard-block.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


BUCKET_LT_025 = "lt_025"
BUCKET_025_050 = "025_050"
BUCKET_050_100 = "050_100"
BUCKET_GT_100 = "gt_100"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def adr_extension_enabled() -> bool:
    """When True, apply soft size cuts. Tags are always written when computable."""
    return _env_bool("TRADING_AGENT_ADR_EXTENSION", False)


def average_daily_range(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    lookback: int = 20,
) -> float:
    """Mean dollar range (high - low) over the last ``lookback`` bars."""
    n = min(len(highs), len(lows), max(1, int(lookback)))
    if n < 1 or not highs or not lows:
        return 0.0
    h = list(highs)[-n:]
    l = list(lows)[-n:]
    total = 0.0
    count = 0
    for hi, lo in zip(h, l):
        try:
            rng = float(hi) - float(lo)
        except (TypeError, ValueError):
            continue
        if rng > 0:
            total += rng
            count += 1
    if count < 1:
        return 0.0
    return round(total / count, 6)


def session_range_from_bars(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    session_bars: int = 0,
) -> Tuple[Optional[float], Optional[float]]:
    """Session high/low.

    If ``session_bars`` > 0, use only the last N bars (intraday slice).
    Otherwise use the last bar only (daily proxy: today's high/low).
    """
    if not highs or not lows:
        return None, None
    n = min(len(highs), len(lows))
    if n < 1:
        return None, None
    if session_bars and session_bars > 0:
        k = min(n, int(session_bars))
        h_slice = list(highs)[-k:]
        l_slice = list(lows)[-k:]
    else:
        h_slice = [highs[-1]]
        l_slice = [lows[-1]]
    try:
        return float(max(h_slice)), float(min(l_slice))
    except (TypeError, ValueError):
        return None, None


def compute_adr_used(
    *,
    entry: float,
    side: str,
    session_low: Optional[float],
    session_high: Optional[float],
    adr: float,
) -> Optional[float]:
    """Return adr_used multiple, or None if inputs incomplete."""
    try:
        entry_f = float(entry)
        adr_f = float(adr)
    except (TypeError, ValueError):
        return None
    if entry_f <= 0 or adr_f <= 0:
        return None
    side_u = (side or "").strip().upper()
    bearish = side_u in (
        "BEARISH",
        "BEAR",
        "SHORT",
        "PUT",
        "SELL",
    )
    try:
        if bearish:
            if session_high is None:
                return None
            return round((float(session_high) - entry_f) / adr_f, 4)
        if session_low is None:
            return None
        return round((entry_f - float(session_low)) / adr_f, 4)
    except (TypeError, ValueError):
        return None


def adr_bucket(adr_used: Optional[float]) -> Optional[str]:
    if adr_used is None:
        return None
    try:
        x = float(adr_used)
    except (TypeError, ValueError):
        return None
    if x < 0.25:
        return BUCKET_LT_025
    if x < 0.50:
        return BUCKET_025_050
    if x <= 1.0:
        return BUCKET_050_100
    return BUCKET_GT_100


def extension_note(adr_used: Optional[float], bucket: Optional[str]) -> str:
    if adr_used is None or not bucket:
        return ""
    labels = {
        BUCKET_LT_025: "too early / noise (<0.25 ADR)",
        BUCKET_025_050: "early band",
        BUCKET_050_100: "live band",
        BUCKET_GT_100: "extended (>1 ADR) — size down",
    }
    return f"ADR used {adr_used:.2f} ({labels.get(bucket, bucket)})"


def discord_extension_line(row: Dict[str, Any]) -> str:
    """One-liner for CIO / Discord cards."""
    used = row.get("adr_used")
    bucket = row.get("adr_bucket") or ""
    note = row.get("extension_note") or ""
    if note:
        return note
    if used is None:
        return ""
    try:
        return f"ADR used {float(used):.2f} ({bucket or 'n/a'})"
    except (TypeError, ValueError):
        return ""


def size_cut_multiplier(bucket: Optional[str], *, apply: bool) -> float:
    """Soft size policy: 0.5× outside the band; else 1.0. Never zero."""
    if not apply or not bucket:
        return 1.0
    if bucket in (BUCKET_LT_025, BUCKET_GT_100):
        return 0.5
    return 1.0


@dataclass(frozen=True)
class ExtensionResult:
    adr: float
    adr_used: Optional[float]
    adr_bucket: Optional[str]
    extension_note: str
    size_mult: float
    applied_size_cut: bool


def evaluate_extension(
    *,
    entry: float,
    side: str,
    session_low: Optional[float],
    session_high: Optional[float],
    adr: float,
    apply_size: Optional[bool] = None,
) -> ExtensionResult:
    used = compute_adr_used(
        entry=entry,
        side=side,
        session_low=session_low,
        session_high=session_high,
        adr=adr,
    )
    bucket = adr_bucket(used)
    note = extension_note(used, bucket)
    do_apply = adr_extension_enabled() if apply_size is None else bool(apply_size)
    mult = size_cut_multiplier(bucket, apply=do_apply)
    return ExtensionResult(
        adr=float(adr or 0),
        adr_used=used,
        adr_bucket=bucket,
        extension_note=note,
        size_mult=mult,
        applied_size_cut=bool(do_apply and mult < 1.0),
    )


def evaluate_extension_from_bars(
    *,
    entry: float,
    side: str,
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 20,
    session_bars: int = 0,
    apply_size: Optional[bool] = None,
) -> Optional[ExtensionResult]:
    adr = average_daily_range(highs, lows, lookback=lookback)
    session_high, session_low = session_range_from_bars(
        highs, lows, session_bars=session_bars
    )
    if adr <= 0 or session_low is None or session_high is None:
        return None
    return evaluate_extension(
        entry=entry,
        side=side,
        session_low=session_low,
        session_high=session_high,
        adr=adr,
        apply_size=apply_size,
    )


def apply_extension_to_entry(
    row: Dict[str, Any],
    result: ExtensionResult,
) -> Dict[str, Any]:
    """Stamp extension fields; optionally cut max_risk_dollars / quantity."""
    row["adr"] = round(float(result.adr), 4)
    row["adr_used"] = result.adr_used
    row["adr_bucket"] = result.adr_bucket
    row["extension_note"] = result.extension_note
    if result.applied_size_cut and result.size_mult < 1.0:
        try:
            risk = float(row.get("max_risk_dollars") or 0)
            if risk > 0:
                row["max_risk_dollars"] = round(risk * result.size_mult, 2)
        except (TypeError, ValueError):
            pass
        try:
            qty = int(row.get("quantity") or 1)
            # Keep at least 1 contract; mark fractional intent via risk cut
            if qty > 1:
                row["quantity"] = max(1, int(qty * result.size_mult))
        except (TypeError, ValueError):
            pass
        note = str(row.get("notes") or "")
        cut = f"adr_size_cut×{result.size_mult}"
        row["notes"] = (note + "; " + cut).strip("; ")[:240]
        row["adr_size_mult"] = result.size_mult
    return row


def enrich_entry_row_from_bars(
    row: Dict[str, Any],
    *,
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 20,
    session_bars: int = 0,
    apply_size: Optional[bool] = None,
) -> Dict[str, Any]:
    """Compute + stamp extension on an ENTER row. No-op if bars insufficient."""
    entry = float(row.get("entry") or 0)
    side = str(row.get("side") or "")
    result = evaluate_extension_from_bars(
        entry=entry,
        side=side,
        highs=highs,
        lows=lows,
        lookback=lookback,
        session_bars=session_bars,
        apply_size=apply_size,
    )
    if result is None:
        return row
    return apply_extension_to_entry(row, result)


def try_enrich_entry_from_market(
    row: Dict[str, Any],
    *,
    apply_size: Optional[bool] = None,
    lookback: int = 20,
) -> Dict[str, Any]:
    """Best-effort daily bars via yfinance. Fail-open (returns row unchanged)."""
    sym = str(row.get("symbol") or "").strip().upper()
    if not sym:
        return row
    try:
        import yfinance as yf  # type: ignore

        df = yf.download(
            sym,
            period=f"{max(lookback + 5, 30)}d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df is None or getattr(df, "empty", True):
            return row
        highs = df["High"].astype(float).tolist()
        lows = df["Low"].astype(float).tolist()
        return enrich_entry_row_from_bars(
            row,
            highs=highs,
            lows=lows,
            lookback=lookback,
            session_bars=0,
            apply_size=apply_size,
        )
    except Exception:  # noqa: BLE001 — fail-open
        return row
