"""Playlist book merge / tags for researcher handoff."""

from trading_agent.export.playlist_book import (
    apply_playlist_tag,
    merge_playlist_into_symbols,
    playlist_candidate_symbols,
)


def test_playlist_candidates_and_merge():
    book = {
        "candidates": [
            {"symbol": "NVDA", "score": 80},
            {"symbol": "aapl"},
            "MSFT",
        ]
    }
    assert playlist_candidate_symbols(book) == ["NVDA", "AAPL", "MSFT"]
    merged = merge_playlist_into_symbols(["SPY", "QQQ"], book=book, enabled=True)
    assert merged[:2] == ["SPY", "QQQ"]
    assert "NVDA" in merged and "AAPL" in merged and "MSFT" in merged
    # no force when disabled
    assert merge_playlist_into_symbols(["SPY"], book=book, enabled=False) == ["SPY"]


def test_playlist_tag():
    book = {"candidates": [{"symbol": "SHOP"}]}
    tags, note = apply_playlist_tag("SHOP", ["other"], book=book)
    assert "watchlist_playlist" in tags
    assert "not CIO" in note.lower() or "playlist" in note.lower()
    tags2, note2 = apply_playlist_tag("ZZZ", [], book=book)
    assert "watchlist_playlist" not in tags2
    assert note2 == ""
