# Layer 1 Refactor — Colombia Desk Foundation

**Branch:** `layer-1-refactor-heartbeat`
**Date:** 2026-05-26
**Status:** Layer 1 complete. Awaiting approval before Layer 2.

> Working directory note: the repo lives on disk at
> `C:\Users\uturn\opshub_global_airfare_intelligence_system\`. The
> directory and GitHub-remote rename to `coming-to-colombia-bot` was
> deferred from the migration plan and is **not** part of this layer.
> All new code uses the post-rename naming conventions internally
> (`colombia_desk.*` loggers, "Colombia Desk" in messages, `Oak Street`
> in code) so no rework will be needed when the rename executes.

---

## 1. Mission and scope

Refactor the existing single-process airfare scanner into an
orchestration-ready architecture that can host **Oak Street** (the
master orchestrator) and a **heartbeat decay engine** — *without
breaking the existing outbound flight scanner*.

Explicit non-goals (per the brief): no lodging, no Echo, no India, no
Juliet, no return pairing, no VPS deploy.

---

## 2. Architecture changes

### Old layout (preserved)

```
src/                          # the working scanner — untouched
├── config.py                 # region-pack loader
├── region.py                 # region pack model
├── flight_fetcher.py         # RapidAPI Skyscanner connector
├── route_compare.py
├── deal_classifier.py
├── arrival_rules.py
├── alert_formatter.py
├── scheduler.py
├── storage.py                # JSON-backed persistence (untouched)
├── heartbeat_alerts.py       # legacy RED-deal heartbeat
└── telegram_handlers.py
main.py                       # untouched
```

### New layout (Layer 1 additions)

```
agents/
├── __init__.py
├── config.py                 # DeskConfig: DRY_RUN, sqlite path, etc.
├── logging_setup.py          # colombia_desk.* logger root
└── oakstreet/
    ├── __init__.py
    └── orchestrator.py       # OakStreet master orchestrator skeleton

intel/
├── __init__.py
└── heartbeat/
    ├── __init__.py
    ├── decay_engine.py       # stage classification + decision logic
    └── trigger_rules.py      # material-change rules

links/
├── __init__.py
└── telegram_dispatcher.py    # one-voice outbound abstraction

db/
├── __init__.py
├── schema.sql                # deals + heartbeat_snapshots + specialist_reports
└── sqlite_manager.py         # SQLite manager, honors DRY_RUN

logs/                         # existing dir — colombia_desk.log appears here
tests/                        # new tests sit alongside the legacy smoke
├── test_heartbeat_decay.py
├── test_scanner_preservation.py
├── test_oakstreet_skeleton.py
├── dry_run_simulations.py    # runnable scenario harness
└── test_smoke.py             # legacy — untouched
docs/
├── LAYER_1_REFACTOR_REPORT.md (this file)
```

### Module-boundary rules (enforced by structure, not just convention)

- **`links/` is the only place the new code touches the outside world.**
  Heartbeat decisions and orchestration logic call through
  `TelegramDispatcher`. DRY_RUN gating lives here in one place.
- **`intel/heartbeat/` is pure** — no I/O. Inputs are dataclasses, output
  is a `HeartbeatDecision`. This is what makes the engine trivially
  testable.
- **`db/sqlite_manager.py`** owns *orchestration* state only. The
  scanner's JSON files in `logs/` (`alerted_deals.json`,
  `scan_history.json`, `deal_log.jsonl`, `active_red_deals.json`) are
  unchanged.
- **`agents/oakstreet/`** is the only consumer that wires the above
  three together. Future specialists (Echo / India / Juliet) will send
  reports to Oak Street, never to Telegram directly — "one voice".

---

## 3. Preserved systems

| System | Status | Verification |
|---|---|---|
| `src/` scanner modules | Untouched | `test_scanner_preservation.test_src_modules_still_importable` |
| Region-pack loading + colombia default | Untouched | `test_default_region_pack_unchanged` |
| Legacy hermetic smoke (14 tests) | Untouched, still 14/14 pass | Re-run from `tests/test_smoke.py` and via `test_scanner_preservation.test_legacy_smoke_still_passes` |
| `airfare.*` logger namespace | Untouched | `test_layer1_does_not_shadow_scanner_logger` |
| `logs/` JSON files | Untouched | `db/` is the new SQLite home; JSON layer is parallel |
| `main.py` entry point | Untouched | Scanner still runs exactly as before |

**No file under `src/`, no file at the repo root other than the new
report, and no existing config was modified.** Layer 1 is purely
additive.

---

## 4. Heartbeat logic

### Stage cadence

`age = now − first_alert_at`

| Age | Stage | Interval (rate limit) |
|---|---|---|
| 0–4 h | `active` | 15 minutes |
| 4–24 h | `cooling` | 1 hour |
| 24–48 h | `stale` | 12 hours |
| 48 h + | `zombie` | — (muted) |

Boundaries inclusive at the low end, exclusive at the high end (4.0 h →
`cooling`; 48.0 h → `zombie`). Tests verify the boundary behavior.

### Material triggers (intel/heartbeat/trigger_rules.py)

A heartbeat is *eligible* only when one of these fires. First match
wins, so the operator gets a single human-readable reason on every
heartbeat:

- **color change** (e.g. `yellow → red`)
- **route change** (`route_signature` string equality — covers both
  direct-vs-positioning *and* carrier/gateway changes)
- **price change** where `|Δ| ≥ $5`
- **departure shift** where `|Δ| ≥ 30 minutes`

### Emission rule (intel/heartbeat/decay_engine.py)

```
if stage is ZOMBIE:                        → suppress (status flips to zombie)
elif silence ≥ 12h:                        → emit (max-silence keepalive)
elif material trigger fires AND
     silence ≥ stage interval:             → emit (rate-limit respected)
elif material trigger fires AND
     silence  < stage interval:            → suppress (rate-limited)
else:                                      → suppress (no change, within max-silence)
```

The initial scanner alert is treated as **heartbeat zero**:
`last_heartbeat_at = first_alert_at`. This makes silence measured
from the original announcement instead of from "infinity", which would
otherwise force every second observation through the max-silence path
during a deal's first 12 hours.

### Why max-silence overrides rate limit but not zombie

A 13-hour-silent deal in `cooling` should send a "still here" beat
even without material change (the max-silence rule). But a 60-hour-old
deal is **noise** — that's the point of zombie. Zombie's mute is
absolute; max-silence cannot override it.

---

## 5. SQLite schema

Created automatically on first connect from `db/schema.sql`.

### `deals`

| Column | Type | Notes |
|---|---|---|
| `deal_id` | TEXT PK | Caller-supplied (the scanner's content hash works) |
| `first_alert_at` | TEXT | ISO-8601 |
| `last_heartbeat_at` | TEXT | ISO-8601; seeded to `first_alert_at` on insert |
| `heartbeat_count` | INTEGER | Counts follow-up beats only (initial alert is beat 0) |
| `status` | TEXT | `active` / `cooling` / `stale` / `zombie` |
| `last_color`, `last_price_usd`, `last_route_signature`, `last_departure_at` | — | Last observed state used by the trigger rules |
| `updated_at` | TEXT | Wall-clock of the last write |

Indexed on `status` and `first_alert_at`.

### `heartbeat_snapshots`

Append-only history of every emitted heartbeat (id, deal_id, emitted_at,
stage, color, price, route, departure, trigger_reason). Indexed on
`(deal_id, emitted_at)`.

### `specialist_reports` (placeholder for Layer 2+)

Holds JSON-encoded reports from future specialists keyed by
(specialist, deal_id, report_at). Already wired through
`OakStreet.ingest_specialist_report(...)` — Echo / India / Juliet
hookup is a Layer-2 concern, not Layer-1, but the storage path is
proven by `test_specialist_report_persisted`.

---

## 6. DRY_RUN validation

`agents/config.py:DeskConfig.dry_run` is read from `DRY_RUN` in the
environment (defaults to **false**). When true:

- `SqliteManager` opens a `:memory:` database — no disk writes.
- `TelegramDispatcher.send(...)` records the message on `outbox` and
  short-circuits before any network call, logging "DRY_RUN suppress …".
- Every `DispatchedMessage` carries `dry_run=True` so simulations and
  tests can assert it.

All four simulation scenarios in `tests/dry_run_simulations.py` run
purely in-memory. Captured output is at
`logs/dry_run_simulations_output.txt`.

### Simulation results

| # | Scenario | Expectation | Result |
|---|---|---|---|
| 1 | RED alert (first observation) | Initial alert emitted, deal row inserted with `status=active`, `heartbeat_count=0`, `last_heartbeat_at=first_alert_at` | ✅ matches |
| 2 | Heartbeat suppression | $30 drop 10 min into ACTIVE → rate-limited (15-min interval) → no emit | ✅ matches, reason recorded |
| 3 | Heartbeat trigger | $30 drop 20 min into ACTIVE → past 15-min interval → emit; snapshot row written; heartbeat_count→1 | ✅ matches |
| 4 | Zombie cutoff | $100 drop at 60 h age → muted; status flips to `zombie` | ✅ matches |

(See §7 for full output.)

---

## 7. Verification: test + simulation output

**Heartbeat decay (14/14 pass)**

```
ok   test_classify_stage_boundaries
ok   test_intervals
ok   test_trigger_price_threshold
ok   test_trigger_route
ok   test_trigger_color
ok   test_trigger_departure_shift
ok   test_zombie_mutes_everything
ok   test_active_emits_on_trigger_after_interval
ok   test_active_rate_limits_within_interval
ok   test_cooling_rate_limits_within_interval
ok   test_max_silence_force_emit_no_change
ok   test_no_change_inside_max_silence_suppressed
ok   test_stale_stage_uses_12h_interval
ok   test_first_observation_treated_as_changed
```

**Scanner preservation (4/4 pass)**

```
ok   test_legacy_smoke_still_passes
ok   test_src_modules_still_importable
ok   test_default_region_pack_unchanged
ok   test_layer1_does_not_shadow_scanner_logger
```

**Oak Street skeleton (6/6 pass)**

```
ok   test_first_alert_registers_and_sends
ok   test_rate_limited_observation_suppresses
ok   test_material_change_after_interval_emits_heartbeat
ok   test_zombie_mutes
ok   test_specialist_report_persisted
ok   test_dispatcher_dry_run_marks_messages
```

**Legacy smoke (unchanged, 14/14 pass)** — confirms the scanner still
behaves bit-for-bit:

```
PASS  test_alert_formatter
PASS  test_all_region_packs_parse
PASS  test_arrival_rule_late_night_downgrade
PASS  test_command_slug_handles_accents
PASS  test_config_loads_with_region
PASS  test_core_imports
PASS  test_deal_classifier_labels
PASS  test_env_example_exists
PASS  test_full_scan_runs
PASS  test_placeholder_fetcher
PASS  test_route_comparison_with_mock_data
PASS  test_scheduler_and_heartbeat_load
PASS  test_skyscanner_itinerary_parsing
PASS  test_telegram_handlers_load
14/14 tests passed
```

**Totals: 38 new + preserved tests, all passing.**

---

## 8. One design call made during build

After the first test run, two Oak Street tests failed because the
heartbeat engine sees `last_heartbeat_at = None` immediately after the
initial alert — making `silence = ∞`, which trips the max-silence
keepalive on every very-next observation. **The fix was to anchor the
initial alert as "heartbeat zero":** the orchestrator inserts the deal
with `last_heartbeat_at = first_alert_at`. `heartbeat_count` stays at 0
(it counts *follow-up* beats only).

Documented in `db/sqlite_manager.py` and `decay_engine.py` so a future
reader doesn't reverse it accidentally.

---

## 9. Next recommended layer (Layer 2 — proposal, not action)

The skeleton's seams are now in place. The natural next layer is **one
specialist + return-pairing**, picked because both unblock real product
work and exercise different seams:

1. **Echo (price-context specialist).** Use the existing
   `flight_fetcher.py` to enrich each alert with "last 14 days low /
   median" context. Emits a structured report that Oak Street injects
   into the rendered Telegram body. Tests the `specialist_reports`
   table and the one-voice render path.
2. **Return pairing.** Today the scanner is one-way. Layer 2 adds a
   return-leg fetch on YELLOW/RED deals and renders the pair. Tests
   the heartbeat engine's robustness to richer `route_signature`
   strings.

Defer to Layer 3+: India, Juliet, lodging intelligence, VPS deploy,
the directory/GitHub rename, monetization wiring.

---

## 10. Outstanding items still pending operator approval

From the previous migration plan, these were not unblocked by this
turn and remain open:

- Decide between Option 1 / 2 / 3 from `REPO_RENAME_MIGRATION.md` §2.
  (Layer 1 was built assuming Colombia-only direction but did not act
  on it — the 8 non-Colombia region packs in `configs/` are untouched.)
- Authorize the directory + GitHub repo rename to
  `coming-to-colombia-bot`.
- Confirm `colombia_desk.*` is the chosen logger / SQLite-file
  namespace. If you want `coming_to_colombia.*` or `oak_street.*`
  instead, it's a 1-PR find-and-replace.
- Provide the live `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` so the
  dispatcher can be wired in a follow-up (Layer 1 ships fully
  hermetic; nothing is wired live yet).

---

**End of report. Stopping at Layer 1 per brief.**
