# Top winners playbook L1–L4 (0DTE CALL)

Paper rules in `trading_test` — signals + backtest (not live OMS).

## Learning upgrades

| Level | What |
|-------|------|
| **L1 Selection** | Re-rank at **10:00 ET** by continuation score (gap + % vs open). Hard: green, above VWAP, HTF 15m bull. Soft: EMA9>EMA21, RSI band. **Chase reject** if RSI>85 and extended vs VWAP. |
| **L2 Entry** | Default **pullback** to VWAP/EMA9 in 10:00–10:30 (not blind clock market). `--entry-mode clock` for old behavior. |
| **L3 Exit** | Brackets + **11:30 ET time stop** + trail after +15% premium (giveback 8pp). |
| **L4 Universe** | Max gap **8%**, min RVOL **1.0×**, prefer single name if quality **4/4**, 2nd name needs 4/4. |

## Default bracket

Shipped default after 1mo A/B: **legacy30_25** (+30% / −25%) with trail — best WR/P/L on L1–L4 path.

| Name | TP | SL |
|------|----|----|
| `legacy30_25` (default) | +30% | −25% |
| `bal25_20` | +25% | −20% |
| `wr20_15` | +20% | −15% |

## CLI

```bash
cd C:\Personal\Grok\trading_test

# Paper brief
python -m trading_agent odte --mode top-winners --symbols NVDA,AMD,TSLA,AAPL,MSFT,META,AMZN,GOOGL,PLTR,MU

# Month backtest (yfinance 5m) — L1–L4 defaults
python -m trading_agent odte --mode top-winners --backtest --period 1mo --source yfinance \
  --symbols NVDA,AMD,TSLA,AAPL,MSFT,META,AMZN,GOOGL,PLTR,MU

# Bracket A/B
python -m trading_agent odte --mode top-winners --ab --period 1mo --source yfinance \
  --symbols NVDA,AMD,TSLA,AAPL,MSFT,META,AMZN,GOOGL,PLTR,MU

# Variants
python -m trading_agent odte --mode top-winners --backtest --period 1mo --source yfinance \
  --bracket wr20_15 --entry-mode clock --no-trail --symbols NVDA,AMD,TSLA
```

## Decision stack

```text
Universe → gap/RVOL filters (L4)
        → re-rank @ 10:00 continuation (L1)
        → drop-fast + hard TA + quality score (L1)
        → pullback fill 10:00–10:30 (L2)
        → manage: TP/SL/trail/time 11:30 (L3)
```
