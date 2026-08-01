# System trade-readiness + methods research (2026-08-01)

## 1. Can the system trade today?

**Yes, semi-auto — not fully auto.**

| Path | Research | Ready orders | Live broker | Human still needed |
|------|----------|--------------|-------------|--------------------|
| **Desk options book** | Strong | Yes | Single-leg debit + equity BUY only | Multi-leg IC/spreads/credit → TOS |
| **OMS consume** | — | Yes | Same + pretrade/kill | Flatten-all incomplete |
| **Scalp bot** (`auto_trade_qqq`) | Live MCP | — | Yes (its own rules) | Monitoring / caps |
| **ORB / momentum sleeves** | Offline BT only | Not wired | No | Research only |

### Live place matrix (desk)

| Package | Auto when LIVE=1? |
|---------|-------------------|
| Long call/put (1 strike) | Yes |
| Equity buy | Yes (no bracket) |
| Credit / multi-leg | Ready-only (default) |

### CIO + cash (unchanged)

Strict by design: `stay_in_cash`, env &lt; 42 hard cash, conf ≥ 60, min cash 20% (60%+ if weak env).  
**Do not loosen** to force trades — desk historical path was net negative on real Schwab data.

---

## 2. What we already built (this project arc)

- Dual research/execute, books, playbook/MTF/rails, options methods  
- OMS: audit, kill switch, pretrade (incl. optional BP floor), manage loop stubs  
- Quant: historical load, walk-forward, features, linear ranker (paper)  
- Scalp multi-ticker BT + variants  
- **New:** ORB+VWAP, momentum/RS, regime×premium sleeves + CLI  

```bash
python3 -m trading_agent research methods-backtest --method all
python3 -m trading_agent research scalp-backtest --period 60d
```

---

## 3. Missing pieces (priority)

### Critical for true desk auto

1. Atomic multi-leg + credit place  
2. Broker OCO/brackets after fill  
3. Position truth from Schwab for exits  
4. Kill → flatten-all  
5. Journal from fills  

### Critical for better edge

6. Wire **only** sleeves that clear offline bars into paper book  
7. News/time blackouts  
8. Paper twin parallel LIVE  

---

## 4. Industry methods map

| Method | Status in repo | BT note |
|--------|----------------|---------|
| Playbook / checklist / MTF / rails | Shipped | Keep |
| Defined-risk options + IV/POP | Shipped | Fill model weak; path losing on hist |
| Prop daily loss / kill | Partial OMS | Finish flatten |
| **ORB + VWAP** | **New sleeve** | See §5 |
| **Cross-section momentum** | **New sleeve** | Underperformed SPY 1y |
| **Regime × premium** | **New ablation** | See §5 |
| Scalp level rules | Live MCP + BT | ETFs best; bear weak (user keeps on) |
| ML ranker | Paper only | Not LIVE |
| Deep RL / order flow | Out of scope | — |

---

## 5. Fresh backtests (implemented methods)

### A) ORB + VWAP (QQQ/SPY/IWM, 60d, 15m, 100 sh, 1.5R)

| Symbol | n | WR | Expectancy | P/L | Avg R |
|--------|---|-----|------------|-----|-------|
| **SPY** | 58 | **52%** | **+$20** | **+$1,170** | **+0.27** |
| QQQ | 58 | 45% | −$49 | −$2,863 | −0.04 |
| IWM | 57 | 39% | −$13 | −$755 | −0.07 |
| **All** | 173 | 45% | −$14 | −$2,447 | +0.05 |

**Suggestion:** Only **SPY ORB+VWAP** is interesting for paper; QQQ/IWM not edge on this window.

### B) Momentum / RS (top-3, 1y daily, 5 bps)

| Metric | Value |
|--------|--------|
| Trades | 31 |
| WR | **25.8%** |
| Total P/L | **−$7,482** |
| SPY buy-hold 100 sh | **+$7,606** |
| Beat SPY? | **No** |

**Suggestion:** Do **not** promote momentum sleeve to LIVE. Revisit with longer lookback/costs-aware ranking later.

### C) Desk premium path × SPY regime (1y, costs on)

| Regime | n | WR | Exp | P/L |
|--------|---|-----|-----|-----|
| trend_up | 105 | **31%** | −$126 | −$13.3k |
| trend_down | 3 | 0% | −$752 | −$2.3k |
| chop | 237 | **14%** | −$543 | −$128.8k |
| **Full** | 345 | 19% | −$418 | −$144k |

**Note:** On this fill model, **chop is not safer** for short premium — losses concentrate in chop with many trades. Classic “sell premium in chop” did **not** rescue this engine. Root issue is likely **strategy mix + fill model**, not only regime.

**Suggestion:** Do not add “only trade IC in chop” as a magic fix until options path is re-specified (real marks, fewer low-quality CC/IC).

### D) Scalp (prior runs, bear ON)

| Config | WR | Notes |
|--------|-----|--------|
| All names 60d | 35% | Bear bleeds |
| ETFs only | 47% | Better |
| ETFs + no bear | 50% | Best relative (user keeps bear on) |

---

## 6. Ranked recommendations

### Operate next week

1. **Scalp:** keep as configured (bear on). Focus attention on **QQQ/SPY/IWM**. Expect ~15–30 entries/week if 4-name bot active.  
2. **Desk LIVE:** ready_orders + selective single-leg; **human for multi-leg/credit**.  
3. **Do not** loosen CIO/cash.  
4. Paper-watch **SPY ORB+VWAP** only (no LIVE until 2 weeks paper).  

### Build next (order)

| # | Work | Why |
|---|------|-----|
| 1 | Fill/exit/journal truth on OMS | Execution debt |
| 2 | Paper SPY ORB signals → Discord only | Only sleeve with positive SPY BT |
| 3 | Fix options desk fill assumptions / cut CC spam | Premium path broken in BT |
| 4 | Multi-leg LIVE only after Schwab package support | Real desk product |

### Do not build

- Promote momentum to LIVE  
- Loosen gates for trade count  
- FinRL production  

---

## 7. Bottom line

| Question | Answer |
|----------|--------|
| Implemented to trade? | **Semi-auto: research full; LIVE partial** |
| Biggest miss? | **Multi-leg/credit + protect/exit + honest options P/L** |
| Best new method BT? | **SPY ORB+VWAP modest +**; momentum **fail**; premium×chop **fail** |
| Next week ops | Scalp as-is; desk conservative; paper SPY ORB |

CLI artifacts: `docs/methods_sleeves_backtest.md`, this file.
