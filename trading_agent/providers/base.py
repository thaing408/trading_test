"""Shared provider result types and HTTP helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests


@dataclass
class QuoteResult:
    symbol: str
    last: float
    change_pct: float
    source: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NewsHeadline:
    symbol: str
    headline: str
    source: str
    provider: str
    category: str = "general"


@dataclass
class ProviderFetchResult:
    """Normalized multi-provider fetch outcome."""

    source: str
    ok: bool
    quotes: Dict[str, QuoteResult] = field(default_factory=dict)
    headlines: List[NewsHeadline] = field(default_factory=list)
    positions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, source: str, reason: str) -> "ProviderFetchResult":
        return cls(source=source, ok=False, errors=[reason], metadata={"status": "unavailable"})


def http_get(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15.0,
) -> requests.Response:
    return requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
