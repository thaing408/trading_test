# Book-informed auto-trade discipline

Mechanisms derived from four process books, wired into `trading_agent` (not prose summaries).

| Author / book | Principle | Module path |
|---------------|-----------|-------------|
| **Mike Bellafiore — The Playbook** | Named setups + hard checklist; only catalogued plays auto-trade | `discipline/playbook.py` → `ranking/ranker.build_opportunities` |
| **Brian Shannon — Multiple Timeframes** | HTF bias gate; conflicting MTF cannot ship A/A+ | `discipline/mtf_gate.py` → `ranking/grades.assign_setup_grade` |
| **Mark Douglas — Trading in the Zone** | Predefined edge: direction, stop, target, size/risk; fail closed | `discipline/edge.py` → ranker + rails |
| **Brett Steenbarger — Daily Trading Coach** | Process metrics by setup (checklist, adherence), not P/L alone | `discipline/process.py` → `performance/insights.generate_insights` |
| **All (discipline)** | Max concurrent plays, aggregate risk, post-stop cool-down (no revenge) | `discipline/rails.py` + `RiskConfig` |

## Seed playbook IDs

- `trend_pullback_long`
- `breakdown_momentum_short`
- `opening_range_breakout_long`
- `mean_reversion_long`

## RiskConfig flags

- `require_playbook_checklist` (default True)
- `require_edge_package` (default True)
- `enforce_mtf_gate` (default True)
- `max_concurrent_plays` / `max_aggregate_risk_pct` / `stop_cooldown_minutes`

## CLI / library checks

```python
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.discipline import apply_mtf_gate, validate_edge_package, require_playbook_pass
```
