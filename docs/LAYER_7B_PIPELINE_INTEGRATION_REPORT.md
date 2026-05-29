# Layer 7B Report — Pipeline Integration

**Branch:** `layer-7b-pipeline-integration` (off `main` @ `6dd3c2b`)
**Status:** Layer 7B complete. NOT merged. NOT pushed. Layer 7C not started.
**Test totals:** **291/291 passing** (283 prior + 8 new) + 4 DRY_RUN simulation scenarios complete.
**Safe posture preserved:** local `.env` keeps `DRY_RUN=true` and `SCANNER_TELEGRAM_ENABLED=false` (untouched). No live sends, no real HTTP, no VPS, no secrets required.

---

## 1. Files changed

| File | Change |
|------|--------|
| `agents/oakstreet/pipeline.py` | **New** — `DeskPipeline` + `PipelineResult`: runs `ingest_alert → specialists → dispatch_briefing` |
| `agents/oakstreet/__init__.py` | Note only — `DeskPipeline` deliberately **not** re-exported here (avoids a circular import); import from `agents.oakstreet.pipeline` |
| `src/scheduler.py` | Added `_event_from_result` (DealResult → AlertEvent, lazy import) and `_emit_red` (gated pipeline routing); RED branch now calls `_emit_red` |
| `main.py` | Composition root: builds a mock-backed `LodgingIntelService` + `DeskPipeline`, exposes `desk_pipeline` in `bot_data` |
| `tests/test_layer7b_pipeline_integration.py` | **New** — 8 integration tests |

**Untouched:** specialists' internals, dispatcher, heartbeat decay engine, `intel/live_providers/` (7A), `src/` scanner classification/format logic, all prior layers.

---

## 2. Architecture summary

```
scan_job (src/scheduler.py)
  └─ RED deal ─► _emit_red(context, result, key)
                   │  pipeline wired AND kill switch off?
                   ├─ yes ─► DeskPipeline.process_event(event)
                   │            1. OakStreet.ingest_alert(event)      → heartbeat decay + initial/heartbeat dispatch
                   │            2. Delta/Echo/India .analyze(event)   → isolated; one failure is skipped
                   │            3. OakStreet.ingest_report(report)     → cache per deal+agent
                   │            4. OakStreet.dispatch_briefing(...)    → synthesize + dispatch (kind=heartbeat)
                   └─ no  ─► legacy _send(...)                         (bit-for-bit prior behavior)
```

Key properties:
- **Gated & reversible.** The pipeline runs only when `desk_pipeline` is in `bot_data` **and** `SCANNER_TELEGRAM_ENABLED=false`. With no pipeline, or the kill switch on, the legacy single-alert `_send` path is preserved exactly — scanner-preservation tests stay green (4/4).
- **DRY_RUN-safe by construction.** The pipeline renders/sends nothing itself; every dispatch flows through `OakStreet`'s dispatcher, which under `DRY_RUN=true` records to the outbox + audit log and never calls the live sender.
- **Heartbeat parity.** `process_event` forwards the event to `ingest_alert` unchanged, so decay decisions are identical to calling `ingest_alert` directly (verified by parity tests).
- **Specialist isolation.** A specialist raising is logged and skipped; the alert and briefing still complete.
- **`src/` stays standalone.** `_event_from_result` uses a lazy `from agents.oakstreet import AlertEvent`, so the scanner has no top-level dependency on `agents/`.
- **Circular-import fix.** `DeskPipeline` imports the specialists, which import `agents.oakstreet.orchestrator`; re-exporting `DeskPipeline` from the package `__init__` created a cycle. Resolved by importing it from the submodule (`agents.oakstreet.pipeline`) everywhere.

Scope note: only **RED** deals route through the pipeline (where heartbeat + briefing matter). YELLOW deals remain on the legacy alert path — a conservative choice that avoids the severity gate suppressing YELLOW briefings; revisit in 7C if YELLOW briefings are wanted.

---

## 3. Tests added (8)

`tests/test_layer7b_pipeline_integration.py`:

| Test | Verifies |
|------|----------|
| `test_pipeline_runs_all_specialists_and_briefs` | delta/echo/india reports cached; DELTA/ECHO/INDIA in briefing |
| `test_dry_run_outbox_and_audit_no_live_send` | DRY_RUN: outbox has alert+heartbeat, all `dry_run`; sender never called; audit rows recorded |
| `test_heartbeat_parity_second_observation` | pipeline decision == direct `ingest_alert` (stage + should_emit) |
| `test_heartbeat_parity_zombie_suppression` | zombie suppressed identically on both paths |
| `test_broken_specialist_does_not_abort_pipeline` | one specialist raising → skipped, recorded, briefing still produced |
| `test_emit_red_routes_to_pipeline_when_killswitch_off` | fake scan context routes to pipeline; no live send |
| `test_emit_red_falls_back_to_send_without_pipeline` | no pipeline → legacy `_send` |
| `test_emit_red_killswitch_on_uses_legacy_even_with_pipeline` | kill switch on → legacy even when pipeline present |

These cover every required dimension: **fake scan context, fake alert ingestion, specialist execution, briefing generation, dispatch simulation, heartbeat parity.**

---

## 4. Full regression results

- **291/291 passing** across 25 `test_*.py` suites (283 prior + 8 Layer 7B). Zero failures.
- **DRY_RUN simulations:** 4/4 complete — "no network, no disk writes."
- **Scanner preservation: 4/4** — confirms the `scan_job`/`_emit_red` edits did not regress the legacy scanner.
- **Phase A freeze §13 invariants** re-verified by name via the existing suites (DRY_RUN safety, severity gate, dedupe/cooldown, heartbeat/zombie suppression, scanner kill switch, audit-row-per-decision, schema strictness, STUB safety) — all green.
- One issue found & fixed during implementation: a circular import from re-exporting `DeskPipeline` in the package `__init__` (resolved as described above).

---

## 5. Layer 7C readiness report

**Ready.** The end-to-end pipeline now runs in DRY_RUN; 7C is the operational + live-data activation layer:

1. **Real provider transport (bridge 7A → pipeline).** Inject a `requests`-backed transport into the 7A `generic` providers; bridge `LodgingQuote`→`LodgingObservation` and feed `LodgingIntelService`; feed live nightly prices into Echo's `lodging_observed_usd` and live flight/return data into Delta.
2. **VPS deploy.** Path-agnostic systemd template is ready; clone, venv, real `.env` (DRY_RUN still true), host smoke.
3. **Live arming (last).** Flip `SCANNER_TELEGRAM_ENABLED=true`, then `DRY_RUN=false`, in a canary window; watch the audit log for the first real `outcome="sent"`; rollback = flip back + restart.
4. **YELLOW briefing decision.** Decide whether YELLOW deals should also produce briefings (currently legacy-alert only).

**Risk note:** Layer 7B opened **no** wire — no live send, no real HTTP, STUB/live-provider gates intact, heartbeat parity proven. 7C must keep DRY_RUN until the final arming step and re-verify the §13 invariants live.

---

**End of report. Layer 7B complete. Not merged. Not pushed. Layer 7C not started.**
