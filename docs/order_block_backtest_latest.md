# Order Block Backtest (ICT + SMC)

Generated via:
`python -m trading_agent research order-block-backtest QQQ,SPY --period 59d --interval 15m --min-score 70`

Also ran default min_score=55 and QQQ style-split (ICT / SMC / both) — summary in session notes.

---

## QQQ

### Assumptions
- Walk-forward: score_order_block_entry on bars[:i+1] only (no lookahead)
- Styles=['ict', 'smc']; min_score=70.0; R=1.5
- Symbol=QQQ; period=59d; interval=15m
- Underlying R multiples (stop beyond zone, target = R×risk)
- RTH entries 09:35:00–15:55:00 ET; max 2/day; hold≤24 bars
- Stop checked before target on same bar (conservative)
- HTF filter off in BT (isolated method edge)

### Results
- **Sessions scanned:** 59
- **Trades:** 59
- **Winners / Losers:** 31 / 28
- **Win rate:** **52.5%**
- **Total R:** -1.91R
- **Expectancy:** -0.032R / trade
- **Exits:** {'stop': 21, 'target': 7, 'time': 31}
- **Sides:** {'CALL': 30, 'PUT': 29}
- **By style tag:** {'ict': {'trades': 25, 'total_r': -0.752, 'win_rate': 0.56}, 'ict+smc': {'trades': 32, 'total_r': 0.128, 'win_rate': 0.531}, 'smc': {'trades': 2, 'total_r': -1.289, 'win_rate': 0.0}}

### Sample trades (up to 12)
- 2026-05-20 PUT [ict] score=83 @ 710.76 → 712.99 (stop) **-1.00R**
- 2026-05-21 PUT [ict] score=83 @ 710.17 → 713.54 (stop) **-1.00R**
- 2026-05-22 CALL [ict+smc] score=91 @ 719.67 → 717.43 (time) **-0.66R**
- 2026-05-27 CALL [ict] score=83 @ 729.90 → 726.14 (stop) **-1.00R**
- 2026-05-27 CALL [ict] score=83 @ 727.30 → 729.49 (time) **+0.72R**
- 2026-05-28 CALL [ict+smc] score=95 @ 728.12 → 731.80 (target) **+1.50R**
- 2026-05-29 CALL [ict+smc] score=95 @ 737.45 → 738.23 (time) **+0.23R**
- 2026-06-01 PUT [ict+smc] score=95 @ 736.40 → 742.67 (stop) **-1.00R**
- 2026-06-02 CALL [ict+smc] score=95 @ 744.08 → 746.14 (time) **+0.47R**
- 2026-06-03 CALL [ict] score=83 @ 745.71 → 744.25 (time) **-0.31R**
- 2026-06-08 CALL [ict] score=83 @ 715.65 → 716.10 (time) **+0.13R**
- 2026-06-09 CALL [ict] score=83 @ 711.04 → 705.98 (stop) **-1.00R**

## SPY

### Assumptions
- Walk-forward: score_order_block_entry on bars[:i+1] only (no lookahead)
- Styles=['ict', 'smc']; min_score=70.0; R=1.5
- Symbol=SPY; period=59d; interval=15m
- Underlying R multiples (stop beyond zone, target = R×risk)
- RTH entries 09:35:00–15:55:00 ET; max 2/day; hold≤24 bars
- Stop checked before target on same bar (conservative)
- HTF filter off in BT (isolated method edge)

### Results
- **Sessions scanned:** 59
- **Trades:** 58
- **Winners / Losers:** 26 / 32
- **Win rate:** **44.8%**
- **Total R:** -1.53R
- **Expectancy:** -0.026R / trade
- **Exits:** {'stop': 17, 'target': 8, 'time': 33}
- **Sides:** {'CALL': 31, 'PUT': 27}
- **By style tag:** {'ict+smc': {'trades': 35, 'total_r': 0.061, 'win_rate': 0.457}, 'ict': {'trades': 22, 'total_r': -1.487, 'win_rate': 0.455}, 'smc': {'trades': 1, 'total_r': -0.105, 'win_rate': 0.0}}

### Sample trades (up to 12)
- 2026-05-21 CALL [ict+smc] score=95 @ 738.59 → 742.21 (target) **+1.50R**
- 2026-05-22 CALL [ict+smc] score=91 @ 747.88 → 745.59 (time) **-0.60R**
- 2026-05-26 CALL [ict] score=83 @ 749.20 → 750.47 (time) **+0.62R**
- 2026-05-27 CALL [ict+smc] score=95 @ 750.49 → 750.47 (time) **-0.01R**
- 2026-05-28 CALL [ict] score=83 @ 750.17 → 754.34 (target) **+1.50R**
- 2026-05-29 CALL [ict] score=83 @ 756.04 → 756.40 (time) **+0.12R**
- 2026-06-01 PUT [ict+smc] score=88 @ 755.55 → 759.34 (stop) **-1.00R**
- 2026-06-02 CALL [ict] score=83 @ 757.62 → 760.36 (target) **+1.50R**
- 2026-06-03 CALL [ict] score=79 @ 755.57 → 754.19 (time) **-0.49R**
- 2026-06-04 PUT [ict] score=83 @ 755.28 → 757.49 (stop) **-1.00R**
- 2026-06-08 PUT [ict+smc] score=88 @ 740.85 → 739.31 (time) **+0.29R**
- 2026-06-09 PUT [ict+smc] score=95 @ 744.38 → 738.84 (target) **+1.50R**

_Research only — mechanical OB proxy. Not financial advice._