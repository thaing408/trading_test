"""CLI entry point for trading agent (pre-market + intraday)."""

from __future__ import annotations

import argparse
import sys

from trading_agent.config import AgentConfig
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.intraday.reporter import render_intraday_report
from trading_agent.cio.config import CIOConfig
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.cio.reporter import render_cio_report
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.performance.reporter import render_performance_report
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan
from trading_agent.runtime.stdio import configure_stdio
from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import run_session_cli
from trading_agent.session.schedule import DeskPhaseKind


def _run_odte(args: argparse.Namespace) -> int:
    from trading_agent.odte.playbook import OdtePlaybookConfig, format_odte_brief, run_odte_playbook
    from trading_agent.strategy.style import TradingStyle, format_style_brief, parse_trading_style

    style = parse_trading_style(getattr(args, "style", None))
    mode = (getattr(args, "mode", None) or "0dte").strip().lower()
    dte = int(getattr(args, "dte", 0) or 0)

    # Explicit breakout style → OR continuation path (HTF)
    if style is TradingStyle.BREAKOUT or mode == "breakout":
        from trading_agent.odte.breakout import (
            BreakoutPlaybookConfig,
            format_breakout_brief,
            render_breakout_backtest,
            run_breakout_backtest,
        )

        interval = getattr(args, "interval", None) or "15m"
        period = "60d" if args.period == "7d" else args.period
        if dte <= 0 and mode in ("2dte", "3dte", "weekly"):
            dte = {"2dte": 2, "3dte": 3, "weekly": 5}.get(mode, 5)
        cfg = BreakoutPlaybookConfig(
            symbol=args.symbol.upper(),
            account_size=float(args.account),
            target_dte=dte or 5,
            bar_interval=interval,
            puts_only=bool(getattr(args, "puts_only", False)),
        )
        source = getattr(args, "source", "auto") or "auto"
        if getattr(args, "backtest", False):
            result = run_breakout_backtest(
                cfg.symbol, period=period, cfg=cfg, data_source=source
            )
            text = render_breakout_backtest(result)
            print(text)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as handle:
                    handle.write(text)
            return 0
        # Simple visual 888 TI decision card (not long rule lists)
        text = format_breakout_brief(
            cfg.symbol, cfg=cfg, data_source=source, period="5d", live=True
        )
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0

    # --dte 2/3/5/7 or --mode weekly|2dte|3dte|multidte implies multi-DTE path
    if mode in ("weekly", "2dte", "3dte", "multidte", "multi") or dte > 0:
        from trading_agent.odte.multidte import (
            MultidtePlaybookConfig,
            format_multidte_brief,
            render_multidte_backtest,
            run_multidte_backtest,
        )

        if mode == "2dte":
            dte = dte or 2
        elif mode == "3dte":
            dte = dte or 3
        elif mode in ("weekly", "multidte", "multi"):
            dte = dte or 5
        dte = dte or 5
        interval = getattr(args, "interval", None) or "15m"
        # multi-DTE: default 60d for yfinance when user left 0DTE default period
        period = "60d" if args.period == "7d" else args.period
        cfg = MultidtePlaybookConfig(
            symbol=args.symbol.upper(),
            account_size=float(args.account),
            target_dte=dte,
            bar_interval=interval,
            # MultidtePlaybookConfig defaults puts_only=True; flag is explicit opt-in no-op
            puts_only=True if getattr(args, "puts_only", False) else True,
        )
        source = getattr(args, "source", "auto") or "auto"
        if getattr(args, "backtest", False):
            result = run_multidte_backtest(
                cfg.symbol,
                period=period,
                cfg=cfg,
                data_source=source,
            )
            text = format_style_brief(TradingStyle.MEAN_REVERSION) + render_multidte_backtest(
                result
            )
            print(text)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as handle:
                    handle.write(text)
            return 0
        text = format_style_brief(TradingStyle.MEAN_REVERSION) + format_multidte_brief(
            cfg.symbol, cfg=cfg
        )
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0

    if getattr(args, "backtest", False):
        from trading_agent.odte.backtest import render_odte_backtest, run_odte_backtest

        cfg = OdtePlaybookConfig(symbol=args.symbol.upper(), account_size=float(args.account))
        if getattr(args, "legacy_rules", False):
            # Pre-improvement defaults for A/B comparison on same bars
            cfg.use_whole_dollar_levels = True
            cfg.take_profit_pct = 0.20
            cfg.stop_loss_pct = 0.125
        if getattr(args, "puts_only", False):
            cfg.call_rsi = -1.0  # disable CALL entries
        source = getattr(args, "source", "auto") or "auto"
        result = run_odte_backtest(
            cfg.symbol,
            period=args.period,
            cfg=cfg,
            data_source=source,
        )
        text = format_style_brief(TradingStyle.MEAN_REVERSION) + render_odte_backtest(result)
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0

    cfg = OdtePlaybookConfig(symbol=args.symbol.upper(), account_size=float(args.account))
    brief = run_odte_playbook(cfg)
    text = format_style_brief(TradingStyle.MEAN_REVERSION) + format_odte_brief(brief)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0 if not brief.errors or brief.levels.last > 0 else 1


def _run_qt(args: argparse.Namespace) -> int:
    from trading_agent.qt.model import (
        QtModelConfig,
        export_qt_auto_trade_book,
        format_qt_brief,
        run_qt_model,
    )

    symbols = [s.upper() for s in (args.symbols or ["QQQ", "SPY", "IWM"])]
    rr = float(getattr(args, "rr", 2.0) or 2.0)
    texts: list[str] = []
    for sym in symbols:
        cfg = QtModelConfig(symbol=sym, rr_default=rr)
        brief = run_qt_model(sym, cfg=cfg)
        texts.append(format_qt_brief(brief))
    text = "\n\n".join(texts)
    if getattr(args, "export", False):
        book = export_qt_auto_trade_book(symbols)
        text += (
            f"\n\n# Auto-trade export\n"
            f"entries={book.get('entry_count')} stay_in_cash={book.get('stay_in_cash')}\n"
            f"paths={book.get('_written_paths')}\n"
        )
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


def _run_oms(args: argparse.Namespace) -> int:
    cmd = getattr(args, "oms_command", None) or "status"
    if cmd == "status":
        import json

        from trading_agent.oms.kill_switch import kill_switch_status
        from trading_agent.oms.pretrade import pretrade_snapshot
        from trading_agent.oms.state import OmsStore

        store = OmsStore()
        payload = {
            "kill_switch": kill_switch_status(),
            "pretrade": pretrade_snapshot(store),
            "open_lots": [lot.to_dict() for lot in store.open_lots()],
            "state_path": str(store.state_path),
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if cmd == "kill":
        from trading_agent.oms.kill_switch import set_kill_switch

        path = set_kill_switch(
            getattr(args, "reason", "manual") or "manual",
            flatten=bool(getattr(args, "flatten", False)),
        )
        print(f"kill_switch active → {path}")
        return 0
    if cmd == "clear-kill":
        from trading_agent.oms.kill_switch import clear_kill_switch

        path = clear_kill_switch()
        print(f"kill_switch cleared → {path}")
        return 0
    if cmd == "manage":
        import json

        from trading_agent.export.mac_execute import call_schwab_mcp
        from trading_agent.oms.exits import manage_open_lots
        from trading_agent.oms.state import OmsStore

        store = OmsStore()
        results = manage_open_lots(
            store,
            live=bool(getattr(args, "live", False)),
            call_mcp=lambda t, p: call_schwab_mcp(t, p),
        )
        print(json.dumps({"manage": results, "open_lots": len(store.open_lots())}, indent=2))
        return 0
    if cmd == "reconcile":
        import json

        from trading_agent.export.mac_execute import call_schwab_mcp
        from trading_agent.oms.lifecycle import reconcile_open_lots
        from trading_agent.oms.state import OmsStore

        store = OmsStore()
        result = reconcile_open_lots(store, lambda t, p: call_schwab_mcp(t, p))
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if cmd == "flatten":
        import json

        from trading_agent.export.mac_execute import call_schwab_mcp
        from trading_agent.oms.exits import flatten_all_lots
        from trading_agent.oms.kill_switch import set_kill_switch
        from trading_agent.oms.state import OmsStore

        live = bool(getattr(args, "live", False))
        if getattr(args, "kill", False):
            set_kill_switch("flatten_cli", flatten=True, source="cli_flatten")
        store = OmsStore()
        result = flatten_all_lots(
            store,
            live=live,
            call_mcp=lambda t, p: call_schwab_mcp(t, p),
            also_broker_account=True,
        )
        print(json.dumps({"live": live, **result}, indent=2, default=str))
        return 0
    if cmd == "consume":
        import os

        from trading_agent.export.mac_execute import run_consume

        if getattr(args, "anytime", False):
            os.environ["TRADING_AGENT_AUTO_TRADE_ANYTIME"] = "1"
        result = run_consume(live=bool(getattr(args, "live", False)), use_oms=True)
        print(result.get("checklist") or "")
        if result.get("ready_orders_path"):
            print(f"\nready_orders: {result['ready_orders_path']}")
        if result.get("blocked"):
            print(f"blocked: {result.get('reason')}")
            return 2
        return 0
    print(
        "oms commands: status | kill | clear-kill | manage | reconcile | flatten | consume",
        file=sys.stderr,
    )
    return 2


def _run_ti888(args: argparse.Namespace) -> int:
    """888 TI TV panel → one-glance card (optionally Discord)."""
    import sys

    from trading_agent.ti888.panel import format_ti888_card, parse_ti888_text

    raw = getattr(args, "paste", None) or ""
    paste_file = getattr(args, "paste_file", None)
    if paste_file:
        with open(paste_file, encoding="utf-8") as handle:
            raw = handle.read()
    if not (raw or "").strip() and not sys.stdin.isatty():
        raw = sys.stdin.read()
    if not (raw or "").strip():
        print(
            "Paste 888 TI panel text via --paste '...' or --paste-file or stdin.\n"
            "Example fields: WAIT, Confidence 49/100, Market PASS..., Structure FAIL...",
            file=sys.stderr,
        )
        return 2

    panel = parse_ti888_text(raw, symbol=getattr(args, "symbol", "") or "")
    text = format_ti888_card(panel)
    print(text)
    if getattr(args, "output", None):
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)

    if getattr(args, "discord", False):
        import os

        from trading_agent.discord.config import DiscordConfig
        from trading_agent.discord.poster import post_message

        if not os.getenv("DISCORD_TOKEN") and os.getenv("DISCORD_BOT_TOKEN"):
            os.environ["DISCORD_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
        if os.getenv("DISCORD_DESK_CHANNEL_ID") and not os.getenv("DISCORD_CHANNEL_ID"):
            os.environ["DISCORD_CHANNEL_ID"] = os.environ["DISCORD_DESK_CHANNEL_ID"]
        cfg = DiscordConfig.from_env()
        if cfg.bot_token and cfg.channel_id:
            cfg = DiscordConfig(
                webhook_url=None,
                bot_token=cfg.bot_token,
                channel_id=cfg.channel_id,
            )
        body = f"```\n{text.rstrip()}\n```"
        post_message(body, cfg, username="888 TI")
        print("[discord] posted 888 TI simple card", file=sys.stderr)
    return 0


def _run_research(args: argparse.Namespace) -> int:
    cmd = getattr(args, "research_command", None)
    if cmd == "hypotheses":
        import json

        from trading_agent.research.hypotheses import list_hypotheses

        print(json.dumps(list_hypotheses(), indent=2))
        return 0
    if cmd == "promotion":
        import json
        from pathlib import Path

        from trading_agent.research.promotion import (
            PromotionChecklist,
            evaluate_promotion,
            format_promotion_report,
        )

        path = Path(args.file)
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = set(PromotionChecklist.__dataclass_fields__.keys())
        check = PromotionChecklist(**{k: v for k, v in data.items() if k in fields})
        result = evaluate_promotion(check)
        print(format_promotion_report(result))
        return 0 if result.approved else 1
    if cmd == "replay":
        from trading_agent.research.replay import format_replay_report, replay_session_candidates

        result = replay_session_candidates(args.session_dir)
        text = format_replay_report(result)
        print(text)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    if cmd == "walk-forward":
        from trading_agent.research.quant_pipeline import (
            format_quant_research_report,
            run_quant_research,
        )

        pack = run_quant_research(
            historical=not bool(getattr(args, "synthetic", False)),
            period=getattr(args, "period", "1y") or "1y",
            train_bars=int(getattr(args, "train_bars", 80) or 80),
            test_bars=int(getattr(args, "test_bars", 20) or 20),
            step_bars=int(getattr(args, "step_bars", 20) or 20),
            embargo_bars=int(getattr(args, "embargo_bars", 5) or 5),
            slippage_bps=float(getattr(args, "slippage_bps", 5.0) or 0.0),
            commission=float(getattr(args, "commission", 1.0) or 0.0),
            include_ml=not bool(getattr(args, "no_ml", False)),
        )
        text = format_quant_research_report(pack)
        print(text)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    if cmd == "features":
        from trading_agent.backtest.data import default_backtest_universe
        from trading_agent.features.builder import FEATURE_SCHEMA_VERSION, build_panel
        from trading_agent.features.labels import align_xy

        ohlcv = default_backtest_universe()
        X, meta, names = build_panel(ohlcv)
        X2, y, meta2 = align_xy(X, meta, ohlcv)
        print(
            f"schema={FEATURE_SCHEMA_VERSION} features={len(names)} "
            f"rows={len(X)} labeled={len(y)} "
            f"mean_fwd_ret={sum(y)/len(y) if y else 0:.5f}"
        )
        print("names:", ", ".join(names))
        return 0
    if cmd == "manage-summary":
        import json
        from datetime import date as date_cls

        from trading_agent.intraday.manage_log import manage_log_path, summarize_manage_log

        day_s = getattr(args, "day", None)
        day = date_cls.fromisoformat(day_s) if day_s else None
        summary = summarize_manage_log(day=day)
        print(json.dumps(summary, indent=2))
        print(f"log: {manage_log_path(day)}")
        return 0
    if cmd == "scalp-backtest":
        from trading_agent.scalp.backtest import (
            format_scalp_backtest_report,
            run_multi_symbol_scalp_backtest,
        )

        syms = getattr(args, "symbols", None)
        if syms:
            symbols = [s.strip().upper() for s in syms if s.strip()]
        else:
            symbols = None
        result = run_multi_symbol_scalp_backtest(
            symbols,
            period=getattr(args, "period", "60d") or "60d",
            vix=getattr(args, "vix", None),
            allow_bear_breakdown=not bool(getattr(args, "no_bear", False)),
            last_n_sessions=getattr(args, "last_sessions", None),
            etfs_only=bool(getattr(args, "etfs_only", False)),
        )
        text = format_scalp_backtest_report(result)
        print(text)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    if cmd == "scalp-universe":
        from trading_agent.scalp.universe_card import (
            format_scalp_universe_card,
            post_scalp_universe_card,
        )

        if getattr(args, "discord", False):
            text = post_scalp_universe_card(discord=True)
            print(text)
            print("[discord] posted scalp universe link", file=sys.stderr)
        else:
            text = format_scalp_universe_card()
            print(text)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    if cmd == "methods-backtest":
        from trading_agent.sleeves.momentum import format_momentum_report, run_momentum_backtest
        from trading_agent.sleeves.orb_vwap import format_orb_report, run_orb_vwap_backtest
        from trading_agent.sleeves.regime_premium import format_regime_report, run_regime_premium_ablation

        which = (getattr(args, "method", None) or "all").lower()
        parts = []
        if which in ("all", "orb", "orb-vwap"):
            orb = run_orb_vwap_backtest(period=getattr(args, "period", "60d") or "60d")
            parts.append(format_orb_report(orb))
        if which in ("all", "momentum", "mom"):
            mom = run_momentum_backtest(period=getattr(args, "mom_period", "1y") or "1y")
            parts.append(format_momentum_report(mom))
        if which in ("all", "regime", "premium"):
            reg = run_regime_premium_ablation(period=getattr(args, "mom_period", "1y") or "1y")
            parts.append(format_regime_report(reg))
        text = "\n".join(parts)
        print(text)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0
    print(
        "research commands: hypotheses | promotion | replay | walk-forward | "
        "features | manage-summary | scalp-backtest | scalp-universe | methods-backtest",
        file=sys.stderr,
    )
    return 2


def _run_backtest(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from trading_agent.backtest.engine import default_sweep_configs, run_backtest, run_config_sweep
    from trading_agent.backtest.report import render_comparison, render_period_report

    slip = float(getattr(args, "slippage_bps", 0.0) or 0.0)
    comm = float(getattr(args, "commission", 0.0) or 0.0)
    exit_mode = str(getattr(args, "exit_mode", "path") or "path")
    manage_n = int(getattr(args, "manage_every_n", 1) or 1)
    ohlcv = None
    if getattr(args, "historical", False):
        from trading_agent.backtest.historical import load_historical_ohlcv

        ohlcv = load_historical_ohlcv(period=getattr(args, "period", "1y") or "1y")

    def _apply_manage(cfg):
        return replace(
            cfg,
            exit_mode=exit_mode,
            manage_every_n_bars=manage_n,
        )

    if getattr(args, "walk_forward", False):
        from trading_agent.backtest.walk_forward import format_walk_forward_report, run_walk_forward

        cfg = default_sweep_configs()[0]
        cfg = replace(
            cfg,
            slippage_bps=slip,
            commission_per_trade=comm,
            use_historical_ohlcv=bool(ohlcv),
            name=f"{cfg.name}_wf",
        )
        cfg = _apply_manage(cfg)
        if ohlcv is None:
            from trading_agent.backtest.data import default_backtest_universe

            ohlcv = default_backtest_universe()
        report = run_walk_forward(cfg, ohlcv)
        text = format_walk_forward_report(report)
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text)
        return 0

    if args.single and not args.sweep:
        cfg = default_sweep_configs()[0]
        cfg = replace(cfg, slippage_bps=slip, commission_per_trade=comm)
        cfg = _apply_manage(cfg)
        result = run_backtest(cfg, ohlcv=ohlcv)
        text = render_period_report(result)
    else:
        if slip or comm or ohlcv is not None or exit_mode != "path" or manage_n != 1:
            cfg = default_sweep_configs()[0]
            cfg = replace(
                cfg,
                slippage_bps=slip,
                commission_per_trade=comm,
                name=f"{cfg.name}_costs_slip{slip}_c{comm}_{exit_mode}_n{manage_n}",
                use_historical_ohlcv=bool(ohlcv),
            )
            cfg = _apply_manage(cfg)
            result = run_backtest(cfg, ohlcv=ohlcv)
            text = render_period_report(result)
        else:
            sweep = run_config_sweep()
            text = render_comparison(sweep)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


def _run_premarket(args: argparse.Namespace) -> int:
    config = AgentConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
        config.use_live_data = False
    if args.output:
        config.output_file = args.output

    plan = run_pipeline(config)
    report = render_daily_plan(plan)
    print(report)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(report)
    return 0


def _run_intraday(args: argparse.Namespace) -> int:
    config = IntradayConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
        config.use_live_data = False
    if args.plan:
        config.plan_file = args.plan
    if args.positions:
        config.positions_file = args.positions
    if args.session:
        config.session_file = args.session
    if args.output:
        config.output_file = args.output
    if args.cycles:
        config.cycles = args.cycles

    report = run_intraday_pipeline(config)
    text = render_intraday_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def _run_performance(args: argparse.Namespace) -> int:
    config = PerformanceConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.trades:
        config.trades_file = args.trades
    if args.history:
        config.history_file = args.history
    if args.output:
        config.output_file = args.output

    report = run_performance_pipeline(config)
    text = render_performance_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def _run_session(args: argparse.Namespace) -> int:
    from datetime import date as date_type

    config = SessionConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.dry_run:
        config.dry_run = True
    if args.no_discord:
        config.no_discord = True
    if args.date:
        config.trading_date = date_type.fromisoformat(args.date)
    if args.interval:
        config.intraday_interval_minutes = args.interval
    if args.cycles:
        config.intraday_cycles = args.cycles
    if args.positions:
        config.positions_file = args.positions
    if args.session:
        config.session_file = args.session
    if args.plan:
        config.plan_file = args.plan
    if args.output:
        config.log_file = args.output
    if args.no_cio:
        config.include_cio = False
    if args.portfolio_value:
        config.portfolio_value = args.portfolio_value

    if args.timezone:
        config.timezone = args.timezone
    if args.from_phase:
        config.from_phase = DeskPhaseKind(args.from_phase)
    if args.until_phase:
        config.until_phase = DeskPhaseKind(args.until_phase)

    if config.fixture_mode or config.dry_run or config.no_discord:
        config.wait_for_schedule = False

    return run_session_cli(config)


def _run_cio(args: argparse.Namespace) -> int:
    config = CIOConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.inputs:
        config.inputs_file = args.inputs
    if args.output:
        config.output_file = args.output
    if args.portfolio_value:
        config.portfolio_value = args.portfolio_value

    report = run_cio_pipeline(config)
    text = render_cio_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Trading Agent — Full Desk (Phases 1–4)")
    subparsers = parser.add_subparsers(dest="command")

    premarket = subparsers.add_parser("premarket", help="Generate Daily Trading Plan (Phase 1)")
    premarket.add_argument("--fixture", action="store_true", help="Use fixture data")
    premarket.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    intraday = subparsers.add_parser("intraday", help="Intraday position management (Phase 2)")
    intraday.add_argument("--fixture", action="store_true", help="Use fixture data")
    intraday.add_argument("--plan", metavar="FILE", help="Daily Trading Plan context JSON")
    intraday.add_argument("--positions", metavar="FILE", help="Open positions JSON")
    intraday.add_argument("--session", metavar="FILE", help="Intraday session fixture JSON")
    intraday.add_argument("--output", "-o", metavar="FILE", help="Write report to file")
    intraday.add_argument("--cycles", type=int, default=1, help="Monitoring cycle count")

    performance = subparsers.add_parser("performance", help="Performance review (Phase 3)")
    performance.add_argument("--fixture", action="store_true", help="Use fixture data")
    performance.add_argument("--trades", metavar="FILE", help="Completed trades JSON")
    performance.add_argument("--history", metavar="FILE", help="Historical trades JSON")
    performance.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    session = subparsers.add_parser(
        "session",
        help="Run full PST trading desk day (7 phases) with Discord delivery",
    )
    session.add_argument("--fixture", action="store_true", help="Use fixture data")
    session.add_argument("--dry-run", action="store_true", help="Run pipelines without Discord posts")
    session.add_argument("--no-discord", action="store_true", help="Skip Discord delivery")
    session.add_argument("--date", metavar="YYYY-MM-DD", help="Trading session date (default: next session)")
    session.add_argument(
        "--timezone",
        default="America/Los_Angeles",
        help="Desk schedule timezone (default: America/Los_Angeles)",
    )
    session.add_argument(
        "--from-phase",
        choices=[p.value for p in DeskPhaseKind],
        help="Start at a specific desk phase (skip earlier phases)",
    )
    session.add_argument(
        "--until-phase",
        choices=[p.value for p in DeskPhaseKind],
        help="Stop after this phase (e.g. preopen = first 4 phases only)",
    )
    session.add_argument("--interval", type=int, default=15, help="Intraday cycle interval in minutes")
    session.add_argument("--cycles", type=int, default=1, help="Intraday cycles to run (fixture/dry-run)")
    session.add_argument("--positions", metavar="FILE", help="Open positions JSON")
    session.add_argument("--session", metavar="FILE", help="Intraday session fixture JSON")
    session.add_argument("--plan", metavar="FILE", help="Existing plan context JSON (skip pre-market regeneration)")
    session.add_argument("--no-cio", action="store_true", help="Skip CIO summary push")
    session.add_argument("--portfolio-value", type=float, default=100_000, help="Portfolio value for CIO allocation")
    session.add_argument("--output", "-o", metavar="FILE", help="Write session log to file")

    cio = subparsers.add_parser("cio", help="CIO final decision (Phase 4)")
    cio.add_argument("--fixture", action="store_true", help="Use fixture data")
    cio.add_argument("--inputs", metavar="FILE", help="CIO inputs JSON (phases 1-3 context)")
    cio.add_argument("--portfolio-value", type=float, default=100_000, help="Portfolio value for allocation")
    cio.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    odte = subparsers.add_parser(
        "odte",
        help="QQQ/SPY playbooks: mean-reversion (Shen 0DTE/multi-DTE) or breakout (OR continuation)",
    )
    odte.add_argument("--symbol", default="QQQ", help="ETF symbol (QQQ or SPY)")
    odte.add_argument("--account", type=float, default=1000.0, help="Account size for risk template")
    odte.add_argument("--backtest", action="store_true", help="Run historical backtest (win rate)")
    odte.add_argument(
        "--period",
        default="7d",
        help="History period (0DTE default 7d; multi-DTE/breakout prefers 60d on yfinance)",
    )
    odte.add_argument(
        "--style",
        default="mean_reversion",
        choices=[
            "mean_reversion",
            "mean-reversion",
            "mr",
            "fade",
            "breakout",
            "bo",
            "continuation",
        ],
        help="mean_reversion=RSI/level fade (default); breakout=OR high/low continuation",
    )
    odte.add_argument(
        "--mode",
        default="0dte",
        choices=["0dte", "weekly", "2dte", "3dte", "multidte", "multi", "breakout"],
        help="0dte=1m Shen; weekly/2dte/3dte=HTF multi-DTE fade; breakout=OR continuation",
    )
    odte.add_argument(
        "--dte",
        type=int,
        default=0,
        help="Target DTE for multi-day path (2,3,5,7). >0 forces multi-DTE mode",
    )
    odte.add_argument(
        "--interval",
        default="15m",
        help="Bar interval for multi-DTE (15m, 5m, 30m; default 15m)",
    )
    odte.add_argument(
        "--puts-only",
        action="store_true",
        help="Disable CALL entries (TOS 0DTE A/B: puts had much higher WR)",
    )
    odte.add_argument(
        "--source",
        default="auto",
        choices=["auto", "schwab", "tos", "yfinance", "yf"],
        help="Data source: auto (Schwab/TOS if token, else yf), schwab/tos, or yfinance",
    )
    odte.add_argument(
        "--legacy-rules",
        action="store_true",
        help="0DTE only: pre-filter rules (whole-$ + TP20/SL12.5) for A/B comparison",
    )
    odte.add_argument("--output", "-o", metavar="FILE", help="Write brief/report to file")

    ti888 = subparsers.add_parser(
        "ti888",
        help="888 TI (TradingView panel) → simple DECISION card (paste panel text)",
    )
    ti888.add_argument("--symbol", default="", help="Ticker (e.g. ORCL)")
    ti888.add_argument(
        "--paste",
        default=None,
        help="Paste of 888 TI table (or use --paste-file / stdin)",
    )
    ti888.add_argument(
        "--paste-file",
        default=None,
        metavar="FILE",
        help="File with pasted 888 TI table text",
    )
    ti888.add_argument(
        "--discord",
        action="store_true",
        help="Post simple card to Discord desk channel",
    )
    ti888.add_argument("--output", "-o", metavar="FILE", help="Write card to file")

    qt = subparsers.add_parser(
        "qt",
        help="QT open-window mech model (9:30–9:50 ET PO3+CISD proxies → auto-trade book)",
    )
    qt.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Symbol to scan (repeatable). Default: QQQ,SPY,IWM",
    )
    qt.add_argument(
        "--export",
        action="store_true",
        help="Write qt_auto_trade_book.json for Mac/ENTER handoff",
    )
    qt.add_argument("--rr", type=float, default=2.0, help="Risk-reward multiple (1.5–2.5)")
    qt.add_argument("--output", "-o", metavar="FILE", help="Write brief to file")

    backtest = subparsers.add_parser(
        "backtest",
        help="Offline multi-day research+CIO backtest and config comparison",
    )
    backtest.add_argument(
        "--sweep",
        action="store_true",
        help="Compare multiple risk/grade configs (default if neither flag set)",
    )
    backtest.add_argument(
        "--single",
        action="store_true",
        help="Run only the baseline config",
    )
    backtest.add_argument("--output", "-o", metavar="FILE", help="Write report to file")
    backtest.add_argument(
        "--slippage-bps",
        type=float,
        default=0.0,
        help="One-way slippage in bps of risk unit (round-trip applied)",
    )
    backtest.add_argument(
        "--commission",
        type=float,
        default=0.0,
        help="Commission dollars per trade",
    )
    backtest.add_argument(
        "--historical",
        action="store_true",
        help="Load real OHLCV (yfinance/Schwab) instead of synthetic",
    )
    backtest.add_argument(
        "--period",
        default="1y",
        help="History period when --historical (default 1y)",
    )
    backtest.add_argument(
        "--walk-forward",
        action="store_true",
        help="Walk-forward OOS evaluation (use with --single or baseline)",
    )
    backtest.add_argument(
        "--exit-mode",
        default="path",
        choices=["path", "close_only"],
        help="Directional exit: path=high/low tags (fast manage); close_only=slower",
    )
    backtest.add_argument(
        "--manage-every-n",
        type=int,
        default=1,
        help="Only evaluate stop/target every N forward bars (default 1)",
    )

    oms = subparsers.add_parser(
        "oms",
        help="OMS: kill switch, status, manage open lots, consume with pretrade",
    )
    oms_sub = oms.add_subparsers(dest="oms_command")
    oms_sub.add_parser("status", help="Show kill switch + open lots")
    kill_p = oms_sub.add_parser("kill", help="Activate kill switch (block new entries)")
    kill_p.add_argument("--reason", default="manual", help="Reason string")
    kill_p.add_argument("--flatten", action="store_true", help="Also request flatten")
    oms_sub.add_parser("clear-kill", help="Clear kill switch")
    manage_p = oms_sub.add_parser("manage", help="Run exit/manage loop on open lots")
    manage_p.add_argument("--live", action="store_true", help="Submit closes live")
    oms_sub.add_parser("reconcile", help="Match open OMS lots to Schwab positions")
    flat_p = oms_sub.add_parser("flatten", help="Close all OMS lots (+ broker sweep)")
    flat_p.add_argument("--live", action="store_true", help="Submit live closes")
    flat_p.add_argument("--kill", action="store_true", help="Also set kill switch + flatten flag")
    consume_p = oms_sub.add_parser("consume", help="OMS-aware book consume")
    consume_p.add_argument("--live", action="store_true")
    consume_p.add_argument("--anytime", action="store_true")

    research = subparsers.add_parser(
        "research",
        help="Hypothesis registry, promotion gate, session replay",
    )
    research_sub = research.add_subparsers(dest="research_command")
    research_sub.add_parser("hypotheses", help="List named edges")
    promo = research_sub.add_parser("promotion", help="Evaluate promotion checklist JSON")
    promo.add_argument(
        "--file",
        required=True,
        help="Path to promotion checklist JSON",
    )
    replay_p = research_sub.add_parser("replay", help="Replay session candidates")
    replay_p.add_argument(
        "session_dir",
        help="Path to ~/.trading_agent/sessions/YYYY-MM-DD",
    )
    replay_p.add_argument("--output", "-o", metavar="FILE")
    wf = research_sub.add_parser(
        "walk-forward",
        help="Historical (or synthetic) walk-forward desk BT + ML vs baseline",
    )
    wf.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic multi-regime data (no network)",
    )
    wf.add_argument("--period", default="1y", help="yfinance/Schwab period when historical")
    wf.add_argument("--train-bars", type=int, default=80)
    wf.add_argument("--test-bars", type=int, default=20)
    wf.add_argument("--step-bars", type=int, default=20)
    wf.add_argument("--embargo-bars", type=int, default=5)
    wf.add_argument("--slippage-bps", type=float, default=5.0)
    wf.add_argument("--commission", type=float, default=1.0)
    wf.add_argument("--no-ml", action="store_true", help="Skip feature ranker compare")
    wf.add_argument("--output", "-o", metavar="FILE")
    feat = research_sub.add_parser("features", help="Build feature panel stats (synthetic or hist)")
    feat.add_argument("--synthetic", action="store_true", default=True)
    feat.add_argument("--period", default="6mo")
    msum = research_sub.add_parser(
        "manage-summary",
        help="Summarize live manage cadence / exit logs for a day",
    )
    msum.add_argument(
        "--day",
        default=None,
        help="YYYY-MM-DD (default: today UTC)",
    )
    scalp_uni = research_sub.add_parser(
        "scalp-universe",
        help="Show desk+gainer/loser link to QQQ scalp rules (optional Discord)",
    )
    scalp_uni.add_argument(
        "--discord",
        action="store_true",
        help="Post card to Discord (scalp/alerts channel if set, else desk)",
    )
    scalp_uni.add_argument("--output", "-o", metavar="FILE")
    scalp_bt = research_sub.add_parser(
        "scalp-backtest",
        help="Apply QQQ scalp rules to multiple tickers; report win rates",
    )
    scalp_bt.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Symbol (repeatable). Default: QQQ,SPY,IWM,AAPL,AMZN,MSFT,NVDA,META,TSLA",
    )
    scalp_bt.add_argument(
        "--period",
        default="60d",
        help="Intraday history window (yfinance; 15m/60m max ~60d)",
    )
    scalp_bt.add_argument("--vix", type=float, default=None, help="Optional static VIX for cap")
    scalp_bt.add_argument(
        "--no-bear",
        action="store_true",
        help="Disable bear_breakdown entries (CALL setups only)",
    )
    scalp_bt.add_argument(
        "--etfs-only",
        action="store_true",
        help="Only QQQ, SPY, IWM",
    )
    scalp_bt.add_argument(
        "--last-sessions",
        type=int,
        default=None,
        metavar="N",
        help="Score only the last N RTH sessions (e.g. 10 ≈ 2 weeks)",
    )
    scalp_bt.add_argument("--output", "-o", metavar="FILE")
    methods_bt = research_sub.add_parser(
        "methods-backtest",
        help="ORB+VWAP, momentum/RS, regime×premium ablations",
    )
    methods_bt.add_argument(
        "--method",
        default="all",
        choices=["all", "orb", "orb-vwap", "momentum", "mom", "regime", "premium"],
    )
    methods_bt.add_argument("--period", default="60d", help="ORB intraday period")
    methods_bt.add_argument("--mom-period", default="1y", help="Momentum/regime daily period")
    methods_bt.add_argument("--output", "-o", metavar="FILE")

    parser.add_argument("--fixture", action="store_true", help="(legacy) fixture mode for premarket")
    parser.add_argument("--output", "-o", metavar="FILE", help="(legacy) output file")

    args = parser.parse_args(argv)

    if args.command == "session":
        return _run_session(args)
    if args.command == "intraday":
        return _run_intraday(args)
    if args.command == "performance":
        return _run_performance(args)
    if args.command == "cio":
        return _run_cio(args)
    if args.command == "backtest":
        return _run_backtest(args)
    if args.command == "odte":
        return _run_odte(args)
    if args.command == "ti888":
        return _run_ti888(args)
    if args.command == "qt":
        return _run_qt(args)
    if args.command == "oms":
        return _run_oms(args)
    if args.command == "research":
        return _run_research(args)
    if args.command == "premarket":
        return _run_premarket(args)

    return _run_premarket(args)


if __name__ == "__main__":
    sys.exit(main())