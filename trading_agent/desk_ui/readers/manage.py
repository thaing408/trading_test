"""Multi-path manage log reader (UTC filename vs PT trading date)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from trading_agent.desk_ui.models import ManageView
from trading_agent.intraday.manage_log import manage_log_path, summarize_manage_log
from trading_agent.session.schedule import DESK_CLOSE_PT, INTELLIGENCE_TIME, PT, resolve_trading_date


def manage_candidate_dates(
    trading_date: date,
    *,
    now: datetime | None = None,
) -> list[date]:
    """Dedupe candidate calendar dates for manage_*.jsonl files."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    utc_today = current.astimezone(timezone.utc).date()
    # trading_date "in UTC sense" ≈ PT midnight of trading_date as UTC date
    pt_midnight = datetime.combine(trading_date, INTELLIGENCE_TIME, tzinfo=PT)
    td_utc = pt_midnight.astimezone(timezone.utc).date()
    out: list[date] = []
    for d in (trading_date, td_utc, utc_today, utc_today - timedelta(days=1)):
        if d not in out:
            out.append(d)
    return out


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def read_manage_events(
    paths: list[Path],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                import json

                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                row = dict(row)
                row["_path"] = str(path)
                events.append(row)
    events.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return events


def tail_manage_events(paths: list[Path], limit: int = 40) -> list[dict[str, Any]]:
    return read_manage_events(paths)[: max(0, limit)]


def load_manage_view(
    trading_date: date,
    *,
    now: datetime | None = None,
    in_intraday_window: bool = False,
    log_dir: Path | None = None,
    limit: int = 40,
) -> ManageView:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    candidates = manage_candidate_dates(trading_date, now=current)
    paths: list[Path] = []
    for d in candidates:
        if log_dir is not None:
            p = Path(log_dir) / f"manage_{d.isoformat()}.jsonl"
        else:
            p = manage_log_path(d)
        if p not in paths:
            paths.append(p)

    existing = [p for p in paths if p.is_file()]
    paths_read = [str(p) for p in existing]

    # Merge summaries
    total_events = 0
    intervals: dict[str, int] = {}
    exit_actions: dict[str, int] = {}
    for p in existing:
        if log_dir is not None:
            summary = summarize_manage_log(path=p)
        else:
            summary = summarize_manage_log(path=p)
        total_events += int(summary.get("events") or 0)
        for k, v in (summary.get("intervals") or {}).items():
            intervals[k] = intervals.get(k, 0) + int(v)
        for k, v in (summary.get("exit_actions") or {}).items():
            exit_actions[k] = exit_actions.get(k, 0) + int(v)

    merged_summary: dict[str, Any] = {
        "events": total_events,
        "intervals": intervals,
        "exit_actions": exit_actions,
        "paths": paths_read,
    }

    recent = tail_manage_events(existing, limit=limit)
    latest_cycle = None
    for row in recent:
        if row.get("event") == "manage_cycle":
            latest_cycle = row
            break

    quiet = False
    quiet_reason = ""
    if in_intraday_window:
        last_ts = None
        for row in recent:
            last_ts = _parse_ts(row.get("ts"))
            if last_ts:
                break
        wait_minutes = 15.0
        for row in recent:
            if row.get("event") == "interval_decision":
                pl = row.get("payload") or {}
                try:
                    wait_minutes = float(pl.get("wait_minutes") or 15)
                except (TypeError, ValueError):
                    wait_minutes = 15.0
                break
            if row.get("event") == "manage_cycle":
                pl = row.get("payload") or {}
                try:
                    wait_minutes = float(pl.get("wait_minutes") or 15)
                except (TypeError, ValueError):
                    wait_minutes = 15.0
                break
        threshold = timedelta(minutes=2.0 * wait_minutes)
        if last_ts is None:
            quiet = True
            quiet_reason = "intraday window but no manage events"
        elif current - last_ts.astimezone(timezone.utc) > threshold:
            quiet = True
            age_m = (current - last_ts.astimezone(timezone.utc)).total_seconds() / 60.0
            quiet_reason = (
                f"last manage event {age_m:.0f}m ago "
                f"(threshold {2 * wait_minutes:.0f}m = 2×{wait_minutes:.0f}m)"
            )

    return ManageView(
        paths_read=paths_read,
        summary=merged_summary,
        latest_cycle=latest_cycle,
        recent=recent,
        quiet=quiet,
        quiet_reason=quiet_reason,
    )
