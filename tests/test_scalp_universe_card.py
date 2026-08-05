"""Scalp universe card — gainer/loser link to QQQ rules."""

from trading_agent.scalp.universe_card import format_scalp_universe_card


def test_format_card_from_payload():
    universe = {
        "system": "desk+movers+policy",
        "trading_date": "2026-08-05",
        "updated_at": "2026-08-05T12:00:00Z",
        "scan_symbols": ["PLTR", "NVDA", "USO", "ARM"],
        "desk_symbols": ["NVDA", "PLTR"],
        "movers_symbols": ["PLTR", "ARM", "USO"],
        "movers_tags": {
            "PLTR": {"tag": "gainer", "change_pct": 5.0},
            "ARM": {"tag": "gainer", "change_pct": 4.0},
            "USO": {"tag": "loser", "change_pct": -3.5},
        },
        "movers_policy": {
            "gainer_calls_only": True,
            "allow_loser_puts": True,
            "skip_both": True,
            "skip_vol_etfs": True,
            "loser_min_abs_pct": 3.0,
            "max_loser_entries_per_day": 1,
        },
    }
    text = format_scalp_universe_card(universe, universe_path="/tmp/u.json")
    assert "SCALP UNIVERSE LINK" in text
    assert "GAINER" in text and "CALL" in text
    assert "LOSER" in text and "PUT" in text
    assert "PLTR" in text and "USO" in text
    assert "NVDA" in text
    assert "QQQ scalp" in text or "scalp engine" in text
