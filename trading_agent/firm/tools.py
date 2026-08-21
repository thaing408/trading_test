"""Shared firm tool registry — P1 live gathers with stub fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from trading_agent.firm import gather as g


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
    stub: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "stub": self.stub,
        }


def tool_ohlcv(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_ohlcv(symbol, period=str(kwargs.get("period") or "6mo"))


def tool_ta_bundle(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_ta_bundle(symbol)


def tool_news(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_news(symbol, limit=int(kwargs.get("limit") or 12))


def tool_fundamentals(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_fundamentals(symbol)


def tool_insider(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_insider(symbol)


def tool_social(symbol: str, **kwargs: Any) -> Dict[str, Any]:
    return g.gather_social(symbol)


TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "ohlcv": ToolSpec("ohlcv", "OHLCV bars for symbol", tool_ohlcv),
    "ta_bundle": ToolSpec("ta_bundle", "Technical indicator pack", tool_ta_bundle),
    "news": ToolSpec("news", "News headlines / catalysts", tool_news),
    "fundamentals": ToolSpec("fundamentals", "Fundamentals snapshot", tool_fundamentals),
    "insider": ToolSpec("insider", "Insider / Form-4 style series", tool_insider),
    "social": ToolSpec("social", "News-tone + Reddit JSON sentiment (informational)", tool_social),
}


def call_tool(name: str, *, symbol: str, **kwargs: Any) -> ToolResult:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return ToolResult(tool=name, ok=False, error=f"unknown_tool:{name}", stub=True)
    if not spec.enabled:
        return ToolResult(tool=name, ok=False, error="tool_disabled", stub=True)
    try:
        data = spec.handler(symbol=symbol, **kwargs)
        if not isinstance(data, dict):
            data = {"raw": data}
        ok = data.get("status") not in ("error",)
        stub = data.get("status") == "stub" or data.get("source") == "stub"
        return ToolResult(tool=name, ok=ok, data=data, stub=bool(stub), error=str(data.get("error") or ""))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(tool=name, ok=False, error=str(exc), stub=True)


def list_tools() -> List[Dict[str, str]]:
    return [
        {"name": t.name, "description": t.description, "enabled": str(t.enabled)}
        for t in TOOL_REGISTRY.values()
    ]
