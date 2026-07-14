"""Shen-style 0DTE playbook applied to QQQ (or SPY).

Source framework (shentrades / SPY 0DTE article, adapted):
- Window: 6:30–8:15 AM PT (9:30–11:15 ET)
- Levels: whole dollars, PDH/PDL, PMH/PML, opening range (first 5 min)
- RSI(14) on 1m: puts when RSI > put_rsi at resistance; calls when RSI < call_rsi at support
- First touch only; 1-strike OTM; bracket TP/SL; small-account risk rules

This module is educational/signal scaffolding for the desk — not auto-execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")


@dataclass
class OdtePlaybookConfig:
    symbol: str = "QQQ"
    rsi_length: int = 14
    # Article: "above 74 puts / below 26 calls" for high conviction (base thresholds 70/30)
    put_rsi: float = 74.0
    call_rsi: float = 26.0
    # Soft band for "near level" (dollars)
    level_tol: float = 0.35
    # Opening range first N minutes after RTH open
    or_minutes: int = 5
    # Risk template (scaled from $1k / $250 max example)
    account_size: float = 1_000.0
    max_position_pct: float = 0.25
    take_profit_pct: float = 0.20
    stop_loss_pct: float = 0.125
    window_start_et: time = time(9, 30)
    window_end_et: time = time(11, 15)


@dataclass
class KeyLevels:
    last: float
    whole_above: List[float]
    whole_below: List[float]
    pdh: float
    pdl: float
    pmh: Optional[float]
    pml: Optional[float]
    or_high: Optional[float]
    or_low: Optional[float]


@dataclass
class OdteSetup:
    side: str  # CALL | PUT
    level: float
    level_name: str
    rsi: float
    price: float
    strike: float
    first_touch: bool
    conviction: str
    checklist: List[str] = field(default_factory=list)


@dataclass
class OdteSessionBrief:
    symbol: str
    asof: str
    in_window: bool
    window_note: str
    levels: KeyLevels
    rsi_1m: Optional[float]
    setups: List[OdteSetup]
    risk_note: str
    source: str
    errors: List[str] = field(default_factory=list)


def rsi_series(closes: Sequence[float], length: int = 14) -> List[float]:
    if len(closes) < length + 1:
        return [50.0] * len(closes)
    arr = np.asarray(closes, dtype=float)
    deltas = np.diff(arr)
    out = [50.0]
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    # Wilder-style seed
    avg_gain = float(np.mean(gains[:length]))
    avg_loss = float(np.mean(losses[:length]))
    for i in range(length, len(deltas)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss <= 1e-12:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(float(100 - (100 / (1 + rs))))
    # pad front
    pad = [50.0] * (len(closes) - len(out))
    return pad + out


def whole_dollar_levels(price: float, n: int = 4) -> tuple[List[float], List[float]]:
    """Nearest whole-dollar rails above and below spot (no duplicate on both sides)."""
    floor_px = float(np.floor(price))
    ceil_px = float(np.ceil(price))
    if ceil_px == floor_px:
        # exactly on a round number: treat as both touch level
        above = [floor_px + i for i in range(1, n + 1)]
        below = [floor_px - i for i in range(1, n + 1)]
    else:
        above = [ceil_px + i for i in range(0, n)]
        below = [floor_px - i for i in range(0, n)]
    return [float(x) for x in above], [float(x) for x in below]


def _in_window(now_et: datetime, cfg: OdtePlaybookConfig) -> bool:
    t = now_et.timetz().replace(tzinfo=None) if False else now_et.time()
    return cfg.window_start_et <= t <= cfg.window_end_et


def _collect_levels(symbol: str, cfg: OdtePlaybookConfig) -> tuple[KeyLevels, Optional[float], str, List[str]]:
    import yfinance as yf

    errors: List[str] = []
    t = yf.Ticker(symbol)
    daily = t.history(period="10d", interval="1d")
    if daily.empty or len(daily) < 2:
        raise ValueError(f"No daily history for {symbol}")
    prev = daily.iloc[-2]
    today = daily.iloc[-1]
    pdh = float(prev["High"])
    pdl = float(prev["Low"])

    # 1m bars for session + RSI
    m1 = t.history(period="1d", interval="1m")
    last = float(today["Close"])
    rsi_last: Optional[float] = None
    pmh = pml = or_h = or_l = None

    if not m1.empty:
        last = float(m1["Close"].iloc[-1])
        # Pre-market: before 9:30 ET
        idx = m1.index
        if getattr(idx, "tz", None) is not None:
            et_idx = idx.tz_convert(ET)
        else:
            et_idx = idx
        times = [ts.time() for ts in et_idx]
        pre_mask = [tm < time(9, 30) for tm in times]
        rth_mask = [tm >= time(9, 30) for tm in times]
        if any(pre_mask):
            pre = m1.loc[[i for i, m in zip(m1.index, pre_mask) if m]]
            if not pre.empty:
                pmh = float(pre["High"].max())
                pml = float(pre["Low"].min())
        # Opening range: first N minutes of RTH
        rth = m1.loc[[i for i, m in zip(m1.index, rth_mask) if m]]
        if not rth.empty:
            or_slice = rth.iloc[: max(cfg.or_minutes, 1)]
            or_h = float(or_slice["High"].max())
            or_l = float(or_slice["Low"].min())
        closes = m1["Close"].astype(float).tolist()
        rsi_vals = rsi_series(closes, cfg.rsi_length)
        rsi_last = float(rsi_vals[-1]) if rsi_vals else None
    else:
        errors.append("No 1m bars — RSI unavailable (market closed or delayed)")

    above, below = whole_dollar_levels(last, n=5)
    levels = KeyLevels(
        last=round(last, 2),
        whole_above=above,
        whole_below=below,
        pdh=round(pdh, 2),
        pdl=round(pdl, 2),
        pmh=round(pmh, 2) if pmh is not None else None,
        pml=round(pml, 2) if pml is not None else None,
        or_high=round(or_h, 2) if or_h is not None else None,
        or_low=round(or_l, 2) if or_l is not None else None,
    )
    return levels, rsi_last, "yfinance", errors


def _level_map(levels: KeyLevels) -> List[tuple[str, float, str]]:
    """name, price, kind support|resistance|both."""
    items: List[tuple[str, float, str]] = []
    for x in levels.whole_above:
        items.append((f"whole ${x:.0f}", x, "resistance"))
    for x in levels.whole_below:
        items.append((f"whole ${x:.0f}", x, "support"))
    items.append(("PDH", levels.pdh, "resistance"))
    items.append(("PDL", levels.pdl, "support"))
    if levels.pmh is not None:
        items.append(("PMH", levels.pmh, "resistance"))
    if levels.pml is not None:
        items.append(("PML", levels.pml, "support"))
    if levels.or_high is not None:
        items.append(("ORH", levels.or_high, "resistance"))
    if levels.or_low is not None:
        items.append(("ORL", levels.or_low, "support"))
    # de-dupe by rounded price preferring named key levels
    seen = set()
    out = []
    for name, px, kind in items:
        key = round(px, 2)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, px, kind))
    return out


def _first_touch_guess(price: float, level: float, tol: float) -> bool:
    """Without full tick history of touches, treat current proximity as candidate first touch.

    Callers should still verify on chart (article: first touch only).
    """
    return abs(price - level) <= tol


def _evaluate_setups(
    levels: KeyLevels,
    rsi: Optional[float],
    cfg: OdtePlaybookConfig,
    in_window: bool,
) -> List[OdteSetup]:
    if rsi is None:
        return []
    setups: List[OdteSetup] = []
    price = levels.last
    for name, lvl, kind in _level_map(levels):
        near = abs(price - lvl) <= cfg.level_tol
        if not near:
            continue
        first = _first_touch_guess(price, lvl, cfg.level_tol)
        if kind in ("resistance", "both") and rsi >= cfg.put_rsi:
            strike = float(int(np.floor(price)))  # 1-strike OTM put ≈ floor
            if strike > price:
                strike = float(int(price) - 1)
            if abs(strike - price) < 0.05:
                strike = float(int(np.floor(price)) - 0)  # ATM-ish; prefer 1 OTM
                if strike >= price:
                    strike -= 1
            swing = "high" if rsi >= 80 else "standard"
            checks = [
                f"{'✅' if in_window else '❌'} Inside 6:30–8:15 PT window",
                f"✅ Price at {name} (${lvl:.2f})",
                f"{'✅' if first else '⚠️'} Treat as first-touch candidate (confirm on 1m chart)",
                f"✅ RSI {rsi:.1f} ≥ {cfg.put_rsi:.0f} (PUT)",
                "✅ 1-strike OTM preference",
                f"✅ Max size {cfg.account_size * cfg.max_position_pct:.0f} "
                f"({cfg.max_position_pct:.0%} of ${cfg.account_size:.0f})",
                f"✅ Bracket ready: TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}%",
            ]
            setups.append(
                OdteSetup(
                    side="PUT",
                    level=lvl,
                    level_name=name,
                    rsi=round(rsi, 1),
                    price=price,
                    strike=strike,
                    first_touch=first,
                    conviction=swing,
                    checklist=checks,
                )
            )
        if kind in ("support", "both") and rsi <= cfg.call_rsi:
            strike = float(int(np.ceil(price)))
            if strike <= price:
                strike += 1
            swing = "high" if rsi <= 20 else "standard"
            checks = [
                f"{'✅' if in_window else '❌'} Inside 6:30–8:15 PT window",
                f"✅ Price at {name} (${lvl:.2f})",
                f"{'✅' if first else '⚠️'} Treat as first-touch candidate (confirm on 1m chart)",
                f"✅ RSI {rsi:.1f} ≤ {cfg.call_rsi:.0f} (CALL)",
                "✅ 1-strike OTM preference",
                f"✅ Max size {cfg.account_size * cfg.max_position_pct:.0f} "
                f"({cfg.max_position_pct:.0%} of ${cfg.account_size:.0f})",
                f"✅ Bracket ready: TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}%",
            ]
            setups.append(
                OdteSetup(
                    side="CALL",
                    level=lvl,
                    level_name=name,
                    rsi=round(rsi, 1),
                    price=price,
                    strike=strike,
                    first_touch=first,
                    conviction=swing,
                    checklist=checks,
                )
            )
    return setups


def run_odte_playbook(cfg: OdtePlaybookConfig | None = None) -> OdteSessionBrief:
    cfg = cfg or OdtePlaybookConfig()
    now_et = datetime.now(ET)
    in_win = _in_window(now_et, cfg)
    window_note = (
        f"Trade window 6:30–8:15 PT (9:30–11:15 ET). "
        f"Now {now_et.strftime('%H:%M %Z')} — "
        f"{'INSIDE window' if in_win else 'OUTSIDE window (no new entries per playbook)'}"
    )
    try:
        levels, rsi, source, errors = _collect_levels(cfg.symbol, cfg)
    except Exception as exc:  # noqa: BLE001
        empty = KeyLevels(0.0, [], [], 0.0, 0.0, None, None, None, None)
        return OdteSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_win,
            window_note=window_note,
            levels=empty,
            rsi_1m=None,
            setups=[],
            risk_note="",
            source="unavailable",
            errors=[str(exc)],
        )
    setups = _evaluate_setups(levels, rsi, cfg, in_win)
    max_pos = cfg.account_size * cfg.max_position_pct
    risk_note = (
        f"Risk template (${cfg.account_size:.0f} account): max ${max_pos:.0f}/trade "
        f"({cfg.max_position_pct:.0%}); bracket TP +{cfg.take_profit_pct:.0%} / "
        f"SL -{cfg.stop_loss_pct * 100:.1f}%; no averaging; daily loss limit set before open; "
        f"one direction, one trade at a time; 0DTE {cfg.symbol} only."
    )
    return OdteSessionBrief(
        symbol=cfg.symbol,
        asof=now_et.isoformat(),
        in_window=in_win,
        window_note=window_note,
        levels=levels,
        rsi_1m=round(rsi, 1) if rsi is not None else None,
        setups=setups,
        risk_note=risk_note,
        source=source,
        errors=errors,
    )


def format_odte_brief(brief: OdteSessionBrief) -> str:
    L = brief.levels
    lines = [
        f"**{brief.symbol} 0DTE Playbook** (Shen-style levels + RSI)",
        f"_As of {brief.asof} | source={brief.source}_",
        brief.window_note,
        "",
        f"**Last:** ${L.last:.2f}"
        + (f" | **1m RSI(14):** {brief.rsi_1m}" if brief.rsi_1m is not None else " | **1m RSI:** n/a"),
        "",
        "**Key levels to mark:**",
        f"- PDH {L.pdh:.2f} | PDL {L.pdl:.2f}",
        f"- PMH {L.pmh if L.pmh is not None else 'n/a'} | PML {L.pml if L.pml is not None else 'n/a'}",
        f"- ORH {L.or_high if L.or_high is not None else 'n/a'} | ORL {L.or_low if L.or_low is not None else 'n/a'}",
        f"- Whole $ above: {', '.join(f'{x:.0f}' for x in L.whole_above)}",
        f"- Whole $ below: {', '.join(f'{x:.0f}' for x in L.whole_below)}",
        "",
        "**Signal rules (QQQ same as SPY playbook):**",
        "- PUT: first touch of resistance + RSI ≥ 74",
        "- CALL: first touch of support + RSI ≤ 26",
        "- Window only 6:30–8:15 PT; 1-strike OTM; set bracket on fill",
        "",
    ]
    if brief.setups:
        lines.append(f"**Active setup candidates ({len(brief.setups)}):**")
        for s in brief.setups:
            lines.extend(
                [
                    f"- **{s.side}** @ {s.level_name} ${s.level:.2f} | RSI {s.rsi} | "
                    f"spot ${s.price:.2f} → strike **${s.strike:.0f}** | conviction {s.conviction}",
                    *[f"  {c}" for c in s.checklist],
                ]
            )
    else:
        lines.append(
            "**No entry now** — need price at a key level **and** RSI extreme "
            "(≥74 put / ≤26 call). Watching is a valid session."
        )
    lines.extend(["", f"**Risk:** {brief.risk_note}"])
    if brief.errors:
        lines.append("**Notes:** " + "; ".join(brief.errors))
    lines.append(
        "_Adapted from @shentrades SPY 0DTE foundation for **QQQ**. "
        "Not financial advice; paper first._"
    )
    return "\n".join(lines)
