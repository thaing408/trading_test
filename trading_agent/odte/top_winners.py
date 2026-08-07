"""Top-2 winners morning playbook (0DTE CALL) — L0→L4 learning upgrades.

L1 Selection: re-rank at decision time (10:00) by continuation score; hard gates
    (green, above VWAP, HTF bull); soft EMA; reject RSI chase.
L2 Entry: pullback to VWAP/EMA9 in entry window (not blind clock market).
L3 Exit: configurable brackets, time stop, optional trail after partial TP.
L4 Universe: max gap cap, relative volume floor, quality (score 4/4 → prefer 1 name).

Paper / signal / backtest only — not live broker execution.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.analysis.technical import ema, rsi
from trading_agent.export.gap_book import default_sync_dir, load_gap_book
from trading_agent.export.playlist_book import load_playlist_book, playlist_candidate_symbols
from trading_agent.odte.backtest import (
    OdteBacktestResult,
    OdteTrade,
    _day_slice,
    _session_days,
    fetch_qqq_1m,
)
from trading_agent.odte.multidte import fetch_htf_bars

ET = ZoneInfo("America/New_York")

DEFAULT_FIXED_UNIVERSE = (
    "NVDA",
    "AMD",
    "TSLA",
    "AAPL",
    "MSFT",
    "META",
    "AMZN",
    "GOOGL",
    "PLTR",
    "MU",
)

# Named exit brackets for A/B (L3)
BRACKET_PRESETS: Dict[str, Tuple[float, float]] = {
    "legacy30_25": (0.30, 0.25),  # shipped default after L1–L4 A/B
    "wr20_15": (0.20, 0.15),
    "bal25_20": (0.25, 0.20),
    "default": (0.30, 0.25),
}


@dataclass
class TopWinnersConfig:
    """Rules for top-winners morning entries (L1–L4)."""

    list_size: int = 10
    monitor_top_n: int = 2
    entry_delay_minutes: int = 30  # 9:30 + 30 → decision clock 10:00 ET
    # L2: search pullback until this many minutes after decision clock
    entry_window_minutes: int = 30  # 10:00–10:30
    entry_mode: str = "pullback"  # pullback | clock

    # L3 exits — 1mo A/B favored legacy30_25 with L1–L4 path (trail + pullback)
    take_profit_pct: float = 0.30
    stop_loss_pct: float = 0.25
    bracket_name: str = "legacy30_25"
    time_exit_et: time = time(11, 30)  # flatten if neither side hit
    trail_activate_pct: float = 0.15  # start trail after +15% premium
    trail_giveback_pct: float = 0.08  # give back 8pp from peak → exit
    use_trail: bool = True

    contracts: int = 1
    # L1 drop-fast / structure
    max_drop_from_high_pct: float = 1.0
    min_change_vs_open_pct: float = 0.10
    require_green_vs_open: bool = True
    require_made_progress: bool = True

    # L1 TA: hard musts + soft score
    require_above_vwap: bool = True  # hard
    require_htf_bullish: bool = True  # hard
    soft_ema_stack: bool = True  # soft (score)
    max_rsi: float = 80.0
    chase_rsi: float = 85.0  # hard reject if RSI > chase and far above VWAP
    chase_vwap_ext_pct: float = 0.8  # % above VWAP counts as "far"
    min_rsi: float = 45.0
    min_ta_score: int = 3  # of soft checks when hard pass (legacy score path)
    vwap_tol_pct: float = 0.15
    htf_rule: str = "15m"
    decision_tf_label: str = "5m/1m"

    # L1 re-rank at decision time
    rank_at_decision: bool = True  # True = continuation score @ 10:00, not open-gap only
    gap_weight: float = 0.35
    cont_weight: float = 0.65

    # L4 universe quality
    max_gap_pct: float = 8.0  # skip exhaustion gaps
    min_gap_pct: float = 0.0
    min_rvol: float = 1.0  # session vol / prior day same-window proxy
    require_quality_4of4_for_second: bool = True  # 2nd name only if ta quality full
    max_entries_per_day: int = 2
    prefer_single_if_perfect: bool = True  # if one name is 4/4, only take that

    premium_delta: float = 0.55
    entry_prem: float = 1.0
    account_size: float = 1_000.0
    rth_open: time = time(9, 30)
    rth_close: time = time(16, 0)


def apply_bracket_preset(cfg: TopWinnersConfig, name: str) -> TopWinnersConfig:
    key = (name or "default").strip().lower().replace("-", "_")
    aliases = {
        "30_25": "legacy30_25",
        "legacy": "legacy30_25",
        "20_15": "wr20_15",
        "wr": "wr20_15",
        "25_20": "bal25_20",
        "bal": "bal25_20",
        "default": "legacy30_25",
    }
    key = aliases.get(key, key)
    if key not in BRACKET_PRESETS:
        key = "legacy30_25"
    tp, sl = BRACKET_PRESETS[key]
    return replace(cfg, take_profit_pct=tp, stop_loss_pct=sl, bracket_name=key)


@dataclass
class DropFastEvaluation:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    open_px: float = 0.0
    high_px: float = 0.0
    last_px: float = 0.0
    drop_from_high_pct: float = 0.0
    change_vs_open_pct: float = 0.0


@dataclass
class TaEvaluation:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    vwap: float = 0.0
    last_px: float = 0.0
    rsi: float = 50.0
    ema9: float = 0.0
    ema21: float = 0.0
    htf_ema9: float = 0.0
    htf_ema21: float = 0.0
    above_vwap: bool = False
    ema_stack_bull: bool = False
    htf_bull: bool = False
    rsi_ok: bool = False
    quality_score: int = 0  # 0–4
    hard_pass: bool = False
    is_chase: bool = False


@dataclass
class EntryEvaluation:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    drop: Optional[DropFastEvaluation] = None
    ta: Optional[TaEvaluation] = None
    continuation_score: float = 0.0
    gap_pct: float = 0.0
    rvol: float = 0.0


@dataclass
class TopWinnerSignal:
    symbol: str
    rank: int
    decision: str  # ENTER | SKIP | WATCH | NO_DATA | WAIT_PULLBACK
    reasons: List[str] = field(default_factory=list)
    drop_eval: Optional[DropFastEvaluation] = None
    ta_eval: Optional[TaEvaluation] = None
    side: str = "CALL"
    contracts: int = 1
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.20
    continuation_score: float = 0.0


@dataclass
class TopWinnersBrief:
    asof: str
    source: str
    top10: List[str]
    monitored: List[TopWinnerSignal]
    entry_time_et: str
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def entry_time_et(cfg: TopWinnersConfig | None = None) -> time:
    cfg = cfg or TopWinnersConfig()
    total = cfg.rth_open.hour * 60 + cfg.rth_open.minute + int(cfg.entry_delay_minutes)
    return time(total // 60, total % 60)


def entry_window_end_et(cfg: TopWinnersConfig | None = None) -> time:
    cfg = cfg or TopWinnersConfig()
    start = entry_time_et(cfg)
    total = start.hour * 60 + start.minute + int(cfg.entry_window_minutes)
    return time(min(total // 60, 16), total % 60 if total // 60 < 16 else 0)


# ── Researcher list loading ───────────────────────────────────────────────


def symbols_from_gap_book(
    book: Dict[str, Any] | None = None,
    *,
    list_size: int = 10,
) -> List[str]:
    data = book if book is not None else load_gap_book()
    rows: List[Dict[str, Any]] = []
    for row in data.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym:
            continue
        direction = str(row.get("direction") or "").lower().strip()
        try:
            gap_pct = float(row.get("gap_pct") or 0.0)
        except (TypeError, ValueError):
            gap_pct = 0.0
        if direction not in ("up", "long", "bull", "bullish") and gap_pct <= 0:
            continue
        try:
            rank_score = float(row.get("rank_score") or 0.0)
        except (TypeError, ValueError):
            rank_score = 0.0
        rows.append({"symbol": sym, "rank_score": rank_score, "gap_pct": gap_pct})
    rows.sort(key=lambda r: (-r["rank_score"], -abs(r["gap_pct"]), r["symbol"]))
    out: List[str] = []
    seen = set()
    for r in rows:
        s = r["symbol"]
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= list_size:
            break
    return out


def symbols_from_auto_trade_book(list_size: int = 10) -> List[str]:
    sync = default_sync_dir()
    paths = [
        sync / "auto_trade_book.json",
        sync / "auto_trade_scan_symbols.json",
        Path.home() / ".trading_agent" / "sessions" / "auto_trade_book.json",
    ]
    today = datetime.now(ET).date().isoformat()
    paths.insert(0, Path.home() / ".trading_agent" / "sessions" / today / "auto_trade_book.json")
    for p in paths:
        try:
            if not p.is_file():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("watchlist", "scan_symbols", "symbols"):
            raw = data.get(key)
            if not isinstance(raw, list) or not raw:
                continue
            out: List[str] = []
            seen = set()
            for item in raw:
                if isinstance(item, str):
                    sym = item.upper().strip()
                elif isinstance(item, dict):
                    sym = str(item.get("symbol") or "").upper().strip()
                else:
                    continue
                if sym and sym not in seen:
                    seen.add(sym)
                    out.append(sym)
                if len(out) >= list_size:
                    return out
            if out:
                return out[:list_size]
    return []


def load_top_winner_symbols(
    *,
    list_size: int = 10,
    symbols_override: Sequence[str] | None = None,
    gap_book: Dict[str, Any] | None = None,
) -> Tuple[List[str], str]:
    if symbols_override:
        out: List[str] = []
        seen = set()
        for s in symbols_override:
            sym = str(s).upper().strip()
            if sym and sym not in seen:
                seen.add(sym)
                out.append(sym)
            if len(out) >= list_size:
                break
        return out, "cli_override"

    gap_syms = symbols_from_gap_book(gap_book, list_size=list_size)
    if gap_syms:
        return gap_syms, "gap_screener_book"
    at_syms = symbols_from_auto_trade_book(list_size=list_size)
    if at_syms:
        return at_syms, "auto_trade_book"
    pl = playlist_candidate_symbols(load_playlist_book())
    if pl:
        return pl[:list_size], "watchlist_playlist"
    return [], "none"


# ── Price / session helpers ───────────────────────────────────────────────


def _bars_up_to_entry(day_df, cfg: TopWinnersConfig):
    t_entry = entry_time_et(cfg)
    return day_df.between_time(cfg.rth_open, t_entry)


def _session_vwap(rth) -> float:
    if rth is None or len(rth) == 0:
        return 0.0
    highs = rth["High"].astype(float)
    lows = rth["Low"].astype(float)
    closes = rth["Close"].astype(float)
    vols = rth["Volume"].astype(float) if "Volume" in rth.columns else None
    typical = (highs + lows + closes) / 3.0
    if vols is None or float(vols.sum()) <= 0:
        return float(typical.mean())
    return float((typical * vols).sum() / vols.sum())


def _gap_pct_open(day_df, prior_close: Optional[float]) -> float:
    rth = day_df.between_time(time(9, 30), time(16, 0))
    if rth.empty:
        return float("-inf")
    o = float(rth.iloc[0]["Open"])
    if prior_close and prior_close > 0:
        return (o - prior_close) / prior_close * 100.0
    return 0.0


def _prior_close(df, d: date) -> Optional[float]:
    days = _session_days(df)
    if d not in days:
        return None
    i = days.index(d)
    if i == 0:
        return None
    prev = _day_slice(df, days[i - 1])
    if prev.empty:
        return None
    return float(prev["Close"].iloc[-1])


def _change_vs_open_pct(day_df, cfg: TopWinnersConfig) -> float:
    rth = _bars_up_to_entry(day_df, cfg)
    if rth is None or len(rth) == 0:
        return float("-inf")
    o = float(rth.iloc[0]["Open"])
    c = float(rth.iloc[-1]["Close"])
    if o <= 0:
        return float("-inf")
    return (c - o) / o * 100.0


def _rvol_proxy(day_df, full_df, d: date, cfg: TopWinnersConfig) -> float:
    """Session open→decision volume vs prior day same window."""
    cur = _bars_up_to_entry(day_df, cfg)
    if cur is None or len(cur) == 0 or "Volume" not in cur.columns:
        return 1.0
    cur_v = float(cur["Volume"].sum())
    days = _session_days(full_df) if full_df is not None else []
    if d not in days:
        return 1.0
    i = days.index(d)
    if i == 0:
        return 1.0
    prev = _day_slice(full_df, days[i - 1])
    prev_w = _bars_up_to_entry(prev, cfg)
    if prev_w is None or len(prev_w) == 0 or "Volume" not in prev_w.columns:
        return 1.0
    prev_v = float(prev_w["Volume"].sum())
    if prev_v <= 0:
        return 1.0
    return cur_v / prev_v


def continuation_score(
    day_df,
    *,
    gap_pct: float,
    cfg: TopWinnersConfig,
) -> float:
    """L1: blend open gap with % change from open at decision (higher = better winner)."""
    cont = _change_vs_open_pct(day_df, cfg)
    if cont == float("-inf"):
        return float("-inf")
    # normalize-ish: gap and cont already in %
    return float(cfg.gap_weight) * float(gap_pct) + float(cfg.cont_weight) * float(cont)


def _htf_closes_from_intraday(full_df, d: date, *, rule: str = "15min") -> List[float]:
    if full_df is None or len(full_df) == 0:
        return []
    try:
        days = _session_days(full_df)
        if d not in days:
            return []
        i = days.index(d)
        start_d = days[max(0, i - 3)]
        mask = [(ts.date() >= start_d and ts.date() <= d) for ts in full_df.index]
        sub = full_df.loc[mask]
        if sub.empty:
            return []
        rs = "15min" if rule in ("15m", "15min", "15") else rule
        ohlc = sub["Close"].astype(float).resample(rs).last().dropna()
        t_end = datetime.combine(d, time(10, 0), tzinfo=ET)
        ohlc = ohlc[ohlc.index <= t_end]
        return [float(x) for x in ohlc.tolist()]
    except Exception:  # noqa: BLE001
        return []


# ── Filters ───────────────────────────────────────────────────────────────


def passes_drop_fast_filter(
    open_px: float,
    high_px: float,
    last_px: float,
    *,
    cfg: TopWinnersConfig | None = None,
) -> DropFastEvaluation:
    cfg = cfg or TopWinnersConfig()
    reasons: List[str] = []
    open_px = float(open_px)
    high_px = float(high_px)
    last_px = float(last_px)

    if open_px <= 0 or last_px <= 0 or high_px <= 0:
        return DropFastEvaluation(
            passed=False,
            reasons=["invalid prices"],
            open_px=open_px,
            high_px=high_px,
            last_px=last_px,
        )

    change_vs_open = (last_px - open_px) / open_px * 100.0
    drop_from_high = (high_px - last_px) / high_px * 100.0 if high_px > 0 else 0.0

    if cfg.require_green_vs_open and last_px < open_px:
        reasons.append(
            f"red vs open ({change_vs_open:+.2f}%): last {last_px:.2f} < open {open_px:.2f}"
        )
    if cfg.require_made_progress and high_px < open_px:
        reasons.append(f"no progress after open (high {high_px:.2f} < open {open_px:.2f})")
    if drop_from_high > float(cfg.max_drop_from_high_pct):
        reasons.append(
            f"drop-fast from high {drop_from_high:.2f}% > {cfg.max_drop_from_high_pct:.2f}%"
        )
    if change_vs_open < float(cfg.min_change_vs_open_pct):
        reasons.append(
            f"weak vs open ({change_vs_open:+.2f}% < min {cfg.min_change_vs_open_pct:+.2f}%)"
        )

    return DropFastEvaluation(
        passed=len(reasons) == 0,
        reasons=reasons,
        open_px=open_px,
        high_px=high_px,
        last_px=last_px,
        drop_from_high_pct=round(drop_from_high, 4),
        change_vs_open_pct=round(change_vs_open, 4),
    )


def evaluate_session_window(
    day_df,
    *,
    cfg: TopWinnersConfig | None = None,
) -> DropFastEvaluation:
    cfg = cfg or TopWinnersConfig()
    rth = _bars_up_to_entry(day_df, cfg)
    if rth is None or len(rth) == 0:
        return DropFastEvaluation(passed=False, reasons=["no bars in open→entry window"])
    open_px = float(rth.iloc[0]["Open"])
    high_px = float(rth["High"].max())
    last_px = float(rth.iloc[-1]["Close"])
    return passes_drop_fast_filter(open_px, high_px, last_px, cfg=cfg)


def evaluate_ta_gate(
    day_df,
    *,
    cfg: TopWinnersConfig | None = None,
    full_df=None,
    day: date | None = None,
) -> TaEvaluation:
    """L1 TA: hard (VWAP + HTF + not chase) + soft quality score (EMA/RSI)."""
    cfg = cfg or TopWinnersConfig()
    rth = _bars_up_to_entry(day_df, cfg)
    if rth is None or len(rth) == 0:
        return TaEvaluation(passed=False, reasons=["no bars for TA window"])

    closes = rth["Close"].astype(float).tolist()
    last_px = float(closes[-1])
    vwap = _session_vwap(rth)
    hist_closes = closes
    if full_df is not None and day is not None:
        try:
            t_entry = entry_time_et(cfg)
            cut = datetime.combine(day, t_entry, tzinfo=ET)
            hist = full_df.loc[full_df.index <= cut, "Close"].astype(float).tolist()
            if len(hist) >= 25:
                hist_closes = hist
        except Exception:  # noqa: BLE001
            pass

    rsi_v = float(rsi(hist_closes, 14))
    e9 = float(ema(hist_closes, 9))
    e21 = float(ema(hist_closes, 21))
    tol = 1.0 - float(cfg.vwap_tol_pct) / 100.0
    above_vwap = last_px >= vwap * tol
    ema_stack = e9 > e21
    rsi_ok = float(cfg.min_rsi) <= rsi_v <= float(cfg.max_rsi)

    htf_closes = (
        _htf_closes_from_intraday(full_df, day, rule="15min")
        if (full_df is not None and day is not None)
        else []
    )
    if len(htf_closes) < 5:
        htf_e9, htf_e21 = e9, e21
        htf_bull = ema_stack
    else:
        htf_e9 = float(ema(htf_closes, 9))
        htf_e21 = float(ema(htf_closes, 21))
        htf_bull = htf_e9 > htf_e21

    ext_pct = ((last_px - vwap) / vwap * 100.0) if vwap > 0 else 0.0
    is_chase = rsi_v > float(cfg.chase_rsi) and ext_pct > float(cfg.chase_vwap_ext_pct)

    # Quality score 0–4
    quality = int(above_vwap) + int(ema_stack) + int(htf_bull) + int(rsi_ok)

    hard_reasons: List[str] = []
    if cfg.require_above_vwap and not above_vwap:
        hard_reasons.append(f"below session VWAP ({last_px:.2f} < {vwap:.2f})")
    if cfg.require_htf_bullish and not htf_bull:
        hard_reasons.append(f"HTF {cfg.htf_rule} not bullish (EMA9 ≤ EMA21)")
    if is_chase:
        hard_reasons.append(
            f"chase reject: RSI {rsi_v:.1f} > {cfg.chase_rsi:.0f} and "
            f"+{ext_pct:.2f}% vs VWAP"
        )

    soft_notes = []
    if cfg.soft_ema_stack and not ema_stack:
        soft_notes.append(f"soft: EMA stack weak (EMA9 {e9:.2f} ≤ EMA21 {e21:.2f})")
    if not rsi_ok:
        soft_notes.append(
            f"soft: RSI {rsi_v:.1f} outside [{cfg.min_rsi:.0f},{cfg.max_rsi:.0f}]"
        )

    # Pass: hard gates + quality >= min_ta_score (still need some soft alignment)
    hard_pass = len(hard_reasons) == 0
    need = int(cfg.min_ta_score)
    passed = hard_pass and quality >= need

    reasons = list(hard_reasons)
    if hard_pass and quality < need:
        reasons.append(f"TA quality {quality}/4 < min {need}")

    notes = [
        f"decision_tf last={last_px:.2f} VWAP={vwap:.2f} RSI(14)={rsi_v:.1f} "
        f"EMA9={e9:.2f} EMA21={e21:.2f}",
        f"HTF({cfg.htf_rule}) EMA9={htf_e9:.2f} EMA21={htf_e21:.2f} "
        f"{'bull' if htf_bull else 'not-bull'}",
        f"quality {quality}/4 hard={'PASS' if hard_pass else 'FAIL'} "
        f"VWAP={'Y' if above_vwap else 'N'} EMA={'Y' if ema_stack else 'N'} "
        f"HTF={'Y' if htf_bull else 'N'} RSI={'Y' if rsi_ok else 'N'}",
    ] + soft_notes

    return TaEvaluation(
        passed=passed,
        reasons=reasons,
        notes=notes,
        vwap=round(vwap, 4),
        last_px=round(last_px, 4),
        rsi=round(rsi_v, 2),
        ema9=round(e9, 4),
        ema21=round(e21, 4),
        htf_ema9=round(htf_e9, 4),
        htf_ema21=round(htf_e21, 4),
        above_vwap=above_vwap,
        ema_stack_bull=ema_stack,
        htf_bull=htf_bull,
        rsi_ok=rsi_ok,
        quality_score=quality,
        hard_pass=hard_pass,
        is_chase=is_chase,
    )


def evaluate_entry(
    day_df,
    *,
    cfg: TopWinnersConfig | None = None,
    full_df=None,
    day: date | None = None,
    gap_pct: float = 0.0,
) -> EntryEvaluation:
    """L1+L4 gates at decision clock (before pullback fill)."""
    cfg = cfg or TopWinnersConfig()
    drop = evaluate_session_window(day_df, cfg=cfg)
    ta = evaluate_ta_gate(day_df, cfg=cfg, full_df=full_df, day=day)
    rvol = _rvol_proxy(day_df, full_df, day, cfg) if day is not None else 1.0
    cont = continuation_score(day_df, gap_pct=gap_pct, cfg=cfg)

    reasons: List[str] = []
    if not drop.passed:
        reasons.extend(drop.reasons)
    if not ta.passed:
        reasons.extend(ta.reasons)

    # L4 gap / RVOL
    if gap_pct != float("-inf") and gap_pct > float(cfg.max_gap_pct):
        reasons.append(f"exhaustion gap {gap_pct:.2f}% > max {cfg.max_gap_pct:.1f}%")
    if gap_pct != float("-inf") and gap_pct < float(cfg.min_gap_pct):
        reasons.append(f"gap {gap_pct:.2f}% < min {cfg.min_gap_pct:.1f}%")
    if rvol < float(cfg.min_rvol):
        reasons.append(f"RVOL {rvol:.2f}x < min {cfg.min_rvol:.2f}x")

    # Universe exhaustion alone fails even if drop/ta ok
    universe_ok = (
        (gap_pct == float("-inf") or gap_pct <= float(cfg.max_gap_pct))
        and (gap_pct == float("-inf") or gap_pct >= float(cfg.min_gap_pct))
        and rvol >= float(cfg.min_rvol)
    )
    passed = drop.passed and ta.passed and universe_ok

    return EntryEvaluation(
        passed=passed,
        reasons=reasons,
        drop=drop,
        ta=ta,
        continuation_score=cont if cont != float("-inf") else -999.0,
        gap_pct=gap_pct if gap_pct != float("-inf") else 0.0,
        rvol=round(rvol, 3),
    )


# ── L2 pullback entry ─────────────────────────────────────────────────────


def find_pullback_entry(
    day_df,
    *,
    cfg: TopWinnersConfig,
    full_df=None,
    day: date | None = None,
) -> Optional[Tuple[Any, float, str]]:
    """L2: after decision clock, wait for touch of VWAP or EMA9 then reclaim.

    Returns (entry_timestamp, entry_spot, tag) or None.
    """
    t0 = entry_time_et(cfg)
    t1 = entry_window_end_et(cfg)
    rth = day_df.between_time(cfg.rth_open, cfg.rth_close)
    if rth.empty:
        return None

    # Structure reference from open→decision
    pre = day_df.between_time(cfg.rth_open, t0)
    if pre is None or len(pre) == 0:
        return None
    vwap = _session_vwap(pre)
    pre_closes = pre["Close"].astype(float).tolist()
    # Seed EMA with history if possible
    hist = pre_closes
    if full_df is not None and day is not None:
        try:
            cut = datetime.combine(day, t0, tzinfo=ET)
            h = full_df.loc[full_df.index <= cut, "Close"].astype(float).tolist()
            if len(h) >= 21:
                hist = h
        except Exception:  # noqa: BLE001
            pass
    e9 = float(ema(hist, 9))

    window = rth.between_time(t0, t1)
    if window.empty:
        return None

    if (cfg.entry_mode or "pullback").lower() == "clock":
        bar = window.iloc[0]
        return window.index[0], float(bar["Open"]), "clock"

    # Running vwap/ema through window for touch detection
    # Use pre vwap as magnet; allow touch within 0.15%
    tol = float(cfg.vwap_tol_pct) / 100.0
    touched = False
    closes_run = list(hist)
    for ts, row in window.iterrows():
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        c = float(row["Close"])
        closes_run.append(c)
        e9 = float(ema(closes_run, 9))
        # Update session vwap including this bar roughly via typical of pre+seen
        # Use fixed pre-vwap + e9 as levels (stable magnets)
        near_vwap = l <= vwap * (1 + tol) and h >= vwap * (1 - tol)
        near_ema = l <= e9 * (1 + tol) and h >= e9 * (1 - tol)
        if near_vwap or near_ema:
            touched = True
        # Reclaim: after touch, close back above both magnets and green bar
        if touched and c >= max(vwap, e9) * (1 - tol) and c >= o:
            tag = "pullback_vwap" if near_vwap or c >= vwap else "pullback_ema9"
            # Enter at close of reclaim bar (conservative)
            return ts, c, tag
    return None


# ── L3 premium path with trail + time stop ────────────────────────────────


def simulate_premium_path_l3(
    side: str,
    entry_spot: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    times: Sequence[Any],
    *,
    entry_prem: float,
    tp_pct: float,
    sl_pct: float,
    delta: float,
    time_exit_et: time | None = None,
    use_trail: bool = True,
    trail_activate_pct: float = 0.15,
    trail_giveback_pct: float = 0.08,
) -> Tuple[float, float, str, Any]:
    """Walk bars; TP/SL + optional trail + time stop."""
    tp_prem = entry_prem * (1 + tp_pct)
    sl_prem = entry_prem * (1 - sl_pct)
    peak_prem = entry_prem
    trail_on = False

    for h, l, c, tm in zip(highs, lows, closes, times):
        # Time stop first (end of bar clock)
        if time_exit_et is not None and tm is not None:
            try:
                tt = tm.timetz().replace(tzinfo=None) if getattr(tm, "tzinfo", None) else tm.time()
                if tt >= time_exit_et:
                    if side == "CALL":
                        prem = entry_prem + delta * (c - entry_spot)
                    else:
                        prem = entry_prem + delta * (entry_spot - c)
                    return max(prem, 0.01), float(c), "time_exit", tm
            except Exception:  # noqa: BLE001
                pass

        if side == "CALL":
            prem_hi = entry_prem + delta * (h - entry_spot)
            prem_lo = entry_prem + delta * (l - entry_spot)
            prem_c = entry_prem + delta * (c - entry_spot)
            peak_prem = max(peak_prem, prem_hi)
            if prem_lo <= sl_prem:
                return sl_prem, float(l), "stop_loss", tm
            if prem_hi >= tp_prem:
                return tp_prem, float(h), "take_profit", tm
            if use_trail:
                if peak_prem >= entry_prem * (1 + trail_activate_pct):
                    trail_on = True
                if trail_on:
                    trail_floor = peak_prem - entry_prem * trail_giveback_pct
                    if prem_lo <= trail_floor:
                        return max(trail_floor, 0.01), float(l), "trail_exit", tm
        else:
            prem_hi = entry_prem + delta * (entry_spot - l)
            prem_lo = entry_prem + delta * (entry_spot - h)
            prem_c = entry_prem + delta * (entry_spot - c)
            peak_prem = max(peak_prem, prem_hi)
            if prem_lo <= sl_prem:
                return sl_prem, float(h), "stop_loss", tm
            if prem_hi >= tp_prem:
                return tp_prem, float(l), "take_profit", tm
            if use_trail:
                if peak_prem >= entry_prem * (1 + trail_activate_pct):
                    trail_on = True
                if trail_on:
                    trail_floor = peak_prem - entry_prem * trail_giveback_pct
                    if prem_lo <= trail_floor:
                        return max(trail_floor, 0.01), float(h), "trail_exit", tm

    c = closes[-1] if closes else entry_spot
    tm = times[-1] if times else None
    if side == "CALL":
        prem = entry_prem + delta * (c - entry_spot)
    else:
        prem = entry_prem + delta * (entry_spot - c)
    return max(prem, 0.01), float(c), "time_exit", tm


# ── Ranking ───────────────────────────────────────────────────────────────


def rank_universe_for_day(
    frames: Dict[str, Any],
    d: date,
    *,
    cfg: TopWinnersConfig,
) -> List[Tuple[str, float, float, EntryEvaluation]]:
    """Return list of (symbol, score, gap_pct, entry_eval) sorted best-first.

    L1: score = continuation blend at decision when rank_at_decision else gap only.
    Only names that pass entry filters are candidates; failures still ranked lower
    for diagnostics but monitor set uses passed-only.
    """
    rows: List[Tuple[str, float, float, EntryEvaluation]] = []
    for sym, df in frames.items():
        day_df = _day_slice(df, d)
        if day_df.empty:
            continue
        pc = _prior_close(df, d)
        gap = _gap_pct_open(day_df, pc)
        if gap == float("-inf"):
            continue
        ev = evaluate_entry(day_df, cfg=cfg, full_df=df, day=d, gap_pct=gap)
        if cfg.rank_at_decision:
            score = ev.continuation_score
        else:
            score = gap
        rows.append((sym, score, gap, ev))
    rows.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return rows


def select_entries_for_day(
    ranked: List[Tuple[str, float, float, EntryEvaluation]],
    *,
    cfg: TopWinnersConfig,
) -> List[Tuple[int, str, float, float, EntryEvaluation]]:
    """L4 quality: top-N that pass; prefer single perfect; 2nd needs 4/4 if configured."""
    passed = [(s, sc, g, e) for s, sc, g, e in ranked if e.passed]
    # Prefer highest quality then score
    passed.sort(
        key=lambda x: (
            -(x[3].ta.quality_score if x[3].ta else 0),
            -x[1],
            -x[2],
            x[0],
        )
    )
    out: List[Tuple[int, str, float, float, EntryEvaluation]] = []
    for s, sc, g, e in passed:
        q = e.ta.quality_score if e.ta else 0
        if not out:
            out.append((1, s, sc, g, e))
            if cfg.prefer_single_if_perfect and q >= 4:
                break
            continue
        if len(out) >= int(cfg.max_entries_per_day):
            break
        if len(out) >= int(cfg.monitor_top_n):
            break
        if cfg.require_quality_4of4_for_second and q < 4:
            continue
        out.append((len(out) + 1, s, sc, g, e))
        if len(out) >= int(cfg.max_entries_per_day):
            break
    return out


# ── Brief ─────────────────────────────────────────────────────────────────


def run_top_winners_brief(
    *,
    cfg: TopWinnersConfig | None = None,
    symbols_override: Sequence[str] | None = None,
    data_source: str = "auto",
    live: bool = True,
    gap_book: Dict[str, Any] | None = None,
) -> TopWinnersBrief:
    cfg = cfg or TopWinnersConfig()
    top10, source = load_top_winner_symbols(
        list_size=max(cfg.list_size, 15),
        symbols_override=symbols_override,
        gap_book=gap_book,
    )
    t_entry = entry_time_et(cfg)
    t_end = entry_window_end_et(cfg)
    now = datetime.now(ET)
    brief = TopWinnersBrief(
        asof=now.isoformat(),
        source=source,
        top10=list(top10)[: cfg.list_size],
        monitored=[],
        entry_time_et=f"{t_entry.strftime('%H:%M')}–{t_end.strftime('%H:%M')} ET",
        notes=[
            "L1: re-rank @ decision by continuation; hard VWAP+HTF; chase reject",
            f"L2: entry_mode={cfg.entry_mode} window {t_entry.strftime('%H:%M')}–"
            f"{t_end.strftime('%H:%M')} ET",
            f"L3: bracket {cfg.bracket_name} TP +{cfg.take_profit_pct:.0%} / "
            f"SL −{cfg.stop_loss_pct:.0%}; time_exit {cfg.time_exit_et.strftime('%H:%M')}; "
            f"trail={'on' if cfg.use_trail else 'off'}",
            f"L4: max_gap {cfg.max_gap_pct}% min_rvol {cfg.min_rvol}x; "
            f"max_entries {cfg.max_entries_per_day}; 2nd needs 4/4={cfg.require_quality_4of4_for_second}",
            f"Drop-fast: dd-high≤{cfg.max_drop_from_high_pct}% min vs-open {cfg.min_change_vs_open_pct}%",
        ],
    )
    if not top10:
        brief.errors.append(
            "No winner list found. Pass --symbols or ensure researcher sync books exist."
        )
        return brief

    # Load frames for re-rank
    frames: Dict[str, Any] = {}
    if live:
        for sym in top10[: max(cfg.list_size, 10)]:
            try:
                try:
                    frames[sym] = fetch_qqq_1m(sym, period="5d", source=data_source)
                except Exception:
                    frames[sym] = fetch_htf_bars(
                        sym, period="5d", interval="5m", source=data_source
                    )
            except Exception as exc:  # noqa: BLE001
                brief.errors.append(f"{sym}: {exc}")

    if not frames:
        for i, sym in enumerate(top10[: cfg.monitor_top_n], 1):
            brief.monitored.append(
                TopWinnerSignal(
                    symbol=sym,
                    rank=i,
                    decision="NO_DATA",
                    reasons=["no bars loaded"],
                    take_profit_pct=cfg.take_profit_pct,
                    stop_loss_pct=cfg.stop_loss_pct,
                )
            )
        return brief

    days = sorted(set().union(*[_session_days(df) for df in frames.values()]))
    d = days[-1]
    ranked = rank_universe_for_day(frames, d, cfg=cfg)
    brief.top10 = [s for s, _, _, _ in ranked[: cfg.list_size]] or brief.top10
    selected = select_entries_for_day(ranked, cfg=cfg)

    # Also show top monitor candidates that failed
    show = selected[:]
    if len(show) < cfg.monitor_top_n:
        for s, sc, g, e in ranked:
            if any(x[1] == s for x in show):
                continue
            show.append((len(show) + 1, s, sc, g, e))
            if len(show) >= cfg.monitor_top_n:
                break

    now_t = now.timetz().replace(tzinfo=None) if now.tzinfo else now.time()
    for rank, sym, sc, g, e in show:
        sig = TopWinnerSignal(
            symbol=sym,
            rank=rank,
            decision="SKIP",
            drop_eval=e.drop,
            ta_eval=e.ta,
            contracts=cfg.contracts,
            take_profit_pct=cfg.take_profit_pct,
            stop_loss_pct=cfg.stop_loss_pct,
            continuation_score=sc,
        )
        if e.ta and e.ta.notes:
            sig.reasons.extend(e.ta.notes)
        sig.reasons.append(
            f"score={sc:.2f} gap={g:.2f}% rvol={e.rvol:.2f}x quality="
            f"{e.ta.quality_score if e.ta else 0}/4"
        )
        if not e.passed:
            sig.decision = "SKIP"
            sig.reasons.extend(e.reasons)
            brief.monitored.append(sig)
            continue

        day_df = _day_slice(frames[sym], d)
        if now_t < t_entry:
            sig.decision = "WATCH"
            sig.reasons.append(f"eligible — wait for {t_entry.strftime('%H:%M')} ET window")
        else:
            fill = find_pullback_entry(day_df, cfg=cfg, full_df=frames[sym], day=d)
            if fill is None and (cfg.entry_mode or "").lower() == "pullback":
                if now_t <= entry_window_end_et(cfg):
                    sig.decision = "WAIT_PULLBACK"
                    sig.reasons.append("passed gates — waiting pullback to VWAP/EMA9")
                else:
                    sig.decision = "SKIP"
                    sig.reasons.append("no pullback fill in entry window")
            else:
                sig.decision = "ENTER"
                tag = fill[2] if fill else "clock"
                px = fill[1] if fill else 0.0
                sig.reasons.append(
                    f"ENTER {cfg.contracts} CALL via {tag} @ {px:.2f}; "
                    f"TP +{cfg.take_profit_pct:.0%} SL −{cfg.stop_loss_pct:.0%} "
                    f"time {cfg.time_exit_et.strftime('%H:%M')}"
                )
        brief.monitored.append(sig)
    return brief


def format_top_winners_brief(brief: TopWinnersBrief) -> str:
    lines = [
        "# Top Winners Playbook L1–L4 (0DTE CALL)",
        "",
        f"- **As of:** {brief.asof}",
        f"- **List source:** {brief.source}",
        f"- **Entry window:** {brief.entry_time_et}",
        "",
        "## Ranked (decision-time continuation)",
    ]
    if brief.top10:
        for i, s in enumerate(brief.top10, 1):
            mark = " ← candidate" if i <= 2 else ""
            lines.append(f"{i}. **{s}**{mark}")
    else:
        lines.append("_empty_")
    lines.extend(["", "## Decisions"])
    if not brief.monitored:
        lines.append("_none_")
    for sig in brief.monitored:
        lines.append(f"### #{sig.rank} {sig.symbol} — **{sig.decision}** (score {sig.continuation_score:.2f})")
        lines.append(
            f"- Side {sig.side} × {sig.contracts} | TP +{sig.take_profit_pct:.0%} / "
            f"SL −{sig.stop_loss_pct:.0%}"
        )
        for r in sig.reasons:
            lines.append(f"- {r}")
        if sig.drop_eval:
            de = sig.drop_eval
            lines.append(
                f"- Snapshot: open={de.open_px:.2f} high={de.high_px:.2f} "
                f"last={de.last_px:.2f} | vs open {de.change_vs_open_pct:+.2f}% | "
                f"dd-high {de.drop_from_high_pct:.2f}%"
            )
        if sig.ta_eval:
            ta = sig.ta_eval
            lines.append(
                f"- TA: RSI={ta.rsi:.1f} quality={ta.quality_score}/4 "
                f"VWAP={'above' if ta.above_vwap else 'below'} "
                f"EMA={'bull' if ta.ema_stack_bull else 'no'} "
                f"HTF={'bull' if ta.htf_bull else 'no'}"
            )
    if brief.notes:
        lines.extend(["", "## Rules (L1–L4)"])
        for n in brief.notes:
            lines.append(f"- {n}")
    if brief.errors:
        lines.extend(["", "## Errors"])
        for e in brief.errors:
            lines.append(f"- {e}")
    lines.append("")
    lines.append("_Paper rules only — not auto-execution._")
    return "\n".join(lines) + "\n"


# ── Backtest ──────────────────────────────────────────────────────────────


def _period_days(period: str) -> int:
    p = (period or "").strip().lower()
    if p.endswith("d") and p[:-1].isdigit():
        return int(p[:-1])
    if p in ("1mo", "1m", "mo", "month"):
        return 30
    if p.endswith("mo") and p[:-2].isdigit():
        return int(p[:-2]) * 30
    return 7


def _fetch_bars_for_backtest(
    symbol: str,
    period: str,
    *,
    data_source: str,
    bar_interval: str,
):
    interval = (bar_interval or "1m").strip().lower()
    if interval == "1m" and _period_days(period) <= 8:
        try:
            return fetch_qqq_1m(symbol, period=period, source=data_source)
        except Exception:
            interval = "5m"
    if interval == "1m":
        interval = "5m"
    yf_period = period
    if period.strip().lower() in ("1mo", "1m", "mo", "month"):
        yf_period = "1mo"
    return fetch_htf_bars(symbol, period=yf_period, interval=interval, source=data_source)


def run_top_winners_backtest(
    *,
    period: str = "10d",
    cfg: TopWinnersConfig | None = None,
    symbols: Sequence[str] | None = None,
    data_source: str = "auto",
    universe: Sequence[str] | None = None,
    bar_interval: str | None = None,
) -> OdteBacktestResult:
    cfg = cfg or TopWinnersConfig()
    delta = float(cfg.premium_delta)
    entry_prem = float(cfg.entry_prem)
    contracts = int(cfg.contracts)
    days_req = _period_days(period)
    interval = bar_interval or ("1m" if days_req <= 8 else "5m")

    if symbols:
        pool = [s.upper().strip() for s in symbols if str(s).strip()]
        rank_mode = "fixed_universe_l1_rerank"
    else:
        pool = [s.upper().strip() for s in (universe or []) if str(s).strip()]
        if not pool:
            pool = list(DEFAULT_FIXED_UNIVERSE)
            rank_mode = "default_universe_l1_rerank"
        else:
            rank_mode = "universe_l1_rerank"

    frames: Dict[str, Any] = {}
    load_errors: List[str] = []
    for sym in pool:
        try:
            frames[sym] = _fetch_bars_for_backtest(
                sym, period, data_source=data_source, bar_interval=interval
            )
        except Exception as exc:  # noqa: BLE001
            load_errors.append(f"{sym}: {exc}")

    if not frames:
        return OdteBacktestResult(
            symbol="TOP_WINNERS",
            days=0,
            trade_count=0,
            winners=0,
            losers=0,
            win_rate=0.0,
            total_pnl=0.0,
            expectancy=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            avg_pnl_pct=0.0,
            assumptions=[f"No data loaded for pool {pool}"],
            metadata={"errors": load_errors, "rank_mode": rank_mode},
        )

    all_days: set[date] = set()
    for df in frames.values():
        all_days.update(_session_days(df))
    days = sorted(all_days)

    trades: List[OdteTrade] = []
    equity = 0.0
    curve = [0.0]
    skip_log: Dict[str, int] = defaultdict(int)

    for d in days:
        ranked = rank_universe_for_day(frames, d, cfg=cfg)
        for _, _, _, e in ranked:
            if not e.passed:
                for r in e.reasons[:1]:
                    key = r.split("(")[0].split(":")[0][:40]
                    skip_log[key] += 1
        selected = select_entries_for_day(ranked, cfg=cfg)

        for rank, sym, sc, gap, e in selected:
            df = frames[sym]
            day_df = _day_slice(df, d)
            fill = find_pullback_entry(day_df, cfg=cfg, full_df=df, day=d)
            if fill is None:
                skip_log["no_pullback_fill"] += 1
                continue
            entry_ts, entry_spot, tag = fill
            rth = day_df.between_time(cfg.rth_open, cfg.rth_close)
            # bars strictly after entry
            rest = rth.loc[rth.index > entry_ts]
            if rest.empty:
                skip_log["no_bars_after_entry"] += 1
                continue
            highs = rest["High"].astype(float).tolist()
            lows = rest["Low"].astype(float).tolist()
            closes = rest["Close"].astype(float).tolist()
            times = list(rest.index)
            ep, exit_spot, reason, exit_tm = simulate_premium_path_l3(
                "CALL",
                entry_spot,
                highs,
                lows,
                closes,
                times,
                entry_prem=entry_prem,
                tp_pct=cfg.take_profit_pct,
                sl_pct=cfg.stop_loss_pct,
                delta=delta,
                time_exit_et=cfg.time_exit_et,
                use_trail=cfg.use_trail,
                trail_activate_pct=cfg.trail_activate_pct,
                trail_giveback_pct=cfg.trail_giveback_pct,
            )
            pnl_pct = (ep - entry_prem) / entry_prem
            pnl_dollars = (ep - entry_prem) * 100 * contracts
            equity += pnl_dollars
            curve.append(equity)
            exit_time_s = (
                exit_tm.isoformat() if hasattr(exit_tm, "isoformat") else str(exit_tm)
            )
            rsi_e = e.ta.rsi if e.ta else 50.0
            trades.append(
                OdteTrade(
                    day=d.isoformat(),
                    side="CALL",
                    level_name=f"L1L4_r{rank}_{tag}",
                    level=entry_spot,
                    entry_time=(
                        entry_ts.isoformat()
                        if hasattr(entry_ts, "isoformat")
                        else str(entry_ts)
                    ),
                    exit_time=exit_time_s,
                    entry_spot=entry_spot,
                    exit_spot=float(exit_spot),
                    entry_prem=entry_prem,
                    exit_prem=float(ep),
                    exit_reason=reason,
                    pnl_pct=round(pnl_pct, 4),
                    pnl_dollars=round(pnl_dollars, 2),
                    rsi_at_entry=float(rsi_e),
                )
            )

    winners = [t for t in trades if t.pnl_dollars > 0]
    losers = [t for t in trades if t.pnl_dollars <= 0]
    total = sum(t.pnl_dollars for t in trades)
    gw = sum(t.pnl_dollars for t in winners)
    gl = abs(sum(t.pnl_dollars for t in losers))
    pf = gw / gl if gl else float(gw > 0)
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
    by_side: Dict[str, Dict[str, float]] = {}
    st = [t for t in trades if t.side == "CALL"]
    if st:
        w = sum(1 for t in st if t.pnl_dollars > 0)
        by_side["CALL"] = {
            "count": float(len(st)),
            "win_rate": w / len(st),
            "total_pnl": sum(t.pnl_dollars for t in st),
        }
    by_exit: Dict[str, int] = defaultdict(int)
    for t in trades:
        by_exit[t.exit_reason] += 1

    return OdteBacktestResult(
        symbol="TOP_WINNERS",
        days=len(days),
        trade_count=len(trades),
        winners=len(winners),
        losers=len(losers),
        win_rate=round(len(winners) / len(trades), 4) if trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(trades), 2) if trades else 0.0,
        profit_factor=round(pf, 2),
        max_drawdown=round(max_dd, 2),
        avg_pnl_pct=round(float(np.mean([t.pnl_pct for t in trades])), 4) if trades else 0.0,
        by_side=by_side,
        by_exit=dict(by_exit),
        trades=trades,
        assumptions=[
            "Style: top_winners L1–L4 (re-rank, pullback, trail/time exit, universe quality)",
            f"Rank mode: {rank_mode}; pool={pool}",
            f"Entry mode={cfg.entry_mode}; decision→window "
            f"{entry_time_et(cfg).strftime('%H:%M')}–{entry_window_end_et(cfg).strftime('%H:%M')} ET",
            f"Bracket {cfg.bracket_name}: TP +{cfg.take_profit_pct:.0%} / "
            f"SL −{cfg.stop_loss_pct:.0%}; time_exit {cfg.time_exit_et.strftime('%H:%M')}; "
            f"trail={'on' if cfg.use_trail else 'off'} "
            f"(act +{cfg.trail_activate_pct:.0%} giveback {cfg.trail_giveback_pct:.0%})",
            f"L4 max_gap={cfg.max_gap_pct}% min_rvol={cfg.min_rvol}x max_entries={cfg.max_entries_per_day}",
            f"Synthetic premium ${entry_prem:.2f}; delta={delta}; contracts={contracts}",
            f"Period={period}; bar_interval={interval}; source={data_source}",
            "Not full options IV/chain model",
        ]
        + ([f"Load warnings: {'; '.join(load_errors[:5])}"] if load_errors else []),
        metadata={
            "period": period,
            "style": "top_winners_l1_l4",
            "rank_mode": rank_mode,
            "pool": pool,
            "bar_interval": interval,
            "bracket_name": cfg.bracket_name,
            "entry_mode": cfg.entry_mode,
            "take_profit_pct": cfg.take_profit_pct,
            "stop_loss_pct": cfg.stop_loss_pct,
            "contracts": contracts,
            "skip_log": dict(skip_log),
            "errors": load_errors,
        },
    )


def render_top_winners_backtest(result: OdteBacktestResult) -> str:
    from trading_agent.odte.backtest import render_odte_backtest

    text = render_odte_backtest(result)
    lines = text.splitlines()
    if lines:
        lines[0] = "# Top Winners L1–L4 0DTE CALL Backtest"
    # Append skip diagnostics if present
    skip = (result.metadata or {}).get("skip_log") or {}
    if skip:
        lines.append("")
        lines.append("## Skip reasons (top)")
        for k, v in sorted(skip.items(), key=lambda x: -x[1])[:12]:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"


def run_bracket_ab_backtest(
    *,
    period: str = "1mo",
    symbols: Sequence[str] | None = None,
    data_source: str = "yfinance",
    base: TopWinnersConfig | None = None,
) -> str:
    """L3 A/B: compare legacy30_25, wr20_15, bal25_20 on same rules."""
    base = base or TopWinnersConfig()
    blocks = ["# Top Winners L3 Bracket A/B", ""]
    summary_rows = []
    for name in ("legacy30_25", "wr20_15", "bal25_20"):
        cfg = apply_bracket_preset(base, name)
        result = run_top_winners_backtest(
            period=period, cfg=cfg, symbols=symbols, data_source=data_source
        )
        summary_rows.append(
            (
                name,
                result.trade_count,
                result.win_rate,
                result.total_pnl,
                result.expectancy,
                result.by_exit,
            )
        )
        blocks.append(render_top_winners_backtest(result))
        blocks.append("---")
    blocks.append("## A/B summary")
    blocks.append("| Bracket | Trades | WR | P/L | Expectancy | Exits |")
    blocks.append("|---------|--------|----|-----|------------|-------|")
    for name, n, wr, pnl, exp, exits in summary_rows:
        ex = ", ".join(f"{k}:{v}" for k, v in sorted(exits.items()))
        blocks.append(
            f"| {name} | {n} | {wr:.1%} | ${pnl:+.2f} | ${exp:+.2f} | {ex} |"
        )
    blocks.append("")
    return "\n".join(blocks)
