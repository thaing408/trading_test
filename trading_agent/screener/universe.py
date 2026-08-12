"""Default and expanded liquid-universe helpers for the pre-market screener.

Scan wide → rank/book gates stay tight. Universe size is the primary lever for
more candidates; floors are softer at scan than at trade (`RiskConfig`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List


# Core mega-liquid names (original ~21)
CORE_LIQUID: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "JPM",
    "XLE",
    "XLF",
    "XLK",
    "SMH",
    "SOXX",
    "XBI",
    "GLD",
    "TLT",
)

# Sector ETFs + liquid single-names for broader coverage (still large-cap / liquid bias)
EXPANDED_LIQUID: tuple[str, ...] = CORE_LIQUID + (
    # More mega-caps / liquid tech
    "AVGO",
    "ORCL",
    "CRM",
    "ADBE",
    "INTC",
    "QCOM",
    "MU",
    "AMAT",
    "LRCX",
    "KLAC",
    "NOW",
    "PANW",
    "CRWD",
    "PLTR",
    "SNOW",
    "NFLX",
    "DIS",
    "BA",
    "CAT",
    "GE",
    "UNH",
    "LLY",
    "JNJ",
    "PFE",
    "ABBV",
    "MRK",
    "V",
    "MA",
    "BAC",
    "WFC",
    "GS",
    "MS",
    "C",
    "XOM",
    "CVX",
    "COP",
    "COST",
    "WMT",
    "HD",
    "NKE",
    "SBUX",
    "PEP",
    "KO",
    "MCD",
    "UBER",
    "ABNB",
    "COIN",
    "HOOD",
    "SHOP",
    "ROKU",
    "SNAP",
    "RBLX",
    "ARM",
    "TSM",
    "ASML",
    # Note: avoid delisted/unstable Yahoo tickers (e.g. former SQ → XYZ)
    # Liquid sector / theme ETFs
    "XLV",
    "XLI",
    "XLY",
    "XLP",
    "XLU",
    "XLB",
    "XLRE",
    "ARKK",
    "IWM",
    "EEM",
    "HYG",
    "LQD",
    "SLV",
    "USO",
    "UNG",
    "TQQQ",
    "SQQQ",
    "SPXU",
    "UVXY",
    # High-beta / momentum names often in retail + pro scanners
    "MARA",
    "RIOT",
    "AFRM",
    "SOFI",
    "DKNG",
    "RIVN",
    "LCID",
    "NIO",
    "BABA",
    "PDD",
    "JD",
    "MELI",
    "SE",
    "NET",
    "DDOG",
    "ZS",
    "MDB",
    "TTD",
    "ABNB",
)

SECTOR_MAP: dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMZN": "Consumer",
    "META": "Technology",
    "GOOGL": "Technology",
    "TSLA": "Consumer",
    "AMD": "Technology",
    "JPM": "Financials",
    "SPY": "Broad Market",
    "QQQ": "Technology",
    "IWM": "Small Cap",
    "DIA": "Broad Market",
    "XLK": "Technology",
    "SMH": "Technology",
    "SOXX": "Technology",
    "XBI": "Healthcare",
    "XLE": "Energy",
    "XLF": "Financials",
    "GLD": "Commodities",
    "TLT": "Bonds",
    "AVGO": "Technology",
    "ORCL": "Technology",
    "CRM": "Technology",
    "ADBE": "Technology",
    "INTC": "Technology",
    "QCOM": "Technology",
    "MU": "Technology",
    "AMAT": "Technology",
    "NFLX": "Communication",
    "DIS": "Communication",
    "BA": "Industrials",
    "CAT": "Industrials",
    "UNH": "Healthcare",
    "LLY": "Healthcare",
    "JNJ": "Healthcare",
    "V": "Financials",
    "MA": "Financials",
    "BAC": "Financials",
    "XOM": "Energy",
    "CVX": "Energy",
    "COST": "Consumer",
    "WMT": "Consumer",
    "HD": "Consumer",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer",
    "XLP": "Consumer",
    "XLU": "Utilities",
    "ARKK": "Thematic",
    "TSM": "Technology",
    "ASML": "Technology",
    "PLTR": "Technology",
    "COIN": "Financials",
    "UBER": "Consumer",
}


def _dedupe_preserve(symbols: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if not sym.replace(".", "").isalnum():
            continue
        seen.add(sym)
        out.append(sym)
    return out


def default_expanded_universe() -> List[str]:
    return _dedupe_preserve(EXPANDED_LIQUID)


def load_symbols_from_file(path: str | Path) -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    tokens: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # CSV or whitespace
        for part in line.replace(";", ",").split(","):
            tokens.extend(part.split())
    return _dedupe_preserve(tokens)


def resolve_screener_symbols(
    configured: List[str] | None = None,
    *,
    env_symbols: str | None = None,
    env_file: str | None = None,
    use_expanded_default: bool = True,
    prefer_shared_scanned_list: bool = True,
) -> List[str]:
    """Resolve scan universe: file → env list → shared scanned_list → configured → default.

    Shared list (same path as trading_test methods lab):
      ~/.trading_agent/sync/scanned_list.json

    Env:
      TRADING_AGENT_SYMBOLS=AAPL,MSFT,NVDA
      TRADING_AGENT_SYMBOLS_FILE=/path/to/symbols.txt
      TRADING_AGENT_IGNORE_SCANNED_LIST=1
    """
    file_path = env_file if env_file is not None else os.getenv("TRADING_AGENT_SYMBOLS_FILE", "").strip()
    if file_path:
        from_file = load_symbols_from_file(file_path)
        if from_file:
            return from_file

    raw = env_symbols if env_symbols is not None else os.getenv("TRADING_AGENT_SYMBOLS", "").strip()
    if raw:
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        resolved = _dedupe_preserve(parts)
        if resolved:
            return resolved

    ignore_shared = os.getenv("TRADING_AGENT_IGNORE_SCANNED_LIST", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if prefer_shared_scanned_list and not ignore_shared:
        try:
            from trading_agent.export.scanned_list import symbols_from_scanned_list

            shared = symbols_from_scanned_list(prefer="universe", limit=0)
            if shared:
                return _dedupe_preserve(shared)
        except Exception:
            pass

    if configured:
        return _dedupe_preserve(configured)

    if use_expanded_default:
        return default_expanded_universe()
    return list(CORE_LIQUID)


def sector_for(symbol: str) -> str:
    return SECTOR_MAP.get(symbol.upper(), "Unknown")
