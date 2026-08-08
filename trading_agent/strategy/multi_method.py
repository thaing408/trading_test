"""Multi-method ticker router: every symbol is evaluated by all playbooks.

Each ticker gets a **chance to play** if any registered method votes PLAY
(with optional multi-method confluence). Methods share one bar fetch.

Methods (paper / research):
  - soulz_pa     — BRR + range + fib confluence
  - top_winners  — drop-fast + TA/HTF + structure (0DTE CALL style)
  - orb_vwap     — opening-range break + VWAP
  - odte_breakout — OR high/low continuation (breakout style)
  - process_methods — baseline process tags (risk/checklist soft score)

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
    aggregate_score: float
    play_methods: List[str] = field(default_factory=list)
    votes: List[MethodVote] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    asof: str = ""


@dataclass
class MultiMethodConfig:
    """Router policy: any method can unlock a play, or require confluence."""

    min_method_score: float = 55.0
    # 1 = any single method can grant a chance; 2+ = multi-method agreement
    min_play_methods: int = 1
    require_side_agreement: bool = True  # conflict if CALL and PUT both strong
    conflict_score_floor: float = 55.0  # only count methods above this for conflict
    enabled_methods: Tuple[str, ...] = METHOD_IDS
    bar_period: str = "10d"
    bar_interval: str = "15m"
    data_source: str = "yfinance"
    soulz_min_confluence: int = 2
    # weights for aggregate score (sum normalized)
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "soulz_pa": 1.0,
            "top_winners": 1.0,
            "orb_vwap": 1.0,
            "odte_breakout": 0.9,
            "process_methods": 0.5,
        }
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

    votes: List[MethodVote] = []
    for mid in cfg.enabled_methods:
        if mid == "process_methods":
            continue  # after others
        fn = EVALUATORS.get(mid)
        if fn is None:
            continue
        votes.append(fn(sym, df, cfg))

    if "process_methods" in cfg.enabled_methods:
        votes.append(eval_process_methods(sym, df, cfg, votes))

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
            + [f"{v.method_id}={v.score:.0f} play={v.play}" for v in votes],
            asof=asof,
        )

    # Side conflict among strong plays
    strong = [v for v in play_votes if v.score >= cfg.conflict_score_floor and v.side in ("CALL", "PUT")]
    sides = {v.side for v in strong}
    if cfg.require_side_agreement and len(sides) > 1:
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
        )

    if len(play_votes) < int(cfg.min_play_methods):
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
        )

    best = max(play_votes, key=lambda v: v.score)
    return TickerMultiEval(
        symbol=sym,
        play=True,
        decision="PLAY",
        best_method=best.method_id,
        best_side=best.side,
        aggregate_score=aggregate,
        play_methods=[v.method_id for v in play_votes],
        votes=votes,
        reasons=[
            f"PLAY via {', '.join(v.method_id for v in play_votes)}",
            f"best={best.method_id} side={best.side} score={best.score:.0f}",
        ],
        asof=asof,
    )


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
) -> str:
    cfg = cfg or MultiMethodConfig()
    plays = [r for r in results if r.play]
    lines = [
        "# Multi-Method Ticker Router",
        "",
        f"- **Symbols:** {len(results)} · **PLAY:** {len(plays)} · "
        f"**min_method_score:** {cfg.min_method_score} · "
        f"**min_play_methods:** {cfg.min_play_methods}",
        f"- **Methods:** {', '.join(cfg.enabled_methods)}",
        "",
        "## Decisions",
        "",
    ]
    for r in results:
        icon = {"PLAY": "✅", "SKIP": "⬜", "CONFLICT": "⚡", "NO_DATA": "⛔"}.get(r.decision, "·")
        lines.append(
            f"### {icon} **{r.symbol}** — {r.decision} "
            f"(agg {r.aggregate_score:.0f}/100)"
        )
        if r.play:
            lines.append(
                f"- Best: **{r.best_method}** → **{r.best_side}** · "
                f"methods: {', '.join(r.play_methods)}"
            )
        for reason in r.reasons[:4]:
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

    lines.append("## Policy")
    lines.append(
        "- Each ticker is evaluated by **all** enabled methods (shared bars)."
    )
    lines.append(
        f"- **PLAY** if ≥{cfg.min_play_methods} method(s) vote play with "
        f"score ≥ {cfg.min_method_score}."
    )
    lines.append(
        "- **CONFLICT** if strong CALL and PUT votes disagree "
        f"(floor score {cfg.conflict_score_floor})."
    )
    lines.append("- `process_methods` is advisory and cannot unlock PLAY alone.")
    lines.append(
        "- Optional: auto trade cards + focus list for PLAY names (`--write-cards`)."
    )
    lines.append("")
    lines.append("_Paper router — OMS still needs process gate Steps 1–3._")
    lines.append("")
    return "\n".join(lines)
