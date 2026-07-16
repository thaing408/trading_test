# Dual-system architecture (fully separated)

## Physical setup

| Location | Machine | Role | Shares with the other machine? |
|----------|---------|------|--------------------------------|
| **Work** | **Windows** | Research / methods / Discord research posts | **No files.** Only **git push** of code. |
| **Home** | **macOS** | Live trading (TOS / Schwab MCP) | **No files from work.** Only **git pull** of code. |

**Hard rule:** do **not** sync positions, journals, `.env`, tokens, or account data between work and home. No shared cloud trading folder. No work secrets on the Mac, no home brokerage state on the work PC.

## What crosses the air gap

| Direction | What | How |
|-----------|------|-----|
| Work → Home | **Code + methods only** | `git push` → GitHub → Mac `git pull` |
| Work → Home | **Human-readable ideas** (optional) | Discord posts (research / discovery / CIO) — not order APIs |
| Home → Work | **Nothing required** | Home Performance/journal stays on Mac |

Windows never needs TOS. Mac never needs work network paths.

## Daily rhythm

### Work (Windows)

1. Scheduled full-day desk (research, discovery, Discord) when the PC is on.
2. **After code/method changes** (or end of your workday): ensure repo is **pushed** to GitHub (`main`).
3. No export of positions or trade books to home.

### Home (macOS) — automatic (no daily manual prepare)

Install once:

```bash
bash scripts/macos/install-auto-trade-launchd.sh
```

| LaunchAgent | When (PT, weekdays) | What |
|-------------|---------------------|------|
| `com.grok.trading-agent-desk` | **01:55** | `git pull` + pip + Schwab positions + full desk → local `auto_trade_book.json` |
| `com.grok.auto-trade-consumer` | **06:25** | Watch local books → `ready_orders_*.json` (optional Schwab MCP live) |
| `com.grok.qt-open-window` | **06:30** | QT 9:30–9:50 ET mech model → `qt_auto_trade_book.json` + consume |

Desk job details:

1. `git pull --ff-only origin main` (code from work pushes)
2. `pip install` + smoke import (options modules)
3. Export local Schwab positions
4. Run full desk through `cio_review` (exports local auto-trade book)

You do **not** run a manual pull script every day when launchd is installed.  
Optional recovery only: `scripts/macos/pull-and-ready.sh`.

## Discord as the “signal channel”

Discord is **notification + briefing**, not a sync bus and not a daily prepare checklist.

| Message type | Mac action |
|--------------|------------|
| Research / CIO / discovery / options ENTER cards | Human/TOS context; next launchd already has latest code if Windows pushed before 01:55 PT |
| Optional `PULL_LATEST` after a late Windows push | Only if you need the Mac **before** next 01:55 — then optional recovery pull; otherwise ignore |

Windows may still post `PULL_LATEST` after a big push; **normal path is wait for morning launchd.**

## Work: push research code

After implementing methods on Windows:

```powershell
cd C:\Personal\Grok\trading_agent
git status
git push origin main   # after commit
```

Optional Discord one-liner so home knows to pull (no paths, no keys).

## Auto-trade quality (still applies, locally)

- **Windows:** TA + fundamentals + playbooks + gates → better **Discord research** and code.
- **Mac:** Same codebase after pull; execution only via **local** TOS MCP and **local** `.env` / positions.

The earlier `auto_trade_book.json` export remains optional **local** tooling if you ever want file-based flow on a **single** machine. It is **not** required for work↔home separation.

## Security checklist

- [ ] Separate Discord tokens / channel if you want (optional)
- [ ] Work `.env` never committed; home Schwab tokens never on work PC
- [ ] No `TRADING_AGENT_SYNC_DIR` shared across locations
- [ ] GitHub repo has code only (no account exports)

## Auto-trade boundary (explicit)

| Host | "Auto trade" means |
|------|---------------------|
| **Windows (work)** | Automated **suggest + Discord + local `auto_trade_book.json` export** — **never** places TOS orders |
| **macOS (home)** | Local desk/QT write **local** books; consumer writes **ready orders**; optional **local Schwab MCP** place when `TRADING_AGENT_AUTO_TRADE_LIVE=1` |

### Mac execute safety (fail-closed)

- Default: **dry-run** — `~/.trading_agent/ready_orders/ready_orders_YYYY-MM-DD.json` + checklist only
- Live: set `TRADING_AGENT_AUTO_TRADE_LIVE=1` in `~/.grok/trading-agent.env` (home only)
- Incomplete risk package / missing strikes / cash book → skip (never order)
- No work blotter paths; books are generated on the Mac after local research/QT

Web method research tags process rules (risk package, checklist, HTF, size, expectancy). They influence eligibility on the research host; they are **not** paid signal tips and **not** a profitability guarantee.

## Options-specific auto-trade (research → Mac)

Windows research is **options-first**:

| Gate | Rule |
|------|------|
| IV regime | High IVR → credit / premium; low IVR → debit / long premium |
| Defined risk | Spreads, condors, long options preferred for auto ENTER |
| Liquidity | Min OI + max bid-ask % |
| POP / R:R | Credit POP floor; debit reward ≥ risk |
| DTE | Default 5–60 DTE (0DTE only with named playbook) |
| Earnings | Block new short premium into earnings window |

Discord suggestions include **IVR, POP, delta, DTE, strikes, defined_risk**.  
`auto_trade_book.json` ENTER rows set `instrument: options` plus strikes/POP/IVR for home TOS.
