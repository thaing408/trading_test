"""Optional local positions file — never refresh brokerage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.models import PositionsView


def load_positions_view(
    *,
    path: str | None = None,
    load_positions_fn: Callable[..., Any] | None = None,
) -> PositionsView:
    """Read positions with refresh=False only (or pure JSON).

    ``load_positions_fn`` is injectable for unit tests (assert refresh=False).
    """
    resolved = (path if path is not None else os.getenv("TRADING_AGENT_POSITIONS_FILE", "")).strip()
    if not resolved:
        return PositionsView(
            available=False,
            path=None,
            positions=[],
            empty_reason="no local positions file (typical on Windows research host)",
        )

    p = Path(resolved)
    if not p.is_file():
        return PositionsView(
            available=False,
            path=str(p),
            positions=[],
            empty_reason="positions path set but file missing",
        )

    if load_positions_fn is not None:
        rows = load_positions_fn(str(p), False, refresh=False)
        positions = [_pos_to_dict(r) for r in rows]
        return PositionsView(
            available=True,
            path=str(p),
            positions=positions,
            empty_reason="" if positions else "positions file empty",
        )

    # Prefer pure file read to avoid any default-arg refresh footgun.
    data, err = read_json_file(p)
    if err or not isinstance(data, dict):
        # Fallback to load_positions with explicit refresh=False
        try:
            from trading_agent.intraday.plan_loader import load_positions

            rows = load_positions(str(p), False, refresh=False)
            positions = [_pos_to_dict(r) for r in rows]
            return PositionsView(
                available=True,
                path=str(p),
                positions=positions,
                empty_reason="" if positions else "positions file empty",
            )
        except Exception as exc:
            return PositionsView(
                available=False,
                path=str(p),
                positions=[],
                empty_reason=f"unreadable: {exc}",
            )

    try:
        from trading_agent.intraday.plan_loader import positions_from_payload

        mapped = positions_from_payload(data)
        positions = [_pos_to_dict(r) for r in mapped]
    except Exception:
        # Raw list fallback
        raw = data.get("positions") if isinstance(data.get("positions"), list) else []
        positions = [x for x in raw if isinstance(x, dict)]

    return PositionsView(
        available=True,
        path=str(p),
        positions=positions,
        empty_reason="" if positions else "positions file empty",
    )


def _pos_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "__dict__"):
        return {
            k: getattr(row, k)
            for k in (
                "symbol",
                "quantity",
                "entry_price",
                "current_price",
                "strategy",
                "thesis",
                "expiration",
                "strike_prices",
            )
            if hasattr(row, k)
        }
    return {"value": str(row)}
