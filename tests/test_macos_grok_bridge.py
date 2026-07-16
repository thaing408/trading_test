"""macOS Grok pipeline integration checks for trading_agent desk automation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
MACOS_SCRIPTS = REPO_ROOT / "scripts" / "macos"
GROK_SCRIPTS = HOME / ".grok" / "scripts"
POSITIONS_PY = MACOS_SCRIPTS / "trading-agent-positions.py"


def _load_positions_module():
    spec = importlib.util.spec_from_file_location("trading_agent_positions", POSITIONS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_macos_desk_scripts_exist():
    assert (MACOS_SCRIPTS / "trading-agent-desk.sh").is_file()
    assert (MACOS_SCRIPTS / "trading-agent-positions.sh").is_file()
    assert (MACOS_SCRIPTS / "install-trading-agent-launchd.sh").is_file()
    assert (MACOS_SCRIPTS / "com.grok.trading-agent-desk.plist").is_file()
    assert (MACOS_SCRIPTS / "install-auto-trade-launchd.sh").is_file()
    assert (MACOS_SCRIPTS / "com.grok.qt-open-window.plist").is_file()
    assert (MACOS_SCRIPTS / "com.grok.auto-trade-consumer.plist").is_file()
    assert (MACOS_SCRIPTS / "qt-open-window.sh").is_file()
    assert (MACOS_SCRIPTS / "auto-trade-consumer.sh").is_file()
    assert (MACOS_SCRIPTS / "consume_auto_trade_book.py").is_file()


def test_schwab_positions_converter_option_and_equity():
    mod = _load_positions_module()
    sample = {
        "positions": [
            {
                "symbol": "ORCL  260717C00220000",
                "asset_type": "OPTION",
                "quantity": 1.0,
                "average_price": 4.1566,
                "market_value": 4.0,
                "description": "ORACLE CORP 07/17/2026 $220 Call",
            },
            {
                "symbol": "QS",
                "asset_type": "EQUITY",
                "quantity": 500.0,
                "average_price": 14.2,
                "market_value": 3302.5,
            },
        ]
    }
    out = mod.schwab_to_trading_agent(sample)
    assert len(out["positions"]) == 2
    orcl = out["positions"][0]
    assert orcl["symbol"] == "ORCL"
    assert orcl["strategy"] == "Long Call"
    assert orcl["strike_prices"] == [220.0]
    assert orcl["expiration"] == "2026-07-17"
    qs = out["positions"][1]
    assert qs["symbol"] == "QS"
    assert qs["strategy"] == "Long Equity"
    assert qs["quantity"] == 500


def test_schwab_converter_skips_zero_quantity():
    mod = _load_positions_module()
    sample = {
        "positions": [
            {
                "symbol": "TSLA",
                "asset_type": "EQUITY",
                "quantity": 0.0,
                "average_price": 250.0,
                "market_value": 0.0,
            },
            {
                "symbol": "AAPL",
                "asset_type": "EQUITY",
                "quantity": 10.0,
                "average_price": 200.0,
                "market_value": 2100.0,
            },
        ]
    }
    out = mod.schwab_to_trading_agent(sample)
    assert [p["symbol"] for p in out["positions"]] == ["AAPL"]


def test_trading_agent_env_example_has_no_preopen_cap():
    active = [
        line.strip()
        for line in (MACOS_SCRIPTS / "trading-agent.env.example").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "TRADING_AGENT_UNTIL_PHASE=preopen" not in active