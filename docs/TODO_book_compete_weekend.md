# Weekend TODO — books compete for ticker

**Status:** **Done** (default mode still `hard`).  
**Shipped:** see `docs/book_discipline.md` → **Books compete for ticker**.

## Observe this week (Mon–Fri)
- [x] Multi-method PLAY / EXPORT quality live (ongoing ops)
- [x] Implement score mode behind env flag

## Implement weekend
- [x] `book_gates_mode=score` (keep `hard` A/B)
- [x] Per-book points + mechanism dedupe
- [x] `compete_score` rank → top candidates / export order
- [x] Safety-only hard vetoes
- [x] Multi-method merge by compete_score
- [x] Tests + `docs/book_discipline.md` update

```bash
# Opt-in on research
TRADING_AGENT_BOOK_GATES_MODE=score
```
