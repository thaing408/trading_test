"""Desk UI role detection, server settings, and env flags."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

HostRole = Literal["windows-research", "mac-execute", "unknown"]

_ROLE_ENV = "TRADING_AGENT_DESK_UI_ROLE"
_FORCE_VALUES = frozenset({"windows-research", "mac-execute"})

COOKIE_NAME = "desk_ui_token"


def _truthy(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _truthy_from(e: Any, name: str) -> bool:
    return str(e.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _has_open_oms_lots(oms_root: Path | None = None) -> bool:
    try:
        from trading_agent.oms.state import OmsStore

        store = OmsStore(root=oms_root)
        return bool(store.open_lots())
    except Exception:
        return False


def _has_ready_orders(state: Path | None = None) -> bool:
    root = state or (Path.home() / ".trading_agent")
    candidates = [
        root / "ready_orders",
        root / "sync" / "ready_orders.json",
    ]
    for path in candidates:
        try:
            if path.is_dir() and any(path.iterdir()):
                return True
            if path.is_file() and path.stat().st_size > 2:
                return True
        except OSError:
            continue
    return False


def detect_host_role(
    *,
    platform: str | None = None,
    env: dict[str, str] | None = None,
    oms_root: Path | None = None,
    state_root: Path | None = None,
) -> HostRole:
    """Platform-first host role (never treat win32 as mac-execute via leftovers)."""
    e = env if env is not None else os.environ
    plat = (platform if platform is not None else sys.platform).lower()

    forced = (e.get(_ROLE_ENV) or "").strip().lower()
    if forced in _FORCE_VALUES:
        return forced  # type: ignore[return-value]

    if plat.startswith("win"):
        return "windows-research"

    if plat == "darwin":
        live = (e.get("TRADING_AGENT_AUTO_TRADE_LIVE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if live or _has_open_oms_lots(oms_root) or _has_ready_orders(state_root):
            return "mac-execute"
        return "unknown"

    return "unknown"


def kill_write_allowed(
    host_role: HostRole,
    *,
    platform: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Stricter gate for kill POST (PR5); exposed for snapshot/debug."""
    e = env if env is not None else os.environ
    plat = (platform if platform is not None else sys.platform).lower()
    if not _truthy_from(e, "TRADING_AGENT_DESK_UI_ALLOW_KILL"):
        return False
    if host_role != "mac-execute":
        return False
    forced = (e.get(_ROLE_ENV) or "").strip().lower() == "mac-execute"
    if plat == "darwin" or forced:
        return True
    return False


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


@dataclass(frozen=True)
class DeskUiSettings:
    """Effective server settings from env / CLI."""

    host: str = "127.0.0.1"
    port: int = 8787
    token: str = ""
    allow_lan: bool = False
    allow_query_token: bool = False
    allow_kill: bool = False
    allow_flags: bool = False
    state_root: Path | None = None
    trading_date: str | None = None  # optional override YYYY-MM-DD

    @property
    def auth_required(self) -> bool:
        return bool(self.token)

    @property
    def token_configured(self) -> bool:
        return bool(self.token)

    def validate_bind(self) -> str | None:
        """Return error message if bind is not allowed, else None."""
        if is_loopback_host(self.host):
            return None
        if not self.allow_lan:
            return (
                f"Non-loopback bind {self.host!r} refused in v1. "
                "Use 127.0.0.1 or set TRADING_AGENT_DESK_UI_ALLOW_LAN=1 "
                "(experimental; token required)."
            )
        if not self.token:
            return (
                f"Non-loopback bind {self.host!r} requires "
                "TRADING_AGENT_DESK_UI_TOKEN (fail-closed)."
            )
        return None


def load_settings(
    *,
    host: str | None = None,
    port: int | None = None,
    state: Path | str | None = None,
    trading_date: str | None = None,
) -> DeskUiSettings:
    env_host = os.getenv("TRADING_AGENT_DESK_UI_HOST", "127.0.0.1").strip() or "127.0.0.1"
    env_port = os.getenv("TRADING_AGENT_DESK_UI_PORT", "8787").strip() or "8787"
    try:
        port_i = int(port if port is not None else env_port)
    except ValueError:
        port_i = 8787
    state_path: Path | None = None
    if state is not None:
        state_path = Path(state)
    return DeskUiSettings(
        host=(host if host is not None else env_host) or "127.0.0.1",
        port=port_i,
        token=os.getenv("TRADING_AGENT_DESK_UI_TOKEN", "").strip(),
        allow_lan=_truthy("TRADING_AGENT_DESK_UI_ALLOW_LAN"),
        allow_query_token=_truthy("TRADING_AGENT_DESK_UI_ALLOW_QUERY_TOKEN"),
        allow_kill=_truthy("TRADING_AGENT_DESK_UI_ALLOW_KILL"),
        allow_flags=_truthy("TRADING_AGENT_DESK_UI_ALLOW_FLAGS"),
        state_root=state_path,
        trading_date=trading_date,
    )


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def templates_dir() -> Path:
    return package_dir() / "templates"


def static_dir() -> Path:
    return package_dir() / "static"
