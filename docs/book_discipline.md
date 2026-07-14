# Book-informed auto-trade discipline

Mechanisms derived from trading books (not prose summaries), including the
[SMB Capital Top Ten Trading Books](https://www.smbtraining.com/blog/top-ten-trading-books)
list (Bellafiore, 2014) plus Shannon MTF from the prior desk goal.

## SMB top ten → code

| # | Book | Author | Mechanism | Module |
|---|------|--------|-----------|--------|
| 1 | Reminiscences of a Stock Operator | Lefèvre | Follow tape/trend; cut losses; never average a loser | `discipline/smb_books.py` → `livermore_tape_and_cut` |
| 2 | Market Wizards series | Schwager | Hard unit risk cap; no discretionary size-up; daily halt | `smb_books.wizards_risk_cap` + `rails` |
| 3 | How to Make Money in Stocks | O'Neil | RVOL + RS + breakout structure (CAN SLIM proxy) | `smb_books.oneil_can_slim_proxy` |
| 4 | The PlayBook | Bellafiore | Named setups + hard checklist | `discipline/playbook.py` |
| 5 | Markets in Profile | Dalton | Value acceptance/rejection proxy | `smb_books.dalton_value_area` |
| 6 | Trading in the Zone | Douglas | Predefined edge (direction/stop/target/risk) | `discipline/edge.py` |
| 7 | Trading to Win | Kiev | Daily loss commitment; no freelanced entries | `smb_books.kiev_commitment` |
| 8 | Enhancing Trader Performance | Steenbarger | Deliberate practice habits in review | `smb_books.smb_process_habit_lines` → insights |
| 9 | The Psychology of Trading | Steenbarger | Internal observer flags (tilt/revenge) | `smb_books.system2_and_observer` |
| 10 | Thinking, Fast and Slow | Kahneman | System-2 veto of FOMO / overconfidence | `smb_books.system2_and_observer` |

### Also wired (prior goal)

| Book | Principle | Module |
|------|-----------|--------|
| **Brian Shannon — Multiple Timeframes** | HTF bias gate; conflict → F | `discipline/mtf_gate.py` |
| **All** | Max concurrent, aggregate risk, post-stop cool-down + `record_open` | `discipline/rails.py` |

## Seed playbook IDs

- `trend_pullback_long`
- `breakdown_momentum_short`
- `opening_range_breakout_long`
- `mean_reversion_long`

## RiskConfig flags

- `require_playbook_checklist` / `require_edge_package` / `enforce_mtf_gate`
- `enforce_discipline_rails` / `max_concurrent_plays` / `max_aggregate_risk_pct` / `stop_cooldown_minutes`
- `enforce_smb_book_gates` (default True)
- `oneil_min_rvol` (default 1.5) / `oneil_min_rs` (default 0 = off)

## Production wire

1. `pipeline.run_pipeline` → `build_session_risk_state` + `build_opportunities`
2. Per candidate: playbook → edge → **SMB book gates** → grade-sort → rails + `record_open`
3. Intraday stop Exit → stopout book for cool-down

```python
from trading_agent.discipline.smb_books import apply_smb_book_gates, SMB_TOP_TEN
from trading_agent.ranking.ranker import build_opportunities
```
