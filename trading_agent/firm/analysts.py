"""P1 firm analysts — heuristic reports + optional LLM enrichment."""

from __future__ import annotations

from typing import Any, Dict, Optional

from trading_agent.firm.llm import chat_json, llm_enabled
from trading_agent.firm.reports import (
    FundamentalReport,
    NewsReport,
    ReportMeta,
    SentimentReport,
    TechnicalReport,
)


def _meta(symbol: str, trading_date: str, role: str, status: str, model: str = "") -> ReportMeta:
    return ReportMeta(
        symbol=symbol.upper(),
        trading_date=trading_date,
        role=role,
        status=status,
        model=model,
    )


def build_technical_report(
    symbol: str,
    trading_date: str,
    ta: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> TechnicalReport:
    sym = symbol.upper()
    if ta.get("status") != "ok":
        return TechnicalReport(
            meta=_meta(sym, trading_date, "technical_analyst", "empty"),
            reasons=[f"TA unavailable: {ta.get('error') or ta.get('status')}"],
            sources=["gather_ta_bundle"],
        )

    regime = str(ta.get("regime") or "")
    bias = str(ta.get("bias") or "neutral")
    rsi = float(ta.get("rsi14") or 50)
    macd = str(ta.get("macd") or "neutral")
    align = str(ta.get("ma_alignment") or "mixed")
    bb = str(ta.get("bollinger") or "middle")
    sr = ta.get("support_resistance") or [0, 0]
    highlights = [
        f"RSI14={rsi}",
        f"MACD={macd}",
        f"MA={align}",
        f"BB={bb}",
        f"ADX={ta.get('adx14')}",
        f"ATR={ta.get('atr14')}",
        f"S/R={sr}",
        f"last={ta.get('last')} ({ta.get('change_pct')}%)",
    ]
    conflicts = []
    if bias == "bullish" and rsi > 70:
        conflicts.append("bullish_trend_but_rsi_overbought")
    if bias == "bearish" and rsi < 30:
        conflicts.append("bearish_trend_but_rsi_oversold")
    if align == "bullish" and macd == "bearish":
        conflicts.append("ma_bullish_vs_macd_bearish")
    if align == "bearish" and macd == "bullish":
        conflicts.append("ma_bearish_vs_macd_bullish")

    entry = "prefer pullback to support" if bias == "bullish" else (
        "prefer bounce failure at resistance" if bias == "bearish" else "wait for range break"
    )
    exit_ = "trail under higher lows" if bias == "bullish" else (
        "trail above lower highs" if bias == "bearish" else "tight invalidation"
    )
    reasons = [
        f"regime={regime} bias={bias}",
        f"alignment={align} macd={macd} rsi={rsi}",
    ]
    report = TechnicalReport(
        meta=_meta(sym, trading_date, "technical_analyst", "stub"),
        regime=regime,
        bias=bias,
        entry_timing=entry,
        exit_timing=exit_,
        method_conflicts=conflicts,
        indicator_highlights=highlights,
        reasons=reasons,
        sources=["gather_ta_bundle", "analysis.technical"],
    )

    if use_llm and llm_enabled():
        sys = (
            "You are the technical analyst on a trading desk. "
            "Return ONLY a JSON object with keys: regime, bias, entry_timing, "
            "exit_timing, method_conflicts (array of strings), summary (short), "
            "confidence (0-100). Be concise."
        )
        user = f"Symbol {sym}. Indicator pack:\n{highlights}\nConflicts so far: {conflicts}"
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            report.regime = str(d.get("regime") or report.regime)
            report.bias = str(d.get("bias") or report.bias)
            report.entry_timing = str(d.get("entry_timing") or report.entry_timing)
            report.exit_timing = str(d.get("exit_timing") or report.exit_timing)
            if isinstance(d.get("method_conflicts"), list):
                report.method_conflicts = [str(x) for x in d["method_conflicts"][:8]]
            if d.get("summary"):
                report.reasons = [str(d["summary"])] + report.reasons[:3]
            report.meta.status = "complete"
            report.meta.model = str(llm.get("model") or "")
            report.sources.append("xai_llm")
    return report


def build_news_report(
    symbol: str,
    trading_date: str,
    news: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> NewsReport:
    sym = symbol.upper()
    items = news.get("items") or []
    if not items and news.get("status") != "ok":
        return NewsReport(
            meta=_meta(sym, trading_date, "news_analyst", "empty"),
            reasons=[f"News unavailable: {news.get('error') or news.get('status')}"],
            sources=["gather_news"],
        )

    headlines = [str(it.get("headline") or "")[:180] for it in items[:10]]
    name = []
    macro = []
    for it in items:
        cat = str(it.get("category") or "general")
        h = str(it.get("headline") or "")[:160]
        if cat in ("geopolitical",) or "fed" in h.lower() or "tariff" in h.lower():
            macro.append(h)
        else:
            name.append(h)
    report = NewsReport(
        meta=_meta(sym, trading_date, "news_analyst", "stub" if headlines else "empty"),
        macro_catalysts=macro[:5],
        name_catalysts=name[:8],
        headlines=headlines,
        what_moves_next="Watch catalysts in name_catalysts vs broad risk tone",
        surprise_vs_consensus="",
        reasons=[f"n_headlines={len(headlines)} source={news.get('source')}"],
        sources=["gather_news", str(news.get("source") or "")],
    )

    if use_llm and llm_enabled() and headlines:
        sys = (
            "You are the news analyst on a trading desk. Return ONLY JSON with keys: "
            "macro_catalysts (array), name_catalysts (array), surprise_vs_consensus, "
            "what_moves_next, summary. Focus on what can move the stock next session."
        )
        user = f"Symbol {sym}. Headlines:\n" + "\n".join(f"- {h}" for h in headlines)
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            if isinstance(d.get("macro_catalysts"), list):
                report.macro_catalysts = [str(x) for x in d["macro_catalysts"][:6]]
            if isinstance(d.get("name_catalysts"), list):
                report.name_catalysts = [str(x) for x in d["name_catalysts"][:8]]
            report.surprise_vs_consensus = str(d.get("surprise_vs_consensus") or "")
            report.what_moves_next = str(d.get("what_moves_next") or report.what_moves_next)
            if d.get("summary"):
                report.reasons = [str(d["summary"])] + report.reasons[:2]
            report.meta.status = "complete"
            report.meta.model = str(llm.get("model") or "")
            report.sources.append("xai_llm")
    return report


def build_fundamental_report(
    symbol: str,
    trading_date: str,
    fund: Dict[str, Any],
    insider: Optional[Dict[str, Any]] = None,
    *,
    use_llm: bool = True,
) -> FundamentalReport:
    sym = symbol.upper()
    score = float(fund.get("score") or 0.0)
    reasons = list(fund.get("reasons") or [])
    if fund.get("status") in ("error",) and score <= 0:
        return FundamentalReport(
            meta=_meta(sym, trading_date, "fundamental_analyst", "empty"),
            reasons=[str(fund.get("error") or "fundamentals_unavailable")],
            sources=["gather_fundamentals"],
        )

    valuation = (
        f"PE={fund.get('pe_ttm')} FPE={fund.get('forward_pe')} "
        f"mcap={fund.get('market_cap')}"
    )
    quality = (
        f"margin={fund.get('profit_margin')} rev_g={fund.get('revenue_growth')} "
        f"sector={fund.get('sector')}"
    )
    leverage = f"D/E={fund.get('debt_to_equity')}"
    earn = (
        f"earnings={fund.get('earnings_date')} days_to={fund.get('days_to_earnings')}"
    )
    if insider and insider.get("items"):
        reasons = reasons + [f"insider_news_n={len(insider['items'])}"]

    report = FundamentalReport(
        meta=_meta(
            sym,
            trading_date,
            "fundamental_analyst",
            "stub" if score > 0 or reasons else "empty",
        ),
        valuation_summary=valuation,
        quality_summary=quality,
        leverage_summary=leverage,
        earnings_risk=earn,
        fundamental_score=score,
        horizon="multi_day",
        reasons=reasons[:12] or ["no_fundamental_reasons"],
        sources=["gather_fundamentals", str(fund.get("source") or "")],
    )

    if use_llm and llm_enabled() and (score > 0 or reasons):
        sys = (
            "You are the fundamental analyst. Return ONLY JSON with keys: "
            "valuation_summary, quality_summary, leverage_summary, earnings_risk, "
            "fundamental_score (0-100), horizon, reasons (array), thesis."
        )
        user = (
            f"Symbol {sym}. Snapshot score={score} passed={fund.get('passed')}.\n"
            f"{valuation}\n{quality}\n{leverage}\n{earn}\nReasons: {reasons[:8]}"
        )
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            report.valuation_summary = str(d.get("valuation_summary") or report.valuation_summary)
            report.quality_summary = str(d.get("quality_summary") or report.quality_summary)
            report.leverage_summary = str(d.get("leverage_summary") or report.leverage_summary)
            report.earnings_risk = str(d.get("earnings_risk") or report.earnings_risk)
            try:
                report.fundamental_score = float(d.get("fundamental_score") or score)
            except (TypeError, ValueError):
                pass
            report.horizon = str(d.get("horizon") or report.horizon)
            if isinstance(d.get("reasons"), list):
                report.reasons = [str(x) for x in d["reasons"][:10]]
            elif d.get("thesis"):
                report.reasons = [str(d["thesis"])] + report.reasons[:5]
            report.meta.status = "complete"
            report.meta.model = str(llm.get("model") or "")
            report.sources.append("xai_llm")
    return report


def build_sentiment_report(
    symbol: str,
    trading_date: str,
    social: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> SentimentReport:
    sym = symbol.upper()
    score = float(social.get("score") or 0.0)
    tilt = str(social.get("tilt") or "neutral")
    peaks = list(social.get("peaks") or [])
    notes = str(social.get("engagement_notes") or "")
    if social.get("status") not in ("ok", "empty"):
        return SentimentReport(
            meta=_meta(sym, trading_date, "sentiment_analyst", "empty"),
            reasons=[str(social.get("error") or social.get("status"))],
            sources=["gather_social"],
        )

    reddit = social.get("reddit") if isinstance(social.get("reddit"), dict) else {}
    report = SentimentReport(
        meta=_meta(
            sym,
            trading_date,
            "sentiment_analyst",
            "stub" if social.get("status") == "ok" else "empty",
        ),
        score=score,
        tilt=tilt,
        peaks=peaks[:12],
        engagement_notes=notes,
        reasons=[f"tilt={tilt} score={score}", notes] if notes else [f"tilt={tilt}"],
        sources=["gather_social", str(social.get("source") or "news_tone_proxy")],
        reddit=dict(reddit),
        news_tone_score=float(social.get("news_tone_score") or 0.0),
    )
    if reddit:
        report.sources.append("reddit_public_json")
        rtilt = reddit.get("tilt")
        rn = reddit.get("n")
        report.reasons.append(f"reddit tilt={rtilt} n={rn} (informational, not auto-ENTER)")

    if use_llm and llm_enabled() and social.get("status") == "ok":
        sys = (
            "You are the sentiment analyst. Return ONLY JSON with keys: "
            "score (-100..100), tilt (bullish|bearish|neutral), peaks (array), "
            "engagement_notes, summary. Reddit is crowd heat only — do not treat "
            "as a trade signal."
        )
        user = f"Symbol {sym}. Sentiment payload={social}"
        llm = chat_json(sys, user, deep=False)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            try:
                report.score = float(d.get("score") or score)
            except (TypeError, ValueError):
                pass
            report.tilt = str(d.get("tilt") or tilt)
            if isinstance(d.get("peaks"), list):
                report.peaks = [str(x) for x in d["peaks"][:12]]
            report.engagement_notes = str(d.get("engagement_notes") or notes)
            if d.get("summary"):
                report.reasons = [str(d["summary"])] + report.reasons[:2]
            report.meta.status = "complete"
            report.meta.model = str(llm.get("model") or "")
            report.sources.append("xai_llm")
    return report
