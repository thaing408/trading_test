"""P2 researcher debate: bull / bear / facilitator → DebateVerdict.

Consumes P1 analyst reports only (no new market tools). Never bypasses
deterministic risk rails — verdict is advisory for CIO/trader (P3+).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trading_agent.firm.llm import chat_json, llm_enabled
from trading_agent.firm.reports import (
    DebateVerdict,
    FundamentalReport,
    NewsReport,
    ReportMeta,
    SentimentReport,
    TechnicalReport,
)


def debate_rounds() -> int:
    try:
        n = int(os.getenv("TRADING_AGENT_FIRM_DEBATE_ROUNDS", "2") or 2)
    except ValueError:
        n = 2
    return max(1, min(5, n))


@dataclass
class DebateRound:
    round_num: int
    bull_args: List[str] = field(default_factory=list)
    bear_args: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round_num,
            "bull_args": self.bull_args,
            "bear_args": self.bear_args,
        }


def _clip(points: Sequence[str], n: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for p in points:
        t = str(p or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t[:180])
        if len(out) >= n:
            break
    return out


def bull_opening_points(
    tech: TechnicalReport,
    news: NewsReport,
    fund: FundamentalReport,
    sent: SentimentReport,
) -> List[str]:
    pts: List[str] = []
    if tech.bias == "bullish" or tech.regime in ("uptrend",):
        pts.append(f"Technical bias {tech.bias}/{tech.regime} — {tech.entry_timing}")
    if tech.bias == "bullish" and not any("overbought" in c for c in tech.method_conflicts):
        pts.append("Trend/MA alignment supports add-on longs")
    if fund.fundamental_score >= 60:
        pts.append(f"Fundamentals supportive (score {fund.fundamental_score:.0f})")
    if fund.fundamental_score >= 75:
        pts.append(f"Quality: {fund.quality_summary[:120]}")
    if sent.tilt == "bullish" or sent.score >= 15:
        pts.append(f"Sentiment tilt {sent.tilt} ({sent.score:+.0f})")
    for h in (news.name_catalysts or news.headlines)[:3]:
        low = h.lower()
        if any(w in low for w in ("beat", "upgrade", "growth", "record", "win", "approval", "surge")):
            pts.append(f"Catalyst: {h[:140]}")
    if not pts:
        pts.append("Limited long case — only soft constructive bias from mixed reports")
    return _clip(pts)


def bear_opening_points(
    tech: TechnicalReport,
    news: NewsReport,
    fund: FundamentalReport,
    sent: SentimentReport,
) -> List[str]:
    pts: List[str] = []
    if tech.bias == "bearish" or tech.regime in ("downtrend",):
        pts.append(f"Technical bias {tech.bias}/{tech.regime} — {tech.exit_timing}")
    for c in tech.method_conflicts[:4]:
        pts.append(f"Conflict risk: {c}")
    if fund.fundamental_score and fund.fundamental_score < 50:
        pts.append(f"Weak fundamentals (score {fund.fundamental_score:.0f})")
    if fund.earnings_risk and any(
        x in fund.earnings_risk.lower() for x in ("days_to=0", "days_to=1", "days_to=2", "event")
    ):
        pts.append(f"Event risk: {fund.earnings_risk[:140]}")
    if "(-20)" in " ".join(fund.reasons) or "Earnings in" in " ".join(fund.reasons):
        pts.append("Near-term earnings / binary event in fundamental reasons")
    if sent.tilt == "bearish" or sent.score <= -15:
        pts.append(f"Sentiment tilt {sent.tilt} ({sent.score:+.0f})")
    for h in (news.name_catalysts or news.headlines)[:3]:
        low = h.lower()
        if any(w in low for w in ("miss", "downgrade", "probe", "lawsuit", "cut", "delay", "fraud", "tariff")):
            pts.append(f"Negative catalyst: {h[:140]}")
    for m in news.macro_catalysts[:2]:
        pts.append(f"Macro overhang: {m[:140]}")
    if not pts:
        pts.append("Limited short case — fade requires clearer deterioration")
    return _clip(pts)


def _bull_rebuttal(round_num: int, bear_pts: List[str], bull_pts: List[str]) -> List[str]:
    """Round 2+: bull answers bear risks without inventing data."""
    out: List[str] = []
    joined = " ".join(bear_pts).lower()
    if "earnings" in joined or "event" in joined:
        out.append("Event risk acknowledged — size smaller / wait post-print rather than abandon trend")
    if "conflict" in joined or "overbought" in joined:
        out.append("Conflicts argue for pullback entries, not full avoidance of bullish structure")
    if "weak fundamental" in joined or "score" in joined:
        out.append("Price/technical leadership can lead fundamentals; use defined-risk options")
    if "macro" in joined or "tariff" in joined:
        out.append("Macro is a haircut to size, not an automatic veto if name catalysts dominate")
    if not out:
        out.append(f"Round {round_num}: prior bull case still stands; bear points are manage-risk items")
    # keep strongest prior bull point
    if bull_pts:
        out.append(f"Reaffirm: {bull_pts[0]}")
    return _clip(out, 6)


def _bear_rebuttal(round_num: int, bull_pts: List[str], bear_pts: List[str]) -> List[str]:
    out: List[str] = []
    joined = " ".join(bull_pts).lower()
    if "technical" in joined or "uptrend" in joined or "bullish" in joined:
        out.append("Trends fail at resistance — without confirmation, long adds are chasing")
    if "fundamental" in joined or "score" in joined:
        out.append("Good scores do not remove gap/liquidity risk into catalysts")
    if "sentiment" in joined or "catalyst" in joined:
        out.append("Headline-driven sentiment can reverse quickly; fade strength into news")
    if not out:
        out.append(f"Round {round_num}: asymmetric downside still underpriced vs bull narrative")
    if bear_pts:
        out.append(f"Reaffirm: {bear_pts[0]}")
    return _clip(out, 6)


def _score_side(points: List[str], *, bull: bool, tech: TechnicalReport, fund: FundamentalReport, sent: SentimentReport) -> float:
    """Heuristic strength 0..100."""
    score = 10.0 * len(points)
    if bull:
        if tech.bias == "bullish":
            score += 20
        if fund.fundamental_score >= 70:
            score += 15
        elif fund.fundamental_score >= 55:
            score += 8
        if sent.tilt == "bullish":
            score += 10
        score -= 5 * len([c for c in tech.method_conflicts if "bullish" in c or "overbought" in c])
    else:
        if tech.bias == "bearish":
            score += 20
        if fund.fundamental_score and fund.fundamental_score < 45:
            score += 15
        if sent.tilt == "bearish":
            score += 10
        score += 8 * min(3, len(tech.method_conflicts))
        if any("earnings" in r.lower() for r in fund.reasons):
            score += 12
    return max(0.0, min(100.0, score))


def facilitate_verdict(
    *,
    symbol: str,
    trading_date: str,
    rounds: Sequence[DebateRound],
    tech: TechnicalReport,
    fund: FundamentalReport,
    sent: SentimentReport,
    news: NewsReport,
) -> DebateVerdict:
    last = rounds[-1] if rounds else DebateRound(0)
    bull_score = _score_side(last.bull_args, bull=True, tech=tech, fund=fund, sent=sent)
    bear_score = _score_side(last.bear_args, bull=False, tech=tech, fund=fund, sent=sent)
    delta = bull_score - bear_score

    if abs(delta) < 8:
        winner = "draw"
        confidence = round(40 + abs(delta), 1)
    elif delta > 0:
        winner = "bull"
        confidence = round(min(92.0, 55 + delta / 2), 1)
    else:
        winner = "bear"
        confidence = round(min(92.0, 55 + abs(delta) / 2), 1)

    open_risks: List[str] = []
    open_risks.extend(tech.method_conflicts[:4])
    open_risks.extend([r for r in fund.reasons if "earnings" in r.lower() or "risk" in r.lower()][:3])
    open_risks.extend(news.macro_catalysts[:2])
    if sent.tilt == "bearish" and winner == "bull":
        open_risks.append("sentiment_disagrees_with_bull_verdict")
    if sent.tilt == "bullish" and winner == "bear":
        open_risks.append("sentiment_disagrees_with_bear_verdict")
    open_risks.append("advisory_only_hard_rails_still_apply")
    open_risks = _clip(open_risks, 10)

    summary = (
        f"{symbol} debate → **{winner}** (conf {confidence:.0f}; "
        f"bull_score={bull_score:.0f} bear_score={bear_score:.0f}, rounds={len(rounds)}). "
        f"Does not bypass stay-in-cash / ADR / OMS rails."
    )

    return DebateVerdict(
        meta=ReportMeta(
            symbol=symbol.upper(),
            trading_date=trading_date,
            role="debate_facilitator",
            status="stub",
        ),
        winner=winner,
        confidence=confidence,
        rounds=len(rounds),
        bull_points=_clip(last.bull_args, 10),
        bear_points=_clip(last.bear_args, 10),
        open_risks=open_risks,
        summary=summary,
    )


def run_debate(
    *,
    symbol: str,
    trading_date: str,
    tech: TechnicalReport,
    news: NewsReport,
    fund: FundamentalReport,
    sent: SentimentReport,
    use_llm: bool = True,
    n_rounds: Optional[int] = None,
) -> Tuple[DebateVerdict, List[Dict[str, Any]]]:
    """N-round bull/bear debate → facilitator verdict + transcript."""
    n = n_rounds if n_rounds is not None else debate_rounds()
    transcript: List[Dict[str, Any]] = []

    bull = bull_opening_points(tech, news, fund, sent)
    bear = bear_opening_points(tech, news, fund, sent)
    rounds: List[DebateRound] = [DebateRound(1, bull_args=bull, bear_args=bear)]
    transcript.append({"role": "bull_researcher", "round": 1, "points": bull})
    transcript.append({"role": "bear_researcher", "round": 1, "points": bear})

    for r in range(2, n + 1):
        bull = _bull_rebuttal(r, bear, bull)
        bear = _bear_rebuttal(r, bull, bear)
        rounds.append(DebateRound(r, bull_args=bull, bear_args=bear))
        transcript.append({"role": "bull_researcher", "round": r, "points": bull})
        transcript.append({"role": "bear_researcher", "round": r, "points": bear})

    verdict = facilitate_verdict(
        symbol=symbol,
        trading_date=trading_date,
        rounds=rounds,
        tech=tech,
        fund=fund,
        sent=sent,
        news=news,
    )
    transcript.append(
        {
            "role": "debate_facilitator",
            "winner": verdict.winner,
            "confidence": verdict.confidence,
            "summary": verdict.summary,
        }
    )

    if use_llm and llm_enabled():
        sys = (
            "You are the debate facilitator for a trading firm. "
            "Given bull and bear points from analyst reports, return ONLY JSON with keys: "
            "winner (bull|bear|draw), confidence (0-100), bull_points (array), "
            "bear_points (array), open_risks (array), summary. "
            "Stay faithful to provided points; do not invent prices. "
            "Reminder: verdict is advisory; hard risk rails still apply."
        )
        user = (
            f"Symbol {symbol}. Heuristic winner={verdict.winner} conf={verdict.confidence}.\n"
            f"Bull: {verdict.bull_points}\nBear: {verdict.bear_points}\n"
            f"Tech bias={tech.bias} fund_score={fund.fundamental_score} sent={sent.tilt}\n"
            f"Open risks so far: {verdict.open_risks}"
        )
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            w = str(d.get("winner") or verdict.winner).lower().strip()
            if w in ("bull", "bear", "draw"):
                verdict.winner = w
            try:
                verdict.confidence = float(d.get("confidence") or verdict.confidence)
            except (TypeError, ValueError):
                pass
            if isinstance(d.get("bull_points"), list):
                verdict.bull_points = _clip([str(x) for x in d["bull_points"]], 10)
            if isinstance(d.get("bear_points"), list):
                verdict.bear_points = _clip([str(x) for x in d["bear_points"]], 10)
            if isinstance(d.get("open_risks"), list):
                risks = [str(x) for x in d["open_risks"]]
                if "advisory_only_hard_rails_still_apply" not in " ".join(risks):
                    risks.append("advisory_only_hard_rails_still_apply")
                verdict.open_risks = _clip(risks, 10)
            if d.get("summary"):
                verdict.summary = str(d["summary"])[:400]
            verdict.meta.status = "complete"
            verdict.meta.model = str(llm.get("model") or "")
            transcript.append({"role": "debate_facilitator_llm", "data": d})

    if verdict.meta.status == "empty":
        verdict.meta.status = "stub"
    return verdict, transcript
