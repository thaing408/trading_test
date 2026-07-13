"""Optional brokerage read paths (Alpaca / Tradier). Fail-closed when unconfigured.

IBKR TWS requires a live Gateway/Workstation process — exposed only as a capability
flag via ProviderConfig.ibkr_enabled; no hard dependency.
"""

from __future__ import annotations

from typing import Any, Dict, List

from trading_agent.providers.base import ProviderFetchResult, http_get
from trading_agent.providers.config import ProviderConfig


def fetch_alpaca_positions(config: ProviderConfig | None = None) -> ProviderFetchResult:
    cfg = config or ProviderConfig.from_env()
    if not cfg.is_configured("alpaca"):
        return ProviderFetchResult.unavailable(
            "alpaca",
            "ALPACA_API_KEY / ALPACA_SECRET_KEY not set; brokerage positions omitted",
        )
    try:
        resp = http_get(
            f"{cfg.alpaca_base_url.rstrip('/')}/v2/positions",
            headers={
                "APCA-API-KEY-ID": cfg.alpaca_api_key,
                "APCA-API-SECRET-KEY": cfg.alpaca_secret_key,
            },
        )
        if resp.status_code in (401, 403):
            return ProviderFetchResult.unavailable(
                "alpaca", f"Alpaca auth failed HTTP {resp.status_code}"
            )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return ProviderFetchResult.unavailable("alpaca", "Unexpected Alpaca positions payload")
        positions: List[Dict[str, Any]] = []
        for row in payload:
            positions.append(
                {
                    "symbol": row.get("symbol", ""),
                    "qty": float(row.get("qty") or 0),
                    "avg_entry_price": float(row.get("avg_entry_price") or 0),
                    "current_price": float(row.get("current_price") or 0),
                    "unrealized_pl": float(row.get("unrealized_pl") or 0),
                    "side": row.get("side") or "long",
                    "broker": "alpaca",
                }
            )
        return ProviderFetchResult(
            source="alpaca",
            ok=True,
            positions=positions,
            metadata={"status": "ok", "count": str(len(positions))},
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderFetchResult.unavailable("alpaca", str(exc))


def fetch_tradier_positions(config: ProviderConfig | None = None) -> ProviderFetchResult:
    cfg = config or ProviderConfig.from_env()
    if not cfg.is_configured("tradier") or not cfg.tradier_account_id:
        return ProviderFetchResult.unavailable(
            "tradier",
            "TRADIER_ACCESS_TOKEN / TRADIER_ACCOUNT_ID not set; brokerage positions omitted",
        )
    try:
        url = (
            f"{cfg.tradier_base_url.rstrip('/')}/v1/accounts/"
            f"{cfg.tradier_account_id}/positions"
        )
        resp = http_get(
            url,
            headers={
                "Authorization": f"Bearer {cfg.tradier_access_token}",
                "Accept": "application/json",
            },
        )
        if resp.status_code in (401, 403):
            return ProviderFetchResult.unavailable(
                "tradier", f"Tradier auth failed HTTP {resp.status_code}"
            )
        resp.raise_for_status()
        data = resp.json()
        # Tradier nests positions under positions.position
        block = (data or {}).get("positions") or {}
        raw = block.get("position") if isinstance(block, dict) else None
        if raw is None:
            rows: list = []
        elif isinstance(raw, list):
            rows = raw
        else:
            rows = [raw]
        positions: List[Dict[str, Any]] = []
        for row in rows:
            positions.append(
                {
                    "symbol": row.get("symbol", ""),
                    "qty": float(row.get("quantity") or 0),
                    "avg_entry_price": float(row.get("cost_basis") or 0),
                    "current_price": 0.0,
                    "unrealized_pl": 0.0,
                    "side": "long" if float(row.get("quantity") or 0) >= 0 else "short",
                    "broker": "tradier",
                }
            )
        return ProviderFetchResult(
            source="tradier",
            ok=True,
            positions=positions,
            metadata={"status": "ok", "count": str(len(positions))},
        )
    except Exception as exc:  # noqa: BLE001
        return ProviderFetchResult.unavailable("tradier", str(exc))


def load_broker_positions(config: ProviderConfig | None = None) -> ProviderFetchResult:
    """Try Alpaca then Tradier; never raises; never fills fixtures."""
    cfg = config or ProviderConfig.from_env()
    alpaca = fetch_alpaca_positions(cfg)
    if alpaca.ok:
        return alpaca
    tradier = fetch_tradier_positions(cfg)
    if tradier.ok:
        return tradier
    errors = alpaca.errors + tradier.errors
    if cfg.ibkr_enabled:
        errors.append(
            "ibkr_tws: enabled but socket client not active in this build — connect TWS/Gateway separately"
        )
    return ProviderFetchResult.unavailable(
        "unavailable",
        "; ".join(errors) if errors else "No brokerage credentials configured",
    )
