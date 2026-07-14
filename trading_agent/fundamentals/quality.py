"""Fundamental quality score for auto-trade (research host — no TOS required).

Combines yfinance info (and optional FMP later) into a 0–100 score plus
hard/soft event risk (earnings proximity). Complements technical book gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


@dataclass
class FundamentalSnapshot:
    symbol: str
    score: float
    passed: bool
    reasons: List[str] = field(default_factory=list)
    market_cap: float = 0.0
    pe_ttm: float = 0.0
    forward_pe: float = 0.0
    profit_margin: float = 0.0
    revenue_growth: float = 0.0
    debt_to_equity: float = 0.0
    earnings_date: str = ""
    days_to_earnings: Optional[int] = None
    sector: str = ""
    source: str = "none"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "passed": self.passed,
            "reasons": self.reasons,
            "market_cap": self.market_cap,
            "pe_ttm": self.pe_ttm,
            "forward_pe": self.forward_pe,
            "profit_margin": self.profit_margin,
            "revenue_growth": self.revenue_growth,
            "debt_to_equity": self.debt_to_equity,
            "earnings_date": self.earnings_date,
            "days_to_earnings": self.days_to_earnings,
            "sector": self.sector,
            "source": self.source,
        }


def _f(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        x = float(val)
        if x != x:  # NaN
            return default
        return x
    except (TypeError, ValueError):
        return default


def _parse_earnings_ts(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            # yfinance sometimes returns epoch seconds
            if raw > 1e12:
                raw = raw / 1000.0
            return datetime.utcfromtimestamp(float(raw)).date()
        text = str(raw).strip()
        if not text:
            return None
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def score_fundamentals_from_info(
    symbol: str,
    info: Dict[str, Any] | None,
    *,
    min_score: float = 45.0,
    block_earnings_within_days: int = 2,
    today: date | None = None,
) -> FundamentalSnapshot:
    """Score a yfinance-like info dict. Safe when info is empty."""
    info = info or {}
    reasons: List[str] = []
    score = 50.0
    today = today or date.today()

    mcap = _f(info.get("marketCap") or info.get("market_cap"))
    pe = _f(info.get("trailingPE") or info.get("pe_ttm"))
    fpe = _f(info.get("forwardPE") or info.get("forward_pe"))
    margin = _f(info.get("profitMargins") or info.get("profit_margin"))
    # profitMargins often 0.12 style
    if abs(margin) > 1.5:
        margin = margin / 100.0
    rev_g = _f(info.get("revenueGrowth") or info.get("revenue_growth"))
    if abs(rev_g) > 2:
        rev_g = rev_g / 100.0
    de = _f(info.get("debtToEquity") or info.get("debt_to_equity"))
    sector = str(info.get("sector") or info.get("category") or "")

    # Market cap quality
    if mcap >= 50e9:
        score += 12
        reasons.append("Mega/large-cap liquidity (+12)")
    elif mcap >= 10e9:
        score += 8
        reasons.append("Large-cap (+8)")
    elif mcap >= 2e9:
        score += 4
        reasons.append("Mid+ institutional floor (+4)")
    elif mcap > 0:
        score -= 8
        reasons.append("Small-cap quality haircut (-8)")
    else:
        score -= 5
        reasons.append("Market cap unknown (-5)")

    # Profitability
    if margin >= 0.15:
        score += 10
        reasons.append(f"Strong margins {margin:.0%} (+10)")
    elif margin >= 0.05:
        score += 5
        reasons.append(f"Positive margins {margin:.0%} (+5)")
    elif margin < 0:
        score -= 12
        reasons.append(f"Negative margins {margin:.0%} (-12)")

    # Growth
    if rev_g >= 0.15:
        score += 10
        reasons.append(f"Revenue growth {rev_g:.0%} (+10)")
    elif rev_g >= 0.05:
        score += 5
        reasons.append(f"Modest growth {rev_g:.0%} (+5)")
    elif rev_g < -0.05:
        score -= 8
        reasons.append(f"Revenue contraction {rev_g:.0%} (-8)")

    # Valuation sanity (not value-only)
    if 0 < pe <= 35 or 0 < fpe <= 30:
        score += 6
        reasons.append("Valuation not extreme (+6)")
    elif pe > 80 or fpe > 60:
        score -= 6
        reasons.append("Rich multiple (-6)")
    elif pe < 0:
        score -= 4
        reasons.append("Negative TTM PE (-4)")

    # Leverage
    if 0 < de <= 100:
        score += 4
        reasons.append("Moderate leverage (+4)")
    elif de > 250:
        score -= 10
        reasons.append(f"High D/E {de:.0f} (-10)")

    # Earnings proximity
    earn_raw = (
        info.get("earningsTimestamp")
        or info.get("earningsDate")
        or info.get("earnings_date")
    )
    if isinstance(earn_raw, (list, tuple)) and earn_raw:
        earn_raw = earn_raw[0]
    earn_d = _parse_earnings_ts(earn_raw)
    days_to: Optional[int] = None
    earn_s = ""
    if earn_d:
        days_to = (earn_d - today).days
        earn_s = earn_d.isoformat()
        if 0 <= days_to <= block_earnings_within_days:
            score -= 20
            reasons.append(
                f"Earnings in {days_to}d ({earn_s}) — event risk (-20)"
            )
        elif -1 <= days_to < 0:
            score -= 10
            reasons.append("Just reported / binary risk residual (-10)")
        elif days_to is not None and days_to > 14:
            score += 2

    score = round(max(0.0, min(100.0, score)), 1)
    passed = score >= min_score
    if not passed:
        reasons.append(f"Fundamental score {score:.0f} < min {min_score:.0f}")

    return FundamentalSnapshot(
        symbol=symbol.upper(),
        score=score,
        passed=passed,
        reasons=reasons,
        market_cap=mcap,
        pe_ttm=pe,
        forward_pe=fpe,
        profit_margin=margin,
        revenue_growth=rev_g,
        debt_to_equity=de,
        earnings_date=earn_s,
        days_to_earnings=days_to,
        sector=sector,
        source="info_dict",
    )


def fetch_fundamental_snapshot(
    symbol: str,
    *,
    min_score: float = 45.0,
    block_earnings_within_days: int = 2,
    use_network: bool = True,
) -> FundamentalSnapshot:
    """Live yfinance fundamentals; fails closed to neutral score if offline."""
    if not use_network:
        return FundamentalSnapshot(
            symbol=symbol.upper(),
            score=50.0,
            passed=True,
            reasons=["Fundamentals skipped (offline)"],
            source="offline",
        )
    try:
        import yfinance as yf

        t = yf.Ticker(symbol)
        info = {}
        try:
            info = dict(t.info or {})
        except Exception:
            info = {}
        # earnings date helper
        try:
            cal = t.calendar
            if cal is not None and hasattr(cal, "empty") and not cal.empty:
                # pandas DataFrame or Series depending on yfinance version
                if hasattr(cal, "columns") and "Earnings Date" in getattr(cal, "index", []):
                    pass
                raw = None
                if hasattr(cal, "iloc"):
                    try:
                        raw = cal.iloc[0, 0] if hasattr(cal, "shape") else None
                    except Exception:
                        raw = None
                if raw is not None:
                    info.setdefault("earningsDate", raw)
        except Exception:
            pass
        snap = score_fundamentals_from_info(
            symbol,
            info,
            min_score=min_score,
            block_earnings_within_days=block_earnings_within_days,
        )
        snap.source = "yfinance"
        return snap
    except Exception as exc:
        return FundamentalSnapshot(
            symbol=symbol.upper(),
            score=45.0,
            passed=True,
            reasons=[f"Fundamentals unavailable ({exc}); soft-pass"],
            source="error",
        )


def combine_quality_score(
    *,
    technical_score: float,
    confidence: float,
    fundamental_score: float,
    grade_score: float = 0.0,
) -> float:
    """Blended 0–100 quality for ranking / export."""
    q = (
        technical_score * 0.30
        + confidence * 0.25
        + fundamental_score * 0.25
        + (grade_score or confidence) * 0.20
    )
    return round(max(0.0, min(100.0, q)), 1)
