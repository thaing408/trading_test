"""Multi-method ticker router: every symbol is evaluated by all playbooks.

Each ticker gets a **chance to play** if any registered method votes PLAY
(with optional multi-method confluence). Methods share one bar fetch.

Methods (paper / research):
  - soulz_pa     — BRR + range + fib confluence
  - top_winners  — drop-fast + TA/HTF + structure (0DTE CALL style)
  - orb_vwap     — opening-range break + VWAP
  - odte_breakout — OR high/low continuation (breakout style)
  - fvg          — fair value gap pullback + rejection
  - range_fade   — pure range-edge fade
  - sweep        — liquidity sweep + reclaim (failed breakout)
  - chart_patterns — classical H&S / double / triangle / flag (measured move)
  - process_methods — baseline process tags (risk/checklist soft score)

HTF bias (daily structure) soft-filters sides when available.

Not live OMS by default — produces ranked play/skip cards for desk prep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")

METHOD_IDS = (
    "soulz_pa",
    "top_winners",
    "orb_vwap",
    "odte_breakout",
    "fvg",
    "range_fade",
    "sweep",
    "chart_patterns",
    "process_methods",
)


@dataclass
class MethodVote:
    method_id: str
    play: bool
    side: str  # CALL | PUT | NEUTRAL | ""
    score: float  # 0–100
    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    error: str = ""


@dataclass
class TickerMultiEval:
    symbol: str
    play: bool
    decision: str  # PLAY | SKIP | CONFLICT | NO_DATA
    best_method: str
    best_side: str
    aggregate_score: float  # weighted avg of ALL method votes (incl. fails)
    play_methods: List[str] = field(default_factory=list)
    votes: List[MethodVote] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    asof: str = ""
    # Quality among methods that actually voted PLAY (export / ranking)
    play_quality_score: float = 0.0  # mean score of play votes
    best_play_score: float = 0.0  # max score among play votes
    export_eligible: bool = False  # passes auto-trade quality gate


@dataclass
class MultiMethodConfig:
    """Router policy: multi-method agreement preferred for PLAY and export."""

    min_method_score: float = 55.0
    # Default 2 = require-two (confluence); 1 = any single method
    min_play_methods: int = 2
    require_side_agreement: bool = True  # conflict if CALL and PUT both strong
    conflict_score_floor: float = 55.0  # only count methods above this for conflict
    enabled_methods: Tuple[str, ...] = METHOD_IDS
    bar_period: str = "10d"
    bar_interval: str = "15m"
    data_source: str = "yfinance"
    soulz_min_confluence: int = 2
    use_htf_bias: bool = True
    htf_strict: bool = False  # if True, block sides against HTF up/down
    # Auto-trade export quality (does not change PLAY decision by itself)
    export_min_play_methods: int = 2
    export_min_best_score: float = 65.0  # best play-method score
    export_min_play_avg_score: float = 65.0  # mean of play-method scores
    # Pass export if (methods>=N) and (best>=B or avg>=A)
    # weights for aggregate score (sum normalized)
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "soulz_pa": 1.0,
            "top_winners": 1.0,
            "orb_vwap": 1.0,
            "odte_breakout": 0.9,
            "fvg": 1.0,
            "range_fade": 0.95,
            "sweep": 1.0,
            "chart_patterns": 1.0,
            "process_methods": 0.5,
        }
    )


def play_votes_of(result: TickerMultiEval) -> List[MethodVote]:
    return [
        v
        for v in result.votes
        if v.play and v.method_id != "process_methods" and v.side in ("CALL", "PUT", "")
    ]


def compute_play_quality(result: TickerMultiEval) -> Tuple[float, float, List[str]]:
    """Return (best_play_score, play_avg_score, play_method_ids)."""
    votes = [
        v
        for v in result.votes
        if v.play and v.method_id != "process_methods"
    ]
    if not votes:
        return 0.0, 0.0, []
    scores = [float(v.score) for v in votes]
    ids = [v.method_id for v in votes]
    return max(scores), float(sum(scores) / len(scores)), ids


def passes_export_quality(
    result: TickerMultiEval,
    *,
    cfg: MultiMethodConfig | None = None,
) -> Tuple[bool, str]:
    """Auto-trade export gate: confluence + strength among *play* methods.

    Requires:
      - decision PLAY
      - len(play_methods) >= export_min_play_methods (default 2)
      - best_play_score >= export_min_best_score **or**
        play_quality_score (avg) >= export_min_play_avg_score (default 65)
    """
    cfg = cfg or MultiMethodConfig()
    if not result.play or result.decision != "PLAY":
        return False, "not_play"
    best_sc, avg_sc, ids = compute_play_quality(result)
    n = len(ids) if ids else len(result.play_methods)
    need_n = int(cfg.export_min_play_methods)
    if n < need_n:
        return False, f"play_methods {n}<{need_n}"
    min_best = float(cfg.export_min_best_score)
    min_avg = float(cfg.export_min_play_avg_score)
    if best_sc >= min_best or avg_sc >= min_avg:
        return True, f"ok best={best_sc:.0f} avg={avg_sc:.0f} n={n}"
    return (
        False,
        f"weak play scores best={best_sc:.0f}<{min_best:.0f} and "
        f"avg={avg_sc:.0f}<{min_avg:.0f}",
    )


def _to_et_index(df):
    idx = df.index
    if getattr(idx, "tz", None) is None:
        return idx.tz_localize(ET)
    return idx.tz_convert(ET)


def fetch_bars(symbol: str, *, period: str, interval: str, source: str):
    from trading_agent.odte.multidte import fetch_htf_bars

    try:
        df = fetch_htf_bars(symbol, period=period, interval=interval, source=source)
    except Exception:
        alt = f"{symbol}-USD" if "-" not in symbol else symbol.replace("-", "")
        df = fetch_htf_bars(alt, period=period, interval=interval, source=source)
    df = df.copy()
    df.index = _to_et_index(df)
    return df


# ── Per-method evaluators (shared df) ─────────────────────────────────────


def eval_soulz_pa(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    from trading_agent.scalp.soulz_pa import SoulzPaConfig, evaluate_bar_signal

    try:
        sc = SoulzPaConfig(
            symbol=symbol,
            min_confluence=cfg.soulz_min_confluence,
            rth_only=symbol.upper() not in ("BTC-USD", "ETH-USD", "BTCUSD", "ETHUSD"),
        )
        closes = df["Close"].astype(float).tolist()
        highs = df["High"].astype(float).tolist()
        lows = df["Low"].astype(float).tolist()
        # scan last 8 bars for a signal
        sig = None
        start = max(sc.range_lookback + 5, len(closes) - 8)
        for i in range(start, len(closes)):
            s = evaluate_bar_signal(closes, highs, lows, i, sc)
            if s is not None:
                sig = s
        if sig is None:
            return MethodVote(
                method_id="soulz_pa",
                play=False,
                side="",
                score=20.0,
                reasons=["no BRR/range/fib confluence on recent bars"],
            )
        score = min(100.0, 50.0 + sig.confluence * 20.0)
        return MethodVote(
            method_id="soulz_pa",
            play=score >= cfg.min_method_score,
            side=sig.side,
            score=score,
            tags=list(sig.setup_tags) + [f"conf={sig.confluence}"],
            reasons=[sig.level_name],
            entry=sig.entry_spot,
            stop=sig.stop_spot,
            target=sig.target_spot,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="soulz_pa", play=False, side="", score=0.0, error=str(exc), reasons=[str(exc)]
        )


def eval_top_winners(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    from trading_agent.odte.backtest import _day_slice, _session_days
    from trading_agent.odte.top_winners import TopWinnersConfig, evaluate_entry

    try:
        days = _session_days(df)
        if not days:
            return MethodVote(
                method_id="top_winners",
                play=False,
                side="",
                score=0.0,
                reasons=["no session days"],
            )
        d = days[-1]
        day_df = _day_slice(df, d)
        tw = TopWinnersConfig()
        # gap proxy from prior close
        gap = 0.0
        if len(days) >= 2:
            prev = _day_slice(df, days[-2])
            if not prev.empty and not day_df.empty:
                pc = float(prev["Close"].iloc[-1])
                o = float(day_df.iloc[0]["Open"])
                if pc > 0:
                    gap = (o - pc) / pc * 100.0
        entry = evaluate_entry(day_df, cfg=tw, full_df=df, day=d, gap_pct=gap)
        if entry.passed:
            score = 70.0
            if entry.ta:
                score = min(100.0, 55.0 + entry.ta.quality_score * 10.0)
            return MethodVote(
                method_id="top_winners",
                play=score >= cfg.min_method_score,
                side="CALL",
                score=score,
                tags=["continuation", f"gap={gap:.2f}%", f"rvol={entry.rvol}"],
                reasons=["drop-fast+TA pass"] + list(entry.reasons[:2]),
                entry=entry.drop.last_px if entry.drop else 0.0,
            )
        reasons = list(entry.reasons[:4]) or ["entry filters failed"]
        # partial credit
        score = 25.0
        if entry.drop and entry.drop.passed:
            score += 15
        if entry.ta and entry.ta.hard_pass:
            score += 15
        return MethodVote(
            method_id="top_winners",
            play=False,
            side="CALL" if score >= 40 else "",
            score=min(score, 54.0),
            tags=[],
            reasons=reasons,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="top_winners",
            play=False,
            side="",
            score=0.0,
            error=str(exc),
            reasons=[str(exc)],
        )


def eval_orb_vwap(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    """Latest RTH session: OR break + VWAP alignment."""
    try:
        rth = df.between_time(time(9, 30), time(16, 0))
        if rth.empty or len(rth) < 4:
            return MethodVote(
                method_id="orb_vwap",
                play=False,
                side="",
                score=15.0,
                reasons=["insufficient RTH bars"],
            )
        # last session day
        last_day = rth.index[-1].date()
        day = rth[[ts.date() == last_day for ts in rth.index]]
        if len(day) < 3:
            return MethodVote(
                method_id="orb_vwap",
                play=False,
                side="",
                score=15.0,
                reasons=["short session"],
            )
        # OR = first 2 × 15m bars ≈ 30m
        or_bars = day.iloc[:2]
        orh = float(or_bars["High"].max())
        orl = float(or_bars["Low"].min())
        # session VWAP
        typ = (day["High"] + day["Low"] + day["Close"]) / 3.0
        vol = day["Volume"].astype(float) if "Volume" in day.columns else None
        if vol is not None and float(vol.sum()) > 0:
            vwap = float((typ * vol).sum() / vol.sum())
        else:
            vwap = float(typ.mean())
        last = float(day["Close"].iloc[-1])
        tags: List[str] = []
        side = ""
        score = 30.0
        reasons: List[str] = [f"ORH={orh:.2f} ORL={orl:.2f} VWAP={vwap:.2f} last={last:.2f}"]
        if last > orh and last > vwap:
            side = "CALL"
            score = 75.0
            tags = ["or_break_up", "above_vwap"]
            reasons.append("close > OR high and > VWAP")
        elif last < orl and last < vwap:
            side = "PUT"
            score = 75.0
            tags = ["or_break_down", "below_vwap"]
            reasons.append("close < OR low and < VWAP")
        elif last > orh:
            side = "CALL"
            score = 50.0
            tags = ["or_break_up"]
            reasons.append("OR break up but not above VWAP")
        elif last < orl:
            side = "PUT"
            score = 50.0
            tags = ["or_break_down"]
            reasons.append("OR break down but not below VWAP")
        else:
            reasons.append("inside OR — no breakout")
        play = score >= cfg.min_method_score and side in ("CALL", "PUT")
        stop = (orh + orl) / 2.0
        target = last + (last - stop) * 1.5 if side == "CALL" else last - (stop - last) * 1.5
        return MethodVote(
            method_id="orb_vwap",
            play=play,
            side=side,
            score=score,
            tags=tags,
            reasons=reasons,
            entry=last,
            stop=stop,
            target=target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="orb_vwap", play=False, side="", score=0.0, error=str(exc), reasons=[str(exc)]
        )


def eval_odte_breakout(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    """Breakout playbook snapshot on latest bars (OR continuation)."""
    try:
        from trading_agent.odte.breakout import breakout_side_from_close

        rth = df.between_time(time(9, 30), time(16, 0))
        if rth.empty or len(rth) < 4:
            return MethodVote(
                method_id="odte_breakout",
                play=False,
                side="",
                score=15.0,
                reasons=["insufficient RTH bars"],
            )
        last_day = rth.index[-1].date()
        day = rth[[ts.date() == last_day for ts in rth.index]]
        or_bars = day.iloc[:2]
        orh = float(or_bars["High"].max())
        orl = float(or_bars["Low"].min())
        last = float(day["Close"].iloc[-1])
        side = breakout_side_from_close(last, orh, orl, require_close_beyond=True)
        if side is None:
            return MethodVote(
                method_id="odte_breakout",
                play=False,
                side="",
                score=25.0,
                reasons=[f"no close beyond OR ({orl:.2f}-{orh:.2f}) last={last:.2f}"],
            )
        score = 72.0
        return MethodVote(
            method_id="odte_breakout",
            play=score >= cfg.min_method_score,
            side=side,
            score=score,
            tags=["or_continuation", side.lower()],
            reasons=[f"close beyond OR → {side}"],
            entry=last,
            stop=(orh + orl) / 2.0,
            target=last * (1.01 if side == "CALL" else 0.99),
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="odte_breakout",
            play=False,
            side="",
            score=0.0,
            error=str(exc),
            reasons=[str(exc)],
        )


def _ohlc_lists(df):
    highs = df["High"].astype(float).tolist()
    lows = df["Low"].astype(float).tolist()
    closes = df["Close"].astype(float).tolist()
    opens = df["Open"].astype(float).tolist() if "Open" in df.columns else closes
    return opens, highs, lows, closes


def eval_fvg(symbol: str, df, cfg: MultiMethodConfig, *, htf_direction: str = "") -> MethodVote:
    try:
        opens, highs, lows, closes = _ohlc_lists(df)
        from trading_agent.pa.fvg import score_fvg_entry

        play, side, score, tags, entry, stop, target = score_fvg_entry(
            highs,
            lows,
            opens,
            closes,
            htf_direction=htf_direction,
            min_size_pct=0.08,
            require_rejection=True,
        )
        return MethodVote(
            method_id="fvg",
            play=play and score >= cfg.min_method_score,
            side=side,
            score=score,
            tags=tags,
            reasons=tags or ["no FVG entry"],
            entry=entry,
            stop=stop,
            target=target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="fvg", play=False, side="", score=0.0, error=str(exc), reasons=[str(exc)]
        )


def eval_range_fade(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    try:
        opens, highs, lows, closes = _ohlc_lists(df)
        from trading_agent.pa.range_fade import evaluate_range_fade

        sig = evaluate_range_fade(highs, lows, opens, closes)
        if not sig:
            return MethodVote(
                method_id="range_fade",
                play=False,
                side="",
                score=20.0,
                reasons=["no edge rejection in range"],
            )
        score = 72.0
        return MethodVote(
            method_id="range_fade",
            play=score >= cfg.min_method_score,
            side=sig.side,
            score=score,
            tags=["range_fade", sig.side.lower()],
            reasons=list(sig.notes),
            entry=sig.entry,
            stop=sig.stop,
            target=sig.target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="range_fade",
            play=False,
            side="",
            score=0.0,
            error=str(exc),
            reasons=[str(exc)],
        )


def eval_chart_patterns(
    symbol: str, df, cfg: MultiMethodConfig, *, htf_direction: str = ""
) -> MethodVote:
    try:
        opens, highs, lows, closes = _ohlc_lists(df)
        from trading_agent.pa.chart_patterns import score_chart_pattern_entry

        play, side, score, tags, entry, stop, target = score_chart_pattern_entry(
            highs,
            lows,
            opens,
            closes,
            htf_direction=htf_direction,
            require_confirmed=True,
        )
        reasons = list(tags) if tags else (["chart pattern PLAY"] if play else ["no confirmed chart pattern"])
        return MethodVote(
            method_id="chart_patterns",
            play=play and score >= cfg.min_method_score,
            side=side,
            score=score,
            tags=tags,
            reasons=reasons,
            entry=entry,
            stop=stop,
            target=target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="chart_patterns",
            play=False,
            side="",
            score=0.0,
            error=str(exc),
            reasons=[str(exc)],
        )


def eval_sweep(symbol: str, df, cfg: MultiMethodConfig) -> MethodVote:
    try:
        opens, highs, lows, closes = _ohlc_lists(df)
        from trading_agent.pa.levels import compute_key_levels
        from trading_agent.pa.sweep import detect_sweep_from_series, detect_sweep_reclaim

        sig = detect_sweep_from_series(highs, lows, opens, closes, lookback=20)
        # also try session OR / PD levels when available
        if sig is None:
            levels = compute_key_levels(df)
            if levels.or_high and levels.or_low:
                sig = detect_sweep_reclaim(
                    highs,
                    lows,
                    opens,
                    closes,
                    level_high=levels.or_high,
                    level_low=levels.or_low,
                )
            if sig is None and levels.pdh and levels.pdl:
                sig = detect_sweep_reclaim(
                    highs,
                    lows,
                    opens,
                    closes,
                    level_high=levels.pdh,
                    level_low=levels.pdl,
                )
        if not sig:
            return MethodVote(
                method_id="sweep",
                play=False,
                side="",
                score=18.0,
                reasons=["no sweep+reclaim"],
            )
        score = 74.0
        entry = float(closes[-1])
        if sig.side == "CALL":
            stop = sig.sweep_extreme * 0.998
            target = entry + (entry - stop) * 1.5
        else:
            stop = sig.sweep_extreme * 1.002
            target = entry - (stop - entry) * 1.5
        return MethodVote(
            method_id="sweep",
            play=score >= cfg.min_method_score,
            side=sig.side,
            score=score,
            tags=["sweep_reclaim", sig.side.lower()],
            reasons=list(sig.notes),
            entry=entry,
            stop=stop,
            target=target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="sweep", play=False, side="", score=0.0, error=str(exc), reasons=[str(exc)]
        )


def eval_process_methods(symbol: str, df, cfg: MultiMethodConfig, votes: List[MethodVote]) -> MethodVote:
    """Soft process/risk checklist using other method votes as context."""
    try:
        from trading_agent.methods.web_methods import BASELINE_METHODS, evaluate_methods_for_setup

        # pick best directional vote for context
        best = max(
            (v for v in votes if v.method_id != "process_methods"),
            key=lambda v: v.score,
            default=None,
        )
        entry = best.entry if best and best.entry else float(df["Close"].iloc[-1])
        stop = best.stop if best and best.stop else entry * 0.98
        target = best.target if best and best.target else entry * 1.02
        ctx = {
            "entry_price": entry,
            "stop_loss": stop,
            "profit_target": target,
            "checklist_passed": True,
            "edge_complete": bool(best and best.play),
            "timeframe_alignment": "aligned" if best and best.play else "mixed",
            "relative_volume": 1.5,
            "direction": (best.side if best else "") or "bullish",
            "setup_id": best.method_id if best else "",
            "proposed_risk_pct": 1.0,
            "max_risk_per_trade_pct": 2.0,
        }
        result = evaluate_methods_for_setup(BASELINE_METHODS, ctx)
        applied = list(result.get("method_ids_ok") or [])
        crit = bool(result.get("critical_fail"))
        n = max(len(BASELINE_METHODS), 1)
        ok_n = len(applied)
        score = 40.0 + 60.0 * (ok_n / n)
        if crit:
            score = min(score, 40.0)
        # Advisory only — never unlock PLAY by itself (filtered later)
        return MethodVote(
            method_id="process_methods",
            play=False,
            side=best.side if best else "",
            score=round(score, 1),
            tags=applied[:8],
            reasons=[
                f"process tags ok={ok_n}/{n}",
                "critical_fail" if crit else "no critical fail",
            ],
            entry=entry,
            stop=stop,
            target=target,
        )
    except Exception as exc:  # noqa: BLE001
        return MethodVote(
            method_id="process_methods",
            play=False,
            side="",
            score=0.0,
            error=str(exc),
            reasons=[str(exc)],
        )


EVALUATORS: Dict[str, Callable[..., MethodVote]] = {
    "soulz_pa": eval_soulz_pa,
    "top_winners": eval_top_winners,
    "orb_vwap": eval_orb_vwap,
    "odte_breakout": eval_odte_breakout,
    "fvg": eval_fvg,
    "range_fade": eval_range_fade,
    "sweep": eval_sweep,
    "chart_patterns": eval_chart_patterns,
}


def evaluate_ticker_all_methods(
    symbol: str,
    *,
    cfg: MultiMethodConfig | None = None,
    df=None,
) -> TickerMultiEval:
    """Run every enabled method on one ticker; decide PLAY / SKIP / CONFLICT."""
    cfg = cfg or MultiMethodConfig()
    sym = symbol.upper().strip()
    asof = datetime.now(ET).isoformat()
    if df is None:
        try:
            df = fetch_bars(
                sym,
                period=cfg.bar_period,
                interval=cfg.bar_interval,
                source=cfg.data_source,
            )
        except Exception as exc:  # noqa: BLE001
            return TickerMultiEval(
                symbol=sym,
                play=False,
                decision="NO_DATA",
                best_method="",
                best_side="",
                aggregate_score=0.0,
                reasons=[f"bar fetch failed: {exc}"],
                asof=asof,
            )

    # HTF bias (daily) for FVG filter + decision notes
    htf_direction = ""
    htf_note = ""
    if cfg.use_htf_bias:
        try:
            from trading_agent.pa.htf_bias import bias_allows_side, compute_htf_bias
            from trading_agent.pa.structure import analyze_structure

            # Prefer structure on provided bars as proxy; daily fetch optional
            _, highs, lows, closes = _ohlc_lists(df)
            st = analyze_structure(highs, lows, closes)
            htf_direction = st.trend if st.trend != "unknown" else "range"
            htf_note = f"structure_tf={htf_direction}"
            # Enrich with daily when network ok (soft fail)
            try:
                daily = compute_htf_bias(sym, period="6mo", interval="1d", source=cfg.data_source)
                if daily.direction not in ("", "unknown"):
                    htf_direction = daily.direction
                    htf_note = f"htf_daily={daily.direction}({daily.strength:.0f})"
            except Exception:
                pass
        except Exception:
            htf_direction = ""

    votes: List[MethodVote] = []
    for mid in cfg.enabled_methods:
        if mid == "process_methods":
            continue  # after others
        fn = EVALUATORS.get(mid)
        if fn is None:
            continue
        if mid == "fvg":
            votes.append(eval_fvg(sym, df, cfg, htf_direction=htf_direction))
        elif mid == "chart_patterns":
            votes.append(eval_chart_patterns(sym, df, cfg, htf_direction=htf_direction))
        else:
            votes.append(fn(sym, df, cfg))

    if "process_methods" in cfg.enabled_methods:
        votes.append(eval_process_methods(sym, df, cfg, votes))

    # Soft HTF filter: demote play votes that fight HTF when strict or always tag
    if htf_direction in ("up", "down"):
        from trading_agent.pa.htf_bias import HtfBias, bias_allows_side

        bias = HtfBias(direction=htf_direction, strength=60.0, source="router")
        for v in votes:
            if not v.play or v.side not in ("CALL", "PUT"):
                continue
            if not bias_allows_side(bias, v.side, strict=cfg.htf_strict):
                if cfg.htf_strict:
                    v.play = False
                    v.reasons.append(f"blocked by HTF {htf_direction}")
                    v.score = min(v.score, 50.0)
                else:
                    v.score = max(0.0, v.score - 12.0)
                    v.reasons.append(f"soft HTF conflict ({htf_direction})")
                    if v.score < cfg.min_method_score:
                        v.play = False

    # Aggregate
    wmap = cfg.weights or {}
    wsum = 0.0
    acc = 0.0
    for v in votes:
        w = float(wmap.get(v.method_id, 1.0))
        acc += v.score * w
        wsum += w
    aggregate = round(acc / wsum, 1) if wsum else 0.0

    play_votes = [
        v
        for v in votes
        if v.play and v.score >= cfg.min_method_score and v.method_id != "process_methods"
    ]

    def _quality(pv: List[MethodVote]) -> Tuple[float, float]:
        if not pv:
            return 0.0, 0.0
        sc = [float(v.score) for v in pv]
        return max(sc), float(sum(sc) / len(sc))

    # process_methods alone never unlocks
    if not play_votes:
        # still list best method by score
        best = max(votes, key=lambda v: v.score) if votes else None
        return TickerMultiEval(
            symbol=sym,
            play=False,
            decision="SKIP",
            best_method=best.method_id if best else "",
            best_side=best.side if best else "",
            aggregate_score=aggregate,
            play_methods=[],
            votes=votes,
            reasons=[
                f"no method cleared play (min_score={cfg.min_method_score}, "
                f"min_methods={cfg.min_play_methods})"
            ]
            + [f"{v.method_id}={v.score:.0f} play={v.play}" for v in votes]
            + ([htf_note] if htf_note else []),
            asof=asof,
            play_quality_score=0.0,
            best_play_score=0.0,
            export_eligible=False,
        )

    # Side conflict among strong plays
    strong = [v for v in play_votes if v.score >= cfg.conflict_score_floor and v.side in ("CALL", "PUT")]
    sides = {v.side for v in strong}
    if cfg.require_side_agreement and len(sides) > 1:
        bsc, asc = _quality(play_votes)
        return TickerMultiEval(
            symbol=sym,
            play=False,
            decision="CONFLICT",
            best_method="",
            best_side="",
            aggregate_score=aggregate,
            play_methods=[v.method_id for v in play_votes],
            votes=votes,
            reasons=[
                f"side conflict among methods: {sorted(sides)}",
                *[f"{v.method_id}→{v.side} ({v.score:.0f})" for v in strong],
            ],
            asof=asof,
            play_quality_score=round(asc, 1),
            best_play_score=round(bsc, 1),
            export_eligible=False,
        )

    if len(play_votes) < int(cfg.min_play_methods):
        bsc, asc = _quality(play_votes)
        return TickerMultiEval(
            symbol=sym,
            play=False,
            decision="SKIP",
            best_method=play_votes[0].method_id,
            best_side=play_votes[0].side,
            aggregate_score=aggregate,
            play_methods=[v.method_id for v in play_votes],
            votes=votes,
            reasons=[
                f"only {len(play_votes)} method(s) play; need ≥{cfg.min_play_methods}"
            ],
            asof=asof,
            play_quality_score=round(asc, 1),
            best_play_score=round(bsc, 1),
            export_eligible=False,
        )

    best = max(play_votes, key=lambda v: v.score)
    bsc, asc = _quality(play_votes)
    reasons = [
        f"PLAY via {', '.join(v.method_id for v in play_votes)}",
        f"best={best.method_id} side={best.side} score={best.score:.0f}",
        f"play_quality best={bsc:.0f} avg={asc:.0f} (n={len(play_votes)})",
    ]
    if htf_note:
        reasons.append(htf_note)
    result = TickerMultiEval(
        symbol=sym,
        play=True,
        decision="PLAY",
        best_method=best.method_id,
        best_side=best.side,
        aggregate_score=aggregate,
        play_methods=[v.method_id for v in play_votes],
        votes=votes,
        reasons=reasons,
        asof=asof,
        play_quality_score=round(asc, 1),
        best_play_score=round(bsc, 1),
        export_eligible=False,
    )
    ok_x, why_x = passes_export_quality(result, cfg=cfg)
    result.export_eligible = ok_x
    if ok_x:
        reasons.append(f"export_eligible: {why_x}")
    else:
        reasons.append(f"export_blocked: {why_x}")
    result.reasons = reasons
    return result


def evaluate_universe(
    symbols: Sequence[str],
    *,
    cfg: MultiMethodConfig | None = None,
) -> List[TickerMultiEval]:
    """Evaluate each ticker through all methods; return list (PLAY first)."""
    cfg = cfg or MultiMethodConfig()
    out: List[TickerMultiEval] = []
    for raw in symbols:
        sym = str(raw).upper().strip()
        if not sym:
            continue
        out.append(evaluate_ticker_all_methods(sym, cfg=cfg))
    out.sort(
        key=lambda t: (
            0 if t.decision == "PLAY" else 1 if t.decision == "CONFLICT" else 2,
            -t.aggregate_score,
            t.symbol,
        )
    )
    return out


@dataclass
class ProcessCardWrite:
    symbol: str
    written: bool
    trigger: str = ""
    stop: str = ""
    size_risk: str = ""
    exit_plan: str = ""
    why: str = ""
    message: str = ""


def trade_card_fields_from_eval(
    result: TickerMultiEval,
    *,
    default_size: str = "0.5R",
    default_exit: str = "plan: +1.5R or trail; honor method stop",
) -> Dict[str, str]:
    """Map a PLAY multi-eval into process trade-card fields."""
    best = None
    for v in result.votes:
        if v.method_id == result.best_method:
            best = v
            break
    if best is None and result.votes:
        best = max(result.votes, key=lambda v: v.score)

    side = result.best_side or (best.side if best else "")
    methods = ", ".join(result.play_methods) or (result.best_method or "multi")
    entry = best.entry if best and best.entry else 0.0
    stop_px = best.stop if best and best.stop else 0.0
    target_px = best.target if best and best.target else 0.0

    trigger = (
        f"{result.best_method} {side} @ {entry:.2f}"
        if entry > 0
        else f"{result.best_method} {side} signal"
    )
    if result.play_methods:
        trigger += f" (also: {methods})"

    if stop_px > 0:
        stop = f"{stop_px:.2f} ({side} invalidation / method stop)"
    else:
        stop = "structure stop per best method (set before open)"

    if target_px > 0:
        exit_plan = f"target {target_px:.2f}; {default_exit}"
    else:
        exit_plan = default_exit

    why = (
        f"multi-method PLAY agg={result.aggregate_score:.0f}; "
        f"best={result.best_method} {side}; methods=[{methods}]"
    )
    return {
        "trigger": trigger[:240],
        "stop": stop[:160],
        "size_risk": default_size,
        "exit_plan": exit_plan[:200],
        "why": why[:280],
    }


def write_process_cards_for_plays(
    results: Sequence[TickerMultiEval],
    *,
    update_focus: bool = True,
    default_size: str = "0.5R",
    day=None,
) -> List[ProcessCardWrite]:
    """Auto-create process trade cards (+ optional focus list) for PLAY tickers.

    Step 2/3 of the systematic runbook: focus list = PLAY symbols; each gets a card
    from the best method's levels. Does not set regime (Step 1 stays human).
    """
    from trading_agent.runbook.process import (
        ensure_day_state,
        load_day_state,
        upsert_focus_list,
        upsert_trade_card,
    )

    ensure_day_state(day)
    # Prefer export-eligible; fall back to all PLAY if none pass quality
    plays = [
        r
        for r in results
        if r.play and r.decision == "PLAY" and getattr(r, "export_eligible", True)
    ]
    if not plays:
        plays = [r for r in results if r.play and r.decision == "PLAY"]
    writes: List[ProcessCardWrite] = []

    if update_focus and plays:
        # Keep existing non-play focus names, prepend plays
        state = load_day_state(day)
        play_syms = [r.symbol for r in plays]
        rest = [s for s in state.focus_list if s not in play_syms]
        upsert_focus_list(play_syms + rest, day=day)

    for r in plays:
        fields = trade_card_fields_from_eval(r, default_size=default_size)
        try:
            upsert_trade_card(
                r.symbol,
                trigger=fields["trigger"],
                stop=fields["stop"],
                size_risk=fields["size_risk"],
                exit_plan=fields["exit_plan"],
                why=fields["why"],
                day=day,
            )
            writes.append(
                ProcessCardWrite(
                    symbol=r.symbol,
                    written=True,
                    trigger=fields["trigger"],
                    stop=fields["stop"],
                    size_risk=fields["size_risk"],
                    exit_plan=fields["exit_plan"],
                    why=fields["why"],
                    message="ok",
                )
            )
        except Exception as exc:  # noqa: BLE001
            writes.append(
                ProcessCardWrite(
                    symbol=r.symbol,
                    written=False,
                    message=str(exc),
                )
            )
    return writes


def format_multi_method_report(
    results: Sequence[TickerMultiEval],
    *,
    cfg: MultiMethodConfig | None = None,
    card_writes: Sequence[ProcessCardWrite] | None = None,
    book_export: Dict[str, Any] | None = None,
) -> str:
    cfg = cfg or MultiMethodConfig()
    plays = [r for r in results if r.play]
    exportable = [r for r in results if getattr(r, "export_eligible", False)]
    lines = [
        "# Multi-Method Ticker Router",
        "",
        f"- **Symbols:** {len(results)} · **PLAY:** {len(plays)} · "
        f"**export-eligible:** {len(exportable)} · "
        f"**min_method_score:** {cfg.min_method_score} · "
        f"**min_play_methods:** {cfg.min_play_methods}",
        f"- **Export gate:** ≥{cfg.export_min_play_methods} methods and "
        f"(best≥{cfg.export_min_best_score:.0f} or play-avg≥{cfg.export_min_play_avg_score:.0f})",
        f"- **Methods:** {', '.join(cfg.enabled_methods)}",
        "",
        "## Decisions",
        "",
    ]
    for r in results:
        icon = {"PLAY": "✅", "SKIP": "⬜", "CONFLICT": "⚡", "NO_DATA": "⛔"}.get(
            r.decision, "·"
        )
        exp = " · **EXPORT**" if getattr(r, "export_eligible", False) else ""
        lines.append(
            f"### {icon} **{r.symbol}** — {r.decision} "
            f"(agg {r.aggregate_score:.0f}/100 · playQ "
            f"{getattr(r, 'play_quality_score', 0):.0f}/{getattr(r, 'best_play_score', 0):.0f})"
            f"{exp}"
        )
        if r.play:
            lines.append(
                f"- Best: **{r.best_method}** → **{r.best_side}** · "
                f"methods: {', '.join(r.play_methods)}"
            )
        for reason in r.reasons[:5]:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append("| Method | Play | Side | Score | Tags / notes |")
        lines.append("|--------|------|------|-------|--------------|")
        for v in r.votes:
            tags = ", ".join(v.tags[:4]) if v.tags else (v.reasons[0] if v.reasons else "")
            if v.error:
                tags = f"ERR: {v.error}"[:60]
            lines.append(
                f"| {v.method_id} | {'Y' if v.play else 'n'} | {v.side or '—'} | "
                f"{v.score:.0f} | {tags[:50]} |"
            )
        lines.append("")

    if card_writes is not None:
        lines.append("## Process cards written (Step 2–3)")
        if not card_writes:
            lines.append("_no PLAY names — nothing written_")
        for w in card_writes:
            if w.written:
                lines.append(f"- **{w.symbol}** card ready")
                lines.append(f"  - trigger: `{w.trigger}`")
                lines.append(f"  - stop: `{w.stop}`")
                lines.append(f"  - size: `{w.size_risk}` · exit: `{w.exit_plan}`")
            else:
                lines.append(f"- **{w.symbol}** failed: {w.message}")
        lines.append("")
        lines.append(
            "_Focus list updated with PLAY symbols. Regime (Step 1) is still manual: "
            "`process regime --bias trade|light|cash`._"
        )
        lines.append("")

    if book_export is not None:
        lines.append("## Auto-trade book export")
        lines.append(
            f"- **Entries written:** {book_export.get('entry_count', 0)} "
            f"(export-eligible plays: {book_export.get('play_export', '?')})"
        )
        lines.append(f"- **stay_in_cash:** {book_export.get('stay_in_cash')}")
        for p in book_export.get("paths") or []:
            lines.append(f"- `{p}`")
        if not book_export.get("paths"):
            lines.append("_no paths written_")
        lines.append("")
        lines.append(
            "_Only export-eligible PLAY rows are written (confluence + play-quality). "
            "OMS still needs process gate Steps 1–3 + live flags. "
            "Rows are **equity** geometry._"
        )
        lines.append("")

    lines.append("## Policy")
    lines.append(
        "- Each ticker is evaluated by **all** enabled methods (shared bars)."
    )
    lines.append(
        f"- **PLAY** if ≥{cfg.min_play_methods} method(s) vote play with "
        f"score ≥ {cfg.min_method_score}."
    )
    lines.append(
        f"- **EXPORT** if PLAY and ≥{cfg.export_min_play_methods} methods and "
        f"(best play score ≥{cfg.export_min_best_score:.0f} or "
        f"play-avg ≥{cfg.export_min_play_avg_score:.0f}). "
        "Uses play-method scores only (not full aggregate)."
    )
    lines.append(
        "- **CONFLICT** if strong CALL and PUT votes disagree "
        f"(floor score {cfg.conflict_score_floor})."
    )
    lines.append("- `process_methods` is advisory and cannot unlock PLAY alone.")
    lines.append(
        "- Default: process cards + auto_trade_book for **export-eligible** names."
    )
    lines.append("")
    lines.append("_Paper router — OMS still needs process gate Steps 1–3._")
    lines.append("")
    return "\n".join(lines)
