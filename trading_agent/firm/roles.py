"""TradingAgents-style role contracts (P0 — no LLM yet)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class RoleContract:
    """Immutable contract for one firm role."""

    name: str
    team: str  # analysts | researchers | trader | risk | manager
    goal: str
    constraints: Tuple[str, ...] = ()
    allowed_tools: Tuple[str, ...] = ()
    output_schema: str = ""  # report type name
    uses_deep_llm: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "team": self.team,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "allowed_tools": list(self.allowed_tools),
            "output_schema": self.output_schema,
            "uses_deep_llm": self.uses_deep_llm,
        }


ANALYST_TOOLS = (
    "ohlcv",
    "ta_bundle",
    "news",
    "fundamentals",
    "insider",
    "social",
)

FIRM_ROLES: Dict[str, RoleContract] = {
    "fundamental_analyst": RoleContract(
        name="fundamental_analyst",
        team="analysts",
        goal="Produce a structured fundamental thesis (valuation, quality, leverage, earnings).",
        constraints=(
            "No trade sizing",
            "Cite tool observations only",
            "Do not bypass stay-in-cash rails",
        ),
        allowed_tools=("fundamentals", "insider", "ohlcv", "news"),
        output_schema="FundamentalReport",
        uses_deep_llm=True,
    ),
    "sentiment_analyst": RoleContract(
        name="sentiment_analyst",
        team="analysts",
        goal="Score short-horizon sentiment from news/social when available.",
        constraints=("Degrade cleanly if social feeds absent",),
        allowed_tools=("social", "news"),
        output_schema="SentimentReport",
        uses_deep_llm=True,
    ),
    "news_analyst": RoleContract(
        name="news_analyst",
        team="analysts",
        goal="Summarize macro + name catalysts and what can move next session.",
        constraints=("No portfolio construction",),
        allowed_tools=("news", "ohlcv"),
        output_schema="NewsReport",
        uses_deep_llm=True,
    ),
    "technical_analyst": RoleContract(
        name="technical_analyst",
        team="analysts",
        goal="Regime + timing write-up from existing TA/PA/multi-method signals.",
        constraints=("Reuse desk indicators; do not invent bars",),
        allowed_tools=("ohlcv", "ta_bundle"),
        output_schema="TechnicalReport",
        uses_deep_llm=True,
    ),
    "bull_researcher": RoleContract(
        name="bull_researcher",
        team="researchers",
        goal="Argue only the long/add case from analyst reports.",
        constraints=("Must cite report fields", "No new tools beyond reports"),
        allowed_tools=(),
        output_schema="DebateVerdict",
        uses_deep_llm=True,
    ),
    "bear_researcher": RoleContract(
        name="bear_researcher",
        team="researchers",
        goal="Argue only fade/avoid/risks from analyst reports.",
        constraints=("Must cite report fields", "No new tools beyond reports"),
        allowed_tools=(),
        output_schema="DebateVerdict",
        uses_deep_llm=True,
    ),
    "debate_facilitator": RoleContract(
        name="debate_facilitator",
        team="researchers",
        goal="Run N-round bull/bear debate and emit structured verdict.",
        constraints=("Cannot bypass deterministic risk rails",),
        allowed_tools=(),
        output_schema="DebateVerdict",
        uses_deep_llm=True,
    ),
    "trader": RoleContract(
        name="trader",
        team="trader",
        goal="BUY/SELL/HOLD + size/timing from reports + debate + book geometry.",
        constraints=(
            "Preserve options structure (DTE, defined risk)",
            "Map into auto_trade_book fields",
        ),
        allowed_tools=("ohlcv", "ta_bundle"),
        output_schema="TraderProposal",
        uses_deep_llm=True,
    ),
    "risk_aggressive": RoleContract(
        name="risk_aggressive",
        team="risk",
        goal="Argue for larger size / looser stops when edge is clear.",
        constraints=("Advisory only; hard rails still win",),
        allowed_tools=("ohlcv",),
        output_schema="RiskAdjustment",
        uses_deep_llm=True,
    ),
    "risk_neutral": RoleContract(
        name="risk_neutral",
        team="risk",
        goal="Balance trader proposal vs open exposure and liquidity.",
        constraints=("Advisory only; hard rails still win",),
        allowed_tools=("ohlcv",),
        output_schema="RiskAdjustment",
        uses_deep_llm=True,
    ),
    "risk_conservative": RoleContract(
        name="risk_conservative",
        team="risk",
        goal="Argue cut size / tighten / veto under uncertainty.",
        constraints=("Advisory only; hard rails still win",),
        allowed_tools=("ohlcv",),
        output_schema="RiskAdjustment",
        uses_deep_llm=True,
    ),
    "risk_facilitator": RoleContract(
        name="risk_facilitator",
        team="risk",
        goal="Synthesize risk personas into one RiskAdjustment.",
        constraints=("Cannot remove cash floor / max risk / earnings hard blocks",),
        allowed_tools=(),
        output_schema="RiskAdjustment",
        uses_deep_llm=True,
    ),
    "fund_manager": RoleContract(
        name="fund_manager",
        team="manager",
        goal="Final Approve/Modify/Reject overlay feeding CIO notes.",
        constraints=(
            "CIO still owns formal Approve/Modify/Reject",
            "Never skip OMS / DTE / eligibility",
        ),
        allowed_tools=(),
        output_schema="ManagerDecision",
        uses_deep_llm=True,
    ),
}


def roles_by_team() -> Dict[str, List[RoleContract]]:
    out: Dict[str, List[RoleContract]] = {}
    for role in FIRM_ROLES.values():
        out.setdefault(role.team, []).append(role)
    return out
