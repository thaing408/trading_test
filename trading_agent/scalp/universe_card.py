"""Discord/terminal card: desk + gainer/loser link to QQQ scalp rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOME = Path.home()
DEFAULT_UNIVERSE = HOME / ".grok" / "state" / "auto_trade_universe.json"
DEFAULT_MOVERS = HOME / ".grok" / "state" / "auto_trade_movers_scan.json"
SYNC_UNIVERSE = HOME / ".trading_agent" / "sync" / "auto_trade_universe.json"
SYNC_MOVERS = HOME / ".trading_agent" / "sync" / "auto_trade_movers_scan.json"


def _load_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_universe_payload() -> Tuple[Optional[dict], str]:
    for p in (DEFAULT_UNIVERSE, SYNC_UNIVERSE):
        data = _load_json(p)
        if data:
            return data, str(p)
    return None, str(DEFAULT_UNIVERSE)


def load_movers_payload() -> Tuple[Optional[dict], str]:
    for p in (DEFAULT_MOVERS, SYNC_MOVERS):
        data = _load_json(p)
        if data:
            return data, str(p)
    return None, str(DEFAULT_MOVERS)


def _tag_of(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        return str(raw.get("tag") or "").strip().lower()
    return str(raw).strip().lower()


def _pct_of(raw: Any) -> Optional[float]:
    if not isinstance(raw, dict):
        return None
    v = raw.get("change_pct")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_sym(sym: str, pct: Optional[float] = None) -> str:
    if pct is None:
        return sym
    sign = "+" if pct >= 0 else ""
    return f"{sym} ({sign}{pct:.1f}%)"


def format_scalp_universe_card(
    universe: Optional[dict] = None,
    movers: Optional[dict] = None,
    *,
    universe_path: str = "",
) -> str:
    """One-screen link: gainers/losers/desk → QQQ scalp rules + policy."""
    if universe is None:
        universe, universe_path = load_universe_payload()
    if movers is None:
        movers, _ = load_movers_payload()

    if not universe:
        return (
            "**Scalp universe link**\n"
            f"_No `auto_trade_universe.json` found (expected {DEFAULT_UNIVERSE})._\n"
            "Run pulse + desk export, or wait for launchd merge.\n"
        )

    meta = universe.get("meta") if isinstance(universe.get("meta"), dict) else {}
    tags: Dict[str, Any] = (
        universe.get("movers_tags")
        or meta.get("movers_tags")
        or meta.get("movers_tags_all")
        or {}
    )
    policy = (
        universe.get("movers_policy")
        or meta.get("movers_policy")
        or {}
    )
    scan = list(universe.get("scan_symbols") or universe.get("symbols") or [])
    desk = list(universe.get("desk_symbols") or meta.get("desk_symbols") or [])
    movers_syms = list(universe.get("movers_symbols") or meta.get("movers_symbols") or [])
    system = universe.get("system") or meta.get("system") or "desk+movers"
    trading_date = universe.get("trading_date") or meta.get("trading_date") or "?"
    updated = universe.get("updated_at") or meta.get("updated_at") or "?"

    gainers: List[str] = []
    losers: List[str] = []
    both: List[str] = []
    for sym, raw in (tags or {}).items():
        t = _tag_of(raw)
        pct = _pct_of(raw)
        label = _fmt_sym(str(sym).upper(), pct)
        if t == "gainer":
            gainers.append(label)
        elif t == "loser":
            losers.append(label)
        elif t == "both":
            both.append(label)

    # Fallback from movers artifact if tags empty
    if not gainers and not losers and movers:
        for row in movers.get("gainers") or movers.get("up") or []:
            if isinstance(row, str):
                gainers.append(row.upper())
            elif isinstance(row, dict) and row.get("symbol"):
                gainers.append(
                    _fmt_sym(
                        str(row["symbol"]).upper(),
                        float(row["change_pct"]) if row.get("change_pct") is not None else None,
                    )
                )
        for row in movers.get("losers") or movers.get("down") or []:
            if isinstance(row, str):
                losers.append(row.upper())
            elif isinstance(row, dict) and row.get("symbol"):
                losers.append(
                    _fmt_sym(
                        str(row["symbol"]).upper(),
                        float(row["change_pct"]) if row.get("change_pct") is not None else None,
                    )
                )

    desk_only = [
        s.upper()
        for s in desk
        if s and _tag_of(tags.get(s) or tags.get(s.upper())) not in ("gainer", "loser", "both")
    ]
    # Also any scan name not tagged
    for s in scan:
        su = str(s).upper()
        if su in desk_only:
            continue
        if _tag_of(tags.get(s) or tags.get(su)) in ("gainer", "loser", "both"):
            continue
        if su not in desk_only and su not in {x.split()[0] for x in gainers + losers}:
            # keep desk_only as primary; skip dumping full scan noise if already listed
            pass

    gainer_calls = bool(policy.get("gainer_calls_only", True))
    loser_puts = bool(policy.get("allow_loser_puts", True))
    max_loser = policy.get("max_loser_entries_per_day", 1)
    loser_min = policy.get("loser_min_abs_pct", 3.0)
    skip_both = bool(policy.get("skip_both", True))
    skip_vol = bool(policy.get("skip_vol_etfs", True))

    lines = [
        "╔══════════════════════════════════════╗",
        "║  SCALP UNIVERSE LINK                 ║",
        "║  QQQ rules + gainer/loser policy     ║",
        "╚══════════════════════════════════════╝",
        "",
        f"  Date     {trading_date}",
        f"  System   {system}",
        f"  Updated  {updated}",
        f"  Scan n=  {len(scan)}",
        "",
        "  ── How names are linked ──",
        "  Every scan symbol runs **QQQ scalp engine**",
        "  (same levels / pullback / breakout / breakdown).",
        "  Tag only restricts **side / setup**:",
        "",
        "  🟢 GAINER → CALL only (pullback / bull_breakout)"
        if gainer_calls
        else "  🟢 GAINER → scalp (both sides allowed)",
        f"  🔴 LOSER  → PUT bear_breakdown only"
        + (f" · max {max_loser}/day · |Δ|≥{loser_min}%" if loser_puts else " · OFF"),
        "  ⚪ DESK   → scalp engine, no mover side filter",
        "  ⛔ BOTH   → skip" if skip_both else "  BOTH → allowed",
        "  ⛔ Vol ETFs skipped on loser side" if skip_vol else "",
        "",
        f"  🟢 GAINERS ({len(gainers)}) — CALL scalp rules",
        ("  " + ", ".join(gainers[:12])) if gainers else "  _(none)_",
    ]
    if len(gainers) > 12:
        lines.append(f"  _…+{len(gainers) - 12} more_")

    lines.append("")
    lines.append(f"  🔴 LOSERS ({len(losers)}) — PUT scalp rules")
    lines.append(("  " + ", ".join(losers[:12])) if losers else "  _(none)_")
    if len(losers) > 12:
        lines.append(f"  _…+{len(losers) - 12} more_")

    if both:
        lines.append("")
        lines.append(f"  ⛔ BOTH ({len(both)}) — no new entries")
        lines.append("  " + ", ".join(both[:10]))

    lines.append("")
    lines.append(f"  ⚪ DESK (untagged) ({len(desk_only)})")
    lines.append(
        ("  " + ", ".join(desk_only[:14])) if desk_only else "  _(none)_"
    )
    if len(desk_only) > 14:
        lines.append(f"  _…+{len(desk_only) - 14} more_")

    lines.append("")
    lines.append("  Full scan order (priority):")
    lines.append("  " + " → ".join(scan[:16]) + (" …" if len(scan) > 16 else ""))
    lines.append("")
    lines.append("  Files:")
    lines.append(f"  · universe: {universe_path or DEFAULT_UNIVERSE}")
    lines.append(f"  · movers:   {DEFAULT_MOVERS}")
    lines.append("")
    lines.append("  Run scalp dry-run:")
    lines.append("  `~/.grok/scripts/auto-trade-qqq.sh`")
    lines.append("")
    lines.append("_Not CIO · not desk multi-leg book · scalp path only_")
    return "\n".join(lines) + "\n"


def post_scalp_universe_card(*, discord: bool = False) -> str:
    text = format_scalp_universe_card()
    if not discord:
        return text
    from trading_agent.discord.config import DiscordConfig
    from trading_agent.discord.poster import post_message

    if not os.getenv("DISCORD_TOKEN") and os.getenv("DISCORD_BOT_TOKEN"):
        os.environ["DISCORD_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
    if os.getenv("DISCORD_DESK_CHANNEL_ID") and not os.getenv("DISCORD_CHANNEL_ID"):
        os.environ["DISCORD_CHANNEL_ID"] = os.environ["DISCORD_DESK_CHANNEL_ID"]
    # Prefer scalp-pulse channel if set
    channel = (
        os.getenv("DISCORD_SCALP_CHANNEL_ID")
        or os.getenv("DISCORD_ALERTS_CHANNEL_ID")
        or os.getenv("DISCORD_CHANNEL_ID")
    )
    cfg = DiscordConfig.from_env()
    if cfg.bot_token and channel:
        cfg = DiscordConfig(
            webhook_url=None,
            bot_token=cfg.bot_token,
            channel_id=channel,
        )
    body = f"```\n{text.rstrip()}\n```"
    post_message(body, cfg, username="Scalp Universe")
    return text
