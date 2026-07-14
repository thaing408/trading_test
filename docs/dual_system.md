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

### Home (macOS) — end of day / next morning

1. See Discord (optional cue: “pull latest” / desk finished).
2. Run **pull-and-ready** (see below).
3. Trade only with **local** TOS MCP + local positions/config.
4. Use Discord messages as **context for a human**, not as an automatic order stream.

## Discord as the “signal channel”

Discord is **notification + briefing**, not a sync bus for secrets or blotters.

| Message type | Mac action (manual or scripted) |
|--------------|----------------------------------|
| Research / CIO / discovery posts | Read for next-day bias; **do not** auto-size from prose |
| Optional: “**PULL_LATEST**” or bot note after Windows push | Run `scripts/macos/pull-and-ready.sh` |
| Risk/PT-SL style posts | Only if generated **on Mac** against local positions |

Suggested cue after a Windows code push (you or the agent posts once):

```text
PULL_LATEST trading_agent main — research methods updated. Mac: run pull-and-ready.
```

## Mac: pull and get ready for next day

```bash
cd /path/to/trading_agent
./scripts/macos/pull-and-ready.sh
```

What it does:

1. `git fetch` + `git pull --ff-only origin main`
2. Install package (`pip install -e .`)
3. Smoke-import `trading_agent`
4. Prints “ready for next session” (does not place trades)

Launchd morning desk already pulls in some setups; EOD pull still keeps you current after workday pushes.

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
| **macOS (home)** | After `git pull` / `pull-and-ready.sh`, human or local MCP executes using **home** TOS only |

Web method research tags process rules (risk package, checklist, HTF, size, expectancy). They influence eligibility on the research host; they are **not** paid signal tips and **not** a profitability guarantee.
