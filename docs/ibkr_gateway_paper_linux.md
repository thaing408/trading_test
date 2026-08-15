# Paper-only IB Gateway on Linux researcher (`me-ai`)

**Goal:** Run IBKR **paper** API on the researcher host so the **Mac only runs TOS + Schwab production**.  
Paper trading / `trading_test` talks to Gateway on Linux (not TWS on the Air).

```text
Mac                          Linux me-ai
────                         ───────────
TOS + Schwab desk            IB Gateway paper :4002
Discord (prod)               trading_test (optional)
                             researcher books / bot
                             Discord paper channel (optional)
```

---

## 0. Prerequisites

| Item | Notes |
|------|--------|
| Host | `me-ai.local` / `10.0.0.52`, user `ubuntu` |
| IB account | Same paper account (e.g. `DUQ…`) |
| Java | IB Gateway installer needs a JRE (bundled on many builds) |
| Ports | **Paper Gateway = 4002**, live Gateway = 4001 (do not open live) |
| Mac TWS | **Off** during RTH if Air is tight |

---

## 1. Install IB Gateway (Linux)

On a machine with a browser (or download on Mac and `scp`):

1. [IBKR API / TWS software](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) → **IB Gateway** for Linux.
2. Copy installer to me-ai, e.g.:
   ```bash
   scp ibgateway-*.sh ubuntu@me-ai.local:~/
   ssh ubuntu@me-ai.local
   chmod +x ibgateway-*.sh
   ./ibgateway-*.sh
   ```
3. Install under e.g. `~/Jts` or `~/ibgateway` (default is fine).

**Headless / no desktop:** use Xvfb or IBC (IB Controller) later; first install can be one interactive login with VNC/x11 if needed.

---

## 2. First login (paper)

1. Start Gateway:
   ```bash
   # path depends on install; example:
   ~/Jts/ibgateway/*/ibgateway
   # or the desktop launcher IB provides
   ```
2. Choose **Paper Trading** (not live).
3. Log in with paper credentials.
4. **Configure → Settings → API → Settings**
   - Enable **ActiveX and Socket Clients**
   - Socket port **4002** (paper)
   - Trusted IPs: `127.0.0.1` (and Mac LAN IP if Mac clients connect remotely)
   - **Uncheck Read-Only API** if you will place paper orders
5. Leave Gateway running (or use systemd — §5).

---

## 3. Network: who connects where

### Option A — Paper consumer **on Linux** (best for Mac resources)

- `trading_test` + env on me-ai  
- `IBKR_HOST=127.0.0.1`  
- `IBKR_PORT=4002`  
- Discord paper channel from Linux  

Mac never runs IBKR.

### Option B — Consumer still on Mac, Gateway on Linux

- Open firewall only to Mac:
  ```bash
  # on me-ai (ufw example)
  sudo ufw allow from <MAC_LAN_IP> to any port 4002 proto tcp
  ```
- On Mac `~/.trading_test/trading-test.env`:
  ```bash
  IBKR_HOST=10.0.0.52   # or me-ai.local
  IBKR_PORT=4002
  IBKR_ENABLED=1
  IBKR_READONLY=0
  TRADING_AGENT_BROKER=ibkr
  ```
- Gateway API must allow the Mac IP (not only 127.0.0.1).

**Prefer Option A** so the Air stays TOS-only.

### Mac TigerVNC (paper Gateway login UI) — automated

me-ai runs **Xvfb :99** + **x11vnc** on **localhost:5900** (not exposed to the LAN).  
Your Mac only needs a local SSH forward + TigerVNC.

**One-time install (Mac):**

```bash
cd ~/trading_test && git pull
bash scripts/macos/install-me-ai-vnc-tunnel-launchd.sh
```

That loads LaunchAgent **`com.grok.me-ai-vnc-tunnel`** which keeps:

`127.0.0.1:5901` → `ubuntu@me-ai:127.0.0.1:5900`

**Daily (only login in the viewer):**

```bash
me-ai-vnc
# or: bash ~/trading_test/scripts/macos/me-ai-vnc-open.sh
```

TigerVNC opens to **`127.0.0.1::5901`**. Log into **IB Gateway paper** (API **4002**). Leave it running.

| CLI | Role |
|-----|------|
| `me-ai-vnc` | Ensure tunnel + open TigerVNC |
| `me-ai-vnc-tunnel --status` | Local tunnel + remote 5900/4002 |
| `me-ai-vnc-tunnel --once` | Start tunnel only (no viewer) |
| `me-ai-vnc-tunnel --stop` | Stop local tunnel |

**Prereq:** passwordless SSH (`ssh ubuntu@me-ai.local`). Host order: `ME_AI_HOST` → `~/.grok/researcher_host` → `me-ai.local` → `10.0.0.52`.

**Manual equivalent (if you skip LaunchAgent):**

```bash
ssh -N -L 5901:127.0.0.1:5900 ubuntu@me-ai.local
# TigerVNC → 127.0.0.1::5901
```

---

## 4. Env sketch (Linux `trading_test`)

```bash
# ~/.trading_test/trading-test.env on me-ai
TRADING_AGENT_INCLUDE_CIO=0
TRADING_AGENT_OPTIONS_ONLY=1
TRADING_AGENT_BROKER=ibkr

IBKR_ENABLED=1
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=17
IBKR_TRADE_CLIENT_ID=27
IBKR_ACCOUNT=DUQ181571          # your paper account
IBKR_READONLY=0                 # for paper orders

DISCORD_PAPER_CHANNEL_ID=1536602374502613013
# DISCORD_TOKEN from bot — keep secret, never commit

TRADING_AGENT_AUTO_TRADE_LIVE=0 # 1 only when paper ready
```

Ping from me-ai:

```bash
cd ~/trading_test   # after clone
IBKR_PORT=4002 IBKR_ENABLED=1 .venv/bin/python scripts/ibkr_research_ping.py
```

---

## 5. Keep Gateway up (systemd sketch)

After one successful interactive paper login, automate restart (IBC recommended long-term). Minimal idea:

```ini
# /etc/systemd/system/ibgateway-paper.service  (customize paths)
[Unit]
Description=IB Gateway Paper
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Jts
# Use IBC or vendor start script; plain GUI may need Xvfb:
# ExecStart=/usr/bin/xvfb-run -a /home/ubuntu/Jts/.../ibgateway
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

**IBC (IB Controller):** better for unattended re-login; install when basic Gateway works.

---

## 6. Mac production day (RTH)

| Do | Don’t |
|----|--------|
| TOS + Schwab desk | Start TWS/Gateway on Mac |
| `IBKR_ENABLED=0` optional in `~/.grok/trading-agent.env` if you want zero IBKR probes | Run paper consumer + live desk on same tiny RAM budget |

Production desk already uses Schwab; IBKR down is fine.

---

## 7. Checklist (first Linux paper weekend)

- [ ] Gateway installed on me-ai  
- [ ] Paper login works  
- [ ] Port **4002** listening: `ss -lntp | grep 4002`  
- [ ] Research ping OK from me-ai  
- [ ] (Optional) 1-share or 1-contract **paper** order test **during RTH**  
- [ ] Discord paper channel gets a test post  
- [ ] Mac RTH: only TOS; Gateway stays on Linux  

---

## 8. What we do *not* move

| Stays on Mac | Stays on / can stay Linux |
|--------------|---------------------------|
| TOS / Schwab production | Gap / playlist researcher |
| Prod Discord desk channel | Paper Gateway + optional trading_test |
| Live Schwab auto-trade | Paper Discord `1536602374502613013` |

---

## 9. Suggested sequence

1. **Install Gateway paper on me-ai** (one evening).  
2. **Ping + paper order** from me-ai localhost.  
3. **Clone `trading_test` on me-ai** (or rsync from Mac).  
4. **Run consumer only on me-ai** when paper testing.  
5. **Mac RTH:** TOS only; never start IBKR on Air.

When you’re ready for step 1–2, we can walk through install commands over SSH on me-ai live.

---

## Install status on me-ai (2026-08-11)

| Step | Status |
|------|--------|
| Download stable Gateway Linux x64 | **Done** |
| Install to `~/ibgateway` | **Done** |
| `jts.ini` + start scripts | **Done** |
| System packages (`xvfb`) | **Blocked** — no passwordless sudo |
| Paper login + API 4002 | **Pending you** |

### Finish on me-ai (one sudo)

```bash
ssh ubuntu@me-ai.local
bash ~/bin/install-xvfb-once.sh
~/bin/start-ibgateway-paper.sh   # log in Paper, set API port 4002
~/bin/ibgateway-status.sh
```

Details also on host: `~/IBGATEWAY_PAPER_SETUP.md`
