# trading_test — No CIO + IBKR paper

Isolated fork of `trading_agent` for **paper trading without CIO approval**.

Production `~/trading_agent` is unchanged.

## What changed

| Area | Behavior |
|------|----------|
| **CIO** | Off by default (`TRADING_AGENT_INCLUDE_CIO=0`). Approval + review phases skipped. |
| **Research** | Still runs full pipeline; **auto-exports** ranked names to `auto_trade_book.json`. |
| **Discovery** | No mid-session CIO promotion. |
| **Broker** | `TRADING_AGENT_BROKER=ibkr` → **options debit** via TWS paper (port **7497**). |
| **Instrument** | **Options only** (`TRADING_AGENT_OPTIONS_ONLY=1`) — share lots blocked. |
| **Data** | IBKR OHLCV when TWS up (`IBKR_ENABLED=1`). |

## Setup (once)

```bash
bash ~/trading_test/scripts/macos/paper-day-setup.sh
# edit ~/.trading_test/trading-test.env
```

## Tomorrow morning

1. **Log into TWS Paper**
   - API: Enable ActiveX and Socket Clients  
   - Port **7497**  
   - For paper **orders**: uncheck **Read-Only API** (or TWS will reject placeOrder)  
   - Keep paper account selected  

2. **Env checks** in `~/.trading_test/trading-test.env`:
   ```bash
   IBKR_PORT=7497
   IBKR_READONLY=0          # required to place paper orders
   TRADING_AGENT_BROKER=ibkr
   TRADING_AGENT_INCLUDE_CIO=0
   TRADING_AGENT_AUTO_TRADE_LIVE=0   # keep 0 until first dry consumer looks good
   ```

3. **Desk (research → book, no CIO)**  
   ```bash
   bash ~/trading_test/scripts/macos/run-paper-session.sh
   ```

4. **Consumer (dry first)**  
   ```bash
   bash ~/trading_test/scripts/macos/run-paper-consumer.sh
   ```
   Inspect `~/.trading_test/sync/auto_trade_book.json` and ready_orders.

5. **Paper live**  
   Set `TRADING_AGENT_AUTO_TRADE_LIVE=1`, restart consumer. Orders go to **IBKR paper**.

## Discord paper journal

All **trading_test** activity posts to channel:

**`1536602374502613013`**

| Event | When |
|-------|------|
| Desk phases (research, intraday, performance) | Session posts |
| **ENTER / EXIT / FAILED / DRY_RUN** | Auto-trade consumer |
| **Manage exits** | OMS manage loop |
| **Positions snapshot** | After order cycles + EOD |
| **EOD summary** | Performance phase + `post-paper-eod.sh` |

```bash
# Manual EOD post
bash ~/trading_test/scripts/macos/post-paper-eod.sh
```

Uses bot token from `~/.grok/discord.env`; production webhook is unset so traffic stays on this channel.

## Safety

- State lives under `~/.trading_test/` (not `~/.trading_agent/`) when env is set.
- Default consumer is **not** live until you flip the flag.
- Multi-leg / credit packages still ready-only (manual).
- Schwab path unused when `TRADING_AGENT_BROKER=ibkr`.

## Re-enable CIO (not recommended for paper fork)

```bash
TRADING_AGENT_INCLUDE_CIO=1
```
