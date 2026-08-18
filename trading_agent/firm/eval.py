"""P6 firm-sleeve evaluation — decision audit + simple agreement metrics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class FirmEvalRow:
    symbol: str
    firm_action: str
    firm_confidence: float
    debate_winner: str
    manager_decision: str
    risk_recommendation: str
    book_action: str = ""
    agree_enter: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FirmEvalReport:
    trading_date: str
    n_symbols: int = 0
    n_buy: int = 0
    n_sell: int = 0
    n_hold: int = 0
    n_veto: int = 0
    n_book_overlap: int = 0
    n_agree_enter: int = 0
    agreement_rate: float = 0.0
    rows: List[FirmEvalRow] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rows"] = [r.to_dict() for r in self.rows]
        return d


def _load_book_actions(book_path: Path) -> Dict[str, str]:
    if not book_path.is_file():
        return {}
    try:
        data = json.loads(book_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, str] = {}
    for e in data.get("entries") or []:
        if isinstance(e, dict) and e.get("symbol"):
            out[str(e["symbol"]).upper()] = str(e.get("action") or "")
    return out


def evaluate_firm_day(
    trading_date: str,
    *,
    session_root: Optional[Path] = None,
    book_path: Optional[Path] = None,
) -> FirmEvalReport:
    """Score one firm day vs multi-method book ENTER overlap."""
    root = Path(session_root) if session_root else Path.home() / ".trading_agent" / "sessions"
    firm_dir = root / trading_date / "firm"
    book = book_path or (Path.home() / ".trading_agent" / "sync" / "auto_trade_book.json")
    book_actions = _load_book_actions(Path(book))

    report = FirmEvalReport(trading_date=trading_date)
    if not firm_dir.is_dir():
        return report

    for sym_dir in sorted(p for p in firm_dir.iterdir() if p.is_dir()):
        sym = sym_dir.name.upper()
        trader_p = sym_dir / "trader_proposal.json"
        debate_p = sym_dir / "debate_verdict.json"
        risk_p = sym_dir / "risk_adjustment.json"
        mgr_p = sym_dir / "manager_decision.json"
        if not trader_p.is_file():
            continue
        try:
            trader = json.loads(trader_p.read_text(encoding="utf-8"))
            debate = json.loads(debate_p.read_text(encoding="utf-8")) if debate_p.is_file() else {}
            risk = json.loads(risk_p.read_text(encoding="utf-8")) if risk_p.is_file() else {}
            mgr = json.loads(mgr_p.read_text(encoding="utf-8")) if mgr_p.is_file() else {}
        except (OSError, json.JSONDecodeError):
            continue

        action = str(trader.get("action") or "HOLD").upper()
        book_act = book_actions.get(sym, "")
        agree: Optional[bool] = None
        if book_act:
            report.n_book_overlap += 1
            firm_enterish = action == "BUY" or (action == "SELL" and str(trader.get("side") or "").lower() == "bearish")
            book_enter = book_act.upper() == "ENTER"
            agree = firm_enterish == book_enter
            if agree:
                report.n_agree_enter += 1

        row = FirmEvalRow(
            symbol=sym,
            firm_action=action,
            firm_confidence=float(trader.get("confidence") or 0),
            debate_winner=str(debate.get("winner") or ""),
            manager_decision=str(mgr.get("decision") or ""),
            risk_recommendation=str(risk.get("recommendation") or ""),
            book_action=book_act,
            agree_enter=agree,
        )
        report.rows.append(row)
        report.n_symbols += 1
        if action == "BUY":
            report.n_buy += 1
        elif action == "SELL":
            report.n_sell += 1
        else:
            report.n_hold += 1
        if str(risk.get("recommendation") or "") == "veto":
            report.n_veto += 1

    if report.n_book_overlap:
        report.agreement_rate = round(report.n_agree_enter / report.n_book_overlap, 3)
    return report


def write_eval_report(report: FirmEvalReport, *, session_root: Optional[Path] = None) -> Path:
    root = Path(session_root) if session_root else Path.home() / ".trading_agent" / "sessions"
    out = root / report.trading_date / "firm" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out
