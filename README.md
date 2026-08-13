# trading_test

**Separate repository** from the live CIO desk (`trading_agent`).

| Repo | Purpose |
|------|---------|
| **This repo (`trading_test`)** | Methods lab + **IBKR paper** paths — multi-method / swing research, **no CIO** capital desk |
| [`trading_agent`](https://github.com/thaing408/trading_agent) | Live multi-phase desk: scan → **CIO** → Mac Schwab/TOS |

**GitHub:** https://github.com/thaing408/trading_test  

See **[docs/repo_split.md](docs/repo_split.md)** and **[PAPER_NO_CIO.md](PAPER_NO_CIO.md)**.

## Defaults

- `product_mode=methods` (`trading_agent/product.py`)
- `include_cio=False` — CIO approval/review skipped
- Paper: IBKR Gateway, state under `~/.trading_test` (see `.env.paper.example`)
- Linux paper: [docs/ibkr_gateway_paper_linux.md](docs/ibkr_gateway_paper_linux.md)

## Quick start

```bash
git clone https://github.com/thaing408/trading_test.git
cd trading_test
python3 -m venv .venv && .venv/bin/pip install -e . ib_insync
cp .env.paper.example ~/.trading_test/trading-test.env   # edit IBKR account/port
python -m trading_agent session --fixture --dry-run --until-phase preopen
python -m trading_agent research multi-method --limit 12
python -m trading_agent research swing-scan --limit 20
```

Paper session / consumer (me-ai):

```bash
bash scripts/macos/run-paper-session.sh
bash scripts/macos/run-paper-consumer.sh
```

## Discord

Same bot/webhook env (`DISCORD_TOKEN` + channel, or webhook). Methods research posts PLAY shortlists without CIO approve/reject.

## Do not

- Point Windows/Mac **prod** 01:55 automation at this repo if you want CIO-gated Schwab live trading — use **`trading_agent`**.
- Push this remote to `trading_agent` — remotes are separate. Optional `upstream` remote is for cherry-picks only.

## Package name

Python package remains `trading_agent` for import compatibility; **git remote is `trading_test` only**.
