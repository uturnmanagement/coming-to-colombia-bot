# Layer 7C — Activation & Deployment Plan

**Project:** coming-to-colombia-bot
**Base:** `main` @ `9671f99` (Layers 0–6 + 7A + 7B merged)
**Status of THIS document:** PLAN ONLY. Nothing is deployed, no live Telegram is enabled, `DRY_RUN` is not disabled, no secrets are present. Local `.env` remains `DRY_RUN=true`, `SCANNER_TELEGRAM_ENABLED=false`.

> This is the runbook for taking the desk live. Execution is deferred — every step below is a documented procedure for an operator to run deliberately, not an action taken by this layer.

---

## 0. Critical activation finding (read first)

There are **two** switches, and only **one** of them arms live sends:

| Switch | Default (code) | Desk value | What it actually does |
|--------|----------------|-----------|------------------------|
| `DRY_RUN` | `false` | **`true`** | The dispatcher's first check. `true` → record to outbox + audit, **sender never called**. `false` → live send allowed (still subject to the gate). **This is the arming switch.** |
| `SCANNER_TELEGRAM_ENABLED` | `true` | **`false`** | Chooses the *path*, not whether to send. `false` → scanner routes RED deals through Oak Street (the 7B pipeline: heartbeat decay + specialists + briefing + dispatcher gate + audit). `true` → **legacy direct `bot.send_message`, which bypasses DRY_RUN, the severity gate, dedupe, cooldown, and the audit log entirely.** |

**Consequence (must not be missed):** the safe live posture is
`SCANNER_TELEGRAM_ENABLED=false` **and** `DRY_RUN=false`.
Setting `SCANNER_TELEGRAM_ENABLED=true` is **not** "arming" — it *disarms the entire safety architecture* by reverting to the legacy direct path. Keep it `false` at all times for the live desk.

So: **arm with `DRY_RUN=false` only. Never flip the kill switch to `true` in production.**

---

## 1. Activation architecture

```
scan_job ─RED─► _emit_red
                 │  SCANNER_TELEGRAM_ENABLED == false  (required for the safe path)
                 ▼
            DeskPipeline.process_event
                 ├─ OakStreet.ingest_alert      → heartbeat decay → dispatcher.send(kind=alert|heartbeat)
                 ├─ Delta/Echo/India.analyze    → ingest_report
                 └─ OakStreet.dispatch_briefing → dispatcher.send(kind=heartbeat)
                                                      │
                                                      ▼
                                         TelegramDispatcher.send  (the ONLY live seam)
                 1. DRY_RUN?            → outcome=dry_run (sender NEVER called)        ← arming gate
                 2. severity gate       → kind heartbeat/system always; alert RED-only; digest blocked
                 3. dedupe (300s)       → identical payload suppressed
                 4. per-deal cooldown   → safety floor (default 60s)
                 5. sender(chat,text)   → _bot_sender (fire-and-forget on PTB loop)   ← only live send
                 └─ LiveSendAuditor     → one JSONL row, every decision
```

**Single live seam:** `dispatcher.sender` (= `_bot_sender` in `main.py`). It is invoked **only** when DRY_RUN is false AND the gate passes AND not a duplicate AND not in cooldown AND a sender is attached. Every other outcome is recorded and silent.

**Audit outcomes (7):** `sent` · `dry_run` · `suppressed_gate` · `suppressed_dedupe` · `suppressed_cooldown` · `no_sender` · `send_error`.

---

## 2. Every switch required for live activation

| # | Setting | Pre-activation | Activated | Notes |
|---|---------|----------------|-----------|-------|
| 1 | `DRY_RUN` | `true` | **`false`** | The arming switch. Flip LAST. |
| 2 | `SCANNER_TELEGRAM_ENABLED` | `false` | `false` (unchanged) | Keep false — routes through the safe path. |
| 3 | `TELEGRAM_BOT_TOKEN` | (set) | (set) | Real bot token on host only. |
| 4 | `TELEGRAM_CHAT_ID` | (set) | (set) | Bare integer chat id. |
| 5 | `REGION_PACK` | `colombia` | `colombia` | Live desk. |
| 6 | `FLIGHT_API_PROVIDER` | `placeholder` | `placeholder` → live | Real flight data is optional for first canary. |
| 7 | `LIVE_PROVIDERS_ENABLE` | `false` | `false` → `true` | Only when real lodging/airfare adapters are wired (later). |

First canary can run on **mock/placeholder data** with only switches 1–5 — proving the *send path* without committing to paid data feeds.

---

## 3. DRY_RUN removal sequence

Pre-flight (all must be true before flipping):
1. On the VPS, venv built, `python tests\...` full suite green on host (291/291).
2. `.env` present; `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` set; `REGION_PACK=colombia`.
3. `SCANNER_TELEGRAM_ENABLED=false` confirmed (see §7 kill-switch verification).
4. Bot started once with `DRY_RUN=true`; `get_me()` succeeded; audit log shows only `outcome=dry_run` rows for a full scan cycle.
5. Operator watching `logs/colombia_desk_live_sends.jsonl` live.

Flip:
6. Edit `.env`: `DRY_RUN=false`. Save.
7. `sudo systemctl restart coming-to-colombia-bot`.
8. Confirm in `logs/service.log`: bot online + polling.

Immediately after: go to §4 canary observation.

---

## 4. Telegram arming sequence (canary)

1. With `DRY_RUN=false` and `SCANNER_TELEGRAM_ENABLED=false`, the dispatcher now sends only what passes the gate (RED alerts + heartbeats/briefings).
2. Trigger or wait for the first RED deal (or inject a controlled RED via a scan against a known-cheap route).
3. Watch the audit log for the first `outcome=sent` row; cross-check the message arrived in the Telegram chat.
4. Verify dedupe + cooldown by confirming a repeat scan of the same deal yields `suppressed_dedupe` / `suppressed_cooldown`, not a second message.
5. Hold a short canary window (e.g., one full recheck interval). If clean, the desk is live. If anything looks wrong, go to §5 rollback.

---

## 5. Rollback procedure

Fastest, safest mute (no redeploy):
1. Edit `.env`: `DRY_RUN=true`.
2. `sudo systemctl restart coming-to-colombia-bot`.
3. Confirm audit log returns to `outcome=dry_run`; no further `sent` rows.

Escalating options:
- **Stop entirely:** `sudo systemctl stop coming-to-colombia-bot`.
- **Code rollback:** `git checkout main && git reset --hard <previous-good-sha>` (e.g., `9671f99`), rebuild venv, restart. Prefer `git revert` if the branch is shared.
- **Never** rely on `SCANNER_TELEGRAM_ENABLED=true` as a rollback — that bypasses safety, not enables it.

Rollback triggers: duplicate/spam messages, wrong chat, malformed HTML, unexpected `send_error` spikes, or any message that should have been gated.

---

## 6. VPS deployment checklist

- [ ] Linux VPS (Hostinger/EC2), Python 3.12, non-root run user created.
- [ ] `git clone https://github.com/uturnmanagement/coming-to-colombia-bot.git`
- [ ] `python -m venv .venv` && `.venv/bin/pip install -r requirements.txt`
- [ ] Copy `.env.example` → `.env`; fill real secrets; **`DRY_RUN=true`**, **`SCANNER_TELEGRAM_ENABLED=false`**.
- [ ] Run full test suite on host (expect 291/291 + 4 DRY_RUN scenarios).
- [ ] `python main.py` once (DRY_RUN) → confirm `get_me()`, polling, outbox/audit populate, **zero `sent`**.
- [ ] Fill `deployment/systemd/coming-to-colombia-bot.service.template` placeholders (`__PROJECT_DIR__`, `__RUN_USER__`, `__REGION__`), install to `/etc/systemd/system/`, `daemon-reload`, `enable`.
- [ ] `systemctl start` under DRY_RUN; verify `logs/service.log`.
- [ ] Set up log retention/monitoring for `logs/service.log` + `logs/colombia_desk_live_sends.jsonl`; disk + uptime alert.
- [ ] Only then proceed to §3 → §4 (arming).

---

## 7. Required environment variables

**Mandatory for live:**
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `REGION_PACK=colombia`,
`DRY_RUN` (false to arm), `SCANNER_TELEGRAM_ENABLED=false`.

**Dispatcher tuning (optional, defaults safe):**
`LIVE_SEND_AUDIT_LOG` (default `logs/colombia_desk_live_sends.jsonl`),
`LIVE_SEND_COOLDOWN_SECONDS` (60), `LOG_LEVEL` (INFO).

**Data sources (optional; mock/placeholder until wired):**
`FLIGHT_API_PROVIDER` (+ `RAPIDAPI_KEY`/`RAPIDAPI_HOST` or `FLIGHT_API_KEY`/`FLIGHT_API_SECRET`),
`LODGING_INTEL_ENABLED` (true), `LIVE_PROVIDERS_ENABLE` (false),
`LIVE_AIRFARE_PROVIDER`/`LIVE_LODGING_PROVIDER` (mock), `LIVE_*_API_KEY`,
`LIVE_PROVIDER_TIMEOUT_SECONDS` (8), `AIRDNA_API_KEY`, `INSIDE_AIRBNB_LOCAL_PATH`,
`INDIA_TYPICAL_PRICES_JSON`, lodging thresholds + return-window knobs.

**Secrets discipline:** secrets live only in the host `.env` (git-ignored). Never commit, never log, never echo. The audit log records outcomes + a payload digest, not tokens.

---

## 8. Kill-switch verification

Before and after arming, confirm the safe path is active:
1. `.env` shows `SCANNER_TELEGRAM_ENABLED=false`.
2. With `DRY_RUN=true`, run a scan; the audit log must show dispatcher rows (`outcome=dry_run` with `kind=alert|heartbeat`). Their presence proves sends route **through the dispatcher** (safe path), not the legacy direct path (which writes **no** audit rows).
3. If a RED scan produces **no** audit rows, the kill switch is wrong (`true`) — sends are bypassing the architecture. Fix to `false` before going further.
4. Negative check: there must be no `digest`/YELLOW `alert` rows with `outcome=sent` (gate must suppress them).

---

## 9. Audit log verification

File: `logs/colombia_desk_live_sends.jsonl` (one JSON object per line).

Per stage, expected outcomes:
- **DRY_RUN host smoke:** every row `outcome=dry_run`. Zero `sent`.
- **Canary (armed):** RED alert → `sent`; briefing (`kind=heartbeat`) → `sent`; repeat of same deal → `suppressed_dedupe`/`suppressed_cooldown`; YELLOW alert → `suppressed_gate`; digest → `suppressed_gate`.
- **Red flags:** `send_error` (Telegram/API problem), `no_sender` (sender not attached — misconfig), any `sent` for a non-RED `alert` or a `digest` (gate breach — stop and investigate).

Quick checks:
```powershell
# tail the audit log
Get-Content logs\colombia_desk_live_sends.jsonl -Wait -Tail 20
# count outcomes
Get-Content logs\colombia_desk_live_sends.jsonl | ForEach-Object { ($_ | ConvertFrom-Json).outcome } | Group-Object | Sort-Object Count -Descending
```

---

## 10. Readiness report

- **Code:** end-to-end pipeline live-capable and DRY_RUN-safe; 291/291 tests + 4 DRY_RUN scenarios green on `main`.
- **Safety:** single live seam; 7-outcome audit; severity/dedupe/cooldown gates; instant DRY_RUN mute; scanner-preservation intact.
- **Deploy:** systemd template path-agnostic and renamed; repo public at the new slug.
- **Gap to live:** operational only — provision VPS, real `.env`, host smoke, then arm via `DRY_RUN=false`. Real (non-mock) data feeds are an independent, optional follow-on (provider keys + a real transport bridging 7A into the pipeline).

## 11. Local test command

```powershell
# Full regression (expect 291 passed, 0 failed):
Get-ChildItem tests\test_*.py | ForEach-Object { .\.venv\Scripts\python.exe $_.FullName }
# DRY_RUN behavior simulations (no network, no disk writes):
.\.venv\Scripts\python.exe tests\dry_run_simulations.py
```

## 12. VPS readiness assessment — **8.5 / 10**

| Dimension | Score | Note |
|-----------|-------|------|
| Code readiness | 10 | Pipeline complete, hermetic, fully tested |
| Safety controls | 10 | Arming isolated to one flag; audit + gates + instant mute |
| Deployment assets | 9 | systemd template ready; path-agnostic |
| Operational setup | 6 | VPS not provisioned; monitoring/log-retention to be configured |
| Live data | 6 | Runs on mock/placeholder; real feeds need keys + a transport bridge (optional) |

**Verdict:** Ready to deploy to a VPS in **DRY_RUN** and run the canary arming sequence whenever the operator chooses. The only blockers to a live desk are operational (provision host, real `.env`, monitoring) — not code. Arming is a single, reversible flag.

---

**End of plan. Nothing deployed. Live Telegram not enabled. DRY_RUN not disabled. No secrets exposed.**
