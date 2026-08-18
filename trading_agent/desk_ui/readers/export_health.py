"""Export path mtimes and stale/wrong-day health."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.models import ExportHealth, ExportPathHealth
from trading_agent.desk_ui.paths import session_dir_for, sync_dir
from trading_agent.session.schedule import DeskSchedule, compute_desk_schedule


def known_export_targets(
    trading_date: date,
    *,
    state: Path | None = None,
) -> list[Path]:
    if state is not None:
        # Fixture / isolated state root — do not probe the operator's real home paths
        root = Path(state)
        sync = root / "sync"
        return [
            sync / "auto_trade_book.json",
            root / "sessions" / trading_date.isoformat() / "auto_trade_book.json",
            sync / "archive" / f"auto_trade_book_{trading_date.isoformat()}.json",
            sync / "scanned_list.json",
            sync / "auto_trade_scan_symbols.json",
        ]
    sync = sync_dir()
    return [
        sync / "auto_trade_book.json",
        session_dir_for(trading_date) / "auto_trade_book.json",
        Path.home() / ".grok" / "state" / "auto_trade_book.json",
        sync / "archive" / f"auto_trade_book_{trading_date.isoformat()}.json",
        sync / "scanned_list.json",
        sync / "auto_trade_scan_symbols.json",
    ]


def _path_health(path: Path, now: datetime) -> ExportPathHealth:
    exists = path.is_file()
    mtime_iso = None
    age = None
    if exists:
        try:
            mtime = path.stat().st_mtime
            mt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            mtime_iso = mt.isoformat()
            age = (now - mt).total_seconds()
        except OSError:
            pass
    return ExportPathHealth(
        path=str(path),
        exists=exists,
        mtime_iso=mtime_iso,
        age_seconds=age,
    )


def compute_export_health(
    trading_date: date,
    book: dict[str, Any],
    *,
    now: datetime | None = None,
    schedule: DeskSchedule | None = None,
    state: Path | None = None,
    plan_missing: bool = False,
) -> ExportHealth:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    targets = [_path_health(p, current) for p in known_export_targets(trading_date, state=state)]
    ages = [t.age_seconds for t in targets if t.age_seconds is not None]
    last_age = min(ages) if ages else None

    book_td = str(book.get("trading_date") or "").strip()
    resolved = trading_date.isoformat()
    has_book = bool(book)
    trading_date_match = (not book_td) or (book_td == resolved)
    wrong_day = bool(book_td) and book_td != resolved

    stay_in_cash = bool(book.get("stay_in_cash")) if has_book else False
    stale_suppressed_cash = bool(stay_in_cash and trading_date_match and has_book)

    sched = schedule or compute_desk_schedule(trading_date)
    grace = timedelta(minutes=2)
    # Book/scanned mtimes
    write_mtimes: list[datetime] = []
    for t in targets:
        if t.exists and t.mtime_iso and (
            "auto_trade_book" in t.path or "scanned" in t.path or "scan_symbols" in t.path
        ):
            try:
                write_mtimes.append(datetime.fromisoformat(t.mtime_iso))
            except ValueError:
                pass

    def _any_write_since(slot: datetime) -> bool:
        threshold = slot - grace  # allow write slightly before scheduled_at? design: mtime >= scheduled + grace means after slot
        # Design: no book/scanned mtime >= scheduled_at (+ 2m grace) → missed
        # so write must be >= scheduled_at - 0 with grace after: mtime >= scheduled_at - grace? 
        # "mtime ≥ that scheduled_at (plus 2m grace)" → mtime >= scheduled_at - grace? 
        # Actually: mtime must be at least scheduled_at, grace means scheduled_at + 2m before flagging
        # "no book/scanned mtime ≥ that scheduled_at (plus 2m grace)"
        # means: if now > scheduled_at + 2m and no mtime >= scheduled_at → stale
        cutoff = slot  # mtime must be >= slot
        for mt in write_mtimes:
            if mt >= cutoff:
                return True
        return False

    stale_missed_slot = False
    missed_label = ""
    slot_kinds = {"research", "cio_approval"}
    slot_times: list[tuple[str, datetime]] = []
    for phase in sched.phases:
        if phase.kind.value in slot_kinds:
            slot_times.append((phase.kind.value, phase.scheduled_at))
    for i, dt in enumerate(sched.discovery_refreshes or ()):
        slot_times.append((f"discovery_{i}", dt))

    for label, slot in slot_times:
        # Convert slot to aware UTC for comparison with mtimes
        slot_utc = slot.astimezone(timezone.utc) if slot.tzinfo else slot.replace(tzinfo=timezone.utc)
        if current < slot_utc + grace:
            continue
        if not _any_write_since(slot_utc):
            stale_missed_slot = True
            missed_label = label
            break

    # Suppress amber spam when cash intentional same day — still allow missed-slot
    # only if a *later* discovery produced no write is already handled by loop.
    # Design: "Do not spam amber solely for age; still show missed-slot only if..."
    # We keep stale_missed_slot but UI may suppress; still report flag.
    if stale_suppressed_cash and stale_missed_slot:
        # Keep flag true but note suppression of age-only; missed slot still shown
        pass

    notes: list[str] = []
    if plan_missing:
        notes.append("plan context missing — rejections may be incomplete")
    if wrong_day:
        notes.append(f"book trading_date={book_td} ≠ resolved {resolved}")
    if stale_missed_slot:
        notes.append(f"no refresh since slot {missed_label}")
    if not has_book:
        notes.append("book missing")

    return ExportHealth(
        targets=targets,
        trading_date_match=trading_date_match if has_book else False,
        wrong_day=wrong_day,
        last_write_age_seconds=last_age,
        stale_missed_slot=stale_missed_slot,
        stale_suppressed_cash=stale_suppressed_cash,
        notes=notes,
    )
