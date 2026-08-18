"""Typed firm documents (P0 schemas — empty/stub fills until LLM analysts land)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReportMeta:
    symbol: str
    trading_date: str
    role: str
    schema_version: str = "firm_report_v1"
    generated_at: str = field(default_factory=_utc_now)
    status: str = "empty"  # empty | stub | complete | error
    model: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FundamentalReport:
    meta: ReportMeta
    valuation_summary: str = ""
    quality_summary: str = ""
    leverage_summary: str = ""
    earnings_risk: str = ""
    fundamental_score: float = 0.0
    horizon: str = "multi_day"
    reasons: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "FundamentalReport":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="fundamental_analyst",
                status="empty",
            ),
            reasons=["P0 stub — LLM fundamental analyst not enabled"],
        )


@dataclass
class SentimentReport:
    meta: ReportMeta
    score: float = 0.0  # -100..100
    tilt: str = "neutral"  # bullish | bearish | neutral
    peaks: List[str] = field(default_factory=list)
    engagement_notes: str = ""
    reasons: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "SentimentReport":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="sentiment_analyst",
                status="empty",
            ),
            reasons=["P0 stub — social/sentiment feeds not wired"],
        )


@dataclass
class NewsReport:
    meta: ReportMeta
    macro_catalysts: List[str] = field(default_factory=list)
    name_catalysts: List[str] = field(default_factory=list)
    surprise_vs_consensus: str = ""
    what_moves_next: str = ""
    headlines: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "NewsReport":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="news_analyst",
                status="empty",
            ),
            reasons=["P0 stub — LLM news analyst not enabled"],
        )


@dataclass
class TechnicalReport:
    meta: ReportMeta
    regime: str = ""
    bias: str = "neutral"
    entry_timing: str = ""
    exit_timing: str = ""
    method_conflicts: List[str] = field(default_factory=list)
    indicator_highlights: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "TechnicalReport":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="technical_analyst",
                status="empty",
            ),
            reasons=["P0 stub — LLM technical analyst not enabled"],
        )


@dataclass
class DebateVerdict:
    meta: ReportMeta
    winner: str = "undecided"  # bull | bear | draw | undecided
    confidence: float = 0.0
    rounds: int = 0
    bull_points: List[str] = field(default_factory=list)
    bear_points: List[str] = field(default_factory=list)
    open_risks: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "DebateVerdict":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="debate_facilitator",
                status="empty",
            ),
            summary="P0 stub — bull/bear debate not enabled",
            open_risks=["debate_not_run"],
        )


@dataclass
class TraderProposal:
    meta: ReportMeta
    action: str = "HOLD"  # BUY | SELL | HOLD
    side: str = ""
    size_hint: str = ""
    timing: str = ""
    confidence: float = 0.0
    thesis: str = ""
    book_hints: Dict[str, Any] = field(default_factory=dict)
    # Preserve options path
    instrument: str = "options"
    defined_risk: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "TraderProposal":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="trader",
                status="empty",
            ),
            thesis="P0 stub — trader agent not enabled",
        )


@dataclass
class RiskAdjustment:
    meta: ReportMeta
    recommendation: str = "unchanged"  # increase | cut_size | tighten_stop | veto | unchanged
    size_mult: float = 1.0
    stop_note: str = ""
    exposure_notes: List[str] = field(default_factory=list)
    persona_votes: Dict[str, str] = field(default_factory=dict)
    hard_rails_respected: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "RiskAdjustment":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="risk_facilitator",
                status="empty",
            ),
            exposure_notes=["P0 stub — risk debate not enabled"],
        )


@dataclass
class ManagerDecision:
    meta: ReportMeta
    decision: str = "defer"  # approve | modify | reject | defer
    size_mult: float = 1.0
    notes: str = ""
    cites_debate_winner: str = ""
    cites_risk_adjustment: str = ""
    cio_handoff: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["meta"] = self.meta.to_dict()
        return d

    @classmethod
    def empty(cls, symbol: str, trading_date: str) -> "ManagerDecision":
        return cls(
            meta=ReportMeta(
                symbol=symbol,
                trading_date=trading_date,
                role="fund_manager",
                status="empty",
            ),
            notes="P0 stub — manager overlay not enabled; CIO unchanged",
            decision="defer",
        )


REPORT_FILENAMES = {
    "fundamental": "fundamental_report.json",
    "sentiment": "sentiment_report.json",
    "news": "news_report.json",
    "technical": "technical_report.json",
    "debate": "debate_verdict.json",
    "trader": "trader_proposal.json",
    "risk": "risk_adjustment.json",
    "manager": "manager_decision.json",
}
