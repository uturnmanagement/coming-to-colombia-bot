# Layer 2 Refactor — Live Telegram wiring + dispatcher hardening

**Branch:** `layer-1-refactor-heartbeat` (continues from Layer 1 — no new branch)
**Date:** 2026-05-27
**Status:** Layer 2 complete. Awaiting approval before VPS / Layer 3.

> Layer 2 builds on the Layer 1 foundation. All Layer 1 invariants
> (heartbeat suppression, zombie cutoff, DRY_RUN safety, scanner
> preservation) are still enforced and tested. The legacy scanner can
> now run unchanged, OR hand off entirely to Oak Street's centralized
> dispatcher via a single kill switch — without code being recompiled.

---

## 1. Mission and scope

Wire the live Telegram sender into Oak Street's dispatcher and put
every outbound message under one set of rules — severity gate, dedupe,
per-deal cooldown, audit log — while keeping DRY_RUN safety, Layer 1
test coverage, and the legacy scanner path intact.

Explicit non-goals (per the brief): no VPS deploy, no Layer 3 work, no
repo rename, no Echo / India / Juliet, no lodging.

---

## 2. Architecture changes (Layer 2 deltas vs Layer 1)

### New files (3)

| File | Purpose |
|---|---|
| `links/telegram_live_sender.py` | `LiveTelegramSender` — thin `telegram.Bot.send_message` adapter exposing the `sender(chat_id, text) -> None` callable shape the dispatcher expects. |
| `links/live_send_audit.py` | `LiveSendAuditor` — append-only JSONL writer. One record per dispatcher decision (sent / dry_run / suppressed_gate / suppressed_dedupe / suppressed_cooldown / no_sender / send_error). |
| `tests/test_layer2_live_send.py` | 21 hermetic tests for sender wiring, severity gate, dedupe, cooldown, kill switch, audit log, and Layer 1 preservation. |

### Modified files (5)

| File | Change |
|---|---|
| `agents/config.py` | `DeskConfig` gains `scanner_telegram_enabled`, `audit_log_path`, `live_send_cooldown_seconds`. Loader reads them from env with safe defaults. |
| `links/telegram_dispatcher.py` | Rewrote with: severity gate, dedupe window, per-deal cooldown, audit hook, structured `DispatchedMessage` (outcome + reason fields). Layer 1 sync surface preserved. |
| `agents/oakstreet/orchestrator.py` | Two callsites now pass `color` + `route_signature` into `dispatcher.send()` so the severity gate can evaluate them. No logic change. |
| `src/scheduler.py` | `_send` grew a kill-switch branch — when `SCANNER_TELEGRAM_ENABLED=false`, routes through `oak.dispatcher.send(...)`; otherwise unchanged. Callsites pass `kind` + `color` + `deal_id` + `route_signature`. Added the `_route_signature(result)` helper. |
| `main.py` | Builds `DeskConfig`, `SqliteManager`, `LiveSendAuditor`, `TelegramDispatcher`, and `OakStreet` at startup; stashes `desk_config` + `oakstreet` into `bot_data` so the scanner's `_send` can find them. Wires a fire-and-forget `_bot_sender` that schedules `application.bot.send_message` via `application.create_task` (correct PTB pattern for sync→async hand-off). |

### Configuration surface (env vars added)

```
SCANNER_TELEGRAM_ENABLED   default true   # kill switch
LIVE_SEND_AUDIT_LOG        default logs/colombia_desk_live_sends.jsonl
LIVE_SEND_COOLDOWN_SECONDS default 60
```

`.env.example` and the local `.env` updated to document and ship these.

---

## 3. Boundary diagram

```
                        ┌────────────────────────────────────────────┐
                        │              Oak Street                    │
                        │  (renders text + chooses dispatcher path)  │
                        └──────────────────┬─────────────────────────┘
                                           │
                  ┌────────────────────────▼────────────────────────┐
                  │           TelegramDispatcher (hardened)         │
                  │                                                 │
                  │   1. DRY_RUN check       → outbox + audit only  │
                  │   2. Severity gate       → RED + heartbeat +    │
                  │                            system pass; YELLOW/ │
                  │                            GREEN alerts +       │
                  │                            digest blocked       │
                  │   3. Dedupe window       → same payload twice   │
                  │                            in N seconds blocked │
                  │   4. Per-deal cooldown   → safety floor between │
                  │                            two sends for one    │
                  │                            deal_id              │
                  │   5. sender(chat, text)  → live wire            │
                  │   6. LiveSendAuditor     → one JSONL line for   │
                  │                            every decision       │
                  └──────────────────┬──────────────────────────────┘
                                     │
                  ┌──────────────────▼──────────────────┐
                  │  application.bot.send_message  ───→ │  Telegram
                  │  (PTB Bot, fire-and-forget task)    │
                  └─────────────────────────────────────┘

Legacy scanner path (src/scheduler.py:_send):

  SCANNER_TELEGRAM_ENABLED=true  → direct context.bot.send_message
  SCANNER_TELEGRAM_ENABLED=false → re-routed into the dispatcher above
                                   (or dropped if Oak Street not wired)
```

---

## 4. Live rules enforced

Per brief: "Only RED and qualifying heartbeat alerts may send. Respect
cooldown intervals. No spam loops. No duplicate route signatures.
Maintain SQLite heartbeat tracking."

Implementation:

| Rule | Where enforced | Test |
|---|---|---|
| **RED alerts only.** Initial-alert messages with `color in {yellow, green}` are dropped at the dispatcher. | `_passes_live_gate` in `TelegramDispatcher` | `test_yellow_alert_blocked_by_severity_gate`, `test_green_alert_blocked_by_severity_gate` |
| **Qualifying heartbeats.** Heartbeats are pre-gated by the Layer 1 decay engine (`should_emit=True`) and bypass the color check — by the time they reach the dispatcher, they have already passed material-trigger / stage-interval / max-silence rules. | `intel/heartbeat/decay_engine.py` + dispatcher `_LIVE_PASS_KINDS_ANY_COLOR` | `test_heartbeat_kind_bypasses_color_check`, `test_heartbeat_path_emits_when_qualifying`, `test_heartbeat_suppression_still_works_through_live_dispatcher` |
| **Cooldown intervals.** `LIVE_SEND_COOLDOWN_SECONDS` (default 60 s) — minimum gap between any two live sends for the same `deal_id`. Independent of stage interval. | `_in_cooldown` | `test_cooldown_suppresses_back_to_back_sends`, `test_cooldown_expires`, `test_cooldown_independent_per_deal` |
| **No spam loops / duplicates.** Same payload (sha1[:16] of text, scoped by `deal_id` + `kind`) within `dedupe_window_seconds` (default 300 s) is dropped. Independent of cooldown. | `_is_recent_duplicate` | `test_identical_payload_inside_window_deduped`, `test_distinct_payload_not_deduped`, `test_dedupe_window_expires` |
| **No duplicate route signatures.** Route signature is part of every dispatched message and is recorded on each audit row; the dedupe key also includes the text hash, which incorporates the route signature in render output. | dispatcher + audit log | covered indirectly by dedupe tests; route signature path proven by `test_scanner_send_seam_routes_through_oak_street_when_disabled` |
| **SQLite heartbeat tracking maintained.** Oak Street still updates the `deals` and `heartbeat_snapshots` tables before / after every emission. | `OakStreet.ingest_alert` | Layer 1 tests + `test_zombie_cutoff_still_works_through_live_dispatcher` |
| **DRY_RUN preserved.** Setting `DRY_RUN=true` bypasses every wire path while still recording the message in the outbox and audit log. | dispatcher first check | `test_sender_not_invoked_in_dry_run` |

Outcomes recorded in the audit log:
`sent`, `dry_run`, `suppressed_gate`, `suppressed_dedupe`,
`suppressed_cooldown`, `no_sender`, `send_error`.

---

## 5. Scanner kill switch — how it works

`SCANNER_TELEGRAM_ENABLED` is a single boolean in the env:

| Value | Scanner direct path | Oak Street path | Behavior |
|---|---|---|---|
| `true` (default) | live | not fed | Legacy behavior — bit-for-bit identical to pre-Layer 2. Layer 1 still runs (DRY_RUN simulations remain valid) but the runtime scanner sends directly. |
| `false` | suppressed | live (RED alerts + qualifying heartbeats only) | Migrated state — every Telegram message flows through the dispatcher. YELLOW alerts and the daily digest are gated out. |

Implementation seam — the only place that branches:

```python
# src/scheduler.py
async def _send(context, text, *, kind="alert", color=None,
                deal_id=None, route_signature=None):
    data = context.bot_data
    desk_config = data.get("desk_config")
    oak = data.get("oakstreet")

    if desk_config is not None and not desk_config.scanner_telegram_enabled:
        if oak is not None:
            oak.dispatcher.send(text, kind=kind, deal_id=deal_id,
                                color=color, route_signature=route_signature)
        else:
            log.info("...suppressed; Oak Street not wired")
        return

    # legacy direct send (unchanged)
    config = data["config"]
    await context.bot.send_message(...)
```

The kill switch defaults to `true` so a deployment that simply pulls
Layer 2 changes is not silently affected — migration requires
explicitly flipping the flag. The Layer 1 logger namespace separation
(`airfare.*` vs `colombia_desk.*`) and the `desk_config` / `oakstreet`
keys in `bot_data` were chosen precisely so this seam fits inside the
existing PTB application without rewiring it.

---

## 6. main.py wiring summary

The startup sequence builds the new objects in order and threads
them through `bot_data` so the scanner can find them by lookup. None
of the legacy scanner setup was removed or reordered — the new wiring
is purely additive:

```
load_config (legacy)        load_desk_config (Colombia Desk)
   │                              │
   ▼                              ▼
Storage / Heartbeat        SqliteManager + LiveSendAuditor
   │                              │
   ▼                              ▼
Application.builder()      TelegramDispatcher + OakStreet
   │                              │
   └──────────► bot_data ◄────────┘
                  │
                  ▼
     dispatcher.sender = _bot_sender   # fire-and-forget bridge
                  │
                  ▼
              setup_jobs(application, config)   # legacy unchanged
              register_handlers(application)    # legacy unchanged
              application.run_polling(...)
```

### Why fire-and-forget for `_bot_sender`

`TelegramDispatcher.send` is synchronous (Layer 1 contract — used by
DRY_RUN simulations and Oak Street). `application.bot.send_message`
is a coroutine. Bridging sync→async from inside a running PTB event
loop is done via `application.create_task(coro)`, which schedules the
send on the loop and returns immediately. Send errors propagate to
PTB's central error handler (`_on_error` in `main.py`). The audit log
records `outcome="sent"` at the *scheduling* moment; in the rare case
of a Telegram API failure, the error handler logs it separately. This
is the same trade-off PTB itself makes for non-awaited callbacks.

---

## 7. Verification — final test results

All test suites run from `.venv/Scripts/python.exe`, fully hermetic:

```
=== heartbeat decay ============= 14/14 pass
=== scanner preservation ========  4/4  pass
=== oakstreet skeleton ==========  6/6  pass
=== layer 2 live send =========== 21/21 pass
=== legacy smoke (unchanged) ==== 14/14 pass
=== DRY_RUN sims (4 scenarios) == all complete
```

**Totals: 59/59 tests passing, 4/4 DRY_RUN scenarios green.**

Notable: **Layer 1 invariants survived a non-trivial dispatcher
rewrite.** The `test_scanner_preservation` suite, the legacy
`test_smoke` (which the scanner-preservation suite re-runs), and the
Layer 1 Oak Street tests all pass against the new dispatcher
signature unchanged.

### Layer 2 test breakdown (21 cases)

```
Live sender wiring
  ok   test_sender_invoked_on_red_alert
  ok   test_sender_not_invoked_in_dry_run

Severity gate
  ok   test_yellow_alert_blocked_by_severity_gate
  ok   test_green_alert_blocked_by_severity_gate
  ok   test_digest_blocked_by_severity_gate
  ok   test_system_message_always_passes
  ok   test_heartbeat_kind_bypasses_color_check

Dedupe
  ok   test_identical_payload_inside_window_deduped
  ok   test_distinct_payload_not_deduped
  ok   test_dedupe_window_expires

Per-deal cooldown
  ok   test_cooldown_suppresses_back_to_back_sends
  ok   test_cooldown_expires
  ok   test_cooldown_independent_per_deal

Audit log
  ok   test_audit_log_writes_every_decision
  ok   test_audit_records_message_hash_and_length

Layer 1 invariants through Layer 2 dispatcher
  ok   test_heartbeat_suppression_still_works_through_live_dispatcher
  ok   test_zombie_cutoff_still_works_through_live_dispatcher
  ok   test_heartbeat_path_emits_when_qualifying

Scanner kill switch + re-routing
  ok   test_scheduler_route_signature_helper
  ok   test_desk_config_default_scanner_telegram_enabled
  ok   test_scanner_send_seam_routes_through_oak_street_when_disabled
```

---

## 8. Two design calls made during build

1. **Severity gate places heartbeats on the always-pass list.** The
   Layer 1 decay engine already gates heartbeat emission by stage
   interval, material trigger, max-silence, and zombie status. By the
   time a heartbeat reaches the dispatcher, those checks have all
   passed — re-running them via the color gate would either be
   redundant (if heartbeats are restricted to RED deals) or wrong (if
   a YELLOW deal's heartbeat is desired). The gate trusts the engine.

2. **`message_id` type-check is strict.** Mock senders auto-populate
   any attribute name via `MagicMock`, including `last_message_id`.
   The audit log serializer chokes on non-JSON types. The dispatcher
   now uses `isinstance(raw_id, int)` to admit only real integers,
   defaulting to `None` otherwise. Caught and fixed via test failure
   during the build.

---

## 9. Outstanding items for the operator

These were already pending from Layers 0–1 and remain open. Layer 2
did not touch any of them:

- The chat ID in `.env` still has a leading colon (`:6140960009`). The
  bot will fail at first live send unless corrected to a bare integer.
- Option 1 / 2 / 3 from `REPO_RENAME_MIGRATION.md` §2 (Colombia-only
  collapse vs keep packs vs fork).
- Directory + GitHub repo rename to `coming-to-colombia-bot`.
- VPS deploy authorization (deferred — Layer 2 is local-only).
- Decision on whether to flip `SCANNER_TELEGRAM_ENABLED=false` in
  `.env` now (start the migration to Oak Street as the only live
  path) or hold until Echo / return pairing arrive in Layer 3.

---

## 10. Recommended Layer 3 scope (proposal, not action)

The dispatcher now has the seams in place for richer payloads.
Natural Layer 3 themes:

1. **Echo specialist (price-context).** Adds price-history context to
   every Oak Street alert via `OakStreet.ingest_specialist_report`.
   Exercises the `specialist_reports` table and one-voice rendering.
2. **Return-leg pairing.** Adds a return-fetch on RED deals; the
   `route_signature` already accommodates richer strings.
3. **Audit log analyzer.** A small CLI that summarizes
   `colombia_desk_live_sends.jsonl` — sent vs gated vs deduped vs
   cooled, by hour, by deal — closing the observability loop.

Layer 4+ candidates (not earlier): India, Juliet, lodging, VPS
deploy, repo rename, monetization.

---

**End of report. Layer 2 complete. No deploy. No push. No Layer 3.**
