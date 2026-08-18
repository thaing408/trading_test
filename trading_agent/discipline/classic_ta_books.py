"""Classic TA top-ten ranked books → auto-trade mechanisms.

User desk ranking (Murphy … Shannon). Overlap with SMB / Investopedia lists is
intentional: catalog ranks 1,2,5,8,10 point at existing modules; this aggregator
only runs the five previously unwired books (Minervini, Weinstein, Elder,
Carter, Grimes).

Soft mode: missing optional inputs → inactive pass (Dalton-style), not hard-block.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from trading_agent.discipline.ta_books import TaBooksResult, TaGateResult, _f, _listish, _s


CLASSIC_TA_TOP_TEN: tuple[dict[str, str], ...] = (
    {
        "rank": "1",
        "title": "Technical Analysis of the Financial Markets",
        "author": "John J. Murphy",
        "best_for": "Complete technical-analysis foundation",
        "mechanism": "murphy_indicator_confluence",
        "module": "discipline/ta_books.py",
        "status": "existing",
    },
    {
        "rank": "2",
        "title": "How to Make Money in Stocks",
        "author": "William J. O'Neil",
        "best_for": "Breakouts, momentum & growth stocks",
        "mechanism": "oneil_can_slim_proxy",
        "module": "discipline/smb_books.py",
        "status": "existing",
    },
    {
        "rank": "3",
        "title": "Trade Like a Stock Market Wizard",
        "author": "Mark Minervini",
        "best_for": "High-quality breakout trading",
        "mechanism": "minervini_vcp_breakout",
        "module": "discipline/classic_ta_books.py",
        "status": "new",
    },
    {
        "rank": "4",
        "title": "Stan Weinstein's Secrets for Profiting in Bull and Bear Markets",
        "author": "Stan Weinstein",
        "best_for": "Market stages & trend following",
        "mechanism": "weinstein_stage_proxy",
        "module": "discipline/classic_ta_books.py",
        "status": "new",
    },
    {
        "rank": "5",
        "title": "How to Trade in Stocks",
        "author": "Jesse Livermore",
        "best_for": "Price action, timing & speculation",
        "mechanism": "livermore_tape_and_cut",
        "module": "discipline/smb_books.py (via Reminiscences)",
        "status": "existing",
    },
    {
        "rank": "6",
        "title": "The New Trading for a Living",
        "author": "Alexander Elder",
        "best_for": "Trading system + risk management",
        "mechanism": "elder_triple_screen",
        "module": "discipline/classic_ta_books.py",
        "status": "new",
    },
    {
        "rank": "7",
        "title": "Mastering the Trade",
        "author": "John F. Carter",
        "best_for": "Practical setups & trade execution",
        "mechanism": "carter_setup_r_multiple",
        "module": "discipline/classic_ta_books.py",
        "status": "new",
    },
    {
        "rank": "8",
        "title": "Japanese Candlestick Charting Techniques",
        "author": "Steve Nison",
        "best_for": "Candlesticks & price action",
        "mechanism": "nison_candle_alignment",
        "module": "discipline/ta_books.py",
        "status": "existing",
    },
    {
        "rank": "9",
        "title": "The Art and Science of Technical Analysis",
        "author": "Adam Grimes",
        "best_for": "Systematic technical trading",
        "mechanism": "grimes_systematic_edge",
        "module": "discipline/classic_ta_books.py",
        "status": "new",
    },
    {
        "rank": "10",
        "title": "Technical Analysis Using Multiple Timeframes",
        "author": "Brian Shannon",
        "best_for": "Multi-timeframe analysis",
        "mechanism": "shannon_mtf_gate",
        "module": "discipline/mtf_gate.py",
        "status": "existing",
    },
)


def _trend_map(ctx: Mapping[str, Any]) -> dict[str, str]:
    raw = ctx.get("timeframe_trends") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {str(k).lower(): str(v).lower().strip() for k, v in raw.items()}


def _rr_multiple(ctx: Mapping[str, Any]) -> Optional[float]:
    """Prefer structure_rr / max reward÷risk; else derive from entry/stop/target."""
    for key in ("structure_rr", "risk_reward"):
        v = _f(ctx, key, 0.0)
        if v > 0:
            return v
    max_risk = _f(ctx, "maximum_risk", 0.0)
    max_reward = _f(ctx, "maximum_reward", 0.0)
    if max_risk > 0 and max_reward > 0:
        return max_reward / max_risk
    entry = _f(ctx, "entry_price", _f(ctx, "price"))
    stop = _f(ctx, "stop_loss")
    target = _f(ctx, "profit_target")
    if entry <= 0 or stop <= 0 or target <= 0:
        return None
    risk = abs(entry - stop)
    if risk < 1e-9:
        return None
    return abs(target - entry) / risk


def _has_rs(ctx: Mapping[str, Any]) -> bool:
    return ctx.get("relative_strength") is not None and str(ctx.get("relative_strength")).strip() != ""


def _has_rvol(ctx: Mapping[str, Any]) -> bool:
    return (
        ctx.get("relative_volume") is not None
        or ctx.get("rvol") is not None
    )


# --- 3 Minervini: VCP / breakout quality ---


def minervini_vcp_breakout(
    ctx: Mapping[str, Any],
    *,
    min_rvol: float = 1.5,
    min_rs: float = 1.0,
) -> TaGateResult:
    """High-quality breakout: trend + RS + volume; refuse failed breakouts."""
    reasons: List[str] = []
    notes: List[str] = []
    direction = _s(ctx, "direction")
    trend = _s(ctx, "trend")
    ma = _s(ctx, "ma_alignment")
    pa = " ".join(_listish(ctx, "pa_signals") + _listish(ctx, "candle_patterns") + [_s(ctx, "pattern_summary")])

    if direction in ("bullish", "long"):
        if "failed_breakout" in pa:
            reasons.append("Minervini: failed_breakout vs long")
        if trend in ("downtrend", "bearish") and ma == "bearish":
            reasons.append("Minervini: long without stage-2 / uptrend structure")
        elif trend in ("downtrend", "bearish") and not ma:
            notes.append("Minervini: trend weak; MA missing — soft")
        if _has_rs(ctx) and min_rs > 0:
            rs = _f(ctx, "relative_strength", 0.0)
            if rs < min_rs:
                reasons.append(f"Minervini: RS {rs:.2f} < {min_rs:.2f}")
        else:
            notes.append("Minervini: RS inactive/missing")
        if _has_rvol(ctx):
            rvol = _f(ctx, "relative_volume", _f(ctx, "rvol"))
            if rvol < min_rvol:
                reasons.append(f"Minervini: RVOL {rvol:.2f}x < {min_rvol}x")
        else:
            notes.append("Minervini: RVOL missing — soft")
        # Note: do not treat structure pattern_height (often full S/R span) as VCP
        # contraction depth — that false-positives on normal ranges.
    elif direction in ("bearish", "short"):
        if "failed_breakdown" in pa:
            reasons.append("Minervini: failed_breakdown vs short")
        if trend in ("uptrend", "bullish") and ma == "bullish":
            reasons.append("Minervini: short against strong uptrend")
    else:
        notes.append("Minervini: neutral direction — soft")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Trade Like a Stock Market Wizard (Minervini)",
        mechanism="minervini_vcp_breakout",
        reasons=reasons or notes,
    )


# --- 4 Weinstein: stage analysis ---


def weinstein_stage_proxy(ctx: Mapping[str, Any]) -> TaGateResult:
    """Stage-2 proxy via weekly trend + EMA50/200; fail-open if MTF/EMA absent."""
    reasons: List[str] = []
    notes: List[str] = []
    direction = _s(ctx, "direction")
    trends = _trend_map(ctx)
    weekly = trends.get("weekly") or trends.get("1w") or trends.get("w")
    daily = trends.get("daily") or trends.get("1d") or trends.get("d")
    ema50 = _f(ctx, "ema_50", 0.0)
    ema200 = _f(ctx, "ema_200", 0.0)
    ma = _s(ctx, "ma_alignment")
    vp = _s(ctx, "volume_profile_bias")

    if not weekly and ema50 <= 0 and ema200 <= 0 and not ma:
        return TaGateResult(
            ok=True,
            book="Weinstein Secrets (stage proxy)",
            mechanism="weinstein_stage_proxy",
            reasons=["Weinstein: stage inputs missing — inactive"],
        )

    if direction in ("bullish", "long"):
        if weekly in ("downtrend", "bearish"):
            reasons.append("Weinstein: weekly stage not bullish for long")
        if ema50 > 0 and ema200 > 0 and ema50 < ema200:
            reasons.append("Weinstein: EMA50 < EMA200 (not stage 2)")
        if weekly in ("downtrend", "bearish") and vp == "distribution":
            reasons.append("Weinstein: stage-4 / distribution proxy")
        if not weekly:
            notes.append("Weinstein: weekly trend missing — soft")
        if ema50 <= 0 or ema200 <= 0:
            notes.append("Weinstein: EMA stack missing — soft")
    elif direction in ("bearish", "short"):
        if weekly in ("uptrend", "bullish"):
            reasons.append("Weinstein: weekly stage still bullish vs short")
        if ema50 > 0 and ema200 > 0 and ema50 > ema200 and daily in ("uptrend", "bullish"):
            reasons.append("Weinstein: short into stage-2 EMA stack")
        if not weekly:
            notes.append("Weinstein: weekly trend missing — soft")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Weinstein Secrets (stage proxy)",
        mechanism="weinstein_stage_proxy",
        reasons=reasons or notes,
    )


# --- 6 Elder: triple screen + risk ---


def elder_triple_screen(
    ctx: Mapping[str, Any],
    *,
    max_risk_per_trade_pct: float = 2.0,
    max_stop_atr: float = 2.5,
) -> TaGateResult:
    """Screen1 HTF + Screen2 impulse + risk/ATR stop hygiene."""
    reasons: List[str] = []
    notes: List[str] = []
    direction = _s(ctx, "direction")
    trends = _trend_map(ctx)
    weekly = trends.get("weekly") or trends.get("1w") or trends.get("w")
    daily = trends.get("daily") or trends.get("1d") or trends.get("d")
    rsi = _f(ctx, "rsi", 50.0)
    macd = _s(ctx, "macd_signal")
    mom = _s(ctx, "momentum")

    if weekly and daily:
        if direction in ("bullish", "long"):
            if weekly in ("downtrend", "bearish") or daily in ("downtrend", "bearish"):
                reasons.append("Elder: triple-screen HTF/daily disagree with long")
        elif direction in ("bearish", "short"):
            if weekly in ("uptrend", "bullish") or daily in ("uptrend", "bullish"):
                reasons.append("Elder: triple-screen HTF/daily disagree with short")
    else:
        notes.append("Elder: weekly/daily trends incomplete — soft")

    if direction in ("bullish", "long") and rsi >= 80:
        reasons.append(f"Elder: RSI exhausted for long ({rsi:.0f})")
    if direction in ("bearish", "short") and rsi <= 20:
        reasons.append(f"Elder: RSI exhausted for short ({rsi:.0f})")

    # Impulse screen — only when MACD/momentum present
    if macd or mom:
        if direction in ("bullish", "long") and macd == "bearish" and mom == "bearish":
            reasons.append("Elder: impulse screen bearish vs long")
        if direction in ("bearish", "short") and macd == "bullish" and mom == "bullish":
            reasons.append("Elder: impulse screen bullish vs short")

    proposed = _f(ctx, "proposed_risk_pct", 0.0)
    if proposed > 0 and proposed > max_risk_per_trade_pct + 1e-9:
        reasons.append(
            f"Elder: risk {proposed:.2f}% > cap {max_risk_per_trade_pct:.2f}%"
        )

    entry = _f(ctx, "entry_price", _f(ctx, "price"))
    stop = _f(ctx, "stop_loss")
    atr = _f(ctx, "atr", 0.0)
    if entry > 0 and stop > 0 and atr > 0:
        stop_dist = abs(entry - stop)
        if stop_dist > max_stop_atr * atr:
            reasons.append(
                f"Elder: stop {stop_dist:.2f} > {max_stop_atr}×ATR ({atr:.2f})"
            )
    elif atr <= 0:
        notes.append("Elder: ATR missing — soft")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="The New Trading for a Living (Elder)",
        mechanism="elder_triple_screen",
        reasons=reasons or notes,
    )


# --- 7 Carter: named setup + R-multiple ---


def carter_setup_r_multiple(
    ctx: Mapping[str, Any],
    *,
    min_rr: float = 1.5,
    require_named_setup: bool = True,
) -> TaGateResult:
    """Playbook-named setup + checklist + minimum R."""
    reasons: List[str] = []
    notes: List[str] = []
    setup = str(ctx.get("setup_id") or ctx.get("playbook_setup_id") or "").strip()
    if require_named_setup:
        if not setup or setup.lower() in ("generic", "none", "n/a", "unknown"):
            reasons.append("Carter: named setup/playbook id required")
    checklist = ctx.get("checklist_passed")
    if checklist is False:
        reasons.append("Carter: setup checklist failed")
    elif checklist is None:
        notes.append("Carter: checklist_passed unset — soft")

    rr = _rr_multiple(ctx)
    if rr is None:
        notes.append("Carter: R-multiple inputs missing — soft")
    elif rr < min_rr:
        reasons.append(f"Carter: R-multiple {rr:.2f} < {min_rr:.2f}")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Mastering the Trade (Carter)",
        mechanism="carter_setup_r_multiple",
        reasons=reasons or notes,
    )


# --- 9 Grimes: systematic edge ---


def grimes_systematic_edge(
    ctx: Mapping[str, Any],
    *,
    min_confluence: int = 2,
) -> TaGateResult:
    """Defined plan + indicator confluence + no discretionary override flags."""
    reasons: List[str] = []
    notes: List[str] = []
    entry = _f(ctx, "entry_price", _f(ctx, "price"))
    stop = _f(ctx, "stop_loss")
    target = _f(ctx, "profit_target")
    if entry <= 0:
        reasons.append("Grimes: entry missing")
    if stop <= 0:
        reasons.append("Grimes: stop / invalidation missing")
    if target <= 0:
        reasons.append("Grimes: target missing")

    direction = _s(ctx, "direction")
    bullish_votes = 0
    bearish_votes = 0
    ma = _s(ctx, "ma_alignment")
    if ma == "bullish":
        bullish_votes += 1
    elif ma == "bearish":
        bearish_votes += 1
    macd = _s(ctx, "macd_signal")
    if macd == "bullish":
        bullish_votes += 1
    elif macd == "bearish":
        bearish_votes += 1
    rsi = _f(ctx, "rsi", 50.0)
    if rsi >= 55:
        bullish_votes += 1
    elif rsi <= 45:
        bearish_votes += 1
    mom = _s(ctx, "momentum")
    if mom == "bullish":
        bullish_votes += 1
    elif mom == "bearish":
        bearish_votes += 1
    trend = _s(ctx, "trend")
    if trend in ("uptrend", "bullish"):
        bullish_votes += 1
    elif trend in ("downtrend", "bearish"):
        bearish_votes += 1

    has_any_indicator = bool(ma or macd or mom or trend or ctx.get("rsi") is not None)
    if has_any_indicator and direction in ("bullish", "long"):
        if bullish_votes < min_confluence:
            reasons.append(
                f"Grimes: systematic confluence {bullish_votes}/{min_confluence}"
            )
    elif has_any_indicator and direction in ("bearish", "short"):
        if bearish_votes < min_confluence:
            reasons.append(
                f"Grimes: systematic confluence {bearish_votes}/{min_confluence}"
            )
    else:
        notes.append("Grimes: indicators sparse — soft")

    if bool(ctx.get("tilt")) or bool(ctx.get("revenge_reentry")):
        reasons.append("Grimes: emotional override (tilt/revenge)")
    if bool(ctx.get("fomo_chase")):
        reasons.append("Grimes: FOMO chase")
    if bool(ctx.get("discretionary_size_up")):
        reasons.append("Grimes: discretionary size-up")

    stop_basis = str(ctx.get("stop_basis") or "").strip()
    geometry = str(ctx.get("geometry_source") or "").strip()
    if not stop_basis and not geometry:
        notes.append("Grimes: stop_basis/geometry unset — soft")

    return TaGateResult(
        ok=len(reasons) == 0,
        book="Art and Science of TA (Grimes)",
        mechanism="grimes_systematic_edge",
        reasons=reasons or notes,
    )


def apply_classic_ta_book_gates(
    ctx: Mapping[str, Any],
    *,
    min_rvol: float = 1.5,
    min_rs: float = 1.0,
    min_rr: float = 1.5,
    max_risk_per_trade_pct: float = 2.0,
    min_confluence: int = 2,
    require_named_setup: bool = True,
    enabled: bool = True,
) -> TaBooksResult:
    """Run the five newly wired classic-TA book gates."""
    if not enabled:
        return TaBooksResult(ok=True, results=[], blocked_by=[])

    results = [
        minervini_vcp_breakout(ctx, min_rvol=min_rvol, min_rs=min_rs),
        weinstein_stage_proxy(ctx),
        elder_triple_screen(ctx, max_risk_per_trade_pct=max_risk_per_trade_pct),
        carter_setup_r_multiple(ctx, min_rr=min_rr, require_named_setup=require_named_setup),
        grimes_systematic_edge(ctx, min_confluence=min_confluence),
    ]
    blocked = [r.summary for r in results if not r.ok]
    return TaBooksResult(
        ok=len(blocked) == 0,
        results=results,
        blocked_by=blocked,
        label="Classic TA book gates",
    )
