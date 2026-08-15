"""Systematic 5-step trading process (Julian Komar-style desk runbook).

Steps:
  1. Read the market   → regime / trade|light|cash
  2. Select stocks     → ranked focus list
  3. Prepare trades    → trade cards (trigger/stop/size/exit)
  4. Execute rules     → RTH = execution only; track violations
  5. Review & improve  → journal notes + weekly metrics hooks

State lives under ~/.trading_agent/process/YYYY-MM-DD.json (override via
TRADING_AGENT_PROCESS_DIR). Probes merge desk artifacts (sync books, OMS,
journal) so the checklist reflects real prep/execution.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

STEP_IDS = (
    "read_market",
    "select_stocks",
    "prepare_trades",
    "execute_rules",
    "review_improve",
)

STEP_LABELS = {
    "read_market": "1. Read the market",
    "select_stocks": "2. Select the right stocks",
    "prepare_trades": "3. Prepare every trade",
    "execute_rules": "4. Execute clear rules",
    "review_improve": "5. Review and improve",
}

STEP_PURPOSE = {
    "read_market": "Decide trade | light | cash before selecting names",
    "select_stocks": "Ranked focus list from fixed criteria (say no often)",
    "prepare_trades": "Trade cards: trigger, stop, size, exit — before open",
    "execute_rules": "RTH = execute only; no re-research or redesign",
    "review_improve": "Journal decisions, violations, emotions — not only P/L",
}


def process_root() -> Path:
    raw = os.getenv("TRADING_AGENT_PROCESS_DIR", "").strip()
    if raw:
        return Path(raw)
    state = os.getenv("TRADING_AGENT_STATE_DIR", "").strip()
    if state:
        return Path(state).expanduser() / "process"
    return Path.home() / ".trading_agent" / "process"


def day_state_path(day: date | None = None) -> Path:
    d = day or datetime.now(ET).date()
    return process_root() / f"{d.isoformat()}.json"


@dataclass
class TradeCard:
    symbol: str
    trigger: str = ""
    stop: str = ""
    size_risk: str = ""
    exit_plan: str = ""
    why: str = ""
    prepared: bool = False

    def is_complete(self) -> bool:
        return bool(
            self.symbol
            and self.trigger.strip()
            and self.stop.strip()
            and self.size_risk.strip()
            and self.exit_plan.strip()
        )


@dataclass
class ProcessStepStatus:
    step_id: str
    label: str
    purpose: str
    status: str  # complete | partial | missing | blocked
    score: float  # 0–100
    notes: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)


@dataclass
class ProcessDayState:
    trading_date: str
    regime: str = ""  # free text e.g. "bull / range"
    bias: str = ""  # trade | light | cash
    regime_reason: str = ""
    focus_list: List[str] = field(default_factory=list)
    trade_cards: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    journal_notes: List[Dict[str, Any]] = field(default_factory=list)
    step_notes: Dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def cards(self) -> List[TradeCard]:
        out: List[TradeCard] = []
        for raw in self.trade_cards:
            if not isinstance(raw, dict):
                continue
            out.append(
                TradeCard(
                    symbol=str(raw.get("symbol") or "").upper(),
                    trigger=str(raw.get("trigger") or ""),
                    stop=str(raw.get("stop") or ""),
                    size_risk=str(raw.get("size_risk") or raw.get("size") or ""),
                    exit_plan=str(raw.get("exit_plan") or raw.get("exit") or ""),
                    why=str(raw.get("why") or ""),
                    prepared=bool(raw.get("prepared", False)),
                )
            )
        return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_day_state(day: date | None = None) -> ProcessDayState:
    path = day_state_path(day)
    d = day or datetime.now(ET).date()
    if not path.is_file():
        return ProcessDayState(trading_date=d.isoformat())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProcessDayState(trading_date=d.isoformat())
    return ProcessDayState(
        trading_date=str(data.get("trading_date") or d.isoformat()),
        regime=str(data.get("regime") or ""),
        bias=str(data.get("bias") or "").lower(),
        regime_reason=str(data.get("regime_reason") or ""),
        focus_list=[str(s).upper() for s in (data.get("focus_list") or []) if s],
        trade_cards=list(data.get("trade_cards") or []),
        violations=list(data.get("violations") or []),
        journal_notes=list(data.get("journal_notes") or []),
        step_notes=dict(data.get("step_notes") or {}),
        updated_at=str(data.get("updated_at") or ""),
    )


def save_day_state(state: ProcessDayState, day: date | None = None) -> Path:
    path = day_state_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _now_iso()
    payload = asdict(state)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def ensure_day_state(day: date | None = None) -> ProcessDayState:
    state = load_day_state(day)
    path = day_state_path(day)
    if not path.is_file():
        save_day_state(state, day)
    return state


def set_regime(
    bias: str,
    *,
    regime: str = "",
    reason: str = "",
    day: date | None = None,
) -> ProcessDayState:
    state = load_day_state(day)
    b = bias.strip().lower()
    if b not in ("trade", "light", "cash"):
        raise ValueError("bias must be trade | light | cash")
    state.bias = b
    state.regime = regime.strip() or state.regime
    state.regime_reason = reason.strip() or state.regime_reason
    save_day_state(state, day)
    return state


def suggest_bias_from_desk(
    *,
    stay_in_cash: bool = False,
    ranked_count: int = 0,
    multi_method_entries: int = 0,
    environment_score: float | None = None,
) -> str:
    """Map desk/research outcome → process bias (trade | light | cash).

    Multi-method ENTERs and non-cash ranked setups unlock trade/light so the
    OMS process gate does not fail with process_bias_unset all day.
    """
    mm = max(0, int(multi_method_entries or 0))
    ranked = max(0, int(ranked_count or 0))
    if mm > 0 or (ranked > 0 and not stay_in_cash):
        if mm >= 2 or ranked >= 3:
            return "trade"
        return "light"
    if stay_in_cash and mm == 0 and ranked == 0:
        return "cash"
    # Default light so consumer can still process QT/gap books when research is empty
    if environment_score is not None and float(environment_score) < 40.0:
        return "cash"
    return "light"


def sync_process_bias_from_desk(
    *,
    stay_in_cash: bool = False,
    market_regime: str = "",
    environment_score: float | None = None,
    ranked_count: int = 0,
    multi_method_entries: int = 0,
    focus_symbols: Sequence[str] | None = None,
    reason: str = "",
    force: bool = False,
    day: date | None = None,
) -> ProcessDayState:
    """Fill process day bias from desk when unset (or force).

    Never overwrites an existing human bias unless force=True or
    TRADING_AGENT_PROCESS_BIAS_FORCE=1. Never upgrades cash→trade when the
    operator already set cash, unless force.
    """
    force = force or os.getenv("TRADING_AGENT_PROCESS_BIAS_FORCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    state = ensure_day_state(day)
    suggested = suggest_bias_from_desk(
        stay_in_cash=stay_in_cash,
        ranked_count=ranked_count,
        multi_method_entries=multi_method_entries,
        environment_score=environment_score,
    )
    # Prefer multi-method / ranked unlock over research-only cash wipe
    if multi_method_entries > 0 and suggested in ("trade", "light"):
        pass
    elif stay_in_cash and multi_method_entries <= 0 and ranked_count <= 0:
        suggested = "cash"

    current = (state.bias or "").strip().lower()
    if current in ("trade", "light", "cash") and not force:
        # Still refresh regime text / focus if empty
        changed = False
        if market_regime and not state.regime:
            state.regime = str(market_regime)[:200]
            changed = True
        if focus_symbols:
            try:
                upsert_focus_list(list(focus_symbols)[:20], day=day)
            except Exception:
                pass
        if changed:
            save_day_state(state, day)
        return load_day_state(day)

    why = reason or (
        f"auto desk: stay_in_cash={stay_in_cash} ranked={ranked_count} "
        f"mm_entries={multi_method_entries} env={environment_score}"
    )
    state = set_regime(
        suggested,
        regime=str(market_regime or state.regime or "")[:200],
        reason=why[:300],
        day=day,
    )
    if focus_symbols:
        try:
            upsert_focus_list(list(focus_symbols)[:20], day=day)
        except Exception:
            pass
    return load_day_state(day)


def upsert_focus_list(symbols: Sequence[str], *, day: date | None = None) -> ProcessDayState:
    state = load_day_state(day)
    seen = set()
    out: List[str] = []
    for s in symbols:
        sym = str(s).upper().strip()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    state.focus_list = out
    save_day_state(state, day)
    return state


def upsert_trade_card(
    symbol: str,
    *,
    trigger: str = "",
    stop: str = "",
    size_risk: str = "",
    exit_plan: str = "",
    why: str = "",
    day: date | None = None,
) -> ProcessDayState:
    state = load_day_state(day)
    sym = symbol.upper().strip()
    cards = [c for c in state.trade_cards if str(c.get("symbol") or "").upper() != sym]
    card = {
        "symbol": sym,
        "trigger": trigger,
        "stop": stop,
        "size_risk": size_risk,
        "exit_plan": exit_plan,
        "why": why,
        "prepared": bool(trigger and stop and size_risk and exit_plan),
    }
    cards.append(card)
    state.trade_cards = cards
    save_day_state(state, day)
    return state


def append_violation(
    message: str,
    *,
    step_id: str = "execute_rules",
    day: date | None = None,
) -> ProcessDayState:
    state = load_day_state(day)
    state.violations.append(
        {
            "at": _now_iso(),
            "step_id": step_id,
            "message": message.strip(),
        }
    )
    save_day_state(state, day)
    return state


def append_journal_note(
    note: str,
    *,
    kind: str = "review",
    day: date | None = None,
) -> ProcessDayState:
    state = load_day_state(day)
    state.journal_notes.append(
        {
            "at": _now_iso(),
            "kind": kind,
            "note": note.strip(),
        }
    )
    save_day_state(state, day)
    return state


def set_step_note(step_id: str, note: str, *, day: date | None = None) -> ProcessDayState:
    if step_id not in STEP_IDS:
        raise ValueError(f"unknown step_id {step_id}; use {STEP_IDS}")
    state = load_day_state(day)
    state.step_notes[step_id] = note.strip()
    save_day_state(state, day)
    return state


# ── Desk artifact probes ──────────────────────────────────────────────────


def probe_desk_artifacts() -> Dict[str, Any]:
    """Read-only snapshot of sync/session/OMS/journal for process scoring."""
    out: Dict[str, Any] = {
        "auto_trade": {},
        "gap_book_symbols": [],
        "playlist_symbols": [],
        "oms_open_lots": 0,
        "ready_orders": 0,
        "journal_trades": 0,
        "stay_in_cash": None,
        "regime_text": "",
        "watchlist": [],
        "entries": [],
    }
    try:
        from trading_agent.export.gap_book import default_sync_dir, load_gap_book
        from trading_agent.export.playlist_book import playlist_candidate_symbols, load_playlist_book
    except Exception as exc:  # noqa: BLE001
        out["probe_error"] = str(exc)
        return out

    sync = default_sync_dir()
    # auto_trade_book
    for name in ("auto_trade_book.json",):
        p = sync / name
        today = datetime.now(ET).date().isoformat()
        session_p = Path.home() / ".trading_agent" / "sessions" / today / "auto_trade_book.json"
        for path in (session_p, p):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out["auto_trade"] = data
            out["stay_in_cash"] = data.get("stay_in_cash")
            out["regime_text"] = str(data.get("regime") or "")
            out["watchlist"] = [
                str(s).upper()
                for s in (data.get("watchlist") or data.get("scan_symbols") or [])
                if s
            ]
            entries = data.get("entries") or []
            out["entries"] = entries if isinstance(entries, list) else []
            break

    book = load_gap_book()
    gap_syms = []
    for row in book.get("candidates") or []:
        if isinstance(row, dict) and row.get("symbol"):
            gap_syms.append(str(row["symbol"]).upper())
    out["gap_book_symbols"] = gap_syms[:30]
    out["playlist_symbols"] = playlist_candidate_symbols(load_playlist_book())[:30]

    # OMS open lots
    try:
        from trading_agent.oms.state import OmsStore

        store = OmsStore()
        lots = store.open_lots()
        out["oms_open_lots"] = len(lots)
    except Exception:  # noqa: BLE001
        out["oms_open_lots"] = 0

    # ready orders
    ready_dir = Path.home() / ".trading_agent" / "ready_orders"
    if ready_dir.is_dir():
        today = datetime.now(ET).date().isoformat()
        n = 0
        for f in ready_dir.glob("*.json"):
            if today in f.name or f.name == "ready_orders.json":
                n += 1
        out["ready_orders"] = n

    # journal
    try:
        from trading_agent.journal.trades import journal_path_for, load_journal_trades

        jpath = journal_path_for(datetime.now(ET).date())
        if jpath.is_file():
            try:
                trades = load_journal_trades(jpath)  # type: ignore[misc]
                out["journal_trades"] = len(trades) if trades else 0
            except Exception:
                raw = json.loads(jpath.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    out["journal_trades"] = len(raw)
                elif isinstance(raw, dict):
                    out["journal_trades"] = len(raw.get("trades") or [])
    except Exception:  # noqa: BLE001
        jpath = (
            Path.home()
            / ".trading_agent"
            / "sync"
            / "journal"
            / f"trades_{datetime.now(ET).date().isoformat()}.json"
        )
        if jpath.is_file():
            try:
                raw = json.loads(jpath.read_text(encoding="utf-8"))
                out["journal_trades"] = len(raw) if isinstance(raw, list) else len(
                    raw.get("trades") or []
                )
            except (OSError, json.JSONDecodeError):
                pass

    return out


def _status_from_score(score: float, *, blocked: bool = False) -> str:
    if blocked:
        return "blocked"
    if score >= 80:
        return "complete"
    if score >= 40:
        return "partial"
    return "missing"


def score_steps(
    state: ProcessDayState,
    *,
    artifacts: Dict[str, Any] | None = None,
    now: datetime | None = None,
) -> List[ProcessStepStatus]:
    """Score each of the 5 steps from state + desk probes."""
    art = artifacts if artifacts is not None else probe_desk_artifacts()
    now = now or datetime.now(ET)
    now_t = now.timetz().replace(tzinfo=None) if now.tzinfo else now.time()
    rth = time(9, 30) <= now_t <= time(16, 0)

    steps: List[ProcessStepStatus] = []

    # 1 Read market
    notes1: List[str] = []
    arts1: List[str] = []
    score1 = 0.0
    bias = (state.bias or "").lower()
    if bias in ("trade", "light", "cash"):
        score1 += 50
        notes1.append(f"Bias recorded: {bias}")
    if state.regime:
        score1 += 20
        notes1.append(f"Regime: {state.regime}")
    if state.regime_reason:
        score1 += 15
        notes1.append(f"Reason: {state.regime_reason}")
    if art.get("stay_in_cash") is True:
        score1 = max(score1, 60)
        notes1.append("Desk auto_trade: stay_in_cash=true")
        arts1.append("auto_trade_book.stay_in_cash")
        if not bias:
            bias = "cash"
    if art.get("regime_text"):
        score1 = max(score1, score1 + 10)
        arts1.append("auto_trade_book.regime")
        notes1.append("Regime text present on desk book")
    if state.step_notes.get("read_market"):
        score1 = min(100, score1 + 5)
    score1 = min(100.0, score1)
    steps.append(
        ProcessStepStatus(
            step_id="read_market",
            label=STEP_LABELS["read_market"],
            purpose=STEP_PURPOSE["read_market"],
            status=_status_from_score(score1),
            score=score1,
            notes=notes1 or ["No regime/bias recorded yet — run: process regime"],
            artifacts=arts1,
        )
    )

    # 2 Select stocks
    notes2: List[str] = []
    arts2: List[str] = []
    focus = list(state.focus_list)
    if not focus and art.get("watchlist"):
        focus = list(art["watchlist"])[:15]
        notes2.append(f"Using desk watchlist ({len(focus)} names)")
        arts2.append("auto_trade_book.watchlist")
    if not focus and art.get("gap_book_symbols"):
        focus = list(art["gap_book_symbols"])[:15]
        notes2.append(f"Using gap screener candidates ({len(focus)})")
        arts2.append("gap_screener_book")
    if not focus and art.get("playlist_symbols"):
        focus = list(art["playlist_symbols"])[:15]
        notes2.append("Using playlist candidates")
        arts2.append("watchlist_playlist")
    score2 = 0.0
    if focus:
        score2 += 55
        notes2.append(f"Focus list n={len(focus)}: {', '.join(focus[:8])}" + (
            "…" if len(focus) > 8 else ""
        ))
    if state.focus_list:
        score2 += 25  # explicit process list better than passive probe
        notes2.append("Explicit process focus_list saved")
    if 1 <= len(focus) <= 15:
        score2 += 15
        notes2.append("List size disciplined (≤15)")
    elif len(focus) > 15:
        score2 += 5
        notes2.append("List large — consider cutting to top 5–15")
    if bias == "cash":
        score2 = max(score2, 80)
        notes2.append("Cash bias — empty/action list OK")
    score2 = min(100.0, score2)
    steps.append(
        ProcessStepStatus(
            step_id="select_stocks",
            label=STEP_LABELS["select_stocks"],
            purpose=STEP_PURPOSE["select_stocks"],
            status=_status_from_score(score2),
            score=score2,
            notes=notes2 or ["No focus list — run: process focus SYM1,SYM2"],
            artifacts=arts2,
        )
    )

    # 3 Prepare trades
    notes3: List[str] = []
    arts3: List[str] = []
    cards = state.cards()
    complete_cards = [c for c in cards if c.is_complete()]
    score3 = 0.0
    if bias == "cash":
        score3 = 90
        notes3.append("Cash bias — no trade cards required")
    else:
        if complete_cards:
            score3 += 50 + min(40, len(complete_cards) * 15)
            notes3.append(f"{len(complete_cards)} complete trade card(s)")
        elif cards:
            score3 += 30
            notes3.append(f"{len(cards)} partial card(s) — fill trigger/stop/size/exit")
        entries = art.get("entries") or []
        if entries:
            score3 = max(score3, 55)
            notes3.append(f"Desk book entries: {len(entries)}")
            arts3.append("auto_trade_book.entries")
        if art.get("ready_orders"):
            score3 = max(score3, 50)
            notes3.append(f"Ready order files: {art['ready_orders']}")
            arts3.append("ready_orders")
    score3 = min(100.0, score3)
    steps.append(
        ProcessStepStatus(
            step_id="prepare_trades",
            label=STEP_LABELS["prepare_trades"],
            purpose=STEP_PURPOSE["prepare_trades"],
            status=_status_from_score(score3),
            score=score3,
            notes=notes3 or ["No trade cards — run: process card --symbol X --trigger …"],
            artifacts=arts3,
        )
    )

    # 4 Execute rules
    notes4: List[str] = []
    arts4: List[str] = []
    score4 = 40.0  # baseline if no violations during RTH
    viol = state.violations
    if rth:
        notes4.append("RTH open — execution-only mode")
        score4 = 50.0
        if complete_cards or bias == "cash":
            score4 += 20
            notes4.append("Prep present (or cash) for clean execution")
        if art.get("oms_open_lots"):
            score4 += 10
            notes4.append(f"OMS open lots: {art['oms_open_lots']}")
            arts4.append("oms.state")
    else:
        notes4.append("Outside RTH — execution step idle (prep/review time)")
        score4 = 70.0 if (complete_cards or bias == "cash" or not rth) else 40.0
    if viol:
        pen = min(50, len(viol) * 15)
        score4 = max(0, score4 - pen)
        notes4.append(f"Rule violations logged: {len(viol)} (−{pen})")
        for v in viol[-3:]:
            notes4.append(f"  · {v.get('message')}")
    else:
        score4 = min(100, score4 + 15)
        notes4.append("No process violations logged today")
    score4 = min(100.0, score4)
    steps.append(
        ProcessStepStatus(
            step_id="execute_rules",
            label=STEP_LABELS["execute_rules"],
            purpose=STEP_PURPOSE["execute_rules"],
            status=_status_from_score(score4),
            score=score4,
            notes=notes4,
            artifacts=arts4,
        )
    )

    # 5 Review
    notes5: List[str] = []
    arts5: List[str] = []
    score5 = 0.0
    jn = state.journal_notes
    if jn:
        score5 += min(50, 20 + len(jn) * 15)
        notes5.append(f"Process journal notes: {len(jn)}")
    jt = int(art.get("journal_trades") or 0)
    if jt:
        score5 += min(40, 15 + jt * 10)
        notes5.append(f"Closed-trade journal rows: {jt}")
        arts5.append("sync/journal")
    if state.step_notes.get("review_improve"):
        score5 += 10
    if now_t < time(15, 0) and not jn and not jt:
        notes5.append("Review typically after close — optional mid-day notes OK")
        score5 = max(score5, 25)
    score5 = min(100.0, score5)
    steps.append(
        ProcessStepStatus(
            step_id="review_improve",
            label=STEP_LABELS["review_improve"],
            purpose=STEP_PURPOSE["review_improve"],
            status=_status_from_score(score5),
            score=score5,
            notes=notes5 or ["No review notes yet — run: process note \"…\""],
            artifacts=arts5,
        )
    )

    return steps


def run_process_status(
    *,
    day: date | None = None,
    probe: bool = True,
) -> Dict[str, Any]:
    state = ensure_day_state(day)
    artifacts = probe_desk_artifacts() if probe else {}
    steps = score_steps(state, artifacts=artifacts)
    overall = sum(s.score for s in steps) / len(steps) if steps else 0.0
    return {
        "trading_date": state.trading_date,
        "bias": state.bias,
        "regime": state.regime,
        "overall_score": round(overall, 1),
        "steps": steps,
        "state": state,
        "artifacts": artifacts,
    }


def evaluate_process_pretrade_gate(
    *,
    day: date | None = None,
    probe: bool = True,
    min_step_score: float = 50.0,
    require_bias: bool = True,
    block_on_cash: bool = True,
) -> tuple[bool, str, Dict[str, Any]]:
    """OMS pretrade gate: Steps 1–3 must be process-complete before new entries.

    Returns (ok, reason, detail).
    Fail-closed when bias=cash or read/select/prepare scores below min_step_score.
    """
    payload = run_process_status(day=day, probe=probe)
    state: ProcessDayState = payload["state"]
    by_id = {s.step_id: s for s in payload["steps"]}
    detail: Dict[str, Any] = {
        "overall_score": payload.get("overall_score"),
        "bias": state.bias,
        "regime": state.regime,
        "steps": {
            sid: {"score": by_id[sid].score, "status": by_id[sid].status}
            for sid in ("read_market", "select_stocks", "prepare_trades")
            if sid in by_id
        },
    }

    bias = (state.bias or "").lower()
    if require_bias and bias not in ("trade", "light", "cash"):
        return False, "process_bias_unset", detail

    if block_on_cash and bias == "cash":
        return False, "process_cash_bias", detail

    # light = reduce risk; still allow entries if prep complete
    for sid, code in (
        ("read_market", "process_step1_incomplete"),
        ("select_stocks", "process_step2_incomplete"),
        ("prepare_trades", "process_step3_incomplete"),
    ):
        st = by_id.get(sid)
        if st is None or st.score < float(min_step_score):
            score = st.score if st else 0.0
            return False, f"{code}:{score:.0f}<{min_step_score:.0f}", detail

    return True, "", detail


def format_process_report(payload: Dict[str, Any]) -> str:
    steps: List[ProcessStepStatus] = payload.get("steps") or []
    state: ProcessDayState = payload.get("state") or ProcessDayState(trading_date="?")
    lines = [
        "# Systematic Process Status (5 steps)",
        "",
        f"- **Trading date:** {payload.get('trading_date')}",
        f"- **Overall process score:** **{payload.get('overall_score', 0):.0f}/100**",
        f"- **Bias:** {state.bias or '_(unset)_'} · **Regime:** {state.regime or '_(unset)_'}",
    ]
    if state.regime_reason:
        lines.append(f"- **Reason:** {state.regime_reason}")
    lines.extend(["", "## Steps", ""])
    for s in steps:
        icon = {
            "complete": "✅",
            "partial": "🟨",
            "missing": "⬜",
            "blocked": "⛔",
        }.get(s.status, "·")
        lines.append(f"### {icon} {s.label} — {s.status} ({s.score:.0f}/100)")
        lines.append(f"_{s.purpose}_")
        for n in s.notes:
            lines.append(f"- {n}")
        if s.artifacts:
            lines.append(f"- Artifacts: {', '.join(s.artifacts)}")
        lines.append("")

    lines.append("## Focus list")
    if state.focus_list:
        for i, sym in enumerate(state.focus_list, 1):
            lines.append(f"{i}. **{sym}**")
    else:
        lines.append("_empty — set with `process focus AAPL,MSFT,…`_")
    lines.append("")
    lines.append("## Trade cards")
    cards = state.cards()
    if not cards:
        lines.append("_none — `process card --symbol X --trigger … --stop … --size … --exit …`_")
    for c in cards:
        flag = "ready" if c.is_complete() else "incomplete"
        lines.append(
            f"- **{c.symbol}** [{flag}]: trigger=`{c.trigger}` stop=`{c.stop}` "
            f"size=`{c.size_risk}` exit=`{c.exit_plan}`"
        )
    lines.append("")
    lines.append("## Violations")
    if not state.violations:
        lines.append("_none logged_")
    for v in state.violations:
        lines.append(f"- {v.get('at', '')}: {v.get('message')}")
    lines.append("")
    lines.append("## Journal notes")
    if not state.journal_notes:
        lines.append("_none_")
    for j in state.journal_notes[-10:]:
        lines.append(f"- ({j.get('kind')}) {j.get('note')}")
    lines.extend(
        [
            "",
            "## Quick commands",
            "```",
            "python -m trading_agent process status",
            "python -m trading_agent process regime --bias cash --regime \"risk-off\" --reason \"…\"",
            "python -m trading_agent process focus NVDA,AMD,META",
            "python -m trading_agent process card --symbol NVDA --trigger \"10:00 VWAP reclaim\" "
            "--stop \"below OR low\" --size \"0.5R\" --exit \"trail EMA\"",
            "python -m trading_agent process violation \"resized mid-trade without rule\"",
            "python -m trading_agent process note \"Reviewed 2 trades; 1 FOMO entry\"",
            "```",
            "",
            "_Process score is a compliance checklist, not a profit guarantee._",
            "",
        ]
    )
    return "\n".join(lines)
