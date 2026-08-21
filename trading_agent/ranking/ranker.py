"""Rank qualified setups by setup grade (A+/A first), then quality/confidence."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List, Tuple

from trading_agent.config import RiskConfig
from trading_agent.models import (
    OptionsMetrics,
    ScreenerCandidate,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.ranking.grades import (
    GRADE_RANK,
    assign_setup_grade,
    grade_sort_key,
)
from trading_agent.strategy.competition import select_strategy_competitive
from trading_agent.strategy.selector import StrategySelection, select_strategy


def compute_confidence_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
) -> float:
    iv_component = (
        (100 - min(options.iv_rank, 100)) * 0.05
        if options.iv_rank > 50
        else options.iv_rank * 0.05 + 2.5
    )
    score = (
        technical.score * 0.35
        + options.liquidity_score * 0.20
        + options.probability_of_profit * 100 * 0.25
        + min(candidate.relative_volume, 3.0) / 3.0 * 100 * 0.10
        + iv_component
    )
    if options.unusual_activity:
        score += 5
    if candidate.institutional_score:
        score += min(5.0, candidate.institutional_score / 20.0)
    return round(min(100.0, max(0.0, score)), 1)


def compute_trade_quality_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    confidence: float,
) -> float:
    """Composite 0-100 quality: technicals, liquidity, POP, confidence, institutional."""
    quality = (
        technical.score * 0.30
        + options.liquidity_score * 0.20
        + options.probability_of_profit * 100 * 0.20
        + confidence * 0.20
        + min(100.0, candidate.institutional_score or 50.0) * 0.10
    )
    if technical.timeframe_alignment == "aligned_bullish" or technical.timeframe_alignment == "aligned_bearish":
        quality += 5
    if technical.breakout_state in ("breakout", "breakdown"):
        quality += 2
    if options.bid_ask_spread_pct and options.bid_ask_spread_pct > 3:
        quality -= 5
    return round(min(100.0, max(0.0, quality)), 1)


def _trade_params(
    price: float,
    strategy: StrategySelection,
    options: OptionsMetrics,
    technical: TechnicalAnalysis,
    *,
    stop_atr_mult: float = 1.0,
    target_atr_mult: float = 1.5,
    size_multiplier: float = 1.0,
    risk_policy: str | None = None,
) -> dict:
    """PT/SL from Brandt LFD + structure (measured move); ATR only as buffer/fallback.

    Prefer Last Full Day / S-R pattern geometry over hardcoded % of price.
    Grade multipliers scale buffer ambition and size, not a pure % stop.
    """
    from trading_agent.analysis.lfd_breakout import RiskPolicy, structure_package_for_setup

    atr = technical.atr or price * 0.02
    risk_unit = max(price * 0.02, atr)
    policy_raw = (risk_policy or os.getenv("TRADING_AGENT_RISK_POLICY", "hybrid") or "hybrid").strip()
    try:
        policy = RiskPolicy(policy_raw)
    except ValueError:
        policy = RiskPolicy.HYBRID

    # Neutral / range strategies: still structure-aware but keep defined-risk $ bands
    direction = strategy.direction or "Bullish"
    pkg = structure_package_for_setup(
        price=price,
        direction=direction,
        support=float(technical.support or 0.0),
        resistance=float(technical.resistance or 0.0),
        atr=float(atr),
        breakout_state=str(technical.breakout_state or "none"),
        risk_policy=policy,
        stop_atr_mult=stop_atr_mult,
        target_atr_mult=target_atr_mult,
        size_multiplier=size_multiplier,
        min_risk_reward=1.5,
    )
    stop_loss = pkg.stop_loss
    profit_target = pkg.profit_target

    # Strategy-class dollar risk envelope (options defined-risk book)
    if strategy.name in ("Iron Condor", "Bull Put Credit Spread", "Bear Call Credit Spread"):
        max_risk = round(risk_unit * 1.5 * size_multiplier, 2)
        max_reward = round(risk_unit * 3.0 * max(size_multiplier, 0.5), 2)
    elif "Spread" in strategy.name or strategy.name in ("Calendar Spread", "Diagonal Spread"):
        max_risk = round(risk_unit * 1.5 * size_multiplier, 2)
        max_reward = round(risk_unit * 3.0 * max(size_multiplier, 0.5), 2)
    elif strategy.name in ("Long Call", "Long Put"):
        max_risk = round(risk_unit * 2.5 * size_multiplier, 2)
        max_reward = round(risk_unit * 5.0 * max(target_atr_mult / 1.5, 0.5), 2)
    elif strategy.name in ("Covered Call", "Cash Secured Put"):
        max_risk = round(risk_unit * size_multiplier, 2)
        max_reward = round(risk_unit * 2.2 * max(target_atr_mult / 1.5, 0.5), 2)
    else:
        # Geometric structure risk when directional outright
        max_risk = round(max(pkg.maximum_risk, risk_unit * size_multiplier), 2)
        max_reward = round(max(pkg.maximum_reward, risk_unit * max(pkg.risk_reward, 1.5)), 2)

    # Keep R:R coherent with structure points when dollar bands dominate
    risk_pts = abs(pkg.entry_price - stop_loss)
    reward_pts = abs(profit_target - pkg.entry_price)
    if risk_pts > 0 and max_risk > 0 and reward_pts > 0:
        rr = reward_pts / risk_pts
        max_reward = max(max_reward, round(max_risk * rr, 2))

    return {
        "entry_price": round(price, 2),
        "profit_target": profit_target,
        "stop_loss": stop_loss,
        "maximum_risk": max_risk,
        "maximum_reward": max_reward,
        "probability_of_success": options.probability_of_profit,
        "stop_atr_mult": stop_atr_mult,
        "target_atr_mult": target_atr_mult,
        "stop_basis": pkg.stop_basis,
        "target_basis": pkg.target_basis,
        "geometry_source": pkg.geometry_source,
        "risk_policy": pkg.risk_policy,
        "lfd_level": pkg.structure.lfd_level,
        "breakout_level": pkg.structure.breakout_level,
        "negation_level": pkg.structure.negation_level,
        "measured_target": pkg.structure.measured_target,
        "pattern_height": pkg.structure.pattern_height,
        "structure_notes": "; ".join(pkg.notes)[:240],
        "structure_rr": pkg.risk_reward,
    }


def _thesis(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    strategy: StrategySelection,
    grade: str = "",
) -> str:
    tf = ", ".join(
        f"{k}={v}"
        for k, v in technical.timeframe_trends.items()
        if k != "intraday" and v != "unavailable"
    )
    pattern_bit = ""
    if technical.pattern_summary and technical.pattern_summary != "none":
        pattern_bit = f", patterns={technical.pattern_summary}"
    grade_bit = f"grade={grade}, " if grade else ""
    return (
        f"{strategy.direction} {strategy.name} on {candidate.symbol}: "
        f"{grade_bit}"
        f"trend={technical.trend}, momentum={technical.momentum}, "
        f"breakout={technical.breakout_state}, RS={technical.relative_strength}"
        f"{pattern_bit}, "
        f"IVR={options.iv_rank}, POP={options.probability_of_profit:.0%}, "
        f"flow={options.institutional_flow_bias}; multi-TF [{tf}]"
    )


def _risks(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    strategy: StrategySelection,
    grade: str = "",
) -> List[str]:
    risks: List[str] = []
    if grade in ("C", "B"):
        risks.append(f"Setup grade {grade} — take profits earlier; do not treat as runner")
    if grade == "F":
        risks.append("Setup grade F — do not deploy capital")
    if technical.timeframe_alignment == "conflicting":
        risks.append("Conflicting multi-timeframe trends")
    if options.iv_rank >= 70:
        risks.append("Elevated IV rank — premium expensive / vol crush risk")
    if options.iv_rank <= 25 and strategy.name in ("Long Call", "Long Put"):
        risks.append("Low IV with long premium — needs expansion for payoff")
    if candidate.bid_ask_spread_pct > 2.0:
        risks.append(f"Options bid/ask {candidate.bid_ask_spread_pct}% — slippage risk")
    if technical.adx < 20:
        risks.append("Weak trend strength (ADX < 20)")
    if technical.breakout_state == "none" and strategy.direction != "Neutral":
        risks.append("No confirmed breakout/breakdown at entry")
    if options.probability_of_touch > 0.7 and "Credit" in strategy.name:
        risks.append("High probability of touch on short strikes")
    for name in technical.pa_signals or []:
        if "fakeout" in name or "stop_hunt_supply" in name:
            if strategy.direction == "Bullish" and ("breakout" in name or "supply" in name):
                risks.append(f"Institutional PA caution: {name} (fakeout/stop-hunt trap risk)")
        if "stop_hunt_demand" in name and strategy.direction == "Bearish":
            risks.append(f"Institutional PA caution: {name} (demand liquidity grab)")
        if name in ("shooting_star",) or name.endswith("bearish"):
            if strategy.direction == "Bullish":
                risks.append(f"Bearish PA/candle context: {name}")
    for name in technical.candle_patterns or []:
        if name in ("shooting_star", "bearish_engulfing", "doji") and strategy.direction == "Bullish":
            risks.append(f"Candlestick caution: {name}")
        if name in ("hammer", "bullish_engulfing") and strategy.direction == "Bearish":
            risks.append(f"Candlestick caution: {name}")
    if not risks:
        risks.append("Standard gap and event risk into the session")
    return risks[:6]


def _min_grade_allowed(risk_config: RiskConfig) -> int:
    min_g = getattr(risk_config, "min_setup_grade", "C") or "C"
    return GRADE_RANK.get(min_g, GRADE_RANK["C"])


def build_opportunities(
    qualified: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]],
    risk_config: RiskConfig,
    max_count: int | None = None,
    *,
    session_state: object | None = None,
    rail_rejections: List | None = None,
) -> List[TradeOpportunity]:
    """Build ranked opportunities: A+/A first, then B, C. F excluded.

    Book discipline (when enabled on RiskConfig):
    - Shannon MTF gate inside assign_setup_grade
    - Bellafiore named playbook checklist
    - Douglas edge package completeness
    - Cool-down / concurrent / aggregate risk rails always (SessionRiskState
      seeded from RiskConfig; desk pipeline injects stop-out book + open book)
    """
    from trading_agent.discipline.edge import validate_edge_package
    from trading_agent.discipline.playbook import require_playbook_pass
    from trading_agent.discipline.rails import (
        SessionRiskState,
        check_discipline_rails,
        session_state_from_risk_config,
    )
    from trading_agent.discipline.classic_ta_books import apply_classic_ta_book_gates
    from trading_agent.discipline.smb_books import apply_smb_book_gates
    from trading_agent.discipline.ta_books import apply_investopedia_ta_gates
    from trading_agent.models import RejectedSetup

    limit = max_count if max_count is not None else risk_config.top_candidates
    prefer_a = bool(getattr(risk_config, "prefer_a_tier_only", False))
    max_rank_allowed = _min_grade_allowed(risk_config)
    require_pb = bool(getattr(risk_config, "require_playbook_checklist", True))
    require_edge = bool(getattr(risk_config, "require_edge_package", True))
    enforce_mtf = bool(getattr(risk_config, "enforce_mtf_gate", True))
    enforce_rails = bool(getattr(risk_config, "enforce_discipline_rails", True))
    enforce_smb = bool(getattr(risk_config, "enforce_smb_book_gates", True))
    enforce_ta = bool(getattr(risk_config, "enforce_ta_book_gates", True))
    enforce_classic = bool(getattr(risk_config, "enforce_classic_ta_book_gates", True))
    from trading_agent.discipline.compete import (
        book_gates_mode,
        compute_compete_score,
        iter_gate_results,
        score_gate_results,
        should_hard_reject_books,
    )

    gates_mode = book_gates_mode()
    enforce_methods = bool(getattr(risk_config, "enforce_web_methods", True))

    # Always apply RiskConfig limits on the auto-trade path (not optional).
    if session_state is None or not isinstance(session_state, SessionRiskState):
        state: SessionRiskState = session_state_from_risk_config(risk_config)
    else:
        state = session_state
        state.apply_risk_config(risk_config)

    # Public process methods (baseline; optional web reinforce once per build)
    methods_list = []
    try:
        from trading_agent.methods.web_methods import research_trading_methods

        offline = os.getenv("TRADING_AGENT_METHODS_OFFLINE", "").lower() in (
            "1",
            "true",
            "yes",
        )
        methods_list = research_trading_methods(use_network=not offline)
    except Exception:
        from trading_agent.methods.web_methods import BASELINE_METHODS

        methods_list = list(BASELINE_METHODS)

    scored: List[dict] = []

    # Multi-sleeve competition on by default; TRADING_AGENT_SLEEVE_COMPETE=0 disables
    use_compete = os.getenv("TRADING_AGENT_SLEEVE_COMPETE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    for candidate, technical, options in qualified:
        confidence = compute_confidence_score(technical, options, candidate)
        if confidence < risk_config.min_confidence_score:
            continue
        competition = None
        competed_setup_id = ""
        if use_compete:
            strategy, competed_setup_id, competition = select_strategy_competitive(
                candidate, technical, options
            )
            # Blend sleeve win score into confidence slightly (capped)
            if competition.winner and competition.winner.viable:
                confidence = min(
                    100.0,
                    confidence + max(0.0, (competition.winner.score - 50.0) * 0.15),
                )
        else:
            strategy = select_strategy(technical, options, candidate.price)
        # Always defined so sleeve competition can append tags even if method gates off
        method_tags: list[str] = []
        method_notes = ""
        quality = compute_trade_quality_score(technical, options, candidate, confidence)
        grade_result = assign_setup_grade(
            technical,
            options,
            candidate,
            quality,
            confidence,
            direction=strategy.direction,
            enforce_mtf_gate=enforce_mtf,
        )
        if grade_result.grade == "F":
            continue
        if GRADE_RANK.get(grade_result.grade, 99) > max_rank_allowed:
            continue
        # Soft A-tier: allow B when aligned MTF + playbook + quality later; pre-filter non-priority
        # unless allow_b_when_aligned (final B check after quality blend below).
        allow_b = bool(getattr(risk_config, "allow_b_when_aligned", True))
        if prefer_a and not grade_result.is_priority:
            if not (allow_b and grade_result.grade == "B"):
                continue

        params = _trade_params(
            candidate.price,
            strategy,
            options,
            technical,
            stop_atr_mult=grade_result.stop_atr_mult,
            target_atr_mult=grade_result.target_atr_mult,
            size_multiplier=grade_result.size_multiplier,
        )

        play_ctx = {
            "direction": strategy.direction,
            "timeframe_alignment": technical.timeframe_alignment,
            "trend": technical.trend,
            "breakout_state": technical.breakout_state,
            "relative_volume": candidate.relative_volume,
            "rsi": technical.rsi,
            "adx": technical.adx,
            "entry_price": params["entry_price"],
            "stop_loss": params["stop_loss"],
            "profit_target": params["profit_target"],
            "price": candidate.price,
            # Options fields for options-native playbooks
            "iv_rank": options.iv_rank,
            "probability_of_profit": options.probability_of_profit,
            "pop": options.probability_of_profit,
            "open_interest": candidate.open_interest or options.open_interest,
            "bid_ask_spread_pct": candidate.bid_ask_spread_pct or options.bid_ask_spread_pct,
            "strategy": strategy.name,
        }
        pb_ok, setup_id, pb_summary, checklist = require_playbook_pass(
            direction=strategy.direction,
            strategy_name=strategy.name,
            context=play_ctx,
            require_named=require_pb,
        )
        # Prefer sleeve competition setup_id when playbook did not assign a named id
        if competed_setup_id and (
            not setup_id or setup_id in ("", "generic", "unspecified")
        ):
            setup_id = competed_setup_id
        elif competed_setup_id and competition and competition.winner:
            # Keep playbook id but tag winner sleeve
            pass
        if require_pb and not pb_ok:
            continue

        edge = validate_edge_package(
            direction=strategy.direction,
            entry_price=params["entry_price"],
            stop_loss=params["stop_loss"],
            profit_target=params["profit_target"],
            maximum_risk=params["maximum_risk"],
            maximum_reward=params["maximum_reward"],
            size_units=max(0.01, float(grade_result.size_multiplier or 1.0)),
        )
        if require_edge and not edge.ok:
            continue

        # Risk % for rails: fixed config per-trade cap (Douglas: no feeling size-up)
        proposed_risk_pct = min(
            float(risk_config.max_risk_per_trade_pct),
            float(risk_config.max_risk_per_trade_pct)
            * float(grade_result.size_multiplier or 1.0),
        )

        # SMB top-ten book gates (Livermore, Wizards, O'Neil, Dalton, Kiev, Kahneman…)
        smb_ctx = {
            "direction": strategy.direction,
            "trend": technical.trend,
            "breakout_state": technical.breakout_state,
            "relative_volume": candidate.relative_volume,
            "relative_strength": technical.relative_strength,
            "rsi": technical.rsi,
            "adx": technical.adx,
            "entry_price": params["entry_price"],
            "stop_loss": params["stop_loss"],
            "profit_target": params["profit_target"],
            "price": candidate.price,
            "support": technical.support,
            "resistance": technical.resistance,
            "setup_id": setup_id,
            "playbook_setup_id": setup_id,
            # Kiev: only treat checklist as failed when playbook is required
            "checklist_passed": (
                True
                if not require_pb
                else bool(checklist.passed)
                if checklist is not None
                else False
            ),
            "proposed_risk_pct": proposed_risk_pct,
            "base_risk_pct": float(risk_config.max_risk_per_trade_pct),
            "daily_loss_halt": bool(getattr(state, "daily_loss_halt", False)),
            "revenge_reentry": False,
            "win_streak": int(getattr(state, "win_streak", 0) or 0),
        }
        book_gate_rows: list = []
        smb = apply_smb_book_gates(
            smb_ctx,
            max_risk_per_trade_pct=float(risk_config.max_risk_per_trade_pct),
            min_rvol=float(getattr(risk_config, "oneil_min_rvol", 1.5) or 1.5),
            min_rs=float(getattr(risk_config, "oneil_min_rs", 0.0) or 0.0),
            enabled=enforce_smb,
        )
        book_gate_rows.extend(iter_gate_results(smb))
        if enforce_smb and should_hard_reject_books(
            mode=gates_mode, bundle_ok=smb.ok, results=iter_gate_results(smb)
        ):
            if rail_rejections is not None:
                rail_rejections.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason=smb.summary,
                    )
                )
            continue

        # Investopedia TA books (Schwager plan, Pring trend+vol, Murphy confluence,
        # Nison candles, Bulkowski PA) — Shannon/O'Neil also covered via MTF + SMB
        ta_ctx = {
            **smb_ctx,
            "ma_alignment": technical.ma_alignment,
            "macd_signal": technical.macd_signal,
            "momentum": technical.momentum,
            "candle_patterns": list(technical.candle_patterns or []),
            "pa_signals": list(technical.pa_signals or []),
            "pattern_summary": technical.pattern_summary or "",
        }
        ta = apply_investopedia_ta_gates(
            ta_ctx,
            min_rvol=float(getattr(risk_config, "ta_pring_min_rvol", 1.2) or 1.2),
            min_confluence=int(getattr(risk_config, "ta_min_indicator_confluence", 2) or 2),
            enabled=enforce_ta,
        )
        book_gate_rows.extend(iter_gate_results(ta))
        if enforce_ta and should_hard_reject_books(
            mode=gates_mode, bundle_ok=ta.ok, results=iter_gate_results(ta)
        ):
            if rail_rejections is not None:
                rail_rejections.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason=ta.summary,
                    )
                )
            continue

        # Classic TA top-ten newly wired books (Minervini, Weinstein, Elder, Carter, Grimes)
        classic_ctx = {
            **ta_ctx,
            "timeframe_trends": getattr(technical, "timeframe_trends", None) or {},
            "timeframe_alignment": getattr(technical, "timeframe_alignment", None),
            "ema_50": getattr(technical, "ema_50", None),
            "ema_200": getattr(technical, "ema_200", None),
            "atr": getattr(technical, "atr", None),
            "pattern_height": params.get("pattern_height"),
            "structure_rr": params.get("structure_rr"),
            "maximum_risk": params.get("maximum_risk"),
            "maximum_reward": params.get("maximum_reward"),
            "stop_basis": params.get("stop_basis"),
            "geometry_source": params.get("geometry_source"),
            "volume_profile_bias": getattr(technical, "volume_profile_bias", None),
            "vwap_relation": getattr(technical, "vwap_relation", None),
        }
        classic = apply_classic_ta_book_gates(
            classic_ctx,
            min_rvol=float(getattr(risk_config, "classic_min_rvol", 1.5) or 1.5),
            min_rs=float(getattr(risk_config, "classic_min_rs", 1.0) or 0.0),
            min_rr=float(getattr(risk_config, "classic_min_rr", 1.5) or 1.5),
            max_risk_per_trade_pct=float(risk_config.max_risk_per_trade_pct),
            min_confluence=int(getattr(risk_config, "ta_min_indicator_confluence", 2) or 2),
            require_named_setup=require_pb,
            enabled=enforce_classic,
        )
        book_gate_rows.extend(iter_gate_results(classic))
        if enforce_classic and should_hard_reject_books(
            mode=gates_mode, bundle_ok=classic.ok, results=iter_gate_results(classic)
        ):
            if rail_rejections is not None:
                rail_rejections.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason=classic.summary,
                    )
                )
            continue

        book_points, _book_by_mech = score_gate_results(book_gate_rows)

        # Fundamentals (research host — yfinance/info; no TOS required)
        fund_score = 50.0
        fund_passed = True
        fund_summary = "Fundamentals soft-default"
        if bool(getattr(risk_config, "enforce_fundamental_gate", True)):
            from trading_agent.fundamentals.quality import (
                combine_quality_score,
                fetch_fundamental_snapshot,
            )

            offline = os.getenv("TRADING_AGENT_FUNDAMENTALS_OFFLINE", "").lower() in (
                "1",
                "true",
                "yes",
            )
            # Backtests set this to avoid network
            use_net = not offline
            snap = fetch_fundamental_snapshot(
                candidate.symbol,
                min_score=float(getattr(risk_config, "min_fundamental_score", 45.0)),
                block_earnings_within_days=int(
                    getattr(risk_config, "block_earnings_within_days", 2)
                ),
                use_network=use_net,
            )
            fund_score = snap.score
            fund_passed = snap.passed
            fund_summary = "; ".join(snap.reasons[:4]) if snap.reasons else snap.source
            if not fund_passed:
                if rail_rejections is not None:
                    rail_rejections.append(
                        RejectedSetup(
                            symbol=candidate.symbol,
                            reason=f"Fundamentals: {fund_summary}",
                        )
                    )
                continue
        else:
            from trading_agent.fundamentals.quality import combine_quality_score

        combined = combine_quality_score(
            technical_score=technical.score,
            confidence=confidence,
            fundamental_score=fund_score,
            grade_score=grade_result.grade_score,
        )
        min_q = float(getattr(risk_config, "min_combined_quality_score", 55.0) or 0)
        if min_q > 0 and combined < min_q:
            if rail_rejections is not None:
                rail_rejections.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason=f"Combined quality {combined:.0f} < min {min_q:.0f}",
                    )
                )
            continue

        # B-exception under A-tier: require alignment + quality threshold
        if prefer_a and grade_result.grade == "B":
            align = (technical.timeframe_alignment or "").lower()
            aligned = align in ("aligned_bullish", "aligned_bearish", "aligned")
            min_b_q = float(getattr(risk_config, "min_quality_for_b_exception", 70.0))
            if not (allow_b and aligned and combined >= min_b_q and pb_ok and edge.ok):
                continue

        mtf_reason = ""
        for gr in grade_result.reasons:
            if "Shannon" in gr or "multi-timeframe" in gr.lower() or "HTF" in gr:
                mtf_reason = gr
                break

        # Web/process method tags (risk package, checklist, HTF, size, revenge, volume…)
        # method_tags / method_notes already initialized; extend below
        if enforce_methods and methods_list:
            from trading_agent.methods.web_methods import evaluate_methods_for_setup

            mctx = {
                "entry_price": params["entry_price"],
                "stop_loss": params["stop_loss"],
                "profit_target": params["profit_target"],
                "checklist_passed": bool(checklist.passed) if checklist else (not require_pb),
                "require_checklist": require_pb,
                "edge_complete": edge.ok,
                "timeframe_alignment": technical.timeframe_alignment,
                "relative_volume": candidate.relative_volume,
                "direction": strategy.direction,
                "setup_id": setup_id,
                "proposed_risk_pct": proposed_risk_pct,
                "max_risk_per_trade_pct": float(risk_config.max_risk_per_trade_pct),
                "strict_events": True,
                "stop_basis": params.get("stop_basis"),
                "lfd_level": params.get("lfd_level"),
                "breakout_level": params.get("breakout_level"),
                "negation_level": params.get("negation_level"),
                "geometry_source": params.get("geometry_source"),
                "require_structure_stop": os.getenv(
                    "TRADING_AGENT_REQUIRE_STRUCTURE_STOP", "0"
                ).strip().lower()
                in ("1", "true", "yes"),
            }
            meval = evaluate_methods_for_setup(methods_list, mctx)
            method_tags = list(meval.get("method_ids_ok") or [])
            method_notes = "; ".join(meval.get("method_failures") or [])[:240]
            if meval.get("critical_fail"):
                if rail_rejections is not None:
                    rail_rejections.append(
                        RejectedSetup(
                            symbol=candidate.symbol,
                            reason="Method gates: " + (method_notes or "critical method fail"),
                        )
                    )
                continue

        # Options-specific methods (IV regime, defined risk, liquidity, POP, DTE)
        opt_class = ""
        opt_notes = ""
        defined_risk = True
        if bool(getattr(risk_config, "enforce_options_methods", True)):
            from trading_agent.methods.options_methods import (
                evaluate_options_methods,
                is_defined_risk_strategy,
            )

            oeval = evaluate_options_methods(
                {
                    "strategy": strategy.name,
                    "iv_rank": options.iv_rank,
                    "probability_of_profit": options.probability_of_profit,
                    "open_interest": candidate.open_interest or options.open_interest,
                    "bid_ask_spread_pct": candidate.bid_ask_spread_pct
                    or options.bid_ask_spread_pct,
                    "expiration_days": strategy.expiration_days,
                    "delta": options.delta,
                    "direction": strategy.direction,
                    "entry_price": params["entry_price"],
                    "stop_loss": params["stop_loss"],
                    "profit_target": params["profit_target"],
                    "maximum_risk": params["maximum_risk"],
                    "maximum_reward": params["maximum_reward"],
                    "setup_id": setup_id,
                },
                min_iv_high=float(getattr(risk_config, "options_min_iv_high", 55.0)),
                max_iv_low=float(getattr(risk_config, "options_max_iv_low", 40.0)),
                min_oi=int(getattr(risk_config, "options_min_oi", 500)),
                max_spread_pct=float(getattr(risk_config, "options_max_spread_pct", 5.0)),
                min_pop_credit=float(getattr(risk_config, "options_min_pop_credit", 0.45)),
                min_dte=int(getattr(risk_config, "options_min_dte", 5)),
                max_dte=int(getattr(risk_config, "options_max_dte", 60)),
            )
            opt_class = oeval.strategy_class
            opt_notes = "; ".join(oeval.failures[:4] + oeval.notes[:2])[:240]
            defined_risk = is_defined_risk_strategy(strategy.name)
            method_tags = list(dict.fromkeys(method_tags + list(oeval.method_ids_ok)))
            if oeval.critical_fail:
                if rail_rejections is not None:
                    rail_rejections.append(
                        RejectedSetup(
                            symbol=candidate.symbol,
                            reason="Options methods: " + ("; ".join(oeval.failures[:3]) or "fail"),
                        )
                    )
                continue

        # Researcher gap screener (Raschke 4-day unfilled continuation) — always soft-apply
        try:
            from trading_agent.export.gap_book import apply_gap_boost_to_opportunity_fields

            method_tags, _, gap_note = apply_gap_boost_to_opportunity_fields(
                symbol=candidate.symbol,
                method_tags=method_tags,
                auto_trade_eligible=True,
            )
            if gap_note:
                method_notes = (method_notes + "; " + gap_note).strip("; ")[:240]
                if "gap_continuation_4d" in method_tags:
                    quality = min(100.0, float(quality) + 5.0)
                    confidence = min(100.0, float(confidence) + 3.0)
        except Exception:
            pass

        auto_eligible = (
            grade_result.grade in ("A+", "A")
            or (
                grade_result.grade == "B"
                and combined >= float(getattr(risk_config, "min_quality_for_b_exception", 70.0))
            )
        ) and bool(checklist.passed if checklist else (not require_pb)) and edge.ok and defined_risk

        compete_summary = ""
        if competition is not None:
            compete_summary = competition.scoreboard_summary(6)
            if competition.winner:
                method_tags = list(
                    dict.fromkeys(
                        method_tags
                        + [
                            f"sleeve:{competition.winner.sleeve_id}",
                            f"setup:{competition.winner.setup_id}",
                        ]
                    )
                )
                method_notes = (
                    f"Sleeve WIN {competition.winner.sleeve_id} "
                    f"score={competition.winner.score:.0f}; {compete_summary}"
                )[:240]

        method_boost = min(10.0, 2.0 * len(method_tags)) if method_tags else 0.0
        compete_score = compute_compete_score(
            setup_core=float(combined or quality or 0),
            book_points=float(book_points or 0),
            method_boost=method_boost,
        )
        scored.append(
            {
                "grade": grade_result.grade,
                "grade_score": grade_result.grade_score,
                "quality": quality,
                "confidence": confidence,
                "candidate": candidate,
                "technical": technical,
                "options": options,
                "strategy": strategy,
                "grade_result": grade_result,
                "params": params,
                "setup_id": setup_id,
                "playbook_name": checklist.setup_name if checklist else "",
                "checklist_passed": bool(checklist.passed) if checklist else (not require_pb),
                "checklist_summary": pb_summary,
                "edge_complete": edge.ok,
                "edge_summary": edge.summary,
                "competition_summary": compete_summary,
                "mtf_gate_reason": mtf_reason,
                "proposed_risk_pct": proposed_risk_pct,
                "smb_summary": smb.summary,
                "ta_summary": ta.summary,
                "fundamental_score": fund_score,
                "fundamental_passed": fund_passed,
                "fundamental_summary": fund_summary,
                "combined_quality_score": combined,
                "auto_trade_eligible": auto_eligible,
                "method_tags": method_tags,
                "method_notes": method_notes,
                "options_strategy_class": opt_class,
                "iv_rank": float(options.iv_rank or 0),
                "options_pop": float(options.probability_of_profit or 0),
                "options_delta": float(options.delta or 0),
                "expiration_days": int(strategy.expiration_days or 0),
                "defined_risk": defined_risk,
                "options_method_notes": opt_notes,
                "book_points": float(book_points or 0),
                "compete_score": compete_score,
                "book_gates_mode": gates_mode,
            }
        )

    if gates_mode == "score":
        scored.sort(
            key=lambda row: (
                -float(row.get("compete_score") or 0),
                grade_sort_key(
                    row["grade"], row["grade_score"], row["quality"], row["confidence"]
                ),
            ),
        )
    else:
        scored.sort(
            key=lambda row: grade_sort_key(
                row["grade"], row["grade_score"], row["quality"], row["confidence"]
            ),
        )

    # Rails after grade-sort: cool-down / concurrent / aggregate apply in rank order.
    # record_open after each accept so one pass cannot emit N > max_concurrent_plays.
    opportunities: List[TradeOpportunity] = []
    for row in scored:
        grade = row["grade"]
        grade_score = row["grade_score"]
        quality = row["quality"]
        confidence = row["confidence"]
        candidate = row["candidate"]
        technical = row["technical"]
        options = row["options"]
        strategy = row["strategy"]
        grade_result = row["grade_result"]
        params = row["params"]
        proposed_risk_pct = float(row["proposed_risk_pct"])

        if enforce_rails:
            rail = check_discipline_rails(
                symbol=candidate.symbol,
                proposed_risk_pct=proposed_risk_pct,
                state=state,
            )
            if not rail.allowed:
                if rail_rejections is not None:
                    rail_rejections.append(
                        RejectedSetup(
                            symbol=candidate.symbol,
                            reason="Discipline rails: " + "; ".join(rail.reasons),
                        )
                    )
                continue

        if len(opportunities) >= limit:
            if rail_rejections is not None:
                rail_rejections.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason=(
                            f"Discipline rails: top_candidates limit {limit} reached "
                            f"(not adding after ranked book fill)"
                        ),
                    )
                )
            continue

        # Claim book slot so subsequent names in this pass see updated concurrent/aggregate
        if enforce_rails:
            state.record_open(candidate.symbol, proposed_risk_pct)

        rank = len(opportunities) + 1
        expiry = (datetime.now() + timedelta(days=strategy.expiration_days)).strftime("%Y-%m-%d")
        thesis = _thesis(candidate, technical, options, strategy, grade=grade)
        risks = _risks(candidate, technical, options, strategy, grade=grade)
        tf_summary = ", ".join(
            f"{k}={v}" for k, v in technical.timeframe_trends.items() if k != "intraday"
        )
        reasons = [
            f"Setup grade {grade} (score {grade_score:.1f}) — trade priority "
            f"{'HIGH (A-tier first)' if grade in ('A+', 'A') else 'secondary'}",
            f"Sleeve competition: {row.get('competition_summary') or 'off'}",
            f"Playbook: {row['playbook_name'] or row['setup_id'] or 'n/a'} — {row['checklist_summary']}",
            f"Edge: {row['edge_summary']}",
            f"SMB books: {row.get('smb_summary') or 'n/a'}",
            f"Investopedia TA books: {row.get('ta_summary') or 'n/a'}",
            f"Hold style: {grade_result.hold_style}",
            f"PT/SL structure: stop@{params.get('stop_basis') or 'n/a'} "
            f"({params.get('geometry_source') or 'n/a'}), "
            f"target@{params.get('target_basis') or 'n/a'}; "
            f"LFD={params.get('lfd_level')}, breakout={params.get('breakout_level')}, "
            f"negation={params.get('negation_level')}, measured={params.get('measured_target')}; "
            f"grade ATR mults stop×{grade_result.stop_atr_mult}/target×{grade_result.target_atr_mult} "
            f"(buffer only)",
            f"Multi-timeframe: {tf_summary} (alignment: {technical.timeframe_alignment})",
            f"EMAs 9/20/50/200: {technical.ema_9:.2f}/{technical.ema_20:.2f}/"
            f"{technical.ema_50:.2f}/{technical.ema_200:.2f}; MA={technical.ma_alignment}",
            f"RSI {technical.rsi}, MACD {technical.macd_signal}, ADX {technical.adx}, "
            f"ATR {technical.atr}, BB {technical.bollinger_position}, VWAP {technical.vwap_relation}",
            f"Breakout={technical.breakout_state}, momentum={technical.momentum}, "
            f"volume profile={technical.volume_profile_bias}, RS={technical.relative_strength}",
            f"Candles={','.join(technical.candle_patterns) or 'none'}; "
            f"institutional PA={','.join(technical.pa_signals) or 'none'} "
            f"({technical.pattern_summary})",
            f"Options IV {options.implied_volatility} IVR {options.iv_rank} IVP {options.iv_percentile} "
            f"EM {options.expected_move_pct}% POP {options.probability_of_profit} "
            f"POT {options.probability_of_touch} liq {options.liquidity_score} "
            f"flow {options.institutional_flow_bias}",
            f"Strategy {strategy.name} ({strategy.direction})",
            f"RVOL {candidate.relative_volume}x, OI {candidate.open_interest}, "
            f"institutional score {candidate.institutional_score}",
        ]
        if row["mtf_gate_reason"]:
            reasons.append(row["mtf_gate_reason"])
        for gr in grade_result.reasons[:3]:
            if gr not in reasons:
                reasons.append(f"Grade factor: {gr}")

        opportunities.append(
            TradeOpportunity(
                rank=rank,
                symbol=candidate.symbol,
                strategy=strategy.name,
                entry_price=params["entry_price"],
                strike_prices=strategy.strike_prices,
                expiration=expiry,
                profit_target=params["profit_target"],
                stop_loss=params["stop_loss"],
                maximum_risk=params["maximum_risk"],
                maximum_reward=params["maximum_reward"],
                probability_of_success=params["probability_of_success"],
                confidence_score=confidence,
                supporting_reasons=reasons,
                technical=technical,
                options=options,
                direction=strategy.direction,
                trade_thesis=thesis,
                trade_quality_score=quality,
                risks=risks,
                setup_grade=grade,
                grade_score=grade_score,
                hold_style=grade_result.hold_style,
                grade_reasons=list(grade_result.reasons),
                playbook_setup_id=row["setup_id"],
                playbook_name=row["playbook_name"],
                checklist_passed=row["checklist_passed"],
                checklist_summary=row["checklist_summary"],
                edge_complete=row["edge_complete"],
                edge_summary=row["edge_summary"],
                mtf_gate_reason=row["mtf_gate_reason"],
                fundamental_score=float(row.get("fundamental_score") or 0.0),
                fundamental_passed=bool(row.get("fundamental_passed", True)),
                fundamental_summary=str(row.get("fundamental_summary") or ""),
                combined_quality_score=float(row.get("combined_quality_score") or quality),
                auto_trade_eligible=bool(row.get("auto_trade_eligible", False)),
                book_points=float(row.get("book_points") or 0.0),
                compete_score=float(row.get("compete_score") or 0.0),
                book_gates_mode=str(row.get("book_gates_mode") or "hard"),
                method_tags=list(row.get("method_tags") or []),
                method_notes=str(row.get("method_notes") or ""),
                options_strategy_class=str(row.get("options_strategy_class") or ""),
                iv_rank=float(row.get("iv_rank") or 0),
                options_pop=float(row.get("options_pop") or 0),
                options_delta=float(row.get("options_delta") or 0),
                expiration_days=int(row.get("expiration_days") or 0),
                defined_risk=bool(row.get("defined_risk", True)),
                options_method_notes=str(row.get("options_method_notes") or ""),
                stop_basis=str(params.get("stop_basis") or ""),
                target_basis=str(params.get("target_basis") or ""),
                geometry_source=str(params.get("geometry_source") or ""),
                risk_policy=str(params.get("risk_policy") or ""),
                lfd_level=float(params.get("lfd_level") or 0.0),
                breakout_level=float(params.get("breakout_level") or 0.0),
                negation_level=float(params.get("negation_level") or 0.0),
                measured_target=float(params.get("measured_target") or 0.0),
                pattern_height=float(params.get("pattern_height") or 0.0),
                structure_notes=str(params.get("structure_notes") or ""),
            )
        )

    return opportunities
