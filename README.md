# Trading Test (methods lab)

**Separate repository** from the live CIO desk.

| Repo | Purpose |
|------|---------|
| **This repo (`trading_test`)** | Combined multi-method scanners, swing scan, research export — **no CIO decision desk** |
| [`trading_agent`](https://github.com/thaing408/trading_agent) | Live multi-phase desk: scan lists → **CIO** capital decisions → Mac/TOS |

See **[docs/repo_split.md](docs/repo_split.md)** for the full split.

**GitHub:** https://github.com/thaing408/trading_test

## Defaults (this product)

- `product_mode=methods` (`trading_agent/product.py`)
- `include_cio=False` — CIO approval/review phases are skipped
- Research = multi-method router + daily swing scan → Discord + `auto_trade_book`

## Quick start

```powershell
git clone https://github.com/thaing408/trading_test.git
cd trading_test
pip install -r requirements.txt
python -m trading_agent session --fixture --dry-run --until-phase preopen
python -m trading_agent research multi-method --limit 12
python -m trading_agent research swing-scan --limit 20
```

## Discord

Same bot/webhook env as before (`DISCORD_TOKEN` + channel, or `DISCORD_WEBHOOK_URL`). Methods research posts PLAY shortlists without CIO approve/reject capital.

## Live desk

Do **not** point Windows 01:55 automation at this repo if you want CIO-gated live trading. Use **`trading_agent`** for that.

## Package name

Python package remains `trading_agent` for import compatibility (`python -m trading_agent …`). Product identity is `trading_test` via `trading_agent.product`.
