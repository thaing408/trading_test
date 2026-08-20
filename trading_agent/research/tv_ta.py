"""TradingView TA enrich (steal P1+P2 from tradingview-mcp).

Research-host only. Never feeds OMS / auto_trade place path.

P1 — ``tradingview_ta`` consensus (BUY/SELL/HOLD + oscillator/MA votes)
P2 — BB position / ±3-style rating + live rating screener via ``tradingview-screener``

Flag (default **off**):

  TRADING_AGENT_TV_TA=1

Optional deps (``pip install -e ".[tv-ta]"``):

  tradingview-ta>=3.3.0
  tradingview-screener==3.0.0
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


def tv_ta_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_TV_TA", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _throttle_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("TRADING_AGENT_TV_TA_THROTTLE", "0.8") or 0.8))
    except ValueError:
        return 0.8


def _deps_available() -> tuple[bool, str]:
    try:
        import tradingview_ta  # noqa: F401
    except ImportError:
        return False, "missing tradingview-ta (pip install -e '.[tv-ta]')"
    return True, ""


@dataclass
class TvTaSnapshot:
    symbol: str
    exchange: str = ""
    interval: str = "1d"
    recommendation: str = ""
    buy: int = 0
    sell: int = 0
    neutral: int = 0
    oscillators: str = ""
    moving_averages: str = ""
    close: Optional[float] = None
    rsi: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_sigma: Optional[float] = None  # ≈ (close-mid)/(BB half-width/2) if BB≈±2σ
    bb_rating: str = ""  # INSIDE | NEAR_UPPER | NEAR_LOWER | EXT_PLUS2 | EXT_MINUS2 | EXT_PLUS3 | EXT_MINUS3
    bbp_signal: str = ""
    error: str = ""
    source: str = "tradingview_ta"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _guess_exchange(symbol: str) -> str:
    sym = symbol.upper().strip()
    # Common liquid names — TA_Handler needs an exchange; NASDAQ default is fine for most tech
    nyse = {
        "IBM",
        "GE",
        "JPM",
        "BAC",
        "XOM",
        "CVX",
        "WMT",
        "V",
        "MA",
        "DIS",
        "BA",
        "CAT",
        "GS",
        "C",
        "T",
        "KO",
        "PEP",
        "MRK",
        "PFE",
        "JNJ",
        "UNH",
        "HD",
        "NKE",
        "MCD",
        "SPY",
        "DIA",
        "IWM",
        "TLT",
        "GLD",
        "SLV",
        "XLF",
        "XLE",
        "XLV",
        "XLI",
        "XLB",
        "XLU",
        "XLP",
        "XLY",
        "XLK",
        "SMH",
        "ARKK",
    }
    if sym in nyse or sym.endswith("X"):  # many sector ETFs
        if sym in ("QQQ", "TQQQ", "SQQQ", "IBIT", "BITO"):
            return "NASDAQ"
        if sym in nyse:
            return "NYSE" if sym not in ("SPY", "IWM", "DIA", "TLT", "GLD", "SLV") else "AMEX"
    if sym in ("SPY", "IWM", "DIA", "GLD", "SLV", "TLT"):
        return "AMEX"
    return "NASDAQ"


def _interval_const(name: str):
    from tradingview_ta import Interval

    key = (name or "1d").strip().lower()
    mapping = {
        "1d": Interval.INTERVAL_1_DAY,
        "1day": Interval.INTERVAL_1_DAY,
        "d": Interval.INTERVAL_1_DAY,
        "4h": Interval.INTERVAL_4_HOURS,
        "1h": Interval.INTERVAL_1_HOUR,
        "60": Interval.INTERVAL_1_HOUR,
        "15m": Interval.INTERVAL_15_MINUTES,
        "15": Interval.INTERVAL_15_MINUTES,
        "1w": Interval.INTERVAL_1_WEEK,
        "w": Interval.INTERVAL_1_WEEK,
    }
    return mapping.get(key, Interval.INTERVAL_1_DAY)


def bb_sigma_and_rating(
    close: Optional[float],
    upper: Optional[float],
    lower: Optional[float],
) -> tuple[Optional[float], str]:
    """Map price vs TradingView BB (typically ±2σ) into a ±3-style label.

    sigma ≈ (close - mid) / ((upper-lower)/4)  because half-band ≈ 2σ → σ = half/2.
    """
    try:
        c = float(close)  # type: ignore[arg-type]
        u = float(upper)  # type: ignore[arg-type]
        lo = float(lower)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, ""
    mid = (u + lo) / 2.0
    half = (u - lo) / 2.0
    if half <= 1e-12:
        return None, ""
    sigma_unit = half / 2.0  # 1σ
    if sigma_unit <= 1e-12:
        return None, ""
    z = (c - mid) / sigma_unit
    if z >= 3.0:
        rating = "EXT_PLUS3"
    elif z >= 2.0:
        rating = "EXT_PLUS2"
    elif z >= 1.0:
        rating = "NEAR_UPPER"
    elif z <= -3.0:
        rating = "EXT_MINUS3"
    elif z <= -2.0:
        rating = "EXT_MINUS2"
    elif z <= -1.0:
        rating = "NEAR_LOWER"
    else:
        rating = "INSIDE"
    return round(z, 3), rating


def fetch_symbol_analysis(
    symbol: str,
    *,
    exchange: Optional[str] = None,
    screener: str = "america",
    interval: str = "1d",
    timeout: float = 15.0,
) -> TvTaSnapshot:
    """P1+P2 per-symbol: consensus + BB rating. Fail-open with error field."""
    sym = symbol.upper().strip()
    ok, why = _deps_available()
    if not ok:
        return TvTaSnapshot(symbol=sym, error=why)
    from tradingview_ta import TA_Handler

    exch = (exchange or _guess_exchange(sym)).upper()
    snap = TvTaSnapshot(symbol=sym, exchange=exch, interval=interval)
    try:
        handler = TA_Handler(
            symbol=sym,
            screener=screener,
            exchange=exch,
            interval=_interval_const(interval),
            timeout=timeout,
        )
        analysis = handler.get_analysis()
    except Exception as exc:  # noqa: BLE001
        # Retry AMEX↔NASDAQ↔NYSE once for ETFs / wrong exchange
        for alt in ("NASDAQ", "NYSE", "AMEX"):
            if alt == exch:
                continue
            try:
                handler = TA_Handler(
                    symbol=sym,
                    screener=screener,
                    exchange=alt,
                    interval=_interval_const(interval),
                    timeout=timeout,
                )
                analysis = handler.get_analysis()
                snap.exchange = alt
                break
            except Exception:
                continue
        else:
            snap.error = str(exc)[:200]
            return snap

    summary = getattr(analysis, "summary", None) or {}
    snap.recommendation = str(summary.get("RECOMMENDATION") or "")
    try:
        snap.buy = int(summary.get("BUY") or 0)
        snap.sell = int(summary.get("SELL") or 0)
        snap.neutral = int(summary.get("NEUTRAL") or 0)
    except (TypeError, ValueError):
        pass
    osc = getattr(analysis, "oscillators", None) or {}
    ma = getattr(analysis, "moving_averages", None) or {}
    snap.oscillators = str(osc.get("RECOMMENDATION") or "")
    snap.moving_averages = str(ma.get("RECOMMENDATION") or "")
    compute = osc.get("COMPUTE") if isinstance(osc, dict) else None
    if isinstance(compute, dict):
        snap.bbp_signal = str(compute.get("BBP") or "")

    inds = getattr(analysis, "indicators", None) or {}
    def _f(key: str) -> Optional[float]:
        try:
            v = inds.get(key)
            if v is None:
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    snap.close = _f("close")
    snap.rsi = _f("RSI")
    snap.bb_upper = _f("BB.upper")
    snap.bb_lower = _f("BB.lower")
    if snap.bb_upper is not None and snap.bb_lower is not None:
        snap.bb_mid = round((snap.bb_upper + snap.bb_lower) / 2.0, 4)
    z, rating = bb_sigma_and_rating(snap.close, snap.bb_upper, snap.bb_lower)
    snap.bb_sigma = z
    snap.bb_rating = rating
    return snap


def enrich_symbols(
    symbols: Sequence[str],
    *,
    interval: str = "1d",
    throttle: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Batch enrich. Respects TRADING_AGENT_TV_TA unless force=True."""
    if not force and not tv_ta_enabled():
        return {
            "enabled": False,
            "skipped": True,
            "reason": "TRADING_AGENT_TV_TA off",
            "symbols": [],
        }
    gap = _throttle_seconds() if throttle is None else max(0.0, float(throttle))
    rows: List[Dict[str, Any]] = []
    for i, sym in enumerate(symbols):
        if i and gap:
            time.sleep(gap)
        snap = fetch_symbol_analysis(str(sym), interval=interval)
        rows.append(snap.as_dict())
    return {
        "enabled": True,
        "skipped": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interval": interval,
        "count": len(rows),
        "symbols": rows,
    }


def rating_scan(
    *,
    min_recommend: float = 0.3,
    limit: int = 25,
    market: str = "america",
    force: bool = False,
) -> Dict[str, Any]:
    """P2 live screener: high Recommend.All names (tradingview-screener)."""
    if not force and not tv_ta_enabled():
        return {"enabled": False, "skipped": True, "reason": "TRADING_AGENT_TV_TA off"}
    try:
        from tradingview_screener import Query, col
    except ImportError:
        return {
            "enabled": True,
            "error": "missing tradingview-screener (pip install -e '.[tv-ta]')",
            "rows": [],
        }
    try:
        q = (
            Query()
            .select("name", "close", "Recommend.All", "BBPower", "RSI", "volume")
            .where(col("Recommend.All") > float(min_recommend))
            .order_by("volume", ascending=False)
            .limit(int(limit))
        )
        if hasattr(q, "set_markets"):
            q = q.set_markets(market)
        total, df = q.get_scanner_data()
    except Exception as exc:  # noqa: BLE001
        return {"enabled": True, "error": str(exc)[:300], "rows": []}

    rows: List[Dict[str, Any]] = []
    if df is not None and hasattr(df, "to_dict"):
        for rec in df.to_dict(orient="records"):
            ticker = str(rec.get("ticker") or "")
            sym = ticker.split(":")[-1] if ":" in ticker else ticker
            rows.append(
                {
                    "ticker": ticker,
                    "symbol": sym.upper(),
                    "name": rec.get("name"),
                    "close": rec.get("close"),
                    "recommend_all": rec.get("Recommend.All"),
                    "bb_power": rec.get("BBPower"),
                    "rsi": rec.get("RSI"),
                    "volume": rec.get("volume"),
                }
            )
    return {
        "enabled": True,
        "skipped": False,
        "market": market,
        "min_recommend": min_recommend,
        "scanner_total": total,
        "count": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }


def bollinger_extreme_scan(
    symbols: Sequence[str],
    *,
    interval: str = "1d",
    min_abs_sigma: float = 2.0,
    force: bool = False,
) -> Dict[str, Any]:
    """P2: filter enrich_symbols for |bb_sigma| >= threshold (±2 / ±3)."""
    pack = enrich_symbols(symbols, interval=interval, force=force)
    if pack.get("skipped"):
        return pack
    hits = [
        r
        for r in (pack.get("symbols") or [])
        if isinstance(r, dict)
        and r.get("bb_sigma") is not None
        and abs(float(r["bb_sigma"])) >= float(min_abs_sigma)
    ]
    return {
        **pack,
        "scan": "bollinger_extreme",
        "min_abs_sigma": min_abs_sigma,
        "hits": hits,
        "hit_count": len(hits),
    }


def format_tv_ta_report(pack: Dict[str, Any]) -> str:
    if pack.get("skipped"):
        return f"# TV TA (skipped)\n\n{pack.get('reason')}\n"
    lines = [
        f"# TradingView TA enrich ({pack.get('interval', '')})",
        "",
        f"generated: {pack.get('generated_at')}",
        "",
        "| Sym | Rec | Buy/Sell/Neu | Osc | MA | BB rating | σ | RSI |",
        "|-----|-----|--------------|-----|----|-----------|---|-----|",
    ]
    for r in pack.get("symbols") or []:
        if r.get("error"):
            lines.append(f"| {r.get('symbol')} | ERR | | | | | | {r.get('error')[:40]} |")
            continue
        lines.append(
            f"| {r.get('symbol')} | {r.get('recommendation')} | "
            f"{r.get('buy')}/{r.get('sell')}/{r.get('neutral')} | "
            f"{r.get('oscillators')} | {r.get('moving_averages')} | "
            f"{r.get('bb_rating')} | {r.get('bb_sigma')} | {r.get('rsi')} |"
        )
    return "\n".join(lines) + "\n"


def format_rating_scan_report(pack: Dict[str, Any]) -> str:
    if pack.get("skipped"):
        return f"# TV rating scan (skipped)\n\n{pack.get('reason')}\n"
    if pack.get("error"):
        return f"# TV rating scan error\n\n{pack.get('error')}\n"
    lines = [
        f"# TV rating screener ({pack.get('market')}, Recommend.All > {pack.get('min_recommend')})",
        "",
        f"scanner_total≈{pack.get('scanner_total')}  shown={pack.get('count')}",
        "",
        "| Ticker | Close | Rec.All | BBPower | RSI | Vol |",
        "|--------|-------|---------|---------|-----|-----|",
    ]
    for r in pack.get("rows") or []:
        lines.append(
            f"| {r.get('ticker')} | {r.get('close')} | {r.get('recommend_all')} | "
            f"{r.get('bb_power')} | {r.get('rsi')} | {r.get('volume')} |"
        )
    return "\n".join(lines) + "\n"


def stamp_tv_fields_on_entry(entry: Dict[str, Any], snap: TvTaSnapshot | Dict[str, Any]) -> Dict[str, Any]:
    """Attach informational tv_* fields (never change ENTER eligibility)."""
    d = snap.as_dict() if isinstance(snap, TvTaSnapshot) else dict(snap)
    entry["tv_recommendation"] = d.get("recommendation") or ""
    entry["tv_oscillators"] = d.get("oscillators") or ""
    entry["tv_moving_averages"] = d.get("moving_averages") or ""
    entry["tv_bb_rating"] = d.get("bb_rating") or ""
    entry["tv_bb_sigma"] = d.get("bb_sigma")
    entry["tv_rsi"] = d.get("rsi")
    if d.get("error"):
        entry["tv_error"] = d["error"]
    return entry
