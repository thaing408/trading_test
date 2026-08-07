"""Researcher lists are merged into CIO candidate board."""

from trading_agent.cio.models import PhaseContext, TradeCandidate
from trading_agent.export.researcher_cio import merge_researcher_into_cio_candidates


def test_merge_appends_gap_and_playlist(tmp_path, monkeypatch):
    sync = tmp_path / "sync"
    sync.mkdir()
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(sync))
    monkeypatch.setenv("TRADING_AGENT_RESEARCHER_CIO", "1")
    (sync / "watchlist_playlist.json").write_text(
        '{"candidates":[{"symbol":"SHOP","score":70,"metrics":{"price":100,"rs_20":1.6,"adr_pct":4}}]}',
        encoding="utf-8",
    )
    (sync / "gap_screener_book.json").write_text(
        '{"continuation":[{"symbol":"MSFT"}],'
        '"candidates":[{"symbol":"MSFT","state":"continuation","continuation_bias":"long",'
        '"last_price":400,"gap_pct":5,"notes":"test gap","rank_score":80}]}',
        encoding="utf-8",
    )
    # force reload paths via env already
    from trading_agent.export import gap_book, playlist_book

    monkeypatch.setattr(gap_book, "default_sync_dir", lambda: sync)
    monkeypatch.setattr(playlist_book, "default_sync_dir", lambda: sync)

    existing = [
        TradeCandidate(
            symbol="AAPL",
            direction="Bullish",
            strategy="Debit Call Spread",
            entry_price=100,
            strike_prices=[100, 105],
            expiration="2026-09-01",
            profit_target=110,
            stop_loss=95,
            maximum_risk=100,
            maximum_reward=200,
            probability_of_success=0.5,
            confidence_score=60,
            primary_catalyst="technical",
            catalyst_type="technical",
            technical_summary="x",
            technical_confirmations=["trend:up"],
            options_summary="ok",
            open_interest=1000,
            daily_options_volume=1000,
            bid_ask_spread_pct=2,
            iv_rank=30,
            expected_move_pct=3,
            probability_of_profit=0.5,
            liquidity_score=60,
            sector="Technology",
            phase1_rank=1,
        )
    ]
    ctx = PhaseContext(
        overall_market_bias="Bullish",
        market_environment_score=60,
        market_regime="bullish",
    )
    merged, ctx2, meta = merge_researcher_into_cio_candidates(existing, ctx)
    syms = {c.symbol for c in merged}
    assert "SHOP" in syms
    assert "MSFT" in syms
    assert "AAPL" in syms
    assert "SHOP" in meta["appended"]
    assert ctx2 is not None
    assert any("Researcher" in ln for ln in (ctx2.research_board_lines or []))


def test_merge_boosts_existing_phase1(tmp_path, monkeypatch):
    sync = tmp_path / "sync"
    sync.mkdir()
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(sync))
    monkeypatch.setenv("TRADING_AGENT_RESEARCHER_CIO", "1")
    monkeypatch.setenv("TRADING_AGENT_RESEARCHER_CIO_BOOST", "10")
    (sync / "watchlist_playlist.json").write_text(
        '{"candidates":[{"symbol":"NVDA","score":80,"metrics":{"price":200,"rs_20":1.8}}]}',
        encoding="utf-8",
    )
    (sync / "gap_screener_book.json").write_text('{"continuation":[],"candidates":[]}', encoding="utf-8")
    from trading_agent.export import gap_book, playlist_book

    monkeypatch.setattr(gap_book, "default_sync_dir", lambda: sync)
    monkeypatch.setattr(playlist_book, "default_sync_dir", lambda: sync)

    existing = [
        TradeCandidate(
            symbol="NVDA",
            direction="Bullish",
            strategy="Debit Call Spread",
            entry_price=200,
            strike_prices=[200, 210],
            expiration="2026-09-01",
            profit_target=220,
            stop_loss=190,
            maximum_risk=100,
            maximum_reward=200,
            probability_of_success=0.5,
            confidence_score=60,
            primary_catalyst="technical",
            catalyst_type="technical",
            technical_summary="x",
            technical_confirmations=["trend:up"],
            options_summary="ok",
            open_interest=1000,
            daily_options_volume=1000,
            bid_ask_spread_pct=2,
            iv_rank=30,
            expected_move_pct=3,
            probability_of_profit=0.5,
            liquidity_score=60,
            sector="Technology",
            phase1_rank=1,
        )
    ]
    ctx = PhaseContext(overall_market_bias="Bullish", market_environment_score=60, market_regime="bullish")
    merged, _, meta = merge_researcher_into_cio_candidates(existing, ctx)
    assert meta["boosted"] == ["NVDA"]
    nv = next(c for c in merged if c.symbol == "NVDA")
    assert nv.confidence_score >= 70
    assert any("researcher:playlist" in t for t in nv.technical_confirmations)
