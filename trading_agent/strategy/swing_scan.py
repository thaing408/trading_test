"""Daily swing scanner — rank liquid names for multi-day holds.

Uses **daily** bars (default 1y / 1d):
  - Classical chart patterns (confirmed break preferred)
  - Market structure (HH/HL vs LH/LL)
  - EMA stack (20 / 50)
  - ATR% / ADR band (room to move, not dead)
  - Soft distance from 52-week range
  - Optional RS vs SPY when benchmark bars available

Not 0DTE: targets and stops are measured in **daily** structure units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")

# Liquid default if caller passes nothing
DEFAULT_SWING_UNIVERSE = (
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMD",
    "TSLA",
    "META",
    "AMZN",
    "GOOGL",
    "NFLX",
    "AVGO",
    "JPM",
    "XOM",
    "COST",
    "CRM",
    "ORCL",
    "PLTR",
    "SMCI",
)


@dataclass
class SwingScanConfig:
    bar_period: str = "1y"
    bar_interval: str = "1d"
    data_source: str = "yfinance"
    min_score: float = 58.0
    require_confirmed_pattern: bool = False  # True = only confirmed pattern PLAY
    allow_structure_only: bool = True  # trend+EMA pullback without named pattern
    min_atr_pct: float = 1.2  # daily ATR / price * 100
    max_atr_pct: float = 8.0
    ema_fast: int = 20
    ema_slow: int = 50
    measured_move_r: float = 1.0
    use_rs: bool = True
    rs_symbol: str = "SPY"
    max_symbols: int = 40
    # Soft: prefer names not extended > max_ext_pct above ema_fast for pullback style
    max_extension_pct: float = 12.0


@dataclass
class SwingCandidate:
    symbol: str
    play: bool
    side: str  # CALL | PUT | ""
    score: float
    style: str  # pattern | structure | both | none
    pattern_name: str = ""
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    atr_pct: float = 0.0
    trend: str = ""
    rs_score: float = 0.0  # relative vs SPY over ~60d, percentage points
    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    error: str = ""
    asof: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "play": self.play,
            "side": self.side,
            "score": self.score,
            "style": self.style,
            "pattern_name": self.pattern_name,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "atr_pct": self.atr_pct,
            "trend": self.trend,
            "rs_score": self.rs_score,
            "tags": list(self.tags),
            "reasons": list(self.reasons),
            "error": self.error,
            "asof": self.asof,
        }


def _ohlc(df) -> Tuple[List[float], List[float], List[float], List[float]]:
    opens = df["Open"].astype(float).tolist() if "Open" in df.columns else []
    highs = df["High"].astype(float).tolist()
    lows = df["Low"].astype(float).tolist()
    closes = df["Close"].astype(float).tolist()
    if not opens:
        opens = closes[:]
    return opens, highs, lows, closes


def _ema(series: Sequence[float], span: int) -> List[float]:
    if not series:
        return []
    alpha = 2.0 / (span + 1.0)
    out = [float(series[0])]
    for x in series[1:]:
        out.append(alpha * float(x) + (1 - alpha) * out[-1])
    return out


def _atr_pct(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 0.0
    trs: List[float] = []
    for i in range(1, len(closes)):
        h, l, pc = float(highs[i]), float(lows[i]), float(closes[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-n:]
    atr = sum(window) / len(window) if window else 0.0
    px = float(closes[-1])
    return (atr / px * 100.0) if px > 0 else 0.0


def _pct_change(closes: Sequence[float], lookback: int) -> float:
    if len(closes) <= lookback or float(closes[-1 - lookback]) <= 0:
        return 0.0
    return (float(closes[-1]) / float(closes[-1 - lookback]) - 1.0) * 100.0


def fetch_daily_bars(symbol: str, *, period: str, interval: str, source: str):
    from trading_agent.strategy.multi_method import fetch_bars

    return fetch_bars(symbol, period=period, interval=interval, source=source)


def score_swing_from_ohlc(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    cfg: SwingScanConfig | None = None,
    rs_closes: Optional[Sequence[float]] = None,
    symbol: str = "",
) -> SwingCandidate:
    """Score one symbol from daily OHLCV lists (pure, no I/O)."""
    cfg = cfg or SwingScanConfig()
    asof = datetime.now(ET).date().isoformat()
    n = len(closes)
    if n < max(cfg.ema_slow + 5, 40):
        return SwingCandidate(
            symbol=symbol,
            play=False,
            side="",
            score=0.0,
            style="none",
            reasons=["insufficient daily bars"],
            asof=asof,
        )

    from trading_agent.pa.chart_patterns import score_chart_pattern_entry, detect_all_chart_patterns
    from trading_agent.pa.structure import analyze_structure

    c = float(closes[-1])
    atrp = _atr_pct(highs, lows, closes)
    st = analyze_structure(highs, lows, closes, left=2, right=2)
    trend = st.trend or "unknown"
    e_fast = _ema(closes, cfg.ema_fast)
    e_slow = _ema(closes, cfg.ema_slow)
    ef, es = float(e_fast[-1]), float(e_slow[-1])

    tags: List[str] = [f"atr={atrp:.1f}%", f"trend={trend}"]
    reasons: List[str] = []
    score = 35.0

    # Volatility band
    if atrp < cfg.min_atr_pct:
        score -= 20.0
        reasons.append(f"ATR% {atrp:.1f} too quiet")
        tags.append("dead_vol")
    elif atrp > cfg.max_atr_pct:
        score -= 12.0
        reasons.append(f"ATR% {atrp:.1f} very wild")
        tags.append("high_vol")
    else:
        score += 10.0
        tags.append("vol_ok")

    # EMA stack / location
    long_stack = c > ef > es
    short_stack = c < ef < es
    pullback_long = ef > es and c >= ef * 0.97 and c <= ef * 1.03
    pullback_short = ef < es and c <= ef * 1.03 and c >= ef * 0.97
    ext_pct = abs(c / ef - 1.0) * 100.0 if ef > 0 else 0.0
    if long_stack:
        score += 14.0
        tags.append("ema_bull_stack")
    elif short_stack:
        score += 14.0
        tags.append("ema_bear_stack")
    elif pullback_long or pullback_short:
        score += 10.0
        tags.append("ema_pullback")
    else:
        score -= 5.0

    if ext_pct > cfg.max_extension_pct and long_stack:
        score -= 10.0
        tags.append("extended")
        reasons.append(f"extended {ext_pct:.1f}% above EMA{cfg.ema_fast}")

    # Structure
    if trend == "up":
        score += 10.0
    elif trend == "down":
        score += 10.0
    elif trend == "range":
        score += 2.0
        tags.append("range")
    else:
        score -= 3.0

    # 52w context (use series high/low as proxy for 1y period)
    series_hi = max(float(x) for x in highs)
    series_lo = min(float(x) for x in lows)
    span = series_hi - series_lo
    if span > 0:
        pos = (c - series_lo) / span  # 0 at low, 1 at high
        tags.append(f"range_pos={pos:.0%}")
        if 0.55 <= pos <= 0.95 and trend == "up":
            score += 6.0  # strength zone
        if 0.05 <= pos <= 0.45 and trend == "down":
            score += 6.0
        if pos > 0.98 and trend == "up":
            score -= 4.0  # melt-up risk
            tags.append("at_highs")

    # RS vs SPY
    rs = 0.0
    if rs_closes is not None and len(rs_closes) >= 60 and n >= 60:
        mine = _pct_change(closes, 60)
        bench = _pct_change(rs_closes, min(60, len(rs_closes) - 1))
        rs = mine - bench
        tags.append(f"rs60={rs:+.1f}pp")
        if rs > 3:
            score += 10.0
        elif rs > 0:
            score += 4.0
        elif rs < -5:
            score -= 10.0
        elif rs < 0:
            score -= 3.0

    # Chart patterns (daily)
    play_p, side_p, sc_p, tags_p, entry_p, stop_p, tgt_p = score_chart_pattern_entry(
        highs,
        lows,
        opens,
        closes,
        htf_direction=trend if trend in ("up", "down") else "",
        require_confirmed=cfg.require_confirmed_pattern,
        min_confidence=52.0,
        measured_move_r=cfg.measured_move_r,
    )
    patterns = detect_all_chart_patterns(highs, lows, closes)
    best_pat = patterns[0] if patterns else None
    pattern_name = best_pat.name if best_pat else ""
    if best_pat:
        tags.append(best_pat.name)
        tags.append(best_pat.status)
        score += min(22.0, sc_p * 0.25)
        if best_pat.status == "confirmed":
            score += 12.0
            reasons.append(f"pattern {best_pat.name} confirmed")
        elif best_pat.status == "approaching":
            score += 4.0
            reasons.append(f"pattern {best_pat.name} approaching")

    # Decide side: pattern and/or structure/EMA
    side = ""
    style = "none"
    entry = c
    stop = 0.0
    target = 0.0
    struct_side = ""
    s_entry = c
    s_stop = 0.0
    s_tgt = 0.0
    atr_abs = c * (atrp / 100.0) if atrp > 0 else c * 0.02

    if cfg.allow_structure_only:
        if trend == "up" and (long_stack or pullback_long) and rs >= -3:
            struct_side = "CALL"
            recent_lo = min(float(x) for x in lows[-5:]) if lows else ef
            s_stop = min(ef, recent_lo) * 0.995 if ef else recent_lo * 0.99
            if s_stop >= c:
                s_stop = c - 1.5 * atr_abs
            s_tgt = c + max((c - s_stop) * 2.0, atr_abs * 2.5)
        elif trend == "down" and (short_stack or pullback_short) and rs <= 3:
            struct_side = "PUT"
            recent_hi = max(float(x) for x in highs[-5:]) if highs else ef
            s_stop = max(ef, recent_hi) * 1.005 if ef else recent_hi * 1.01
            if s_stop <= c:
                s_stop = c + 1.5 * atr_abs
            s_tgt = c - max((s_stop - c) * 2.0, atr_abs * 2.5)

    pat_ok = bool(play_p and side_p in ("CALL", "PUT"))
    if pat_ok and struct_side and side_p == struct_side:
        side = side_p
        style = "both"
        entry, stop, target = entry_p, stop_p, tgt_p
        score = max(score, sc_p * 0.55 + score * 0.45) + 6.0
        tags.append("pattern+structure")
        reasons.append(f"structure {struct_side.lower()} agrees with pattern")
    elif pat_ok:
        side = side_p
        style = "pattern"
        entry, stop, target = entry_p, stop_p, tgt_p
        score = max(score, sc_p * 0.55 + score * 0.45)
    elif struct_side:
        side = struct_side
        style = "structure"
        entry, stop, target = s_entry, s_stop, s_tgt
        score += 8.0
        reasons.append(
            "structure long: uptrend + EMA support"
            if struct_side == "CALL"
            else "structure short: downtrend + EMA resistance"
        )

    # Align soft: don't fight structure if both present
    if side == "CALL" and trend == "down":
        score -= 15.0
        reasons.append("CALL vs down structure")
    if side == "PUT" and trend == "up":
        score -= 15.0
        reasons.append("PUT vs up structure")

    if tags_p:
        tags.extend([t for t in tags_p if t not in tags])

    score = float(min(100.0, max(0.0, score)))
    play = (
        side in ("CALL", "PUT")
        and score >= cfg.min_score
        and atrp >= cfg.min_atr_pct * 0.75  # slight soft floor
    )
    if cfg.require_confirmed_pattern and (not play_p or not best_pat or best_pat.status != "confirmed"):
        if style != "both":
            play = False
            if not reasons:
                reasons.append("need confirmed daily pattern")

    if play and not reasons:
        reasons.append(f"swing {side} score={score:.0f}")

    return SwingCandidate(
        symbol=symbol.upper() if symbol else "",
        play=play,
        side=side if play or score >= 45 else "",
        score=round(score, 1),
        style=style,
        pattern_name=pattern_name,
        entry=round(entry, 2) if entry else 0.0,
        stop=round(stop, 2) if stop else 0.0,
        target=round(target, 2) if target else 0.0,
        atr_pct=round(atrp, 2),
        trend=trend,
        rs_score=round(rs, 2),
        tags=tags[:16],
        reasons=reasons[:8],
        asof=asof,
    )


def evaluate_swing_symbol(
    symbol: str,
    *,
    cfg: SwingScanConfig | None = None,
    df=None,
    rs_closes: Optional[Sequence[float]] = None,
) -> SwingCandidate:
    """Fetch (or use) daily bars and score one symbol."""
    cfg = cfg or SwingScanConfig()
    sym = symbol.upper().strip()
    asof = datetime.now(ET).date().isoformat()
    try:
        if df is None:
            df = fetch_daily_bars(
                sym,
                period=cfg.bar_period,
                interval=cfg.bar_interval,
                source=cfg.data_source,
            )
        opens, highs, lows, closes = _ohlc(df)
        return score_swing_from_ohlc(
            highs,
            lows,
            opens,
            closes,
            cfg=cfg,
            rs_closes=rs_closes,
            symbol=sym,
        )
    except Exception as exc:  # noqa: BLE001
        return SwingCandidate(
            symbol=sym,
            play=False,
            side="",
            score=0.0,
            style="none",
            error=str(exc),
            reasons=[str(exc)],
            asof=asof,
        )


def resolve_swing_universe(
    symbols: Optional[Sequence[str]] = None,
    *,
    limit: int = 40,
) -> List[str]:
    """Resolve symbols: explicit → shared scanned_list → screener → defaults."""
    if symbols:
        out = [str(s).upper().strip() for s in symbols if str(s).strip()]
        return out[:limit] if limit > 0 else out
    try:
        from trading_agent.export.scanned_list import symbols_from_scanned_list

        shared = symbols_from_scanned_list(prefer="universe", limit=limit)
        if shared:
            return shared
    except Exception:
        pass
    try:
        from trading_agent.screener.universe import resolve_screener_symbols

        uni = resolve_screener_symbols()
        if uni:
            return [str(s).upper() for s in uni[:limit]]
    except Exception:
        pass
    try:
        from trading_agent.config import load_config

        cfg = load_config()
        uni = list(getattr(cfg, "symbols", None) or [])
        if uni:
            return [str(s).upper() for s in uni[:limit]]
    except Exception:
        pass
    try:
        from trading_agent.odte.top_winners import resolve_data_driven_pool

        pool, _ = resolve_data_driven_pool(max_symbols=limit)
        if pool:
            return [str(s).upper() for s in pool[:limit]]
    except Exception:
        pass
    return list(DEFAULT_SWING_UNIVERSE)[:limit]


def scan_swing_universe(
    symbols: Optional[Sequence[str]] = None,
    *,
    cfg: SwingScanConfig | None = None,
) -> List[SwingCandidate]:
    """Score many symbols; PLAY first then by score."""
    cfg = cfg or SwingScanConfig()
    syms = resolve_swing_universe(symbols, limit=cfg.max_symbols)
    rs_closes: Optional[List[float]] = None
    if cfg.use_rs:
        try:
            rdf = fetch_daily_bars(
                cfg.rs_symbol,
                period=cfg.bar_period,
                interval=cfg.bar_interval,
                source=cfg.data_source,
            )
            rs_closes = rdf["Close"].astype(float).tolist()
        except Exception:
            rs_closes = None

    out: List[SwingCandidate] = []
    for sym in syms:
        out.append(evaluate_swing_symbol(sym, cfg=cfg, rs_closes=rs_closes))
    out.sort(key=lambda c: (0 if c.play else 1, -c.score, c.symbol))
    return out


def format_swing_scan_report(
    candidates: Sequence[SwingCandidate],
    *,
    cfg: SwingScanConfig | None = None,
) -> str:
    cfg = cfg or SwingScanConfig()
    plays = [c for c in candidates if c.play]
    lines = [
        "# Daily swing scan",
        "",
        f"- **Bars:** {cfg.bar_period} / {cfg.bar_interval}  ·  **min score:** {cfg.min_score}",
        f"- **Scanned:** {len(candidates)}  ·  **PLAY:** {len(plays)}",
        f"- **Pattern required:** {cfg.require_confirmed_pattern}  ·  "
        f"**structure-only OK:** {cfg.allow_structure_only}",
        "",
        "## PLAY candidates",
        "",
    ]
    if not plays:
        lines.append("_No PLAY names at current thresholds._")
        lines.append("")
    else:
        lines.append("| Sym | Side | Score | Style | Pattern | Entry | Stop | Target | ATR% | RS60 | Trend |")
        lines.append("|-----|------|------:|-------|---------|------:|-----:|-------:|-----:|-----:|-------|")
        for c in plays:
            lines.append(
                f"| {c.symbol} | {c.side} | {c.score:.0f} | {c.style} | "
                f"{c.pattern_name or '—'} | {c.entry:.2f} | {c.stop:.2f} | "
                f"{c.target:.2f} | {c.atr_pct:.1f} | {c.rs_score:+.1f} | {c.trend} |"
            )
        lines.append("")
        for c in plays[:12]:
            why = "; ".join(c.reasons) if c.reasons else ",".join(c.tags[:5])
            lines.append(f"- **{c.symbol}** {c.side}: {why}")
        lines.append("")

    near = [c for c in candidates if not c.play and c.score >= cfg.min_score - 10 and c.score > 0]
    if near:
        lines.append("## Near miss (watch)")
        lines.append("")
        for c in near[:10]:
            lines.append(
                f"- {c.symbol} score={c.score:.0f} trend={c.trend} "
                f"pat={c.pattern_name or '—'} · {', '.join(c.tags[:4])}"
            )
        lines.append("")

    errs = [c for c in candidates if c.error]
    if errs:
        lines.append("## Data errors")
        lines.append("")
        for c in errs[:8]:
            lines.append(f"- {c.symbol}: {c.error[:80]}")
        lines.append("")

    lines.append(
        "_Hold thesis: days–weeks. Confirm earnings/calendar before size. "
        "Optional: use 15m multi-method only for entry timing._"
    )
    return "\n".join(lines)


def format_swing_scan_discord(
    candidates: Sequence[SwingCandidate],
    *,
    cfg: SwingScanConfig | None = None,
    max_plays: int = 12,
) -> str:
    """Compact Discord message (prefer under ~1800 chars before code fence)."""
    cfg = cfg or SwingScanConfig()
    plays = [c for c in candidates if c.play]
    asof = plays[0].asof if plays else (candidates[0].asof if candidates else "")
    lines = [
        f"**Daily swing scan** · {asof or 'today'}",
        f"Bars `{cfg.bar_period}/{cfg.bar_interval}` · min score **{cfg.min_score:.0f}** · "
        f"scanned **{len(candidates)}** · PLAY **{len(plays)}**",
        "",
    ]
    if not plays:
        lines.append("_No PLAY names — thresholds not met._")
        near = [c for c in candidates if not c.play and c.score >= cfg.min_score - 10 and c.score > 0]
        if near:
            lines.append("")
            lines.append("**Near miss**")
            for c in near[:6]:
                lines.append(
                    f"• `{c.symbol}` {c.score:.0f} {c.trend} {c.pattern_name or '—'}"
                )
        lines.append("")
        lines.append("_Multi-day holds · check earnings before size_")
        return "\n".join(lines)

    lines.append("```")
    lines.append(f"{'Sym':<6} {'Side':<5} {'Sc':>3} {'Style':<9} {'Pat':<14} {'Entry':>8} {'Stop':>8} {'Tgt':>8}")
    for c in plays[:max_plays]:
        pat = (c.pattern_name or "—")[:14]
        lines.append(
            f"{c.symbol:<6} {c.side:<5} {c.score:>3.0f} {c.style:<9} {pat:<14} "
            f"{c.entry:>8.2f} {c.stop:>8.2f} {c.target:>8.2f}"
        )
    if len(plays) > max_plays:
        lines.append(f"... +{len(plays) - max_plays} more")
    lines.append("```")
    lines.append("")
    for c in plays[:8]:
        why = ("; ".join(c.reasons[:2]) if c.reasons else ",".join(c.tags[:3]))[:120]
        lines.append(
            f"• **{c.symbol}** {c.side} · ATR {c.atr_pct:.1f}% · RS {c.rs_score:+.1f} · {why}"
        )
    lines.append("")
    lines.append("_Multi-day swing · not 0DTE · confirm calendar / size risk_")
    return "\n".join(lines)


def post_swing_scan_to_discord(
    candidates: Sequence[SwingCandidate],
    *,
    cfg: SwingScanConfig | None = None,
    username: str = "Swing Scan",
) -> Dict[str, Any]:
    """Post PLAY shortlist to Discord. Returns status dict (never raises for config miss)."""
    import os

    from trading_agent.discord.config import DiscordConfig
    from trading_agent.discord.poster import DiscordPostError, post_message

    body = format_swing_scan_discord(candidates, cfg=cfg)
    try:
        if not os.getenv("DISCORD_TOKEN") and os.getenv("DISCORD_BOT_TOKEN"):
            os.environ["DISCORD_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
        if os.getenv("DISCORD_DESK_CHANNEL_ID") and not os.getenv("DISCORD_CHANNEL_ID"):
            os.environ["DISCORD_CHANNEL_ID"] = os.environ["DISCORD_DESK_CHANNEL_ID"]
        # Prefer research/alerts channel when set
        channel = (
            os.getenv("DISCORD_SWING_CHANNEL_ID")
            or os.getenv("DISCORD_ALERTS_CHANNEL_ID")
            or os.getenv("DISCORD_RESEARCH_CHANNEL_ID")
            or os.getenv("DISCORD_DESK_CHANNEL_ID")
            or os.getenv("DISCORD_CHANNEL_ID")
        )
        dcfg = DiscordConfig.from_env()
        # Prefer explicit research/alerts channel via bot when token present
        if dcfg.bot_token and channel:
            dcfg = DiscordConfig(
                webhook_url=None,
                bot_token=dcfg.bot_token,
                channel_id=channel,
            )
        if not dcfg.webhook_url and not (dcfg.bot_token and dcfg.channel_id):
            return {
                "ok": False,
                "error": "Discord not configured (DISCORD_WEBHOOK_URL or TOKEN+CHANNEL_ID)",
                "body": body,
            }
        results = post_message(body, dcfg, username=username)
        return {"ok": True, "chunks": len(results), "body": body, "results": results}
    except DiscordPostError as exc:
        return {"ok": False, "error": str(exc), "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "body": body}


def write_swing_process_cards(
    candidates: Sequence[SwingCandidate],
    *,
    update_focus: bool = True,
    default_size: str = "1R",
    day=None,
) -> List[Dict[str, Any]]:
    """Write process trade cards for PLAY swing names."""
    from trading_agent.runbook.process import (
        ensure_day_state,
        load_day_state,
        upsert_focus_list,
        upsert_trade_card,
    )

    ensure_day_state(day)
    plays = [c for c in candidates if c.play]
    writes: List[Dict[str, Any]] = []
    if update_focus and plays:
        state = load_day_state(day)
        play_syms = [c.symbol for c in plays]
        rest = [s for s in state.focus_list if s not in play_syms]
        upsert_focus_list(play_syms + rest, day=day)

    for c in plays:
        trigger = (
            f"swing_daily {c.side} @ {c.entry:.2f} ({c.style}"
            f"{' ' + c.pattern_name if c.pattern_name else ''})"
        )
        stop = f"{c.stop:.2f} daily structure invalidation" if c.stop else "daily swing low/high"
        exit_plan = (
            f"target {c.target:.2f} (measured/2R); trail after +1R; multi-day hold"
            if c.target
            else "scale at +1R / +2R; honor daily stop"
        )
        why = (
            f"swing score={c.score:.0f} trend={c.trend} atr={c.atr_pct:.1f}% "
            f"rs={c.rs_score:+.1f}; " + "; ".join(c.reasons[:3])
        )
        try:
            upsert_trade_card(
                c.symbol,
                trigger=trigger[:240],
                stop=stop[:160],
                size_risk=default_size,
                exit_plan=exit_plan[:200],
                why=why[:280],
                day=day,
            )
            writes.append({"symbol": c.symbol, "written": True, "side": c.side})
        except Exception as exc:  # noqa: BLE001
            writes.append({"symbol": c.symbol, "written": False, "error": str(exc)})
    return writes
