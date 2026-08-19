"""FastAPI desk UI factory — auth middleware, overview/book, snapshot APIs."""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, AsyncIterator, Callable

try:
    from fastapi import Request as FastAPIRequest
except ImportError:  # pragma: no cover
    FastAPIRequest = Any  # type: ignore[misc, assignment]

from trading_agent.desk_ui.config import (
    COOKIE_NAME,
    DeskUiSettings,
    detect_host_role,
    load_settings,
    static_dir,
    templates_dir,
)
from trading_agent.desk_ui.paths import state_root as default_state_root
from trading_agent.desk_ui.snapshot import assemble_snapshot

logger = logging.getLogger("trading_agent.desk_ui")

# Nav — Session/Settings still stubbed (PR4/PR6)
NAV_ITEMS = (
    ("/", "Overview"),
    ("/book", "Book"),
    ("/manage", "Manage"),
    ("/oms", "OMS"),
    ("/firm", "Firm"),
    ("/rejections", "Rejections"),
    ("/discovery", "Discovery"),
    ("/session", "Session"),
    ("/settings", "Settings"),
)


def _filter_params(request: Any) -> tuple[str, str]:
    """Return (symbol, q) query filters, lowercased/stripped."""
    try:
        qp = request.query_params
    except Exception:  # noqa: BLE001
        return "", ""
    symbol = str(qp.get("symbol") or "").strip()
    q = str(qp.get("q") or "").strip()
    return symbol, q


def _filter_rejections(rows: list[Any], *, symbol: str = "", q: str = "") -> list[Any]:
    sym = symbol.strip().upper()
    needle = q.strip().lower()
    out: list[Any] = []
    for r in rows:
        r_sym = str(getattr(r, "symbol", "") or "").upper()
        if sym and r_sym != sym and sym not in r_sym:
            continue
        if needle:
            reason = str(getattr(r, "reason", "") or "").lower()
            source = str(getattr(r, "source", "") or "").lower()
            gates = " ".join(str(g) for g in (getattr(r, "gates", None) or [])).lower()
            blob = f"{r_sym.lower()} {reason} {source} {gates}"
            if needle not in blob:
                continue
        out.append(r)
    return out


def _filter_symbol_list(symbols: list[str], *, symbol: str = "", q: str = "") -> list[str]:
    sym = symbol.strip().upper()
    needle = q.strip().lower()
    out: list[str] = []
    for s in symbols:
        su = str(s or "").upper()
        if sym and su != sym and sym not in su:
            continue
        if needle and needle not in su.lower():
            continue
        out.append(su)
    return out


def _filter_process_cards(
    cards: list[dict[str, Any]], *, symbol: str = "", q: str = ""
) -> list[dict[str, Any]]:
    sym = symbol.strip().upper()
    needle = q.strip().lower()
    out: list[dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        c_sym = str(c.get("symbol") or c.get("ticker") or "").upper()
        if sym and c_sym != sym and sym not in c_sym:
            continue
        if needle:
            blob = " ".join(
                str(c.get(k) or "")
                for k in (
                    "symbol",
                    "ticker",
                    "bias",
                    "side",
                    "setup",
                    "setup_id",
                    "status",
                    "notes",
                    "note",
                    "summary",
                )
            ).lower()
            if needle not in blob:
                continue
        out.append(c)
    return out


def _check_token(settings: DeskUiSettings, provided: str | None) -> bool:
    if not settings.token:
        return True
    if not provided:
        return False
    try:
        return hmac.compare_digest(settings.token, provided)
    except (TypeError, ValueError):
        return False


def _extract_token(request: Any, settings: DeskUiSettings) -> str | None:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return auth.strip()
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    if settings.allow_query_token:
        q = request.query_params.get("token")
        if q:
            return q
    return None


def _template_response(templates: Any, request: Any, name: str, context: dict[str, Any]) -> Any:
    """Starlette/FastAPI TemplateResponse API (request-first or name-first)."""
    try:
        return templates.TemplateResponse(request, name, context)
    except TypeError:
        return templates.TemplateResponse(name, {**context, "request": request})


def create_app(settings: DeskUiSettings | None = None) -> Any:
    """Build FastAPI app. Imports FastAPI only when called (lazy)."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ImportError as exc:
        raise ImportError(
            'desk-ui requires optional deps. Install: pip install -e ".[desk-ui]"'
        ) from exc

    # Bind for nested route annotations (future annotations resolve in this module)
    global FastAPIRequest
    try:
        from fastapi import Request as FastAPIRequest  # noqa: F811
    except ImportError as exc:
        raise ImportError(
            'desk-ui requires optional deps. Install: pip install -e ".[desk-ui]"'
        ) from exc

    cfg = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        role = detect_host_role(state_root=cfg.state_root or default_state_root())
        logger.info(
            "desk_ui start host=%s port=%s state=%s host_role=%s auth=%s templates=%s",
            cfg.host,
            cfg.port,
            cfg.state_root or default_state_root(),
            role,
            "on" if cfg.auth_required else "off",
            tdir,
        )
        yield

    app = FastAPI(
        title="Trading Agent Desk UI",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.desk_ui_settings = cfg

    tdir = templates_dir()
    sdir = static_dir()
    templates = Jinja2Templates(directory=str(tdir))
    if sdir.is_dir():
        app.mount("/static", StaticFiles(directory=str(sdir)), name="static")

    def _snap_kwargs() -> dict[str, Any]:
        td = None
        if cfg.trading_date:
            try:
                td = date.fromisoformat(cfg.trading_date)
            except ValueError:
                td = None
        return {
            "trading_date": td,
            "state": cfg.state_root,
        }

    def get_snapshot():
        return assemble_snapshot(**_snap_kwargs())

    @app.middleware("http")
    async def auth_middleware(request: FastAPIRequest, call_next: Callable):
        path = request.url.path or ""
        if path.startswith("/static/"):
            return await call_next(request)

        if cfg.auth_required:
            token = _extract_token(request, cfg)
            if not _check_token(cfg, token):
                logger.warning("desk_ui auth failed path=%s", path)
                return JSONResponse(
                    {"detail": "Unauthorized", "hint": "Bearer token or cookie required"},
                    status_code=401,
                )
        return await call_next(request)

    def _base_ctx(request: FastAPIRequest, snap: Any, active: str) -> dict[str, Any]:
        age = snap.export_health.last_write_age_seconds
        age_label = f"{age / 60:.0f}m ago" if age is not None else "—"
        next_phase = ""
        if snap.phase.next_phase_kind and snap.phase.next_phase_at:
            next_phase = (
                f"{snap.phase.next_phase_kind} @ "
                f"{snap.phase.next_phase_at.strftime('%H:%M %Z')}"
            )
        return {
            "request": request,
            "snap": snap,
            "nav": NAV_ITEMS,
            "active": active,
            "cash_badge": "CASH" if snap.stay_in_cash else "ARMED",
            "last_write_label": age_label,
            "next_phase_label": next_phase,
            "token_configured": cfg.token_configured,
            "settings": cfg,
            "state_root": str(cfg.state_root or default_state_root()),
            "poll_seconds": 30 if snap.phase.in_intraday_window else 90,
        }

    @app.get("/", response_class=HTMLResponse)
    async def overview(request: FastAPIRequest):
        snap = get_snapshot()
        return _template_response(
            templates, request, "overview.html", _base_ctx(request, snap, "/")
        )

    @app.get("/book", response_class=HTMLResponse)
    async def book(request: FastAPIRequest):
        snap = get_snapshot()
        return _template_response(
            templates, request, "book.html", _base_ctx(request, snap, "/book")
        )

    @app.get("/manage", response_class=HTMLResponse)
    async def manage(request: FastAPIRequest):
        snap = get_snapshot()
        return _template_response(
            templates, request, "manage.html", _base_ctx(request, snap, "/manage")
        )

    @app.get("/rejections", response_class=HTMLResponse)
    async def rejections(request: FastAPIRequest):
        snap = get_snapshot()
        symbol, q = _filter_params(request)
        filtered = _filter_rejections(snap.rejections, symbol=symbol, q=q)
        plan_count = sum(1 for r in snap.rejections if r.source == "plan")
        book_count = sum(1 for r in snap.rejections if r.source == "book_incomplete")
        return _template_response(
            templates,
            request,
            "rejections.html",
            {
                **_base_ctx(request, snap, "/rejections"),
                "filtered_rejections": filtered,
                "filter_symbol": symbol,
                "filter_q": q,
                "plan_count": plan_count,
                "book_count": book_count,
            },
        )

    @app.get("/discovery", response_class=HTMLResponse)
    async def discovery(request: FastAPIRequest):
        snap = get_snapshot()
        symbol, q = _filter_params(request)
        return _template_response(
            templates,
            request,
            "discovery.html",
            {
                **_base_ctx(request, snap, "/discovery"),
                "filter_symbol": symbol,
                "filter_q": q,
                "filtered_cards": _filter_process_cards(
                    snap.process_cards, symbol=symbol, q=q
                ),
                "filtered_watch": _filter_symbol_list(
                    snap.watchlist, symbol=symbol, q=q
                ),
                "filtered_play": _filter_symbol_list(
                    snap.play_symbols, symbol=symbol, q=q
                ),
            },
        )

    @app.get("/oms", response_class=HTMLResponse)
    async def oms(request: FastAPIRequest):
        snap = get_snapshot()
        return _template_response(
            templates, request, "oms.html", _base_ctx(request, snap, "/oms")
        )

    @app.get("/firm", response_class=HTMLResponse)
    async def firm(request: FastAPIRequest):
        snap = get_snapshot()
        return _template_response(
            templates, request, "firm.html", _base_ctx(request, snap, "/firm")
        )

    async def _stub(request: FastAPIRequest):
        snap = get_snapshot()
        path = request.url.path
        return _template_response(
            templates,
            request,
            "stub.html",
            {
                **_base_ctx(request, snap, path),
                "page_title": path.strip("/").title() or "Page",
                "stub_message": (
                    "This panel is stubbed. Use Overview, Book, Manage, OMS, Firm, "
                    "Rejections, Discovery, or desk-status /api/v1/snapshot."
                ),
            },
        )

    for stub_path in (
        "/session",
        "/settings",
    ):
        app.add_api_route(stub_path, _stub, methods=["GET"], response_class=HTMLResponse)

    @app.get("/api/v1/snapshot")
    async def api_snapshot():
        snap = get_snapshot()
        return snap.to_dict()

    @app.get("/api/v1/health")
    async def api_health():
        snap = get_snapshot()
        root = cfg.state_root or default_state_root()
        sync = root / "sync"
        book_path = sync / "auto_trade_book.json"
        session_plan = root / "sessions" / snap.trading_date / "daily_plan_context.json"
        return {
            "ok": True,
            "trading_date": snap.trading_date,
            "host": snap.host,
            "host_role": snap.host_role,
            "platform": snap.platform,
            "parse_failures": snap.parse_failures,
            "panel_errors": snap.panel_errors,
            "stay_in_cash": snap.stay_in_cash,
            "entry_count": len(snap.entries),
            "rejection_count": len(snap.rejections),
            "paths": {
                "state_root": str(root),
                "sync_dir": str(sync),
                "auto_trade_book": {
                    "path": str(book_path),
                    "exists": book_path.is_file(),
                },
                "plan_context": {
                    "path": str(session_plan),
                    "exists": session_plan.is_file(),
                },
            },
            "auth_required": cfg.auth_required,
            "bind_host": cfg.host,
            "generated_at": snap.generated_at,
        }

    @app.get("/api/v1/rejections")
    async def api_rejections(request: FastAPIRequest):
        snap = get_snapshot()
        symbol, q = _filter_params(request)
        rows = _filter_rejections(snap.rejections, symbol=symbol, q=q)
        return {
            "trading_date": snap.trading_date,
            "filter": {"symbol": symbol, "q": q},
            "rejections": [
                {
                    "symbol": r.symbol,
                    "reason": r.reason,
                    "source": r.source,
                    "gates": r.gates,
                }
                for r in rows
            ],
        }

    @app.get("/api/v1/discovery")
    async def api_discovery(request: FastAPIRequest):
        snap = get_snapshot()
        symbol, q = _filter_params(request)
        return {
            "trading_date": snap.trading_date,
            "filter": {"symbol": symbol, "q": q},
            "watchlist": _filter_symbol_list(snap.watchlist, symbol=symbol, q=q),
            "play_symbols": _filter_symbol_list(snap.play_symbols, symbol=symbol, q=q),
            "process_cards": _filter_process_cards(
                snap.process_cards, symbol=symbol, q=q
            ),
            "gap_book_summary": snap.gap_book_summary,
            "next_discovery_at": (
                snap.phase.next_discovery_at.isoformat()
                if snap.phase.next_discovery_at
                else None
            ),
            "discovery_slot_label": snap.phase.discovery_slot_label,
        }

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(_request: FastAPIRequest):
        return HTMLResponse(
            """<!DOCTYPE html><html><head><title>Desk UI login</title></head>
<body style="font-family:system-ui;max-width:28rem;margin:3rem auto">
<h1>Desk UI</h1>
<p>Set auth cookie (SameSite=Lax, httpOnly).</p>
<form method="post" action="/login">
<label>Token <input type="password" name="token" autofocus style="width:100%"/></label>
<button type="submit">Set cookie</button>
</form>
</body></html>"""
        )

    @app.post("/login")
    async def login_post(request: FastAPIRequest):
        form = await request.form()
        token = str(form.get("token") or "").strip()
        if cfg.auth_required and not _check_token(cfg, token):
            return JSONResponse({"detail": "Invalid token"}, status_code=401)
        resp = RedirectResponse("/", status_code=303)
        if token:
            resp.set_cookie(
                COOKIE_NAME,
                token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )
        return resp

    return app

