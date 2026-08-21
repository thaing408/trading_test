"""Tests for desk-ui FastAPI shell (auth, overview, book, health)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "desk_ui"
TD = "2026-08-13"

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")


@pytest.fixture
def settings_factory():
    from trading_agent.desk_ui.config import DeskUiSettings

    def _make(**kwargs):
        base = dict(
            host="127.0.0.1",
            port=8787,
            token="",
            allow_lan=False,
            allow_query_token=False,
            state_root=FIXTURE_ROOT,
            trading_date=TD,
        )
        base.update(kwargs)
        return DeskUiSettings(**base)

    return _make


@pytest.fixture
def client(settings_factory):
    from fastapi.testclient import TestClient
    from trading_agent.desk_ui.app import create_app

    app = create_app(settings_factory())
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["trading_date"] == TD
    assert data["stay_in_cash"] is True
    assert data["entry_count"] == 0
    assert "parse_failures" in data
    assert data["paths"]["state_root"]


def test_snapshot_json(client):
    r = client.get("/api/v1/snapshot")
    assert r.status_code == 200
    data = r.json()
    assert data["stay_in_cash"] is True
    assert len(data["rejections"]) == 4
    assert data["entries"] == []


def test_overview_html_cash_badge(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "CASH" in body
    assert "Overview" in body
    assert "Empty entries" in body or "No ENTER" in body or "entry" in body.lower()


def test_book_html_empty_entries(client):
    r = client.get("/book")
    assert r.status_code == 200
    body = r.text
    assert "Auto-trade book" in body or "Book" in body
    assert "Empty entries" in body or "entry_count" in body
    assert "stay_in_cash" in body


def test_static_css(client):
    r = client.get("/static/desk.css")
    assert r.status_code == 200
    assert "desk-header" in r.text or "--bg" in r.text


def test_auth_required_401(settings_factory):
    from fastapi.testclient import TestClient
    from trading_agent.desk_ui.app import create_app

    app = create_app(settings_factory(token="secret-token-xyz"))
    with TestClient(app) as c:
        r = c.get("/api/v1/health")
        assert r.status_code == 401
        r2 = c.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer secret-token-xyz"},
        )
        assert r2.status_code == 200
        r3 = c.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer wrong"},
        )
        assert r3.status_code == 401


def test_auth_cookie(settings_factory):
    from fastapi.testclient import TestClient
    from trading_agent.desk_ui.app import create_app
    from trading_agent.desk_ui.config import COOKIE_NAME

    app = create_app(settings_factory(token="cookie-secret"))
    with TestClient(app) as c:
        c.cookies.set(COOKIE_NAME, "cookie-secret")
        r = c.get("/api/v1/health")
        assert r.status_code == 200


def test_query_token_debug_only(settings_factory):
    from fastapi.testclient import TestClient
    from trading_agent.desk_ui.app import create_app

    app = create_app(
        settings_factory(token="qtok", allow_query_token=False)
    )
    with TestClient(app) as c:
        r = c.get("/api/v1/health?token=qtok")
        assert r.status_code == 401

    app2 = create_app(
        settings_factory(token="qtok", allow_query_token=True)
    )
    with TestClient(app2) as c2:
        r2 = c2.get("/api/v1/health?token=qtok")
        assert r2.status_code == 200


def test_validate_bind_non_loopback():
    from trading_agent.desk_ui.config import DeskUiSettings

    s = DeskUiSettings(host="0.0.0.0", allow_lan=False, token="")
    assert s.validate_bind() is not None
    s2 = DeskUiSettings(host="0.0.0.0", allow_lan=True, token="")
    assert s2.validate_bind() is not None  # needs token
    s3 = DeskUiSettings(host="0.0.0.0", allow_lan=True, token="x")
    assert s3.validate_bind() is None
    s4 = DeskUiSettings(host="127.0.0.1")
    assert s4.validate_bind() is None


def test_templates_dir_exists():
    from trading_agent.desk_ui.config import static_dir, templates_dir

    assert (templates_dir() / "base.html").is_file()
    assert (templates_dir() / "overview.html").is_file()
    assert (templates_dir() / "book.html").is_file()
    assert (templates_dir() / "manage.html").is_file()
    assert (templates_dir() / "oms.html").is_file()
    assert (templates_dir() / "firm.html").is_file()
    assert (templates_dir() / "rejections.html").is_file()
    assert (templates_dir() / "discovery.html").is_file()
    assert (templates_dir() / "session.html").is_file()
    assert (static_dir() / "desk.css").is_file()


def test_overview_shows_execute_cash(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Execute (Mac)" in body
    assert "Tradable cash" in body or "tradable" in body.lower()
    assert "11500" in body or "12,500" in body or "12500" in body


def test_manage_oms_firm_routes(client):
    for path, needle in (
        ("/manage", "Manage"),
        ("/oms", "Ready orders"),
        ("/firm", "Firm sleeve"),
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert needle in r.text


def test_oms_shows_export_health_and_dual_system(client):
    r = client.get("/oms")
    assert r.status_code == 200
    body = r.text
    assert "Export health" in body
    assert "auto_trade_book.json" in body
    # Fixture assemble uses win32 → windows-research caveat
    assert "windows-research" in body or "Mac-local" in body or "research host" in body


def test_session_page_lists_fixture_files(client):
    r = client.get("/session")
    assert r.status_code == 200
    body = r.text
    assert "stubbed" not in body.lower()
    assert "Session files" in body
    assert "daily_plan_context.json" in body
    assert "auto_trade_book.json" in body
    api = client.get("/api/v1/session")
    assert api.status_code == 200
    data = api.json()
    assert data["exists"] is True
    rels = {f["rel"] for f in data["files"]}
    assert any("daily_plan_context.json" in x for x in rels)


def test_firm_page_shows_aapl(client):
    r = client.get("/firm")
    assert r.status_code == 200
    assert "AAPL" in r.text
    assert "BUY" in r.text


def test_rejections_page_shows_plan_rows(client):
    r = client.get("/rejections")
    assert r.status_code == 200
    body = r.text
    assert "stubbed" not in body.lower()
    assert "Rejections" in body
    assert "QQQ" in body
    assert "IWM" in body
    assert "ADR" in body
    assert "RVOL" in body or "volume" in body.lower()
    assert "plan" in body


def test_rejections_filter_symbol(client):
    r = client.get("/rejections", params={"symbol": "IWM"})
    assert r.status_code == 200
    body = r.text
    assert "IWM" in body
    assert "52w" in body or "strength" in body.lower()
    # QQQ-only ADR row should be filtered out of the table body sense —
    # page still has nav, so check API filter instead for precision
    api = client.get("/api/v1/rejections", params={"symbol": "IWM"})
    assert api.status_code == 200
    rows = api.json()["rejections"]
    assert rows
    assert all(row["symbol"] == "IWM" for row in rows)


def test_rejections_filter_text(client):
    api = client.get("/api/v1/rejections", params={"q": "rvol"})
    assert api.status_code == 200
    rows = api.json()["rejections"]
    assert rows
    assert all("rvol" in (row["reason"] or "").lower() or "volume" in (row["reason"] or "").lower() for row in rows)


def test_discovery_page_process_cards(client):
    r = client.get("/discovery")
    assert r.status_code == 200
    body = r.text
    assert "stubbed" not in body.lower()
    assert "Discovery" in body
    assert "Process trade cards" in body
    assert "QQQ" in body
    assert "IWM" in body
    assert "ADR" in body or "process card" in body.lower()


def test_discovery_api_and_filter(client):
    api = client.get("/api/v1/discovery")
    assert api.status_code == 200
    data = api.json()
    assert len(data["process_cards"]) >= 2
    filtered = client.get("/api/v1/discovery", params={"symbol": "QQQ"}).json()
    assert filtered["process_cards"]
    assert all(
        (c.get("symbol") or "").upper() == "QQQ" for c in filtered["process_cards"]
    )


def test_stub_routes_remaining(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "stubbed" in r.text.lower()
