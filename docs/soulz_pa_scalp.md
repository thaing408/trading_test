# Soulz-style PA scalp (BRR + Range + Fib)

Paper implementation inspired by [CryptoSoulz @SoulzBTC scalping video](https://x.com/SoulzBTC/status/2085693599262363780) (BRR, Range, Fibonacci, combine).

**Not affiliated.** Educational reimplementation of common price-action tactics.

## Setups

| Tag | Idea |
|-----|------|
| **brr** | Break of prior swing high/low → retest holds → continuation candle |
| **range** | Rejection at range edge (bottom 15% / top 15%), not mid-box |
| **fib** | Pullback into 38.2–61.8% of last impulse + bounce |

**Default:** need **confluence ≥ 2** tags agreeing on the same side.

## CLI

```bash
# Recent signals brief
python -m trading_agent research soulz --symbol QQQ

# Backtest (15m, ~60d yfinance)
python -m trading_agent research soulz-backtest --symbol QQQ --period 60d --interval 15m

# Crypto
python -m trading_agent research soulz-backtest --symbol BTC-USD --period 60d --interval 15m

# Stricter / looser
python -m trading_agent research soulz-backtest --symbol QQQ --min-confluence 2
python -m trading_agent research soulz --symbol QQQ --backtest --period 30d
```

## Exits

Synthetic premium (same family as ODTE/top-winners):

- TP **+25%** / SL **−20%** on premium  
- Optional trail (+12% activate / 8pp giveback)  
- RTH time exit 15:45 ET when `rth_only` (equities)

## Code

- `trading_agent/scalp/soulz_pa.py`  
- Tests: `tests/test_soulz_pa.py`
