"""Shared firm tool registry (P0 stubs — real collectors wired in P1+)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Dict[str, Any]]
    enabled: bool = True


@dataclass
class ToolResult:
    tool: str
    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    stub: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "stub": self.stub,
        }


def _stub(tool: str, **kwargs: Any) -> Dict[str, Any]:
    return {
        "status": "stub",
        "tool": tool,
        "args": {k: v for k, v in kwargs.items() if k != "symbol"},
        "symbol": kwargs.get("symbol"),
        "message": f"P0 stub tool `{tool}` — no live fetch",
    }


def tool_ohlcv(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("ohlcv", symbol=symbol, **kwargs)


def tool_ta_bundle(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("ta_bundle", symbol=symbol, **kwargs)


def tool_news(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("news", symbol=symbol, **kwargs)


def tool_fundamentals(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("fundamentals", symbol=symbol, **kwargs)


def tool_insider(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("insider", symbol=symbol, **kwargs)


def tool_social(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return _stub("social", symbol=symbol, **kwargs)


TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "ohlcv": ToolSpec("ohlcv", "OHLCV bars for symbol", tool_ohlcv),
    "ta_bundle": ToolSpec("ta_bundle", "Technical indicator pack", tool_ta_bundle),
    "news": ToolSpec("news", "News headlines / catalysts", tool_news),
    "fundamentals": ToolSpec("fundamentals", "Fundamentals snapshot", tool_fundamentals),
    "insider": ToolSpec("insider", "Insider / Form-4 style series", tool_insider),
    "social": ToolSpec("social", "Social / X / Reddit sentiment", tool_social),
}


def call_tool(name: str, *, symbol: str, **kwargs: Any) -> ToolResult:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return ToolResult(tool=name, ok=False, error=f"unknown_tool:{name}", stub=True)
    if not spec.enabled:
        return ToolResult(tool=name, ok=False, error="tool_disabled", stub=True)
    try:
        data = spec.handler(symbol=symbol, **kwargs)
        return ToolResult(tool=name, ok=True, data=data if isinstance(data, dict) else {"raw": data})
    except Exception as exc:  # noqa: BLE001
        return ToolResult(tool=name, ok=False, error=str(exc), stub=True)


def list_tools() -> List[Dict[str, str]]:
    return [
        {"name": t.name, "description": t.description, "enabled": str(t.enabled)}
        for t in TOOL_REGISTRY.values()
    ]
