"""Market scan for pulse / Discord: rank desk screener universe by day change.

Uses the same symbol list as Trading Research (`resolve_screener_symbols` /
`TRADING_AGENT_SYMBOLS` / expanded liquid universe) — not a fixed 4-name loop.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from trading_agent.screener.universe import resolve_screener_symbols, sector_for


@dataclass
class MoverRow:
    symbol: str
    change_pct: float
    last: Optional[float] = None
    sector: str = ""
    source: str = "yfinance"


@dataclass
class MarketScanResult:
    universe_size: int
    scanned: int
    gainers: List[MoverRow] = field(default_factory=list)
    losers: List[MoverRow] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    source: str = "screener_universe"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "universe_size": self.universe_size,
            "scanned": self.scanned,
            "source": self.source,
            "gainers": [asdict(r) for r in self.gainers],
            "losers": [asdict(r) for r in self.losers],
            "errors": self.errors,
        }


def _batch_day_changes(symbols: List[str]) -> tuple[List[MoverRow], List[str]]:
    """Fetch last vs prior close % change via yfinance (desk default free path)."""
    errors: List[str] = []
    rows: List[MoverRow] = []
    if not symbols:
        return rows, errors
    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        return rows, [f"yfinance unavailable: {exc}"]

    # Chunk to avoid huge single requests
    chunk = max(10, int(os.getenv("TRADING_AGENT_SCAN_CHUNK", "40")))
    for i in range(0, len(symbols), chunk):
        batch = symbols[i : i + chunk]
        try:
            data = yf.download(
                batch,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"download {batch[:3]}…: {exc}")
            continue
        if data is None or getattr(data, "empty", True):
            errors.append(f"empty bars for chunk starting {batch[0]}")
            continue

        # Multi-ticker columns are MultiIndex (ticker, field) or (field, ticker)
        for sym in batch:
            try:
                if len(batch) == 1:
                    closes = data["Close"].dropna()
                else:
                    # yfinance multi: often columns.levels[0] are tickers
                    if hasattr(data.columns, "levels") and sym in data.columns.get_level_values(0):
                        closes = data[sym]["Close"].dropna()
                    elif hasattr(data.columns, "levels") and "Close" in data.columns.get_level_values(0):
                        closes = data["Close"][sym].dropna()
                    else:
                        closes = data[sym]["Close"].dropna()
                if len(closes) < 2:
                    continue
                prev = float(closes.iloc[-2])
                last = float(closes.iloc[-1])
                if prev <= 0:
                    continue
                chg = (last - prev) / prev * 100.0
                rows.append(
                    MoverRow(
                        symbol=sym.upper(),
                        change_pct=round(chg, 2),
                        last=round(last, 2),
                        sector=sector_for(sym),
                        source="yfinance",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sym}: {exc}")
    return rows, errors


def run_market_scan(
    *,
    top_n: int = 8,
    max_symbols: int | None = None,
    symbols: List[str] | None = None,
) -> MarketScanResult:
    """Rank desk screener universe by day % change → gainers / losers."""
    universe = symbols or resolve_screener_symbols()
    cap = max_symbols
    if cap is None:
        env_cap = os.getenv("TRADING_AGENT_SCAN_MAX_SYMBOLS", "").strip()
        if env_cap.isdigit() and int(env_cap) > 0:
            cap = int(env_cap)
    if cap and cap > 0:
        universe = universe[:cap]

    rows, errors = _batch_day_changes(universe)
    gainers = sorted(
        [r for r in rows if r.change_pct > 0],
        key=lambda r: r.change_pct,
        reverse=True,
    )[:top_n]
    losers = sorted(
        [r for r in rows if r.change_pct < 0],
        key=lambda r: r.change_pct,
    )[:top_n]

    return MarketScanResult(
        universe_size=len(universe),
        scanned=len(rows),
        gainers=gainers,
        losers=losers,
        errors=errors[:12],
        source="screener_universe+yfinance",
    )


def format_market_scan_block(result: MarketScanResult) -> str:
    lines = [
        f"**Market scan** (desk universe n={result.universe_size}, "
        f"scanned {result.scanned} — code screener, not fixed 4-name loop)",
    ]
    for title, rows in (("Gainers", result.gainers), ("Losers", result.losers)):
        if not rows:
            lines.append(f"_{title}: none_")
            continue
        lines.append(f"*{title}*")
        lines.append("```")
        lines.append(f"{'SYM':<6} {'CHG%':>7}  {'PX':>8}  SECTOR")
        for r in rows:
            px = f"${r.last:.2f}" if r.last is not None else "   n/a"
            lines.append(
                f"{r.symbol:<6} {r.change_pct:+7.2f}  {px:>8}  {r.sector[:12]}"
            )
        lines.append("```")
    if result.errors:
        lines.append(f"_Scan notes: {len(result.errors)} fetch issue(s)_")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Desk-universe market scan (gainers/losers)")
    p.add_argument("--top", type=int, default=8, help="Top N gainers and losers")
    p.add_argument("--max-symbols", type=int, default=0, help="Cap universe size (0=all)")
    p.add_argument("--json", action="store_true", help="Print JSON")
    args = p.parse_args(argv)
    res = run_market_scan(
        top_n=args.top,
        max_symbols=args.max_symbols or None,
    )
    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        print(format_market_scan_block(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
