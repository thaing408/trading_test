"""Collapse the busy 888 TI v0.5.x TradingView panel into a one-glance card.

The real indicator draws many overlays + a dense table. Humans only need:
  DECISION · confidence · which gates failed · entry/stop/target if ready.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Ti888Panel:
    """Fields mirrored from 888 TI dashboard (TV)."""

    symbol: str = ""
    version: str = ""
    decision: str = "WAIT"  # WAIT | LONG | SHORT | BUILDING | …
    confidence: str = ""  # e.g. 49/100
    market: str = ""
    trend: str = ""
    structure: str = ""
    volume: str = ""
    rs: str = ""
    mtf: str = ""
    setup: str = ""
    trigger: str = ""
    entry: str = ""
    stop: str = ""
    target: str = ""
    trade: str = ""
    reason: str = ""
    tests: str = ""
    day_bias: str = ""
    pdl_od: str = ""
    extras: Dict[str, str] = field(default_factory=dict)


# Map panel row labels (as shown on TV) → attribute names
_LABEL_MAP = {
    "confidence": "confidence",
    "market": "market",
    "trend": "trend",
    "structure": "structure",
    "volume": "volume",
    "rs": "rs",
    "mtf": "mtf",
    "setup": "setup",
    "trigger": "trigger",
    "entry": "entry",
    "stop": "stop",
    "target": "target",
    "trade": "trade",
    "reason": "reason",
    "tests": "tests",
    "daybias": "day_bias",
    "day bias": "day_bias",
    "pdl/od": "pdl_od",
    "pdlod": "pdl_od",
    "pdl": "pdl_od",
}


def _norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _is_pass(val: str) -> Optional[bool]:
    v = (val or "").upper()
    if not v:
        return None
    if "FAIL" in v or "NOT READY" in v:
        return False
    if "PASS" in v:
        return True
    if "BUILDING" in v or "WAIT" in v or "NONE" in v:
        return False
    return None


def _gate_rows(p: Ti888Panel) -> List[Tuple[str, str, Optional[bool]]]:
    """(name, value, pass?) for checklist."""
    return [
        ("Market", p.market, _is_pass(p.market)),
        ("Trend", p.trend, _is_pass(p.trend)),
        ("Structure", p.structure, _is_pass(p.structure)),
        ("Volume", p.volume, _is_pass(p.volume)),
        ("RS", p.rs, _is_pass(p.rs)),
        ("MTF", p.mtf, _is_pass(p.mtf)),
    ]


def panel_from_fields(
    *,
    symbol: str = "",
    decision: str = "WAIT",
    confidence: str = "",
    market: str = "",
    trend: str = "",
    structure: str = "",
    volume: str = "",
    rs: str = "",
    mtf: str = "",
    setup: str = "",
    trigger: str = "",
    entry: str = "",
    stop: str = "",
    target: str = "",
    trade: str = "",
    reason: str = "",
    tests: str = "",
    day_bias: str = "",
    pdl_od: str = "",
    version: str = "",
) -> Ti888Panel:
    return Ti888Panel(
        symbol=(symbol or "").upper().strip(),
        version=version,
        decision=(decision or "WAIT").strip().upper() or "WAIT",
        confidence=confidence.strip(),
        market=market.strip(),
        trend=trend.strip(),
        structure=structure.strip(),
        volume=volume.strip(),
        rs=rs.strip(),
        mtf=mtf.strip(),
        setup=setup.strip(),
        trigger=trigger.strip(),
        entry=entry.strip(),
        stop=stop.strip(),
        target=target.strip(),
        trade=trade.strip(),
        reason=reason.strip(),
        tests=tests.strip(),
        day_bias=day_bias.strip(),
        pdl_od=pdl_od.strip(),
    )


def parse_ti888_text(text: str, *, symbol: str = "") -> Ti888Panel:
    """Parse a paste/OCR of the 888 TI table (label then value per line or 'Label Value')."""
    p = Ti888Panel(symbol=(symbol or "").upper().strip())
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    # Header: "888 TI v0.5.1" and/or lone WAIT / LONG
    for ln in lines[:6]:
        m = re.search(r"888\s*TI\s*(v?[\d.]+)?", ln, re.I)
        if m:
            p.version = (m.group(1) or "").strip()
        up = ln.upper().strip()
        if up in ("WAIT", "LONG", "SHORT", "BUY", "SELL", "BUILDING"):
            p.decision = "LONG" if up == "BUY" else "SHORT" if up == "SELL" else up

    # Pair consecutive lines: Label \n Value  OR  "Label  Value"
    i = 0
    while i < len(lines):
        ln = lines[i]
        # Skip pure header chrome
        if re.match(r"^888\s*TI", ln, re.I):
            i += 1
            continue
        if ln.upper() in ("WAIT", "LONG", "SHORT", "BUY", "SELL") and not p.decision:
            p.decision = ln.upper().replace("BUY", "LONG").replace("SELL", "SHORT")
            i += 1
            continue

        # "Confidence 49/100" or "Confidence: 49/100"
        m = re.match(r"^([A-Za-z][A-Za-z0-9 /]+?)\s*[:|]?\s+(.+)$", ln)
        label_raw, val = "", ""
        if m:
            label_raw, val = m.group(1), m.group(2)
        elif i + 1 < len(lines):
            # two-line form
            maybe_label = ln
            maybe_val = lines[i + 1]
            key = _norm_label(maybe_label).replace(" ", "")
            # only treat as label if short-ish and known-ish
            if len(maybe_label) < 24 and (
                _norm_label(maybe_label) in _LABEL_MAP
                or key in {k.replace(" ", "") for k in _LABEL_MAP}
            ):
                label_raw, val = maybe_label, maybe_val
                i += 1

        if label_raw:
            key = _norm_label(label_raw)
            attr = _LABEL_MAP.get(key) or _LABEL_MAP.get(key.replace(" ", ""))
            if attr and hasattr(p, attr):
                setattr(p, attr, val.strip())
            elif label_raw:
                p.extras[label_raw] = val.strip()
        i += 1

    # Decision often also in Reason: "Structure FAIL — WAIT"
    if p.reason:
        ru = p.reason.upper()
        if "WAIT" in ru and p.decision in ("", "BUILDING"):
            p.decision = "WAIT"
        if re.search(r"\bLONG\b|\bBUY\b", ru) and "WAIT" not in ru:
            p.decision = "LONG"
        if re.search(r"\bSHORT\b|\bSELL\b", ru) and "WAIT" not in ru:
            p.decision = "SHORT"

    if not p.decision:
        p.decision = "WAIT"
    return p


def format_ti888_card(p: Ti888Panel) -> str:
    """One-screen decision card — ignore chart clutter."""
    dec = (p.decision or "WAIT").upper()
    if dec in ("BUY",):
        dec = "LONG"
    if dec in ("SELL",):
        dec = "SHORT"

    if dec in ("LONG", "BUY"):
        head = "🟢  LONG / GO"
        action = "Only if Trigger READY and you confirm on chart"
    elif dec in ("SHORT", "SELL"):
        head = "🔴  SHORT / GO"
        action = "Only if Trigger READY and you confirm on chart"
    elif "BUILD" in dec:
        head = "🟠  BUILDING"
        action = "NO TRADE — setup not complete"
    else:
        head = "🟡  WAIT"
        action = "NO TRADE"

    # Confidence bar (text)
    conf = p.confidence or "?"
    conf_n = None
    m = re.search(r"(\d+)\s*/\s*(\d+)", conf)
    if m:
        conf_n = int(m.group(1))
    if conf_n is not None:
        if conf_n >= 70:
            conf_emoji = "🟢"
        elif conf_n >= 50:
            conf_emoji = "🟡"
        else:
            conf_emoji = "🔴"
        conf_line = f"{conf_emoji}  Confidence  {conf}"
    else:
        conf_line = f"   Confidence  {conf}"

    gates = _gate_rows(p)
    pass_n = sum(1 for _, _, ok in gates if ok is True)
    fail_n = sum(1 for _, _, ok in gates if ok is False)
    gate_lines: List[str] = []
    blockers: List[str] = []
    for name, val, ok in gates:
        if not val:
            continue
        if ok is True:
            mark = "✅"
        elif ok is False:
            mark = "❌"
            blockers.append(name)
        else:
            mark = "·"
        # short value
        short = val if len(val) <= 36 else val[:33] + "…"
        gate_lines.append(f"  {mark} {name:<10} {short}")

    sym = p.symbol or "—"
    ver = f" {p.version}" if p.version else ""
    lines = [
        "╔══════════════════════════════════════╗",
        f"║  888 TI{ver:<8} · {sym:<6}           ║",
        "╚══════════════════════════════════════╝",
        "",
        f"  DECISION   {head}",
        f"  ACTION     {action}",
        f"  {conf_line}",
        "",
    ]

    if p.reason:
        lines.append(f"  WHY        {p.reason}")
        lines.append("")

    if gate_lines:
        lines.append(f"  GATES      {pass_n} pass · {fail_n} fail")
        lines.extend(gate_lines)
        if blockers:
            lines.append(f"  BLOCKED BY {', '.join(blockers)}")
        lines.append("")

    # Levels only if useful
    has_levels = any([p.entry, p.stop, p.target])
    if has_levels:
        ready = (p.trigger or "").upper().find("NOT READY") < 0 and (
            "READY" in (p.trigger or "").upper() or dec in ("LONG", "SHORT")
        )
        lines.append("  LEVELS (from panel — use only if GO)")
        if p.entry:
            lines.append(f"     Entry   {p.entry}")
        if p.stop:
            lines.append(f"     Stop    {p.stop}")
        if p.target:
            lines.append(f"     Target  {p.target}")
        if p.trigger:
            lines.append(f"     Trigger {p.trigger}")
        if p.setup:
            lines.append(f"     Setup   {p.setup}")
        if not ready and dec in ("WAIT", "BUILDING"):
            lines.append("     → levels are provisional (not a go signal)")
        lines.append("")

    # Tiny footer context
    foot: List[str] = []
    if p.day_bias:
        foot.append(f"DayBias {p.day_bias}")
    if p.tests:
        foot.append(f"Tests {p.tests}")
    if p.trade:
        foot.append(f"Trade {p.trade}")
    if foot:
        lines.append("  " + " · ".join(foot))
        lines.append("")

    lines.append("  ── How to use ──")
    lines.append("  1. Read DECISION only (WAIT = flat)")
    lines.append("  2. If not GO, ignore Entry/Stop/Target")
    lines.append("  3. ❌ gates = why you sit out")
    lines.append("  4. Chart lines = noise for this card")
    lines.append("")
    lines.append("_888 TI simple card · from TV panel · not auto-execution_")
    return "\n".join(lines) + "\n"
