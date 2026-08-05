# Scalp + gainer/loser policy backtest (2026-08-05)

Offline backtest of **QQQ scalp rules** (`schwab_mcp.qqq_strategy`) under flavors that match the live **desk+movers+policy** link.

## Engine assumptions

- Levels each session from **prior close** via `levels_from_spot` (% bands), not fixed TV pins
- Bars: yfinance **15m** (ETFs) or **60m** (stocks); ~60d window
- Synthetic option **$1** entry; PT **+25%** / SL **−30%** on premium **or** underlying stop/target (first hit)
- Delta ≈ 0.45 for premium path; one open scalp per symbol; daily trip caps
- No live IV/VIX gate unless `vix=` passed
- **Not** the CIO desk research path

## Configs run

| ID | Rules | Symbols |
|----|--------|---------|
| **A** Default scalp (bear ON) | Full setups | QQQ, SPY, IWM, AAPL, AMZN, MSFT, NVDA, META, TSLA |
| **B Gainer policy** | **CALL only** (`allow_bear_breakdown=False`) | PLTR, ARM, SNAP, TQQQ, AMD, QQQ |
| **C Loser-style** | Bear ON | USO, UNG, SQQQ |
| **D ETFs only** | Full rules | QQQ, SPY, IWM |
| **E Last ~10 sessions** | Full book | same as A, last 10 RTH days only |

## Aggregate results (~60d)

| Run | Trades | Win rate | Expectancy | Total P/L |
|-----|--------|----------|------------|-----------|
| **A** Default multi-ticker | 778 | 35.3% | −$51.05 | −$39,715 |
| **B** Gainer CALL-only | 295 | 35.6% | −$14.07 | −$4,151 |
| **C** Loser-style names | 283 | 11.7% | −$25.27 | −$7,151 |
| **D** ETFs only | 280 | 47.1% | −$9.36 | −$2,621 |
| **E** Last 10 sessions | 128 | 30.5% | −$106.59 | −$13,643 |

P/L is **synthetic $1 premium** units (not account equity).

## By setup (run A — full book)

| Setup | n | WR | P/L |
|-------|---|-----|-----|
| pullback_long | 107 | **55%** | **+$77** |
| bull_breakout | 446 | 41% | −$8,277 |
| bear_breakdown | 225 | **15%** | **−$31,515** |

## Interpretation (live link)

Live system:

```text
pulse movers → auto_trade_universe.json (tags)
            → auto_trade_qqq (QQQ scalp engine + movers_policy)
```

Policy (env):

- Gainer → CALL setups only (pullback / bull_breakout)
- Loser → PUT bear_breakdown only, max 1/day, min |Δ%|, skip vol ETFs / both-tag

**BT support for policy:**

1. **Loser / bear_breakdown** is the worst pocket → caps and vol-ETF skip are justified.  
2. **Gainer CALL-only** bleeds less than full multi-name book with puts, still net negative offline.  
3. **ETF core** (QQQ/SPY/IWM) has the best WR in this sample, still slightly negative expectancy.  
4. **pullback_long** is the only aggregate setup near flat/green.

## Caveats

- Synthetic options path ≠ live fills / IV crush  
- Levels ≠ TradingView 888 TI panel  
- Symbols treated as “gainer/loser” every day offline, not only true mover sessions  
- Live also: window **5:35–12:55 PT**, 2 dry-runs then LIVE, trip caps  

## How to re-run

```bash
python -m trading_agent research scalp-backtest --period 60d
python -m trading_agent research scalp-backtest --period 60d --no-bear \
  --symbol PLTR --symbol ARM --symbol SNAP --symbol TQQQ --symbol AMD --symbol QQQ
python -m trading_agent research scalp-backtest --period 60d \
  --symbol USO --symbol UNG --symbol SQQQ
python -m trading_agent research scalp-backtest --period 60d --symbol QQQ --symbol SPY --symbol IWM
python -m trading_agent research scalp-backtest --period 60d --last-sessions 10
```

Universe card (live link visibility):

```bash
python -m trading_agent research scalp-universe
python -m trading_agent research scalp-universe --discord
```

## Recommendation

- Keep **gainer CALL / loser cap** policy.  
- Do not expand loser PUT blanketing.  
- Prefer ETF quality over single-name churn if reducing activity.  
- Do not treat this offline BT as proof of edge for live size.
