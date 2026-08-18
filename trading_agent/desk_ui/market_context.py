"""Parse free-text market bias / intelligence into a table-friendly view."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketContext:
    """Structured market briefing for desk UI (header short + overview table)."""

    bias_short: str = ""  # e.g. Bullish
    regime_code: str = ""  # e.g. bullish / risk_off
    posture: str = ""  # e.g. risk-on pre-market conditions
    environment_score: float | None = None
    catalyst_symbol: str = ""
    catalyst_headline: str = ""
    catalyst_kind: str = ""  # earnings, etc.
    overnight: dict[str, str] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    catalyst_symbols: list[str] = field(default_factory=list)
    data_sources: str = ""
    raw_bias: str = ""
    market_posture: str = ""
    vix_note: str = ""
    rows: list[tuple[str, str]] = field(default_factory=list)

    @property
    def header_label(self) -> str:
        """Compact chip for sticky header."""
        parts: list[str] = []
        if self.environment_score is not None:
            parts.append(f"env {self.environment_score:g}")
        label = self.bias_short or self.regime_code
        if label:
            parts.append(label)
        if self.posture and self.posture.lower() not in (label or "").lower():
            # keep short — first clause only
            short = self.posture.split(";")[0].strip()
            if len(short) > 48:
                short = short[:45] + "…"
            parts.append(short)
        return " · ".join(parts) if parts else "—"


_BIAS_SPLIT = re.compile(
    r"^\s*(?P<bias>[A-Za-z][A-Za-z \-/]+?)\s*[—\-–:]\s*(?P<rest>.+)$",
    re.DOTALL,
)
_CATALYST = re.compile(
    r"active catalyst:\s*(?:\[(?P<sym>[A-Z0-9.\-]+)\])?\s*(?P<head>.+?)(?:\s*\((?P<kind>[^)]+)\))?\s*(?=\(|\[data:|$)",
    re.IGNORECASE | re.DOTALL,
)
_DATA_BLOCK = re.compile(r"\[data:\s*(?P<data>[^\]]+)\]\s*$", re.IGNORECASE | re.DOTALL)
_PAREN_CHUNKS = re.compile(r"\(([^)]+)\)")


def parse_bias_blob(text: str) -> dict[str, Any]:
    """Best-effort parse of overall_market_bias / book.regime free text."""
    raw = (text or "").strip()
    out: dict[str, Any] = {
        "bias_short": "",
        "posture": "",
        "catalyst_symbol": "",
        "catalyst_headline": "",
        "catalyst_kind": "",
        "signals": [],
        "data_sources": "",
        "raw_bias": raw,
    }
    if not raw:
        return out

    data_m = _DATA_BLOCK.search(raw)
    body = raw
    if data_m:
        out["data_sources"] = data_m.group("data").strip()
        body = raw[: data_m.start()].strip()

    m = _BIAS_SPLIT.match(body)
    if m:
        out["bias_short"] = m.group("bias").strip()
        rest = m.group("rest").strip()
    else:
        # First word-ish token
        first = body.split("—")[0].split("-")[0].strip()
        if len(first) <= 24 and " " not in first.strip() or first.lower() in (
            "bullish",
            "bearish",
            "neutral",
            "risk-on",
            "risk-off",
        ):
            out["bias_short"] = first.split(";")[0].strip()
            rest = body[len(first) :].lstrip(" —–-:;")
        else:
            out["bias_short"] = body.split(";")[0][:40]
            rest = body

    # posture before catalyst / first paren blob of tape
    cat = _CATALYST.search(rest)
    if cat:
        before = rest[: cat.start()].strip(" ;,")
        out["posture"] = before or out["posture"]
        out["catalyst_symbol"] = (cat.group("sym") or "").upper()
        head = (cat.group("head") or "").strip()
        # trim trailing junk
        head = re.sub(r"\s+", " ", head).strip(" .;")
        out["catalyst_headline"] = head
        out["catalyst_kind"] = (cat.group("kind") or "").strip()
        after = rest[cat.end() :]
    else:
        # posture = text before first (
        if "(" in rest:
            out["posture"] = rest.split("(", 1)[0].strip(" ;,")
            after = "(" + rest.split("(", 1)[1]
        else:
            out["posture"] = rest.split(";")[0].strip()
            after = ""

    # Parenthetical chunks often hold tape notes; last non-kind ones are signals
    chunks = _PAREN_CHUNKS.findall(after or rest)
    signals: list[str] = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        low = ch.lower()
        if low in ("earnings", "news", "guidance", "fda", "macro"):
            if not out["catalyst_kind"]:
                out["catalyst_kind"] = ch
            continue
        # split multi-signal parens on ;
        if ";" in ch:
            for part in ch.split(";"):
                p = part.strip()
                if p:
                    signals.append(p)
        else:
            signals.append(ch)
    out["signals"] = signals
    return out


def _clean_num_str(s: str) -> str:
    """Round noisy floats inside free text: VIX 14.68999 → 14.7."""

    def _repl(m: re.Match[str]) -> str:
        try:
            return f"{float(m.group(0)):.2f}".rstrip("0").rstrip(".")
        except ValueError:
            return m.group(0)

    return re.sub(r"\d+\.\d{3,}", _repl, s)


def _overnight_rows(overnight: Any) -> dict[str, str]:
    if not isinstance(overnight, dict):
        return {}
    labels = {
        "futures": "ES / futures",
        "asia": "Asia",
        "europe": "Europe",
        "international": "International",
        "bonds": "Bonds",
        "dxy": "Dollar (DXY)",
        "commodities": "Commodities",
        "crypto": "Crypto",
        "vix": "VIX",
    }
    out: dict[str, str] = {}
    for key, label in labels.items():
        val = overnight.get(key)
        if val is None or val == "":
            continue
        out[label] = _clean_num_str(str(val))
    # any extra keys
    for key, val in overnight.items():
        if key in labels or val is None or val == "":
            continue
        out[str(key).replace("_", " ").title()] = _clean_num_str(str(val))
    return out


def build_market_context(
    *,
    environment_score: float | None,
    regime: str,
    plan: dict[str, Any] | None = None,
    book: dict[str, Any] | None = None,
    intelligence: dict[str, Any] | None = None,
) -> MarketContext:
    plan = plan or {}
    book = book or {}
    intel = intelligence or {}

    score = environment_score
    if score is None and intel.get("environment_score") is not None:
        try:
            score = float(intel["environment_score"])
        except (TypeError, ValueError):
            pass
    if score is None and plan.get("market_environment_score") is not None:
        try:
            score = float(plan["market_environment_score"])
        except (TypeError, ValueError):
            pass

    regime_code = str(
        plan.get("market_regime") or book.get("market_regime") or book.get("regime") or ""
    ).strip()
    # Prefer short code if free-text leaked into regime
    if len(regime_code) > 40 or "—" in regime_code or "catalyst" in regime_code.lower():
        regime_code = str(plan.get("market_regime") or "").strip() or ""
        if len(regime_code) > 40:
            regime_code = regime_code.split()[0].lower() if regime_code else ""

    raw_bias = str(
        intel.get("bias")
        or plan.get("overall_market_bias")
        or book.get("regime")
        or regime
        or ""
    ).strip()

    parsed = parse_bias_blob(raw_bias)

    bias_short = (
        str(intel.get("outlook") or "").strip()
        or parsed.get("bias_short")
        or (regime_code.title() if regime_code else "")
    )
    # Normalize single-token outlook
    if bias_short and len(bias_short) < 24:
        bias_short = bias_short.strip()

    posture = str(intel.get("market_posture") or "").strip() or str(
        parsed.get("posture") or ""
    ).strip()

    overnight = _overnight_rows(intel.get("overnight_summary"))
    signals = [str(s) for s in (intel.get("market_signals") or []) if s]
    if not signals:
        signals = list(parsed.get("signals") or [])

    highlights = [str(h) for h in (intel.get("news_highlights") or plan.get("news_highlights") or []) if h]
    cat_syms = [str(s).upper() for s in (intel.get("catalyst_symbols") or []) if s]

    cat_sym = parsed.get("catalyst_symbol") or (cat_syms[0] if cat_syms else "")
    cat_head = parsed.get("catalyst_headline") or ""
    if not cat_head and highlights:
        # strip [SYM] prefix for display
        cat_head = re.sub(r"^\[[A-Z0-9.\-]+\]\s*", "", highlights[0]).strip()
        m = re.match(r"^\[([A-Z0-9.\-]+)\]", highlights[0])
        if m and not cat_sym:
            cat_sym = m.group(1)

    cat_kind = parsed.get("catalyst_kind") or ""
    if not cat_kind and cat_head:
        km = re.search(r"\((earnings|news|guidance|fda|macro)\)\s*$", cat_head, re.I)
        if km:
            cat_kind = km.group(1)
            cat_head = cat_head[: km.start()].strip()

    data_sources = str(parsed.get("data_sources") or "")
    if not data_sources and isinstance(intel.get("metadata"), dict):
        meta = intel["metadata"]
        bits = [f"{k}: {v}" for k, v in meta.items() if v not in (None, "")]
        data_sources = ", ".join(bits[:8])

    vix_note = str(intel.get("vix_term_note") or "").strip()

    ctx = MarketContext(
        bias_short=bias_short,
        regime_code=regime_code or (bias_short.lower() if bias_short else ""),
        posture=posture,
        environment_score=score,
        catalyst_symbol=cat_sym,
        catalyst_headline=cat_head,
        catalyst_kind=cat_kind,
        overnight=overnight,
        signals=signals,
        highlights=highlights[:12],
        catalyst_symbols=cat_syms,
        data_sources=data_sources,
        raw_bias=raw_bias,
        market_posture=str(intel.get("market_posture") or posture),
        vix_note=vix_note,
    )
    ctx.rows = _build_rows(ctx)
    return ctx


def _build_rows(ctx: MarketContext) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if ctx.environment_score is not None:
        rows.append(("Environment score", f"{ctx.environment_score:g}"))
    if ctx.bias_short:
        rows.append(("Bias / outlook", ctx.bias_short))
    if ctx.regime_code and ctx.regime_code.lower() != ctx.bias_short.lower():
        rows.append(("Regime", ctx.regime_code))
    if ctx.posture:
        rows.append(("Posture", ctx.posture))
    if ctx.catalyst_symbol or ctx.catalyst_headline:
        cat = ""
        if ctx.catalyst_symbol:
            cat += f"[{ctx.catalyst_symbol}] "
        cat += ctx.catalyst_headline
        if ctx.catalyst_kind:
            cat += f" ({ctx.catalyst_kind})"
        rows.append(("Active catalyst", cat.strip()))
    if ctx.catalyst_symbols:
        rows.append(("Catalyst symbols", ", ".join(ctx.catalyst_symbols[:12])))
    # Overnight tape, signals, and headlines render in dedicated UI sections
    # (avoid one giant free-text row).
    if ctx.vix_note:
        rows.append(("VIX term", ctx.vix_note))
    if ctx.data_sources:
        rows.append(("Data sources", ctx.data_sources))
    return rows
