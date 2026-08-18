"""Tests for desk_ui readers, phase status, snapshot, host role."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from trading_agent.desk_ui.config import detect_host_role, kill_write_allowed
from trading_agent.desk_ui.phase import current_phase_status
from trading_agent.desk_ui.readers.session_plan import heuristic_gate_tags, merge_rejections
from trading_agent.desk_ui.snapshot import assemble_snapshot
from trading_agent.session.schedule import PT, compute_desk_schedule

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "desk_ui"
TD = date(2026, 8, 13)


def test_parse_bias_blob_into_table_fields():
    from trading_agent.desk_ui.market_context import build_market_context, parse_bias_blob

    raw = (
        "Bullish — risk-on pre-market conditions; active catalyst: [INTC] "
        "Cerebras Plummets 13% After Earnings. But Intel & AMD Barrel Ahead "
        "with Strong Gains. (earnings) (ES futures +0.69%; Asia firm (avg +0.81%); "
        "Bond bid (TLT +0.55%) — flight-to-quality; VIX subdued at 14.7) "
        "[data: sentiment: live yfinance, calendar: omitted (no live feed), catalysts: yfinance]"
    )
    p = parse_bias_blob(raw)
    assert p["bias_short"].lower().startswith("bullish")
    assert "risk-on" in p["posture"].lower()
    assert p["catalyst_symbol"] == "INTC"
    assert "Intel" in p["catalyst_headline"] or "Cerebras" in p["catalyst_headline"]
    assert p["catalyst_kind"].lower() == "earnings"
    assert p["data_sources"]
    assert any("VIX" in s or "ES" in s or "Asia" in s for s in p["signals"])

    ctx = build_market_context(
        environment_score=61.5,
        regime=raw,
        plan={"market_regime": "bullish", "overall_market_bias": raw},
        intelligence={
            "outlook": "Bullish",
            "market_posture": "Risk-on bias with standard overnight gap discipline",
            "overnight_summary": {
                "futures": "ES +0.69%",
                "asia": "avg +0.81%",
                "vix": "VIX 14.7",
            },
            "market_signals": ["VIX subdued at 14.7", "Asia firm (avg +0.81%)"],
            "news_highlights": [
                "[INTC] Cerebras Plummets 13% After Earnings. But Intel & AMD Barrel Ahead"
            ],
            "catalyst_symbols": ["INTC", "AMD"],
        },
    )
    assert ctx.bias_short == "Bullish"
    assert ctx.environment_score == 61.5
    assert ctx.header_label.startswith("env 61.5")
    assert "Bullish" in ctx.header_label
    assert len(ctx.header_label) < 120  # not the whole blob
    labels = [r[0] for r in ctx.rows]
    assert "Environment score" in labels
    assert "Bias / outlook" in labels
    assert "ES / futures" in ctx.overnight
    assert "VIX subdued at 14.7" in ctx.signals


def test_ui_trading_date_after_close_same_calendar_day():
    """After 13:00 PT, orchestrator rolls to next session; UI keeps today."""
    from trading_agent.desk_ui.readers.schedule_status import resolve_ui_trading_date
    from trading_agent.session.schedule import resolve_trading_date

    now = datetime(2026, 8, 13, 21, 25, tzinfo=PT)
    assert resolve_trading_date(now=now) == date(2026, 8, 14)
    assert resolve_ui_trading_date(now=now) == date(2026, 8, 13)


def test_ui_trading_date_during_rth_matches_orchestrator():
    from trading_agent.desk_ui.readers.schedule_status import resolve_ui_trading_date
    from trading_agent.session.schedule import resolve_trading_date

    now = datetime(2026, 8, 13, 10, 0, tzinfo=PT)
    assert resolve_ui_trading_date(now=now) == resolve_trading_date(now=now) == date(
        2026, 8, 13
    )


def test_snapshot_after_close_no_wrong_day_for_todays_book():
    """Overnight review of today's cash book must not red-flag wrong day."""
    now = datetime(2026, 8, 13, 21, 25, tzinfo=PT)
    snap = assemble_snapshot(
        now=now,
        state=FIXTURE_ROOT,
        platform="darwin",
        env={},
    )
    assert snap.trading_date == "2026-08-13"
    assert snap.export_health.wrong_day is False
    assert snap.stay_in_cash is True


def test_phase_pre_session_0100_pt():
    now = datetime(2026, 8, 13, 1, 0, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "pre_session"
    assert st.next_phase_kind == "intelligence"
    assert st.next_phase_at is not None
    assert st.in_intraday_window is False


def test_phase_research_0530_pt():
    now = datetime(2026, 8, 13, 5, 30, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "research"
    assert st.next_phase_kind == "cio_approval"


def test_phase_intraday_0640_pt():
    now = datetime(2026, 8, 13, 6, 40, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "intraday"
    assert st.in_intraday_window is True
    assert st.next_phase_kind == "performance"


def test_phase_discovery_slot_0932_pt():
    now = datetime(2026, 8, 13, 9, 32, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "intraday"
    assert st.discovery_slot_label == "09:30 PT"
    assert st.next_discovery_at is not None  # 11:00


def test_phase_desk_closed_1305_pt():
    now = datetime(2026, 8, 13, 13, 5, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "intraday"
    assert st.in_intraday_window is False
    assert st.next_phase_kind == "performance"
    assert "desk closed" in st.phase_label.lower() or "awaiting" in st.phase_label.lower()


def test_phase_performance_1320_pt():
    now = datetime(2026, 8, 13, 13, 20, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    assert st.phase_kind == "performance"
    assert st.next_phase_kind == "cio_review"


def test_phase_post_evening_1600_pt():
    now = datetime(2026, 8, 13, 16, 0, tzinfo=PT)
    st = current_phase_status(now, trading_date=TD)
    # 16:00 PT is after evening_scan (15:00 PT / 18:00 ET)
    assert st.phase_kind == "post_evening"
    assert st.next_phase_kind is None


def test_host_role_win32_always_windows_research_even_with_live():
    role = detect_host_role(
        platform="win32",
        env={"TRADING_AGENT_AUTO_TRADE_LIVE": "1"},
    )
    assert role == "windows-research"


def test_host_role_forced_env():
    role = detect_host_role(
        platform="linux",
        env={"TRADING_AGENT_DESK_UI_ROLE": "mac-execute"},
    )
    assert role == "mac-execute"


def test_host_role_darwin_without_markers_unknown(tmp_path):
    # Isolate from this machine's real OMS / ready_orders
    empty_oms = tmp_path / "oms"
    empty_oms.mkdir()
    role = detect_host_role(
        platform="darwin",
        env={},
        oms_root=empty_oms,
        state_root=tmp_path,
    )
    assert role == "unknown"


def test_host_role_darwin_live_mac_execute(tmp_path):
    role = detect_host_role(
        platform="darwin",
        env={"TRADING_AGENT_AUTO_TRADE_LIVE": "1"},
        oms_root=tmp_path / "oms",
        state_root=tmp_path,
    )
    assert role == "mac-execute"


def test_kill_write_refused_on_win32():
    assert (
        kill_write_allowed(
            "mac-execute",
            platform="win32",
            env={"TRADING_AGENT_DESK_UI_ALLOW_KILL": "1"},
        )
        is False
    )


def test_heuristic_gate_tags():
    assert "adr" in heuristic_gate_tags("ADR% below 2.5 minimum")
    assert "rvol" in heuristic_gate_tags("Relative volume (RVOL) below 2.0")
    assert "strength_52w" in heuristic_gate_tags("52w strength too weak")


def test_merge_rejections_plan_and_book():
    plan = {
        "rejection_reasons": [
            {"symbol": "qqq", "reason": "ADR% low"},
            {"symbol": "QQQ", "reason": "ADR% low"},  # dedupe
        ]
    }
    book = {"rejected_incomplete": ["SPY:checklist", "QQQ:edge"]}
    rows = merge_rejections(plan, book)
    assert len(rows) == 3  # one plan + two book
    sources = {(r.source, r.symbol) for r in rows}
    assert ("plan", "QQQ") in sources
    assert ("book_incomplete", "SPY") in sources


def test_assemble_snapshot_fixture_cash_and_rejections():
    now = datetime(2026, 8, 13, 10, 0, tzinfo=PT)
    snap = assemble_snapshot(
        now=now,
        trading_date=TD,
        state=FIXTURE_ROOT,
        platform="win32",
        env={},
    )
    assert snap.trading_date == "2026-08-13"
    assert snap.stay_in_cash is True
    assert len(snap.entries) == 0
    assert snap.host_role == "windows-research"
    assert len(snap.rejections) == 4
    assert all(r.source == "plan" for r in snap.rejections)
    assert any("ADR" in r.reason or "adr" in r.reason.lower() for r in snap.rejections)
    assert snap.manage.summary.get("events", 0) >= 2
    assert snap.manage.latest_cycle is not None
    pl = snap.manage.latest_cycle.get("payload") or {}
    assert pl.get("n_recommendations") == 0
    assert snap.book_raw.get("watchlist") == ["QQQ", "IWM"]


def test_positions_refresh_false_only():
    """Snapshot path must call load_positions with refresh=False when injected."""
    calls: list[dict] = []

    def fake_load(path, fixture_mode, *, refresh=None):
        calls.append({"path": path, "fixture_mode": fixture_mode, "refresh": refresh})
        return []

    pos_path = str(FIXTURE_ROOT / "positions.json")
    now = datetime(2026, 8, 13, 10, 0, tzinfo=PT)
    snap = assemble_snapshot(
        now=now,
        trading_date=TD,
        state=FIXTURE_ROOT,
        positions_path=pos_path,
        load_positions_fn=fake_load,
        platform="darwin",
        env={},
    )
    assert calls, "expected load_positions_fn to be called"
    assert calls[0]["refresh"] is False
    assert snap.positions.path == pos_path


def test_positions_pure_file_no_refresh_env():
    """Pure JSON path works without calling Schwab refresh."""
    pos_path = str(FIXTURE_ROOT / "positions.json")
    from trading_agent.desk_ui.readers.positions import load_positions_view

    view = load_positions_view(path=pos_path)
    assert view.available is True
    assert len(view.positions) >= 1
    assert view.positions[0].get("symbol") == "SPY"


def test_cli_desk_status_runs(capsys):
    from trading_agent.desk_ui.cli_status import run_desk_status

    code = run_desk_status(
        ["--state", str(FIXTURE_ROOT), "--date", "2026-08-13"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "CASH" in out or "stay_in_cash" in out
    assert "2026-08-13" in out
    assert "QQQ" in out or "rejections" in out.lower() or "Rejection" in out


def test_cli_json(capsys):
    from trading_agent.desk_ui.cli_status import run_desk_status

    code = run_desk_status(
        ["--json", "--state", str(FIXTURE_ROOT), "--date", "2026-08-13"]
    )
    assert code == 0
    import json

    data = json.loads(capsys.readouterr().out)
    assert data["stay_in_cash"] is True
    assert data["trading_date"] == "2026-08-13"
    assert len(data["rejections"]) == 4


def test_main_module_desk_status():
    from trading_agent.__main__ import main

    code = main(
        [
            "desk-status",
            "--state",
            str(FIXTURE_ROOT),
            "--date",
            "2026-08-13",
        ]
    )
    assert code == 0
