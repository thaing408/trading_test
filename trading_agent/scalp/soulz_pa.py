"""Soulz-style PA scalping: BRR + Range + Fibonacci + confluence.

Paper / research only (synthetic premium path). Inspired by CryptoSoulz
(@SoulzBTC) "BEST Scalping Strategies" framing:

1. **BRR** — Break → Retest → Rally (continuation after structure break)
2. **Range** — Trade range edges (sweep/reject) or skip mid-box
3. **Fibonacci** — Pullback into 38.2–61.8 of last impulse for entry zone
4. **Combine** — Prefer entries with ≥2 of the above agreeing

Not affiliated with Soulz; educational reimplementation of common PA tactics.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.odte.backtest import (
    OdteBacktestResult,
    OdteTrade,
    _session_days,
    _to_et_index,
)
from trading_agent.odte.multidte import fetch_htf_bars
from trading_agent.odte.top_winners import simulate_premium_path_l3

ET = ZoneInfo("America/New_York")


@dataclass
class SoulzPaConfig:
    symbol: str = "BTC-USD"
    # Range: rolling window of bars for high/low box
    range_lookback: int = 24
    range_edge_tol_pct: float = 0.20  # % of range height near edge
    range_min_height_pct: float = 0.15  # min (high-low)/mid %
    # BRR
    break_lookback: int = 12
    break_buffer_pct: float = 0.05  # close beyond swing by this % of price
    retest_tol_pct: float = 0.25  # how close retest must come to broken level
    retest_max_bars: int = 18  # bars after break to allow retest
    # Fib zone on last impulse
    fib_lo: float = 0.382
    fib_hi: float = 0.618
    impulse_lookback: int = 30
    # Confluence
    min_confluence: int = 2  # need ≥2 of {brr, range, fib}
    allow_single_brr: bool = False  # if True, BRR alone can fire
    allow_single_range: bool = False
    # Sides
    calls_only: bool = False  # False = both CALL and PUT
    puts_only: bool = False
    # Exits (premium)
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.20
    premium_delta: float = 0.45
    entry_prem: float = 1.0
    contracts: int = 1
    use_trail: bool = True
    trail_activate_pct: float = 0.12
    trail_giveback_pct: float = 0.08
    time_exit_et: time = time(15, 45)
    max_trades_per_day: int = 4
    # Session
    rth_only: bool = False  # crypto 24/7; stocks set True
    rth_open: time = time(9, 30)
    rth_close: time = time(16, 0)


@dataclass
class SoulzSignal:
    side: str  # CALL | PUT
    setup_tags: List[str]  # brr, range, fib
    confluence: int
    level: float
    level_name: str
    entry_spot: float
    stop_spot: float
    target_spot: float
    bar_index: int
    notes: List[str] = field(default_factory=list)


@dataclass
class SoulzBrief:
    symbol: str
    asof: str
    signals: List[SoulzSignal]
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ── Pure helpers ──────────────────────────────────────────────────────────


def _pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a - b) / abs(b) * 100.0


def rolling_range(
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    lookback: int,
) -> Tuple[float, float]:
    """Range high/low over bars [i-lookback+1, i] inclusive, excluding current optional.

    Uses bars ending at i-1 so the open of bar i is not in the defining window.
    """
    if i < 1:
        return float("nan"), float("nan")
    start = max(0, i - lookback)
    end = i  # exclusive of current for structure (use prior)
    if end <= start:
        return float("nan"), float("nan")
    rh = max(highs[start:end])
    rl = min(lows[start:end])
    return float(rh), float(rl)


def last_impulse(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    lookback: int,
) -> Tuple[float, float, str]:
    """Return (impulse_low, impulse_high, direction) for last swing in window."""
    start = max(0, i - lookback)
    if i - start < 5:
        return float("nan"), float("nan"), "none"
    window_h = highs[start:i]
    window_l = lows[start:i]
    window_c = closes[start:i]
    hi = float(max(window_h))
    lo = float(min(window_l))
    hi_i = start + int(np.argmax(window_h))
    lo_i = start + int(np.argmin(window_l))
    # Direction of last completed impulse: if high is more recent → up impulse
    if hi_i > lo_i:
        return lo, hi, "up"
    if lo_i > hi_i:
        return lo, hi, "down"
    # tie-break on net close
    if window_c[-1] >= window_c[0]:
        return lo, hi, "up"
    return lo, hi, "down"


def fib_zone(lo: float, hi: float, direction: str, fib_lo: float, fib_hi: float) -> Tuple[float, float]:
    """Price zone for pullback (between fib_lo and fib_hi of impulse)."""
    span = hi - lo
    if span <= 0 or direction == "none":
        return float("nan"), float("nan")
    if direction == "up":
        # retrace from hi toward lo
        z_hi = hi - span * fib_lo  # shallower (e.g. 38.2)
        z_lo = hi - span * fib_hi  # deeper (e.g. 61.8)
        return min(z_lo, z_hi), max(z_lo, z_hi)
    # down impulse: retrace from lo toward hi
    z_lo = lo + span * fib_lo
    z_hi = lo + span * fib_hi
    return min(z_lo, z_hi), max(z_lo, z_hi)


def detect_brr_long(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    """BRR long: break above swing high, retest holds, rally candle."""
    if i < cfg.break_lookback + 2:
        return None
    # Find break bar in recent past
    for b in range(i - cfg.retest_max_bars, i):
        if b < cfg.break_lookback:
            continue
        rh, _ = rolling_range(highs, lows, b, cfg.break_lookback)
        if rh != rh:
            continue
        buf = rh * (cfg.break_buffer_pct / 100.0)
        # break bar: close above prior range high
        if closes[b] <= rh + buf:
            continue
        level = rh
        # after break, retest: low comes within tol of level, then current close > level
        retested = False
        for t in range(b + 1, i + 1):
            tol = level * (cfg.retest_tol_pct / 100.0)
            if lows[t] <= level + tol and lows[t] >= level - tol * 2:
                retested = True
            if retested and t == i and closes[i] > level and closes[i] >= opens_safe(closes, highs, lows, i):
                return level, f"brr_long@{level:.4f}"
    return None


def opens_safe(closes, highs, lows, i) -> float:
    # approximate open as prior close if no opens series
    return float(closes[i - 1]) if i > 0 else float(closes[i])


def detect_brr_short(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    if i < cfg.break_lookback + 2:
        return None
    for b in range(i - cfg.retest_max_bars, i):
        if b < cfg.break_lookback:
            continue
        _, rl = rolling_range(highs, lows, b, cfg.break_lookback)
        if rl != rl:
            continue
        buf = rl * (cfg.break_buffer_pct / 100.0)
        if closes[b] >= rl - buf:
            continue
        level = rl
        retested = False
        for t in range(b + 1, i + 1):
            tol = level * (cfg.retest_tol_pct / 100.0)
            if highs[t] >= level - tol and highs[t] <= level + tol * 2:
                retested = True
            if retested and t == i and closes[i] < level and closes[i] <= opens_safe(closes, highs, lows, i):
                return level, f"brr_short@{level:.4f}"
    return None


def detect_range_long(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    rh, rl = rolling_range(highs, lows, i, cfg.range_lookback)
    if rh != rh or rl != rl or rh <= rl:
        return None
    height = rh - rl
    mid = (rh + rl) / 2.0
    if mid <= 0 or (height / mid) * 100 < cfg.range_min_height_pct:
        return None
    edge = height * (cfg.range_edge_tol_pct / 100.0) * 5  # scale: use fraction of height
    edge = height * 0.15  # within bottom 15% of range
    # near lows + bullish close (rejection)
    if lows[i] <= rl + edge and closes[i] > opens_safe(closes, highs, lows, i) and closes[i] > (rl + height * 0.2):
        # avoid mid-range
        if closes[i] < mid:
            return rl, f"range_long@{rl:.4f}"
    return None


def detect_range_short(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    rh, rl = rolling_range(highs, lows, i, cfg.range_lookback)
    if rh != rh or rl != rl or rh <= rl:
        return None
    height = rh - rl
    mid = (rh + rl) / 2.0
    if mid <= 0 or (height / mid) * 100 < cfg.range_min_height_pct:
        return None
    edge = height * 0.15
    if highs[i] >= rh - edge and closes[i] < opens_safe(closes, highs, lows, i) and closes[i] < (rh - height * 0.2):
        if closes[i] > mid:
            return rh, f"range_short@{rh:.4f}"
    return None


def detect_fib_long(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    lo, hi, direction = last_impulse(closes, highs, lows, i, cfg.impulse_lookback)
    if direction != "up" or lo != lo:
        return None
    z_lo, z_hi = fib_zone(lo, hi, "up", cfg.fib_lo, cfg.fib_hi)
    c = closes[i]
    # in fib zone + bounce (close > open, low tagged zone)
    if z_lo <= c <= z_hi or (lows[i] <= z_hi and closes[i] >= z_lo):
        if lows[i] <= z_hi and closes[i] > opens_safe(closes, highs, lows, i) and closes[i] >= z_lo:
            mid = (z_lo + z_hi) / 2
            return mid, f"fib_long_{cfg.fib_lo:.0%}-{cfg.fib_hi:.0%}"
    return None


def detect_fib_short(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
) -> Optional[Tuple[float, str]]:
    lo, hi, direction = last_impulse(closes, highs, lows, i, cfg.impulse_lookback)
    if direction != "down" or lo != lo:
        return None
    z_lo, z_hi = fib_zone(lo, hi, "down", cfg.fib_lo, cfg.fib_hi)
    if highs[i] >= z_lo and closes[i] < opens_safe(closes, highs, lows, i) and closes[i] <= z_hi:
        mid = (z_lo + z_hi) / 2
        return mid, f"fib_short_{cfg.fib_lo:.0%}-{cfg.fib_hi:.0%}"
    return None


def evaluate_bar_signal(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    cfg: SoulzPaConfig,
    *,
    opens: Sequence[float] | None = None,
) -> Optional[SoulzSignal]:
    """Combine BRR + Range + Fib; return signal if confluence met."""
    if i < max(cfg.range_lookback, cfg.break_lookback, 10) + 2:
        return None

    tags_long: List[str] = []
    tags_short: List[str] = []
    levels_long: List[Tuple[float, str]] = []
    levels_short: List[Tuple[float, str]] = []
    notes: List[str] = []

    brr_l = detect_brr_long(closes, highs, lows, i, cfg)
    if brr_l:
        tags_long.append("brr")
        levels_long.append(brr_l)
    brr_s = detect_brr_short(closes, highs, lows, i, cfg)
    if brr_s:
        tags_short.append("brr")
        levels_short.append(brr_s)

    rng_l = detect_range_long(closes, highs, lows, i, cfg)
    if rng_l:
        tags_long.append("range")
        levels_long.append(rng_l)
    rng_s = detect_range_short(closes, highs, lows, i, cfg)
    if rng_s:
        tags_short.append("range")
        levels_short.append(rng_s)

    fib_l = detect_fib_long(closes, highs, lows, i, cfg)
    if fib_l:
        tags_long.append("fib")
        levels_long.append(fib_l)
    fib_s = detect_fib_short(closes, highs, lows, i, cfg)
    if fib_s:
        tags_short.append("fib")
        levels_short.append(fib_s)

    def _pick(side: str, tags: List[str], levels: List[Tuple[float, str]]) -> Optional[SoulzSignal]:
        if not tags:
            return None
        conf = len(set(tags))
        allow = conf >= cfg.min_confluence
        if not allow:
            if conf == 1 and "brr" in tags and cfg.allow_single_brr:
                allow = True
            if conf == 1 and "range" in tags and cfg.allow_single_range:
                allow = True
        if not allow:
            return None
        level = levels[0][0]
        name = "+".join(sorted(set(tags))) + ":" + levels[0][1]
        spot = float(closes[i])
        if side == "CALL":
            stop = min(float(lows[i]), level) * 0.998
            target = spot + (spot - stop) * 1.5
        else:
            stop = max(float(highs[i]), level) * 1.002
            target = spot - (stop - spot) * 1.5
        return SoulzSignal(
            side=side,
            setup_tags=sorted(set(tags)),
            confluence=conf,
            level=level,
            level_name=name,
            entry_spot=spot,
            stop_spot=stop,
            target_spot=target,
            bar_index=i,
            notes=notes + [f"confluence={conf}"],
        )

    if cfg.puts_only:
        return _pick("PUT", tags_short, levels_short)
    if cfg.calls_only:
        return _pick("CALL", tags_long, levels_long)

    # Prefer higher confluence; tie → skip dual conflict
    long_s = _pick("CALL", tags_long, levels_long)
    short_s = _pick("PUT", tags_short, levels_short)
    if long_s and short_s:
        if long_s.confluence > short_s.confluence:
            return long_s
        if short_s.confluence > long_s.confluence:
            return short_s
        return None  # conflict
    return long_s or short_s


# ── Data + backtest ───────────────────────────────────────────────────────


def fetch_soulz_bars(
    symbol: str,
    period: str = "60d",
    interval: str = "15m",
    *,
    source: str = "yfinance",
):
    """Load bars; crypto symbols use yfinance 15m/5m."""
    yf_period = period
    if period.strip().lower() in ("1mo", "mo", "month"):
        yf_period = "60d" if interval in ("5m", "15m") else "1mo"
    # Yahoo 15m ~60d
    try:
        df = fetch_htf_bars(symbol, period=yf_period, interval=interval, source=source)
        return df
    except Exception:
        # try hyphen form for crypto
        alt = symbol.replace("-", "") if "-" in symbol else f"{symbol}-USD"
        if alt != symbol:
            return fetch_htf_bars(alt, period=yf_period, interval=interval, source=source)
        raise


def _in_session(ts, cfg: SoulzPaConfig) -> bool:
    if not cfg.rth_only:
        return True
    t = ts.timetz().replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts.time()
    return cfg.rth_open <= t <= cfg.rth_close


def run_soulz_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "60d",
    interval: str = "15m",
    cfg: SoulzPaConfig | None = None,
    data_source: str = "yfinance",
    df=None,
) -> OdteBacktestResult:
    """Backtest Soulz PA confluence with synthetic option premium."""
    cfg = cfg or SoulzPaConfig(symbol=symbol)
    cfg.symbol = symbol
    if df is None:
        df = fetch_soulz_bars(symbol, period=period, interval=interval, source=data_source)
    df = df.copy()
    df.index = _to_et_index(df)

    closes = df["Close"].astype(float).tolist()
    highs = df["High"].astype(float).tolist()
    lows = df["Low"].astype(float).tolist()
    times = list(df.index)

    trades: List[OdteTrade] = []
    equity = 0.0
    curve = [0.0]
    day_counts: Dict[str, int] = defaultdict(int)
    i = max(cfg.range_lookback, cfg.break_lookback, cfg.impulse_lookback) + 2
    n = len(closes)

    while i < n - 2:
        ts = times[i]
        if not _in_session(ts, cfg):
            i += 1
            continue
        day_key = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        if day_counts[day_key] >= cfg.max_trades_per_day:
            i += 1
            continue

        sig = evaluate_bar_signal(closes, highs, lows, i, cfg)
        if sig is None:
            i += 1
            continue

        entry_spot = sig.entry_spot
        entry_prem = cfg.entry_prem
        # path after entry bar
        j0 = i + 1
        # hold until end of day or max 40 bars
        j1 = min(n, i + 40)
        # clip to same calendar day if RTH equity style
        if cfg.rth_only:
            d0 = times[i].date()
            while j1 > j0 and times[j1 - 1].date() != d0:
                j1 -= 1
        if j1 <= j0:
            i += 1
            continue

        path_h = highs[j0:j1]
        path_l = lows[j0:j1]
        path_c = closes[j0:j1]
        path_t = times[j0:j1]
        ep, exit_spot, reason, exit_tm = simulate_premium_path_l3(
            sig.side,
            entry_spot,
            path_h,
            path_l,
            path_c,
            path_t,
            entry_prem=entry_prem,
            tp_pct=cfg.take_profit_pct,
            sl_pct=cfg.stop_loss_pct,
            delta=cfg.premium_delta,
            time_exit_et=cfg.time_exit_et if cfg.rth_only else None,
            use_trail=cfg.use_trail,
            trail_activate_pct=cfg.trail_activate_pct,
            trail_giveback_pct=cfg.trail_giveback_pct,
        )
        pnl_pct = (ep - entry_prem) / entry_prem
        pnl_dollars = (ep - entry_prem) * 100 * cfg.contracts
        equity += pnl_dollars
        curve.append(equity)
        day_counts[day_key] += 1
        exit_s = exit_tm.isoformat() if hasattr(exit_tm, "isoformat") else str(exit_tm)
        trades.append(
            OdteTrade(
                day=day_key,
                side=sig.side,
                level_name=sig.level_name,
                level=sig.level,
                entry_time=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                exit_time=exit_s,
                entry_spot=entry_spot,
                exit_spot=float(exit_spot),
                entry_prem=entry_prem,
                exit_prem=float(ep),
                exit_reason=reason,
                pnl_pct=round(pnl_pct, 4),
                pnl_dollars=round(pnl_dollars, 2),
                rsi_at_entry=float(sig.confluence),
            )
        )
        # skip forward past exit bar to avoid re-firing same structure
        i = max(j0 + 1, j1)

    winners = [t for t in trades if t.pnl_dollars > 0]
    losers = [t for t in trades if t.pnl_dollars <= 0]
    total = sum(t.pnl_dollars for t in trades)
    gw = sum(t.pnl_dollars for t in winners)
    gl = abs(sum(t.pnl_dollars for t in losers))
    pf = gw / gl if gl else float(gw > 0)
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    by_side: Dict[str, Dict[str, float]] = {}
    for side in ("CALL", "PUT"):
        st = [t for t in trades if t.side == side]
        if not st:
            continue
        w = sum(1 for t in st if t.pnl_dollars > 0)
        by_side[side] = {
            "count": float(len(st)),
            "win_rate": w / len(st),
            "total_pnl": sum(t.pnl_dollars for t in st),
        }
    by_exit: Dict[str, int] = defaultdict(int)
    by_setup: Dict[str, int] = defaultdict(int)
    for t in trades:
        by_exit[t.exit_reason] += 1
        tag = t.level_name.split(":")[0] if ":" in t.level_name else t.level_name
        by_setup[tag] += 1

    days = _session_days(df) if len(df) else []
    return OdteBacktestResult(
        symbol=symbol,
        days=len(days),
        trade_count=len(trades),
        winners=len(winners),
        losers=len(losers),
        win_rate=round(len(winners) / len(trades), 4) if trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(trades), 2) if trades else 0.0,
        profit_factor=round(pf, 2),
        max_drawdown=round(max_dd, 2),
        avg_pnl_pct=round(float(np.mean([t.pnl_pct for t in trades])), 4) if trades else 0.0,
        by_side=by_side,
        by_exit=dict(by_exit),
        trades=trades,
        assumptions=[
            "Style: Soulz-inspired PA scalp (BRR + Range + Fib confluence)",
            f"Min confluence={cfg.min_confluence}; tags={{brr,range,fib}}",
            f"Interval={interval}; period={period}; source={data_source}",
            f"Premium ${cfg.entry_prem:.2f} delta={cfg.premium_delta}; "
            f"TP +{cfg.take_profit_pct:.0%} / SL −{cfg.stop_loss_pct:.0%}; "
            f"trail={'on' if cfg.use_trail else 'off'}",
            f"contracts={cfg.contracts}; max_trades/day={cfg.max_trades_per_day}",
            f"rth_only={cfg.rth_only}",
            "Synthetic premium model — not exchange fills",
        ],
        metadata={
            "style": "soulz_pa",
            "interval": interval,
            "period": period,
            "by_setup": dict(by_setup),
            "min_confluence": cfg.min_confluence,
            "take_profit_pct": cfg.take_profit_pct,
            "stop_loss_pct": cfg.stop_loss_pct,
        },
    )


def render_soulz_backtest(result: OdteBacktestResult) -> str:
    from trading_agent.odte.backtest import render_odte_backtest

    text = render_odte_backtest(result)
    lines = text.splitlines()
    if lines:
        lines[0] = f"# Soulz PA Scalp Backtest — {result.symbol}"
    by_setup = (result.metadata or {}).get("by_setup") or {}
    if by_setup:
        lines.append("")
        lines.append("## By setup tag cluster")
        for k, v in sorted(by_setup.items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append(
        "_Inspired by public PA education (BRR/range/fib confluence). "
        "Not financial advice; synthetic premium only._"
    )
    return "\n".join(lines) + "\n"


def run_soulz_brief(
    symbol: str = "QQQ",
    *,
    cfg: SoulzPaConfig | None = None,
    data_source: str = "yfinance",
    period: str = "10d",
    interval: str = "15m",
) -> SoulzBrief:
    cfg = cfg or SoulzPaConfig(symbol=symbol)
    cfg.symbol = symbol
    brief = SoulzBrief(
        symbol=symbol,
        asof=datetime.now(ET).isoformat(),
        signals=[],
        notes=[
            "BRR = Break → Retest → Rally/Run",
            "Range = edge rejection (not mid-box)",
            f"Fib pullback zone {cfg.fib_lo:.0%}–{cfg.fib_hi:.0%} of last impulse",
            f"Entry needs confluence ≥ {cfg.min_confluence} of {{brr, range, fib}}",
        ],
    )
    try:
        df = fetch_soulz_bars(symbol, period=period, interval=interval, source=data_source)
        df.index = _to_et_index(df)
        closes = df["Close"].astype(float).tolist()
        highs = df["High"].astype(float).tolist()
        lows = df["Low"].astype(float).tolist()
        # scan last 30 bars for active/recent signals
        start = max(cfg.range_lookback + 5, len(closes) - 30)
        for i in range(start, len(closes)):
            sig = evaluate_bar_signal(closes, highs, lows, i, cfg)
            if sig:
                brief.signals.append(sig)
        brief.signals = brief.signals[-5:]
        if not brief.signals:
            brief.notes.append("No confluence signal in recent bars")
    except Exception as exc:  # noqa: BLE001
        brief.errors.append(str(exc))
    return brief


def format_soulz_brief(brief: SoulzBrief) -> str:
    lines = [
        f"# Soulz PA Scalp Brief — {brief.symbol}",
        "",
        f"- **As of:** {brief.asof}",
        "",
        "## Recent confluence signals",
    ]
    if not brief.signals:
        lines.append("_none_")
    for s in brief.signals:
        lines.append(
            f"- **{s.side}** conf={s.confluence} tags={s.setup_tags} "
            f"@ {s.entry_spot:.2f} level={s.level:.2f} ({s.level_name})"
        )
        lines.append(
            f"  stop={s.stop_spot:.2f} target={s.target_spot:.2f}"
        )
    if brief.notes:
        lines.extend(["", "## Rules"])
        for n in brief.notes:
            lines.append(f"- {n}")
    if brief.errors:
        lines.extend(["", "## Errors"])
        for e in brief.errors:
            lines.append(f"- {e}")
    lines.append("")
    lines.append("_Paper rules only — not auto-execution._")
    return "\n".join(lines) + "\n"
