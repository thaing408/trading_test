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
- `enforce_discipline_rails` (default True)
- `max_concurrent_plays` / `max_aggregate_risk_pct` / `stop_cooldown_minutes`

## Production wire (desk path)

1. `pipeline.run_pipeline` → `build_session_risk_state(config.risk)` loads:
   - open symbols from `TRADING_AGENT_POSITIONS_FILE` (or brokerage via plan_loader)
   - stop-outs from `TRADING_AGENT_STOPOUT_FILE` or `~/.trading_agent/stopouts.json`
2. `build_opportunities(..., session_state=..., rail_rejections=...)` **always** applies rails;
   when `session_state` is None it seeds limits from `RiskConfig` via `session_state_from_risk_config`.
3. Intraday Exit on `stop_loss_triggered` → `record_stopout_event(symbol)` for cool-down.

## CLI / library checks

```python
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.discipline import apply_mtf_gate, validate_edge_package, require_playbook_pass
```
