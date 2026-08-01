# Manage frequency: live log + backtest sim

## Live desk

When in a trade, PT/SL checks speed up (default **3m** vs **15m** flat).

**Logging (default on):** each cycle writes JSONL:

`~/.trading_agent/logs/manage/manage_YYYY-MM-DD.jsonl`

| Event | Content |
|-------|---------|
| `interval_decision` | wait_minutes, baseline vs in_position, open symbols |
| `manage_cycle` | per-position actions (Exit/Hold/…), alerts, why |

Disable: `TRADING_AGENT_MANAGE_LOG=0`

```bash
python -m trading_agent research manage-summary
python -m trading_agent research manage-summary --day 2026-08-01
```

Review after a week of live desk: count `in_position_fast` cycles vs exitish actions.

## Backtest manage simulation

| Flag | Meaning |
|------|---------|
| `--exit-mode path` | High/low tags stop/target (default; “fast/continuous”) |
| `--exit-mode close_only` | Only bar **close** can stop/target (“slower manage”) |
| `--manage-every-n N` | Only evaluate every N forward bars |

```bash
python -m trading_agent backtest --historical --period 1y --single \
  --slippage-bps 5 --commission 1 --exit-mode path --manage-every-n 1

python -m trading_agent backtest --historical --period 1y --single \
  --slippage-bps 5 --commission 1 --exit-mode close_only
```

### A/B result (1y Schwab, costs on, 347 trades)

| Mode | WR | Exp | PnL |
|------|-----|-----|-----|
| path n=1 (default) | 20.8% | −$395 | −$137.1k |
| close_only n=1 | 21.6% | −$404 | −$140.2k |
| path n=2 | 21.0% | −$392 | −$135.9k |
| path n=3 | 21.6% | −$380 | −$131.9k |

**Read:** slower/less frequent manage does **not** rescue the desk path; small differences only. Adaptive 3m live is **not** the main driver of these offline losses.
