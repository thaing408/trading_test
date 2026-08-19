# Packaging roadmap — installable Operator Desk (Mac / Windows)

| Field | Value |
|-------|--------|
| **Status** | Active product direction (2026-08-18) |
| **v1 product** | Installable **Operator Desk** app (read-mostly local UI) |
| **Not v1** | Cloud SaaS, Android LIVE trading, public LAN desk-ui |
| **Related** | [`DESK_UI_AUTO_TRADE.md`](DESK_UI_AUTO_TRADE.md), [`dual_system.md`](dual_system.md), [`options_auto_trade.md`](options_auto_trade.md) |

---

## Why this exists

Today’s delivery model (`git clone` + `pip install -e` + `install.ps1` / `install.sh` + launchd / Task Scheduler) is fine for a single operator but **does not scale** as a long-run product:

- Python interpreter / editable-install drift across machines  
- Role knowledge (Windows research vs Mac execute) lives in docs, not the installer  
- Desk UI is a terminal-started localhost process, not a double-click app  
- State/secrets layout is powerful but not “install → open Desk”

**Keep the engine; productize delivery.**

---

## North star (v1)

```
Operator Desk (Mac .app / Windows installer)
  → local snapshot API / files under ~/.trading_agent
trading-agent runtime (same package family)
  → scheduled desk / consume; role = windows-research | mac-execute
```

**v1 promise:** Install → open Desk → see today’s CASH/ARMED, book, gates, health.  
**Engines stay local.** No cloud sync of books. No order placement from the Desk shell in v1.

---

## Dual-system constraints (never regress)

| Host role | Desk app may | Desk app must not |
|-----------|--------------|-------------------|
| `windows-research` | Read local book/plan/manage; Discord is separate | Place TOS/Schwab orders; assume Mac OMS is local |
| `mac-execute` | Read local book/OMS/ready_orders; kill only if gated | Treat Windows sync paths as Mac truth; rsync books from UI |
| Either | Optional token on localhost | Ship LAN/phone bind as default |

Installer **must** set an explicit role (or detect platform-first the same way `desk_ui` does).

---

## Phases

### Phase 0 — Stabilize the data plane *(in progress)*

- `DeskSnapshot` + `/api/v1/snapshot` + `desk-status` as the **canonical read model**  
- Finish desk-ui investigation panels (rejections / discovery / manage / OMS) per `DESK_UI_AUTO_TRADE.md`  
- Reduce dual-truth noise (plan CASH vs book ARMED, `empty_attempt` overwrites, OMS vs broker CSV)  
- **Feature rule:** new operator-visible state should land in snapshot/readers, not only Discord text  

### Phase 1 — Versioned runtime package

- Ship as versioned wheel / `pipx`-friendly install (not forever `-e`)  
- Bundled or pinned Python story documented per OS  
- CLI entrypoints stable: `trading-agent`, `desk-status`, `desk-ui`  
- First-run: role + Discord mode + LIVE default **off** + state root  
- Keep `install.ps1` / `install.sh` as thin wrappers over the same wizard  

### Phase 2 — Operator Desk shell

- Installable Mac/Windows shell that opens local desk-ui (Tauri/Wails/Electron **or** managed browser to `127.0.0.1`)  
- Templates/static remain package-data (already required for wheels)  
- No auto-start of LIVE trading; optional “start desk-ui at login” only after explicit opt-in  

### Phase 3 — First-run / update UX

- Role picker, health check, schedule opt-in (launchd / Task Scheduler)  
- In-app link to dual_system + options_auto_trade one-pagers  
- Safe upgrade path (migrate state, never clobber prod env without `--force`)  

### Phase 4 — Optional phone companion *(later)*

- Read-only snapshot over VPN/Tailscale (not public internet)  
- Same API as Desk; **no** place/cancel/LIVE from phone in first mobile cut  

---

## Implementation rules (apply to every new feature)

When adding features to `trading_agent`, default to these unless the user overrides:

1. **Prefer local file contracts + `DeskSnapshot` readers** over one-off Discord-only surfaces.  
2. **Do not require** cloud services, shared DBs, or cross-host book rsync for core desk flows.  
3. **Desk UI / status stay read-only** for brokerage (no Schwab refresh subprocess from snapshot).  
4. **Writes** only under `~/.trading_agent/ui/` (acks/notes/flags) until auth + role gates exist; flags stay display-only.  
5. **Kill / LIVE / place** remain Mac-execute gated; Windows research never unlocks via leftover env.  
6. **Package-data awareness:** anything the Desk shell needs (templates, static, default configs) must ship in the wheel/`package-data`, not only the git checkout.  
7. **Avoid new “editable-only” paths** (hard-coded repo `scripts/` for core product flows). Scripts may remain for ops, but product features should work from an installed package.  
8. **Version + role** should be visible in health/snapshot (`host_role`, platform, package version when easy).  
9. **Android / remote UI** is Phase 4 — don’t block desktop packaging on mobile.  
10. **trading_test** stays the methods lab; don’t merge lab UX into the Operator Desk product surface.

---

## Non-goals (near term)

- Multi-tenant SaaS  
- Replacing Discord as the human briefing channel  
- One binary that places orders from the Windows research PC  
- Rewriting the CIO/desk engine in another language “for the app”  

---

## Success metrics

| Milestone | Done when |
|-----------|-----------|
| Phase 0 | Fresh machine can `desk-status` / desk-ui against real `~/.trading_agent` without tribal paths |
| Phase 1 | `pipx install` (or equiv) + role wizard; no `pip install -e` required for daily use |
| Phase 2 | Double-click Desk on Mac **or** Windows shows today’s book without opening a terminal first |
| Phase 3 | New user completes install → dry-run session without reading more than one short guide |

---

## Open decisions (non-blocking)

- Shell tech: Tauri vs Wails vs Electron vs “browser helper”  
- Whether Mac execute ships Schwab MCP inside the same installer or as a documented companion  
- Auto-update channel (GitHub Releases vs manual)

---

*End of packaging roadmap.*
