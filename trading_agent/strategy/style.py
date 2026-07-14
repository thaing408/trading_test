"""Trading style taxonomy: breakout vs mean reversion.

Aligned with common market definitions and desk playbooks:
- BREAKOUT: trade *continuation* after price leaves a range/level.
- MEAN_REVERSION: fade extremes back toward a mean or level (RSI/level bounce).

888 Trading Intelligence is breakout-oriented; Shen 0DTE RSI fades are mean-reversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TradingStyle(str, Enum):
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"


# CLI / config aliases
STYLE_ALIASES = {
    "breakout": TradingStyle.BREAKOUT,
    "bo": TradingStyle.BREAKOUT,
    "continuation": TradingStyle.BREAKOUT,
    "mean_reversion": TradingStyle.MEAN_REVERSION,
    "mean-reversion": TradingStyle.MEAN_REVERSION,
    "mean_revert": TradingStyle.MEAN_REVERSION,
    "mean-revert": TradingStyle.MEAN_REVERSION,
    "mr": TradingStyle.MEAN_REVERSION,
    "fade": TradingStyle.MEAN_REVERSION,
    "reversion": TradingStyle.MEAN_REVERSION,
}


def parse_trading_style(raw: str | None, *, default: TradingStyle = TradingStyle.MEAN_REVERSION) -> TradingStyle:
    """Parse user/CLI style string; default mean_reversion (desk ODTE default)."""
    if raw is None or not str(raw).strip():
        return default
    key = str(raw).strip().lower().replace(" ", "_")
    if key in STYLE_ALIASES:
        return STYLE_ALIASES[key]
    raise ValueError(
        f"Unknown trading style {raw!r}; use breakout|mean_reversion "
        f"(aliases: bo, mr, fade, continuation)"
    )


@dataclass(frozen=True)
class StyleProfile:
    style: TradingStyle
    label: str
    bet: str
    entry_idea: str
    typical_failure: str
    desk_playbooks: tuple[str, ...]


PROFILES = {
    TradingStyle.BREAKOUT: StyleProfile(
        style=TradingStyle.BREAKOUT,
        label="Breakout / continuation",
        bet="Price leaves a range or level and keeps going",
        entry_idea="Buy strength through resistance / sell weakness through support (ORH/ORL, range high/low)",
        typical_failure="False break → reclaim inside range",
        desk_playbooks=("odte --style breakout", "888 Trading Intelligence (TV)"),
    ),
    TradingStyle.MEAN_REVERSION: StyleProfile(
        style=TradingStyle.MEAN_REVERSION,
        label="Mean reversion / fade",
        bet="Price stretched from a mean or level snaps back",
        entry_idea="Fade RSI extremes at support/resistance (first touch bounce/reject)",
        typical_failure="Trend day — extreme extends, mean never returns",
        desk_playbooks=("odte --style mean_reversion (default 0DTE/Shen)", "multi-DTE level+RSI fade"),
    ),
}


def style_profile(style: TradingStyle) -> StyleProfile:
    return PROFILES[style]


def classify_level_signal(
    *,
    side: str,
    kind: str,
    level_name: str = "",
    rsi: Optional[float] = None,
    put_rsi: float = 74.0,
    call_rsi: float = 26.0,
    close_beyond_level: bool = False,
) -> TradingStyle:
    """Heuristic: tag a level+RSI event as breakout vs mean-reversion.

    - Fade (mean reversion): PUT at resistance with high RSI, or CALL at support with low RSI,
      without requiring close *through* the level in the trade direction.
    - Breakout: close beyond the level in the trade direction (through resistance for CALL,
      through support for PUT), independent of RSI extremes.
    """
    side_u = side.upper()
    kind_l = kind.lower()
    if close_beyond_level:
        if side_u == "CALL" and kind_l in ("resistance", "both"):
            return TradingStyle.BREAKOUT
        if side_u == "PUT" and kind_l in ("support", "both"):
            return TradingStyle.BREAKOUT
        # through ORH as call / ORL as put also breakout
        name = level_name.upper()
        if side_u == "CALL" and ("ORH" in name or "PDH" in name or "RESIST" in name):
            return TradingStyle.BREAKOUT
        if side_u == "PUT" and ("ORL" in name or "PDL" in name or "SUPPORT" in name):
            return TradingStyle.BREAKOUT

    if rsi is not None:
        if side_u == "PUT" and kind_l in ("resistance", "both") and rsi >= put_rsi:
            return TradingStyle.MEAN_REVERSION
        if side_u == "CALL" and kind_l in ("support", "both") and rsi <= call_rsi:
            return TradingStyle.MEAN_REVERSION

    # Default: structural fade if resistance→put / support→call without beyond-close
    if side_u == "PUT" and kind_l in ("resistance", "both"):
        return TradingStyle.MEAN_REVERSION
    if side_u == "CALL" and kind_l in ("support", "both"):
        return TradingStyle.MEAN_REVERSION
    return TradingStyle.BREAKOUT


def format_style_brief(style: TradingStyle) -> str:
    p = style_profile(style)
    lines = [
        f"**Trading style: {p.label}** (`{style.value}`)",
        f"- **Bet:** {p.bet}",
        f"- **Entry idea:** {p.entry_idea}",
        f"- **Typical failure:** {p.typical_failure}",
        f"- **Desk playbooks:** {', '.join(p.desk_playbooks)}",
        "",
        "_Do not mix styles on the same signal without re-labeling risk (false break ≠ RSI fade)._",
    ]
    return "\n".join(lines) + "\n"
