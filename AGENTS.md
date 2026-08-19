# Agent notes — trading_agent

## Product direction (keep in mind)

Long-run delivery target is an **installable Operator Desk** on Mac/Windows (local read-mostly UI over `~/.trading_agent`), not an endless `pip install -e` + script farm.

**Canonical roadmap:** [`docs/PACKAGING_ROADMAP.md`](docs/PACKAGING_ROADMAP.md)

When implementing features:

- Prefer `DeskSnapshot` / `desk_ui` readers + stable file contracts  
- Don’t add cloud sync or cross-host book rsync for core flows  
- Package-data for anything the Desk UI needs; avoid editable-only / repo-path assumptions for product features  
- Preserve dual_system: Windows research never places orders; Mac execute is LIVE/OMS home  
- Phone/Android is later (read-only); don’t prioritize it over desktop packaging  

Also see: `docs/DESK_UI_AUTO_TRADE.md`, `docs/dual_system.md`, `docs/options_auto_trade.md`.
