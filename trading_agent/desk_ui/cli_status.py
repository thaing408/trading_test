"""CLI ``desk-status`` — text/JSON snapshot without FastAPI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.snapshot import DeskSnapshot, assemble_snapshot
from trading_agent.session.schedule import PT


def format_desk_status(snap: DeskSnapshot) -> str:
    """Human-readable multi-section status report."""
    lines: list[str] = []
    cash = "CASH" if snap.stay_in_cash else "ARMED"
    phase = snap.phase
    next_phase = ""
    if phase.next_phase_kind and phase.next_phase_at:
        next_phase = f" → next {phase.next_phase_kind} @ {phase.next_phase_at.strftime('%H:%M %Z')}"
    disc = ""
    if phase.next_discovery_at:
        disc = f" | next discovery {phase.next_discovery_at.strftime('%H:%M %Z')}"
    if phase.discovery_slot_label:
        disc += f" | slot {phase.discovery_slot_label}"

    lines.append(f"# Desk status — {snap.trading_date}")
    lines.append(
        f"host={snap.host}  role={snap.host_role}  platform={snap.platform}  "
        f"book_role={snap.book_role or '—'}"
    )
    lines.append(
        f"phase={phase.phase_kind} ({phase.phase_label}){next_phase}{disc}"
    )
    lines.append(
        f"status=**{cash}**  entries={len(snap.entries)}  "
        f"env={snap.environment_score if snap.environment_score is not None else '—'}  "
        f"regime={snap.regime or '—'}"
    )
    if snap.cash_reason:
        lines.append(f"cash_reason: {snap.cash_reason}")
    if snap.broker_boundary:
        lines.append(f"broker_boundary: {snap.broker_boundary}")
    lines.append("")

    # Market context table
    m = snap.market
    if m and m.rows:
        lines.append("## Market context")
        # column widths for plain text
        w = max((len(k) for k, _ in m.rows), default=8)
        w = min(max(w, 12), 22)
        lines.append(f"{'Field'.ljust(w)}  Detail")
        lines.append(f"{'-' * w}  {'-' * 40}")
        for field, detail in m.rows:
            # skip duplicate signal blob if we print list below
            if field == "Market signals" and m.signals:
                continue
            if field.startswith("Headline ") and m.highlights:
                continue
            detail_one = " ".join(str(detail).split())
            if len(detail_one) > 100:
                detail_one = detail_one[:97] + "..."
            lines.append(f"{field.ljust(w)}  {detail_one}")
        if m.overnight:
            lines.append("")
            lines.append("Overnight tape:")
            ow = max((len(k) for k in m.overnight), default=8)
            ow = min(max(ow, 10), 16)
            for label, val in m.overnight.items():
                lines.append(f"  {label.ljust(ow)}  {val}")
        if m.signals:
            lines.append("")
            lines.append("Signals:")
            for s in m.signals[:10]:
                lines.append(f"  • {s}")
        if m.highlights:
            lines.append("")
            lines.append("Headlines:")
            for h in m.highlights[:5]:
                lines.append(f"  • {h}")
        lines.append("")

    # Export health
    eh = snap.export_health
    age = eh.last_write_age_seconds
    age_s = f"{age / 60:.0f}m ago" if age is not None else "—"
    flags = []
    if eh.wrong_day:
        flags.append("WRONG_DAY")
    if eh.stale_missed_slot:
        flags.append("MISSED_SLOT")
    if eh.stale_suppressed_cash:
        flags.append("cash_suppress")
    lines.append(f"## Export health  last_write={age_s}  {' '.join(flags) or 'ok'}")
    for note in eh.notes:
        lines.append(f"  - {note}")
    for t in eh.targets:
        mark = "✓" if t.exists else "·"
        age_p = f" age={t.age_seconds / 60:.0f}m" if t.age_seconds is not None else ""
        lines.append(f"  {mark} {t.path}{age_p}")
    lines.append("")

    # Book / entries
    lines.append(f"## Book  stay_in_cash={snap.stay_in_cash}  entry_count={len(snap.entries)}")
    if snap.watchlist:
        lines.append(f"watchlist: {', '.join(snap.watchlist)}")
    if snap.play_symbols:
        lines.append(f"play: {', '.join(snap.play_symbols)}")
    if snap.entries:
        for e in snap.entries[:20]:
            if isinstance(e, dict):
                lines.append(
                    f"  ENTER {e.get('symbol')} {e.get('side')} "
                    f"grade={e.get('setup_grade')} entry={e.get('entry')}"
                )
    else:
        lines.append("  (no ENTER rows)")
    lines.append("")

    # Rejections
    lines.append(f"## Rejections  n={len(snap.rejections)}")
    for r in snap.rejections:
        gates = f" [{','.join(r.gates)}]" if r.gates else ""
        lines.append(f"  [{r.source}] {r.symbol}: {r.reason}{gates}")
    if not snap.rejections:
        lines.append("  (none)")
    lines.append("")

    # Manage
    mv = snap.manage
    quiet = " QUIET" if mv.quiet else ""
    lines.append(
        f"## Manage{quiet}  events={mv.summary.get('events', 0)}  "
        f"paths={len(mv.paths_read)}"
    )
    if mv.quiet_reason:
        lines.append(f"  quiet: {mv.quiet_reason}")
    for p in mv.paths_read:
        lines.append(f"  path: {p}")
    if mv.latest_cycle:
        pl = mv.latest_cycle.get("payload") or {}
        lines.append(
            f"  latest_cycle ts={mv.latest_cycle.get('ts')} "
            f"n_recommendations={pl.get('n_recommendations')} "
            f"wait={pl.get('wait_minutes')}"
        )
    for row in mv.recent[:8]:
        if row.get("event") == "manage_cycle":
            pl = row.get("payload") or {}
            lines.append(
                f"  cycle ts={row.get('ts')} n_rec={pl.get('n_recommendations')}"
            )
    if not mv.recent:
        lines.append("  (no manage events)")
    lines.append("")

    # Positions
    pv = snap.positions
    lines.append(f"## Positions  available={pv.available}")
    if pv.path:
        lines.append(f"  path: {pv.path}")
    if pv.empty_reason:
        lines.append(f"  {pv.empty_reason}")
    for pos in pv.positions[:15]:
        lines.append(
            f"  {pos.get('symbol')} qty={pos.get('quantity')} "
            f"entry={pos.get('entry_price')}"
        )
    lines.append("")

    # Execute (Mac) — cash / consumer / ready orders
    ac = snap.account_cash or {}
    ch = snap.consumer_health or {}
    ro = snap.ready_orders or {}
    counts = ro.get("counts") or {}
    tradable = ac.get("tradable_after_reserve")
    tradable_s = f"${tradable:.0f}" if isinstance(tradable, (int, float)) else "—"
    cash_av = ac.get("cash_available")
    cash_av_s = f"${cash_av:.2f}" if isinstance(cash_av, (int, float)) else "—"
    lines.append("## Execute (Mac)")
    lines.append(
        f"  cash available={cash_av_s}  tradable_after_reserve={tradable_s}  "
        f"source={ac.get('source') or '—'}"
    )
    if ac.get("error"):
        lines.append(f"  cash_error: {ac.get('error')}")
    alive = "UP" if ch.get("alive") else "DOWN"
    pids = ", ".join(str(p) for p in (ch.get("pids") or [])) or "—"
    lines.append(f"  consumer={alive}  pids={pids}")
    if ch.get("last_log_line"):
        lines.append(f"  last_log: {str(ch['last_log_line'])[:120]}")
    lines.append(
        f"  ready_orders submitted={counts.get('submitted', 0)}  "
        f"skipped={counts.get('skipped', 0)}  failed={counts.get('failed', 0)}  "
        f"exists={ro.get('exists')}"
    )
    for o in (ro.get("orders") or [])[:8]:
        if isinstance(o, dict):
            skip = o.get("skip_reason") or ""
            lines.append(
                f"    {o.get('symbol')} {o.get('status')} "
                f"exp={o.get('expiration') or '—'} {skip}".rstrip()
            )
    lines.append("")

    # OMS
    ks = snap.kill_switch
    oms_sum = snap.oms_summary or {}
    open_n = oms_sum.get("open_lots", len(snap.oms_lots))
    open_risk = oms_sum.get("open_risk", 0)
    day_pnl = oms_sum.get("day_realized_pnl", 0)
    lines.append(
        f"## OMS  open_lots={open_n}  open_risk=${float(open_risk or 0):.0f}  "
        f"day_pnl=${float(day_pnl or 0):.0f}  "
        f"kill_active={ks.get('active')}  path={ks.get('path')}"
    )
    for lot in snap.oms_lots[:10]:
        trail = lot.get("trail_stop")
        trail_s = f" trail={trail}" if trail else ""
        lines.append(
            f"  lot {lot.get('lot_id')} {lot.get('symbol')} "
            f"status={lot.get('status')}{trail_s}"
        )
    lines.append("")

    # Firm sleeve
    firm = snap.firm or {}
    if firm.get("enabled_artifacts"):
        ev = firm.get("eval") or {}
        lines.append(
            f"## Firm  symbols={len(firm.get('symbols') or [])}  "
            f"path={firm.get('path')}"
        )
        if ev:
            lines.append(
                f"  eval buy={ev.get('n_buy', 0)} hold={ev.get('n_hold', 0)} "
                f"veto={ev.get('n_veto', 0)} agree={ev.get('agreement_rate', '—')}"
            )
        for row in (firm.get("cards") or [])[:10]:
            if not isinstance(row, dict):
                continue
            t = row.get("trader") or {}
            m = row.get("manager") or {}
            action = t.get("action") or (row.get("card") or {}).get("trader_action") or "—"
            decision = m.get("decision") or (row.get("card") or {}).get("manager_decision") or "—"
            lines.append(f"  {row.get('symbol')} trader={action} manager={decision}")
        lines.append("")
    else:
        lines.append(
            f"## Firm  (no artifacts)  path={firm.get('path') or '—'}"
        )
        lines.append("")

    if snap.process_cards:
        lines.append(f"## Process cards  n={len(snap.process_cards)}")
        for c in snap.process_cards[:5]:
            sym = c.get("symbol") or c.get("ticker") or "?"
            lines.append(f"  {sym}: {str(c.get('thesis') or c.get('setup') or '')[:80]}")
        lines.append("")

    if snap.panel_errors:
        lines.append("## Panel errors")
        for k, v in snap.panel_errors.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    lines.append(f"generated_at={snap.generated_at}  parse_failures={snap.parse_failures}")
    return "\n".join(lines) + "\n"


def run_desk_status(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="desk-status",
        description="Print local auto-trade desk snapshot (no broker, no FastAPI).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full DeskSnapshot as JSON",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override trading date (default: resolve_trading_date PT)",
    )
    parser.add_argument(
        "--state",
        metavar="DIR",
        help="Fixture/state root (instead of ~/.trading_agent)",
    )
    parser.add_argument(
        "--positions",
        metavar="FILE",
        help="Positions JSON path (never refreshes brokerage)",
    )
    args = parser.parse_args(argv)

    td = date.fromisoformat(args.date) if args.date else None
    state = Path(args.state) if args.state else None
    snap = assemble_snapshot(
        trading_date=td,
        state=state,
        positions_path=args.positions,
    )
    if args.json:
        print(json.dumps(snap.to_dict(), indent=2, default=str))
    else:
        print(format_desk_status(snap))
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_desk_status(argv)


if __name__ == "__main__":
    sys.exit(main())
