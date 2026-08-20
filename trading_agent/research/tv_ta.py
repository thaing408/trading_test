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
    # TV rate-limits hard if we hammer; default 1.2s between symbols
    try:
        return max(0.0, float(os.getenv("TRADING_AGENT_TV_TA_THROTTLE", "1.2") or 1.2))
    except ValueError:
        return 1.2


def _fmt_num(value: Any, digits: int = 2) -> str:
    try:
        if value is None or value == "":
            return "—"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(value: Any) -> str:
    try:
        if value is None or value == "":
            return "—"
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_vol(value: Any) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}K"
    return f"{v:.0f}"


def _short_rec(rec: Any) -> str:
    s = str(rec or "").upper().replace("STRONG_", "S_")
    return (s or "—")[:10]


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


def _enrich_via_screener(
    symbols: Sequence[str],
    *,
    interval: str = "1d",
) -> List[Dict[str, Any]]:
    """Batch enrich using tradingview-screener set_tickers (fewer rate limits)."""
    try:
        from tradingview_screener import Query
    except ImportError:
        return []
    tickers = []
    for sym in symbols:
        s = str(sym).upper().strip()
        if ":" in s:
            tickers.append(s)
        else:
            tickers.append(f"{_guess_exchange(s)}:{s}")
    if not tickers:
        return []
    try:
        q = (
            Query()
            .select(
                "name",
                "close",
                "Recommend.All",
                "Recommend.MA",
                "Recommend.Other",
                "BBPower",
                "RSI",
                "BB.upper",
                "BB.lower",
            )
            .set_tickers(*tickers)
        )
        _total, df = q.get_scanner_data()
    except Exception:
        return []
    if df is None or not hasattr(df, "to_dict"):
        return []
    by_sym: Dict[str, Dict[str, Any]] = {}
    for rec in df.to_dict(orient="records"):
        ticker = str(rec.get("ticker") or "")
        sym = ticker.split(":")[-1].upper() if ticker else ""
        if not sym:
            continue
        close = rec.get("close")
        upper = rec.get("BB.upper")
        lower = rec.get("BB.lower")
        try:
            close_f = float(close) if close is not None else None
            upper_f = float(upper) if upper is not None else None
            lower_f = float(lower) if lower is not None else None
        except (TypeError, ValueError):
            close_f = upper_f = lower_f = None
        z, rating = bb_sigma_and_rating(close_f, upper_f, lower_f)
        # Map Recommend.All (-1..1) to BUY/SELL/HOLD style
        try:
            rec_all = float(rec.get("Recommend.All") or 0)
        except (TypeError, ValueError):
            rec_all = 0.0
        if rec_all >= 0.5:
            recommendation = "STRONG_BUY"
        elif rec_all >= 0.1:
            recommendation = "BUY"
        elif rec_all <= -0.5:
            recommendation = "STRONG_SELL"
        elif rec_all <= -0.1:
            recommendation = "SELL"
        else:
            recommendation = "NEUTRAL"
        try:
            rec_ma = float(rec.get("Recommend.MA") or 0)
        except (TypeError, ValueError):
            rec_ma = 0.0
        try:
            rec_osc = float(rec.get("Recommend.Other") or 0)
        except (TypeError, ValueError):
            rec_osc = 0.0

        def _side(v: float) -> str:
            if v >= 0.5:
                return "S_BUY"
            if v >= 0.1:
                return "BUY"
            if v <= -0.5:
                return "S_SELL"
            if v <= -0.1:
                return "SELL"
            return "NEUTRAL"

        # Fake B/S/N counts from score magnitude for display parity
        buy = max(0, int(round(abs(rec_all) * 20))) if rec_all > 0 else 0
        sell = max(0, int(round(abs(rec_all) * 20))) if rec_all < 0 else 0
        neutral = max(0, 20 - buy - sell)
        by_sym[sym] = {
            "symbol": sym,
            "exchange": ticker.split(":")[0] if ":" in ticker else "",
            "interval": interval,
            "recommendation": recommendation,
            "buy": buy,
            "sell": sell,
            "neutral": neutral,
            "oscillators": _side(rec_osc),
            "moving_averages": _side(rec_ma),
            "close": round(close_f, 2) if close_f is not None else None,
            "rsi": round(float(rec.get("RSI") or 0), 1) if rec.get("RSI") is not None else None,
            "bb_upper": round(upper_f, 2) if upper_f is not None else None,
            "bb_lower": round(lower_f, 2) if lower_f is not None else None,
            "bb_mid": round((upper_f + lower_f) / 2, 2) if upper_f and lower_f else None,
            "bb_sigma": z,
            "bb_rating": rating,
            "bbp_signal": "",
            "error": "",
            "source": "tradingview_screener",
            "recommend_all": round(rec_all, 2),
        }
    # Preserve input order; mark missing
    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        s = str(sym).upper().strip().split(":")[-1]
        if s in by_sym:
            rows.append(by_sym[s])
        else:
            rows.append({"symbol": s, "error": "not_in_screener_response", "source": "tradingview_screener"})
    return rows


def enrich_symbols(
    symbols: Sequence[str],
    *,
    interval: str = "1d",
    throttle: Optional[float] = None,
    force: bool = False,
    retries: int = 2,
) -> Dict[str, Any]:
    """Batch enrich. Prefer screener set_tickers; fall back to tradingview_ta."""
    if not force and not tv_ta_enabled():
        return {
            "enabled": False,
            "skipped": True,
            "reason": "TRADING_AGENT_TV_TA off",
            "symbols": [],
        }
    rows = _enrich_via_screener(symbols, interval=interval)
    # If screener returned nothing usable, fall back to per-symbol TA
    if not rows or all(r.get("error") for r in rows):
        gap = _throttle_seconds() if throttle is None else max(0.0, float(throttle))
        rows = []
        for i, sym in enumerate(symbols):
            if i and gap:
                time.sleep(gap)
            snap = fetch_symbol_analysis(str(sym), interval=interval)
            attempt = 0
            while (
                snap.error
                and attempt < max(0, int(retries))
                and any(
                    x in snap.error.lower()
                    for x in ("http", "rate", "429", "503", "timeout", "can't access")
                )
            ):
                attempt += 1
                time.sleep(gap * (1.5 + attempt) + 1.0)
                snap = fetch_symbol_analysis(str(sym), interval=interval)
            rows.append(snap.as_dict())
    ok_n = sum(1 for r in rows if not r.get("error"))
    return {
        "enabled": True,
        "skipped": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interval": interval,
        "count": len(rows),
        "ok_count": ok_n,
        "error_count": len(rows) - ok_n,
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
        # Over-fetch then filter OTC/pennies so we still return `limit` clean rows
        fetch_n = max(int(limit) * 4, int(limit) + 20)
        q = (
            Query()
            .select("name", "close", "Recommend.All", "BBPower", "RSI", "volume")
            .where(col("Recommend.All") > float(min_recommend))
            .order_by("volume", ascending=False)
            .limit(fetch_n)
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
            close = rec.get("close")
            try:
                close_f = float(close) if close is not None else None
            except (TypeError, ValueError):
                close_f = None
            # Drop OTC micro-pennies / noise by default
            skip_otc = os.getenv("TRADING_AGENT_TV_TA_INCLUDE_OTC", "").strip().lower() not in (
                "1",
                "true",
                "yes",
                "on",
            )
            if skip_otc and ticker.upper().startswith("OTC:"):
                continue
            if close_f is not None and close_f < 1.0:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "symbol": sym.upper(),
                    "name": rec.get("name"),
                    "close": round(close_f, 2) if close_f is not None else None,
                    "recommend_all": round(float(rec.get("Recommend.All") or 0), 2),
                    "bb_power": round(float(rec.get("BBPower") or 0), 2),
                    "rsi": round(float(rec.get("RSI") or 0), 1),
                    "volume": int(float(rec.get("volume") or 0)),
                }
            )
            if len(rows) >= int(limit):
                break
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


def format_tv_ta_report(pack: Dict[str, Any], *, for_discord: bool = True) -> str:
    """Discord-friendly fixed-width block (markdown tables render poorly)."""
    if pack.get("skipped"):
        return f"TV TA skipped — {pack.get('reason')}"
    when = str(pack.get("generated_at") or "")[:19].replace("T", " ")
    interval = pack.get("interval") or "1d"
    ok_n = pack.get("ok_count")
    err_n = pack.get("error_count")
    if ok_n is None:
        rows_all = pack.get("symbols") or []
        ok_n = sum(1 for r in rows_all if not r.get("error"))
        err_n = len(rows_all) - ok_n

    header = (
        f"TradingView TA · enrich ({interval})\n"
        f"{when} UTC · ok {ok_n}"
        + (f" · errors {err_n}" if err_n else "")
    )
    # Fixed-width columns inside a code fence
    col = (
        f"{'Sym':<6} {'Rec':<10} {'B/S/N':<9} {'Osc':<10} "
        f"{'MA':<10} {'BB':<11} {'σ':>5} {'RSI':>5}"
    )
    lines = [col, "-" * len(col)]
    failed: List[str] = []
    for r in pack.get("symbols") or []:
        sym = str(r.get("symbol") or "?")[:6]
        if r.get("error"):
            failed.append(sym)
            continue
        bsn = (
            f"{int(r.get('buy') or 0)}/"
            f"{int(r.get('sell') or 0)}/"
            f"{int(r.get('neutral') or 0)}"
        )
        lines.append(
            f"{sym:<6} {_short_rec(r.get('recommendation')):<10} "
            f"{bsn:<9} "
            f"{_short_rec(r.get('oscillators')):<10} "
            f"{_short_rec(r.get('moving_averages')):<10} "
            f"{str(r.get('bb_rating') or '—')[:11]:<11} "
            f"{_fmt_num(r.get('bb_sigma'), 2):>5} "
            f"{_fmt_num(r.get('rsi'), 1):>5}"
        )
    body = "\n".join(lines)
    if for_discord:
        out = f"{header}\n```\n{body}\n```"
    else:
        out = f"{header}\n{body}"
    if failed:
        out += f"\n_Failed ({len(failed)}): {', '.join(failed)}_ — rate-limit/retry later"
    # BB hits section if present
    hits = pack.get("hits")
    if hits is not None:
        out += f"\n**BB extreme (|σ|≥{pack.get('min_abs_sigma', 2)}):** {len(hits)}"
        if hits:
            hit_lines = [
                f"{h.get('symbol'):<6} {str(h.get('bb_rating') or ''):<11} "
                f"σ={_fmt_num(h.get('bb_sigma'), 2)}  {_short_rec(h.get('recommendation'))}"
                for h in hits[:20]
            ]
            out += "\n```\n" + "\n".join(hit_lines) + "\n```"
    return out


def format_rating_scan_report(pack: Dict[str, Any], *, for_discord: bool = True) -> str:
    if pack.get("skipped"):
        return f"TV rating scan skipped — {pack.get('reason')}"
    if pack.get("error"):
        return f"TV rating scan error — {pack.get('error')}"
    when = str(pack.get("generated_at") or "")[:19].replace("T", " ")
    header = (
        f"TradingView · rating screener ({pack.get('market')})\n"
        f"Recommend.All > {pack.get('min_recommend')} · "
        f"shown {pack.get('count')} / ~{pack.get('scanner_total')} · {when} UTC"
    )
    col = f"{'Ticker':<14} {'Close':>8} {'Rec':>5} {'BBPwr':>7} {'RSI':>5} {'Vol':>7}"
    lines = [col, "-" * len(col)]
    for r in pack.get("rows") or []:
        ticker = str(r.get("ticker") or r.get("symbol") or "?")
        if len(ticker) > 14:
            ticker = ticker[:14]
        lines.append(
            f"{ticker:<14} {_fmt_num(r.get('close'), 2):>8} "
            f"{_fmt_num(r.get('recommend_all'), 2):>5} "
            f"{_fmt_num(r.get('bb_power'), 2):>7} "
            f"{_fmt_num(r.get('rsi'), 1):>5} "
            f"{_fmt_vol(r.get('volume')):>7}"
        )
    body = "\n".join(lines)
    if for_discord:
        return f"{header}\n```\n{body}\n```"
    return f"{header}\n{body}"


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


DEFAULT_TV_TA_CHANNEL_ID = "1539794451612958761"


def post_tv_ta_discord(
    text: str,
    *,
    title: str = "TradingView TA research",
    channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a TV TA report to the dedicated Discord research channel.

    Uses bot token + ``DISCORD_TV_TA_CHANNEL_ID`` (default
    ``1539794451612958761``). Fail-open dict on errors.
    """
    try:
        from trading_agent.discord.config import DiscordConfig
        from trading_agent.discord.poster import DiscordPostError, post_message
    except Exception as exc:  # noqa: BLE001
        return {"error": f"discord_import:{exc}"}

    cfg = DiscordConfig.tv_ta_channel_from_env()
    if channel_id:
        if cfg is None:
            from trading_agent.discord.env import load_project_env

            load_project_env()
            token = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN") or ""
            if not token:
                return {"error": "missing_discord_bot_token"}
            cfg = DiscordConfig(webhook_url=None, bot_token=token, channel_id=str(channel_id))
        else:
            cfg = DiscordConfig(
                webhook_url=None,
                bot_token=cfg.bot_token,
                channel_id=str(channel_id),
            )
    if cfg is None or not cfg.bot_token or not cfg.channel_id:
        return {"error": "missing_discord_bot_or_tv_ta_channel"}

    body = (text or "").strip()
    if not body:
        return {"skipped": True, "reason": "empty"}
    # Don't spam the channel with all-failed enrich cards
    if "ok 0" in body and "errors" in body and "Failed" in body:
        return {"skipped": True, "reason": "all_symbols_failed"}
    header = f"**{title}** · research only (not OMS)\n"
    content = header + body
    try:
        results = post_message(content, cfg, username="Trading Agent TV TA")
        return {
            "ok": True,
            "channel_id": cfg.channel_id,
            "chunks": len(results),
            "results": results,
        }
    except DiscordPostError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:300]}
