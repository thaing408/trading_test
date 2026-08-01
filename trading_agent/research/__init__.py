"""Research integrity helpers: hypotheses, promotion gates, session replay."""

from trading_agent.research.hypotheses import HYPOTHESIS_REGISTRY, list_hypotheses
from trading_agent.research.promotion import PromotionChecklist, evaluate_promotion
from trading_agent.research.replay import replay_session_candidates

__all__ = [
    "HYPOTHESIS_REGISTRY",
    "list_hypotheses",
    "PromotionChecklist",
    "evaluate_promotion",
    "replay_session_candidates",
]
