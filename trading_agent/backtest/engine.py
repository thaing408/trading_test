"""Multi-day offline backtest using real technicals, risk, ranking, and CIO decisions."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple
from zlib import adler32

from trading_agent.analysis.options import compute_options_metrics, iv_rank as compute_iv_rank
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.backtest.data import default_backtest_universe
from trading_agent.backtest.fills import (
    max_drawdown_from_equity,
    pnl_dollars,
    simulate_directional_exit,
    simulate_neutral_exit,
)
from trading_agent.backtest.models import (
    BacktestConfig,
    BacktestPeriodResult,
    DayResult,
    SimulatedTrade,
    SweepResult,
)
from trading_agent.cio.config import CIOConfig
from trading_agent.cio.decisions import process_all_candidates
from trading_agent.cio.loader import build_cio_approval_inputs
from trading_agent.cio.models import PhaseContext
from trading_agent.config import RiskConfig
from trading_agent.models import DailyTradingPlan, ScreenerCandidate, TradeOpportunity
from trading_agent.ranking.grades import GRADE_TRADE_GEOMETRY
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.regime import infer_market_regime
from trading_agent.risk.manager import evaluate_risk


ASSUMPTIONS = [
    "Fill model: entry at decision close; stop/target or time exit over hold_bars",
    "Options P/L via underlying path scaled to risk budget × GRADE_TRADE_GEOMETRY size",
    "Multi-regime synthetic OHLCV (bull/chop/bear/recovery) — deterministic, offline",
    "News/calendar thinned; research risk+ranking+CIO is the measured core",
    "Neutral strategies lose on range breaks; directional hit stops in counter-trend",
]


def _slice_bars(data: dict, end_idx: int, lookback: int) -> Tuple[list, list, list, list]:
    start = max(0, end_idx - lookback + 1)
    closes = list(data.get("close", []))[start : end_idx + 1]
    highs = list(data.get("high", closes))[start : end_idx + 1]
    lows = list(data.get("low", closes))[start : end_idx + 1]
    volumes = list(data.get("volume", [1_000_000] * len(closes)))[start : end_idx + 1]
    n = min(len(closes), len(highs), len(lows), len(volumes))
    return closes[-n:], highs[-n:], lows[-n:], volumes[-n:]


def _sector(symbol: str) -> str:
    return {
        "NVDA": "Technology",
        "AMD": "Technology",
        "AAPL": "Technology",
        "MSFT": "Technology",
        "GOOGL": "Technology",
        "META": "Technology",
        "AMZN": "Consumer",
        "TSLA": "Consumer",
        "JPM": "Financials",
        "XLF": "Financials",
        "SPY": "Broad Market",
        "QQQ": "Technology",
    }.get(symbol, "Unknown")


def _stable_seed(symbol: str, day_idx: int = 0) -> int:
    """Deterministic seed independent of PYTHONHASHSEED."""
    payload = f"{symbol}:{day_idx}".encode("utf-8")
    return adler32(payload) & 0xFFFFFFFF


def _make_candidate(
    symbol: str,
    price: float,
    volume: float,
    *,
    day_idx: int,
) -> ScreenerCandidate:
    # Vary liquidity/institutional scores by symbol+day so grades diversify
    seed = _stable_seed(symbol, day_idx) % 100
    inst = 40.0 + (seed % 50)
    liq = 45.0 + (seed % 45)
    rvol = 1.5 + (seed % 20) / 10.0  # 1.5–3.4
    spread = 0.5 + (seed % 25) / 10.0  # 0.5–3.0
    return ScreenerCandidate(
        symbol=symbol,
        price=round(price, 2),
        volume=int(max(volume, 2_500_000)),
        relative_volume=round(rvol, 2),
        options_liquidity_score=round(liq, 1),
        open_interest=5_000 + seed * 100,
        bid_ask_spread_pct=round(min(spread, 2.9), 2),
        sector=_sector(symbol),
        avg_daily_volume=3_000_000,
        market_cap=50_000_000_000,
        institutional_score=round(inst, 1),
        options_volume=5_000 + seed * 50,
    )


def _risk_from_bt(cfg: BacktestConfig) -> RiskConfig:
    return RiskConfig(
        min_confidence_score=cfg.min_confidence_score,
        min_setup_grade=cfg.min_setup_grade,
        prefer_a_tier_only=cfg.prefer_a_tier_only,
        min_technical_score=cfg.min_technical_score,
        min_probability_of_success=cfg.min_probability_of_success,
        top_candidates=cfg.max_trades_per_day,
        # Soften rvol/spread floors so synthetic candidates aren't mass-rejected
        min_relative_volume=1.5,
        max_bid_ask_spread_pct=3.0,
        min_institutional_score=35.0,
    )


def _cio_from_bt(cfg: BacktestConfig) -> CIOConfig:
    return CIOConfig(
        fixture_mode=True,
        portfolio_value=cfg.portfolio_value,
        min_confidence=cfg.cio_min_confidence,
        min_risk_reward=cfg.cio_min_risk_reward,
    )


def _analyze_symbol(
    symbol: str,
    ohlcv: dict,
    day_idx: int,
    lookback: int,
    bench_closes: List[float] | None,
) -> Tuple[ScreenerCandidate, object, object] | None:
    data = ohlcv.get(symbol) or {}
    closes_full = list(data.get("close") or [])
    if len(closes_full) <= day_idx or day_idx < 15:
        return None
    closes, highs, lows, volumes = _slice_bars(data, day_idx, lookback)
    if len(closes) < 15:
        return None
    price = float(closes[-1])
    vol = float(volumes[-1]) if volumes else 3_000_000
    candidate = _make_candidate(symbol, price, vol, day_idx=day_idx)
    bench = bench_closes[-len(closes) :] if bench_closes else closes
    technical = compute_technical_analysis(
        symbol, closes, highs, lows, volumes, benchmark_closes=bench
    )
    # Regime-aware IV: chop/bear days → higher IV rank; calm bull → lower
    rets = [
        abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100
        for i in range(1, len(closes))
    ]
    realized = float(sum(rets[-10:]) / max(len(rets[-10:]), 1)) if rets else 1.0
    # Fixed history so iv_rank actually moves with current IV
    iv_hist = list(data.get("iv_history") or [18, 20, 22, 25, 28, 32, 35, 40, 30, 24])
    base_iv = float(data.get("iv") or 28.0)
    # Scale current IV by recent realized vol so rank spans low/mid/high
    current_iv = max(12.0, min(55.0, base_iv * (0.6 + realized * 0.8)))
    # Nudge by day so not all symbols share rank (stable across processes)
    current_iv += (_stable_seed(symbol, day_idx) % 9) - 4
    rank = compute_iv_rank(current_iv, iv_hist)
    # Inject rank-aware history endpoints so options.iv_rank matches intent
    if rank < 35:
        iv_hist = [current_iv + 5, current_iv + 10, current_iv + 15, current_iv + 8]
    elif rank > 60:
        iv_hist = [current_iv - 15, current_iv - 10, current_iv - 5, current_iv - 12]

    strike = round(price * (1.02 if technical.trend == "uptrend" else 0.98), 2)
    options = compute_options_metrics(
        symbol=symbol,
        price=price,
        iv=current_iv,
        iv_history=iv_hist,
        strike=strike,
        days_to_expiry=30,
        open_interest=candidate.open_interest,
        relative_volume=candidate.relative_volume,
        bid_ask_spread_pct=candidate.bid_ask_spread_pct,
        trend=technical.trend,
        options_volume=candidate.options_volume,
    )
    return candidate, technical, options


def _research_day(
    ohlcv: Dict[str, dict],
    day_idx: int,
    cfg: BacktestConfig,
    symbols: Sequence[str],
) -> Tuple[List[TradeOpportunity], int, int]:
    spy = ohlcv.get("SPY") or ohlcv.get(symbols[0], {})
    spy_closes = list(spy.get("close") or [])
    bench = spy_closes[: day_idx + 1] if spy_closes else None

    analyzed = []
    for symbol in symbols:
        pack = _analyze_symbol(symbol, ohlcv, day_idx, cfg.lookback_bars, bench)
        if pack:
            analyzed.append(pack)

    risk = _risk_from_bt(cfg)
    qualified, _rejected = evaluate_risk(analyzed, risk)
    opps = build_opportunities(qualified, risk, max_count=cfg.max_trades_per_day)
    return opps, len(analyzed), len(qualified)


def _env_score_for_day(day_idx: int, total_bars: int) -> float:
    """Map bar index to environment score (weaker in bear segment)."""
    # 4 regimes of ~equal length
    frac = day_idx / max(total_bars, 1)
    if frac < 0.25:
        return 62.0
    if frac < 0.50:
        return 52.0
    if frac < 0.75:
        return 38.0  # elevated uncertainty / bear
    return 58.0


def _cio_filter(
    opps: List[TradeOpportunity],
    cfg: BacktestConfig,
    env_score: float = 60.0,
) -> List[TradeOpportunity]:
    if not opps:
        return []
    # Below ~42 CIO rejects all as cash mandate — reflect regime
    if env_score < 42:
        return []
    bias = (
        "Bullish" if env_score >= 55 else "Neutral" if env_score >= 45 else "Bearish"
    )
    plan = DailyTradingPlan(
        date="backtest",
        overall_market_bias=bias,
        market_environment_score=env_score,
        top_watchlist=[o.symbol for o in opps],
        ranked_opportunities=opps,
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    candidates, context = build_cio_approval_inputs(plan, fixture_mode=True)
    context = PhaseContext(
        overall_market_bias=plan.overall_market_bias,
        market_environment_score=env_score,
        market_regime=infer_market_regime(plan.overall_market_bias),
        stay_in_cash=False,
        intraday_flags={},
        strategy_refinement=context.strategy_refinement,
        sector_refinement=context.sector_refinement,
        weakest_strategies=context.weakest_strategies,
        performance_notes=context.performance_notes,
    )
    approved, modified, _rejected = process_all_candidates(
        candidates, context, _cio_from_bt(cfg)
    )
    ok = {t.ticker for t in approved + modified}
    return [o for o in opps if o.symbol in ok]


def _geometry_size(grade: str) -> float:
    """Use shipped GRADE_TRADE_GEOMETRY size multiplier (index 3)."""
    geom = GRADE_TRADE_GEOMETRY.get(grade or "C") or GRADE_TRADE_GEOMETRY["C"]
    return float(geom[3])


def _simulate_trade(
    opp: TradeOpportunity,
    ohlcv: dict,
    day_idx: int,
    cfg: BacktestConfig,
) -> SimulatedTrade | None:
    data = ohlcv.get(opp.symbol) or {}
    closes = list(data.get("close") or [])
    highs = list(data.get("high") or closes)
    lows = list(data.get("low") or closes)
    if day_idx + 1 >= len(closes):
        return None
    end = min(len(closes) - 1, day_idx + cfg.hold_bars)
    fh = highs[day_idx + 1 : end + 1]
    fl = lows[day_idx + 1 : end + 1]
    fc = closes[day_idx + 1 : end + 1]
    entry = float(opp.entry_price)
    stop = float(opp.stop_loss)
    target = float(opp.profit_target)
    grade = getattr(opp, "setup_grade", "") or "C"
    size_m = _geometry_size(grade)
    if size_m <= 0:
        return None
    risk_dollars = cfg.portfolio_value * (cfg.risk_per_trade_pct / 100.0) * size_m

    strategy = opp.strategy or ""
    direction = (opp.direction or "").lower()
    # Iron Condor / calendar → neutral premium path; never directional short-by-default
    neutral = "Condor" in strategy or strategy in ("Calendar Spread",)
    # Bull put / covered call / debit call / long call → long-bias even if direction mislabeled
    credit_bull = strategy in (
        "Bull Put Credit Spread",
        "Covered Call",
        "Debit Spread",
        "Long Call",
        "Diagonal Spread",
    )
    credit_bear = strategy in ("Bear Call Credit Spread", "Long Put", "Cash Secured Put")
    if neutral:
        bullish = False
        use_directional = False
    elif credit_bull or direction.startswith("bull"):
        bullish = True
        use_directional = True
    elif credit_bear or direction.startswith("bear"):
        bullish = False
        use_directional = True
    else:
        # Unknown / Neutral direction: prefer neutral fill, not inverted short
        bullish = True
        use_directional = False
        neutral = True

    trend_strength = 0.0
    if day_idx >= 5:
        window = closes[day_idx - 5 : day_idx + 1]
        trend_strength = (window[-1] - window[0]) / max(abs(window[0]), 1e-9)

    if neutral or not use_directional:
        atr = max(abs(target - entry), entry * 0.015)
        exit_px, reason, held = simulate_neutral_exit(
            entry,
            atr,
            fh,
            fl,
            fc,
            band_pct=0.012,
            trend_strength=trend_strength,
        )
        pl = round(risk_dollars * ((exit_px - entry) / max(atr, entry * 0.005)), 2)
        if reason == "range_break" and pl > 0:
            pl = -abs(risk_dollars)
    else:
        exit_px, reason, held = simulate_directional_exit(
            entry, stop, target, fh, fl, fc, bullish=bullish
        )
        pl = pnl_dollars(
            entry,
            exit_px,
            bullish=bullish,
            risk_dollars=risk_dollars,
            stop=stop,
            exit_reason=reason,
        )

    return SimulatedTrade(
        symbol=opp.symbol,
        strategy=opp.strategy,
        direction=opp.direction or "Bullish",
        entry_price=entry,
        exit_price=exit_px,
        stop_loss=stop,
        profit_target=target,
        entry_day_index=day_idx,
        exit_day_index=day_idx + held,
        exit_reason=reason,
        profit_loss=pl,
        grade=grade,
        confidence=opp.confidence_score,
        approved=True,
    )


def load_fixture_ohlcv() -> Dict[str, dict]:
    """Default backtest universe: multi-regime synthetic (offline)."""
    return default_backtest_universe()


def _max_common_bars(ohlcv: Dict[str, dict], symbols: Sequence[str]) -> int:
    lengths = []
    for s in symbols:
        c = ohlcv.get(s, {}).get("close") or []
        if c:
            lengths.append(len(c))
    return min(lengths) if lengths else 0


def run_backtest(
    cfg: BacktestConfig,
    ohlcv: Dict[str, dict] | None = None,
    symbols: Sequence[str] | None = None,
) -> BacktestPeriodResult:
    data = ohlcv or load_fixture_ohlcv()
    preferred = ["NVDA", "AMD", "AAPL", "MSFT", "SPY", "QQQ", "TSLA", "META", "AMZN", "JPM"]
    syms = list(symbols or [s for s in preferred if s in data] or list(data.keys())[:10])

    n_bars = _max_common_bars(data, syms)
    start = max(cfg.lookback_bars, 20)
    end = n_bars - cfg.hold_bars - 1
    if end <= start:
        end = max(start + 1, n_bars - 2)

    days: List[DayResult] = []
    all_trades: List[SimulatedTrade] = []
    equity = cfg.portfolio_value
    curve = [equity]
    cash_samples: List[float] = []

    for day_idx in range(start, max(start + 1, end + 1)):
        opps, screened, qualified = _research_day(data, day_idx, cfg, syms)
        env = _env_score_for_day(day_idx, n_bars)
        approved_opps = _cio_filter(opps, cfg, env_score=env)
        day_trades: List[SimulatedTrade] = []
        for opp in approved_opps[: cfg.max_trades_per_day]:
            t = _simulate_trade(opp, data, day_idx, cfg)
            if t:
                day_trades.append(t)
                all_trades.append(t)
                equity += t.profit_loss
        day_pnl = sum(t.profit_loss for t in day_trades)
        used = len(day_trades) * cfg.risk_per_trade_pct * 5
        cash_pct = max(0.0, 100.0 - used)
        cash_samples.append(cash_pct)
        curve.append(equity)
        days.append(
            DayResult(
                day_index=day_idx,
                candidates_screened=screened,
                research_opportunities=len(opps),
                cio_approved=len(approved_opps),
                trades=day_trades,
                day_pnl=round(day_pnl, 2),
                cash_pct=cash_pct,
                notes=f"qualified={qualified};env={env:.0f}",
            )
        )

    winners = [t for t in all_trades if t.profit_loss > 0]
    losers = [t for t in all_trades if t.profit_loss < 0]
    total_pnl = sum(t.profit_loss for t in all_trades)
    gross_win = sum(t.profit_loss for t in winners)
    gross_loss = abs(sum(t.profit_loss for t in losers))
    pf = gross_win / gross_loss if gross_loss else float(gross_win > 0)

    return BacktestPeriodResult(
        config_name=cfg.name,
        config=cfg,
        days=days,
        trades=all_trades,
        total_pnl=round(total_pnl, 2),
        win_rate=round(len(winners) / len(all_trades), 4) if all_trades else 0.0,
        trade_count=len(all_trades),
        winner_count=len(winners),
        loser_count=len(losers),
        expectancy=round(total_pnl / len(all_trades), 2) if all_trades else 0.0,
        max_drawdown=max_drawdown_from_equity(curve),
        profit_factor=round(pf, 2) if gross_loss or gross_win else 0.0,
        avg_cash_pct=round(sum(cash_samples) / len(cash_samples), 1) if cash_samples else 100.0,
        equity_curve=curve,
        assumptions=list(ASSUMPTIONS),
        metadata={
            "symbols": ",".join(syms),
            "days_simulated": str(len(days)),
            "start_bar": str(start),
            "end_bar": str(end),
            "strategies": ",".join(sorted({t.strategy for t in all_trades})),
            "grades": ",".join(sorted({t.grade for t in all_trades})),
        },
    )


def default_sweep_configs() -> List[BacktestConfig]:
    """Configs that must diverge on multi-regime data (including 3 vs 5 book size)."""
    return [
        BacktestConfig(
            name="baseline_grade_C_book3",
            min_confidence_score=55.0,
            min_setup_grade="C",
            prefer_a_tier_only=False,
            min_technical_score=40.0,
            cio_min_confidence=60.0,
            max_trades_per_day=3,
        ),
        BacktestConfig(
            name="wide_book5_grade_C",
            min_confidence_score=55.0,
            min_setup_grade="C",
            prefer_a_tier_only=False,
            min_technical_score=40.0,
            cio_min_confidence=60.0,
            max_trades_per_day=5,
        ),
        BacktestConfig(
            name="strict_a_tier_book3",
            min_confidence_score=60.0,
            min_setup_grade="B",
            prefer_a_tier_only=True,
            min_technical_score=45.0,
            cio_min_confidence=65.0,
            max_trades_per_day=3,
        ),
        BacktestConfig(
            name="high_confidence_book3",
            min_confidence_score=70.0,
            min_setup_grade="B",
            prefer_a_tier_only=False,
            min_technical_score=50.0,
            cio_min_confidence=70.0,
            max_trades_per_day=3,
        ),
    ]


def score_period(result: BacktestPeriodResult) -> float:
    """Capital-preservation score: expectancy + PF + P/L − drawdown − overtrading."""
    port = max(result.config.portfolio_value, 1.0)
    dd_pen = result.max_drawdown / port * 100.0
    pnl_term = result.total_pnl / 1000.0
    # Mild penalty for huge trade counts with flat expectancy (capital churn)
    churn = max(0, result.trade_count - 40) * 0.15
    return (
        result.expectancy * 2.0
        + result.profit_factor * 12.0
        + result.win_rate * 25.0
        + pnl_term
        - dd_pen * 4.0
        - churn
        + (5.0 if 5 <= result.trade_count <= 80 else -8.0)
    )


def run_config_sweep(
    configs: List[BacktestConfig] | None = None,
    ohlcv: Dict[str, dict] | None = None,
) -> SweepResult:
    data = ohlcv or load_fixture_ohlcv()
    variants = configs or default_sweep_configs()
    results = [run_backtest(c, ohlcv=data) for c in variants]
    ranked = sorted(results, key=score_period, reverse=True)
    best = ranked[0].config_name if ranked else ""
    return SweepResult(
        results=results,
        best_name=best,
        objective="maximize expectancy+PF+win_rate+P/L − drawdown − churn (capital preservation)",
        ranking=[r.config_name for r in ranked],
    )


def apply_best_to_risk_defaults(best: BacktestConfig) -> RiskConfig:
    return RiskConfig(
        min_confidence_score=best.min_confidence_score,
        min_setup_grade=best.min_setup_grade,
        prefer_a_tier_only=best.prefer_a_tier_only,
        min_technical_score=best.min_technical_score,
        min_probability_of_success=best.min_probability_of_success,
        top_candidates=best.max_trades_per_day,
    )
