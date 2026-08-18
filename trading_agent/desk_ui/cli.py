"""CLI entry for ``desk-ui`` HTTP server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def run_server(
    *,
    host: str | None = None,
    port: int | None = None,
    reload: bool = False,
    state: str | Path | None = None,
    trading_date: str | None = None,
) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "desk-ui requires optional deps. Install:\n"
            '  pip install -e ".[desk-ui]"',
            file=sys.stderr,
        )
        return 2

    from trading_agent.desk_ui.app import create_app
    from trading_agent.desk_ui.config import load_settings

    settings = load_settings(
        host=host,
        port=port,
        state=state,
        trading_date=trading_date,
    )
    err = settings.validate_bind()
    if err:
        print(err, file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Avoid logging full query strings (token leakage)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    app = create_app(settings)
    print(
        f"desk-ui listening on http://{settings.host}:{settings.port}/ "
        f"(auth={'on' if settings.auth_required else 'off'}; "
        f"manual launch only — no auto-start)",
        file=sys.stderr,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=reload,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="desk-ui",
        description="Local auto-trade desk web UI (localhost; optional token auth).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host (default 127.0.0.1 / TRADING_AGENT_DESK_UI_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port (default 8787 / TRADING_AGENT_DESK_UI_PORT)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Uvicorn reload (dev only)",
    )
    parser.add_argument(
        "--state",
        metavar="DIR",
        help="Fixture/state root instead of ~/.trading_agent",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Override trading date for snapshot",
    )
    args = parser.parse_args(argv)
    return run_server(
        host=args.host,
        port=args.port,
        reload=args.reload,
        state=args.state,
        trading_date=args.date,
    )


if __name__ == "__main__":
    sys.exit(main())
