"""ReAct step logging (thought → tool → observation). No LLM in P0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from trading_agent.firm.tools import ToolResult, call_tool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReactStep:
    role: str
    thought: str
    tool: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    observation: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def react_call(
    role: str,
    *,
    symbol: str,
    thought: str,
    tool: str,
    tool_args: Optional[Dict[str, Any]] = None,
    log: Optional[List[Dict[str, Any]]] = None,
) -> ReactStep:
    """Execute one stub tool call and append to an optional react log."""
    args = dict(tool_args or {})
    result: ToolResult = call_tool(tool, symbol=symbol, **args)
    step = ReactStep(
        role=role,
        thought=thought,
        tool=tool,
        tool_args=args,
        observation=result.to_dict(),
    )
    if log is not None:
        log.append(step.to_dict())
        if len(log) > 500:
            del log[:-500]
    return step


def analyst_stub_react_pass(
    role: str,
    symbol: str,
    tools: List[str],
    *,
    log: Optional[List[Dict[str, Any]]] = None,
) -> List[ReactStep]:
    """P0: one thought+tool per allowed tool (stubs only)."""
    steps: List[ReactStep] = []
    for tool in tools:
        steps.append(
            react_call(
                role,
                symbol=symbol,
                thought=f"P0 stub: gather `{tool}` for {symbol}",
                tool=tool,
                log=log,
            )
        )
    return steps
