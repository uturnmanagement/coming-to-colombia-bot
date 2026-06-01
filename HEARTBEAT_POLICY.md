# HEARTBEAT POLICY — Phase 2.8

Color-driven heartbeat / repeat-alert policy, duplicate suppression, and
round-trip combo cadence. Implemented, tested, and documented. **No deploy,
no service restart, no Telegram, `DRY_RUN=true` throughout.**

---

## 1. Policy at a glance

| Color  | Initial alert | Heartbeat cadence | Lifetime | Max reminders |
|--------|---------------|-------------------|----------|---------------|
| RED    | immediately   | every **3 hours** | **48 h** | **16**        |
| YELLOW | immediately   | every **12 hours**| **48 h** | **4**         |
| GREEN  | none          | none              | n/a      | n/a           |

- **GREEN** never heartbeats and never alerts.
- A deal **stops** (becomes a zombie) once it is **48 h** past its first
  alert. Past that point only a **new `deal_id`** revives it.
- "Reminders" counts the routine, identical-information keep-alive
  heartbeats. **Reactivations do not count against the cap** (see §3).

### Reactivation — re-arms a rate-limited or capped deal

A deal that is rate-limited or has hit its reminder cap emits anyway
(within the 48 h lifetime) when something genuinely new happens:

- **new `deal_id`** — a different deal; restarts via the orchestrator's
  first-observation path (not the heartbeat path);
- **price improves materially** — drops by **≥ $5**;
- **route changes** — the route signature differs;
- **departure or return date changes** — the date combo differs;
- **color upgrades** — e.g. `YELLOW → RED`.

Reactivation bypasses both the cadence interval and the reminder cap,
because each reactivation carries new information — caps exist to stop
*identical* keep-alive spam, not to swallow a better deal. Reactivation
does **not** bypass the 48 h lifetime ceiling.

A **color downgrade** (e.g. `RED → YELLOW`) and a **price increase** are
**not** reactivations.

---

## 2. Where it lives

| Concern | File |
|---------|------|
| Color-driven policy (cadence, caps, 48 h stop, reactivation, fingerprint, combo) | `intel/heartbeat/policy.py` (new) |
| Package exports | `intel/heartbeat/__init__.py` |
| Authoritative wiring into the desk | `agents/oakstreet/orchestrator.py` → `OakStreet.ingest_alert` |
| Existing stage engine (now subordinate) | `intel/heartbeat/decay_engine.py` (unchanged) |
| Combo classification reused | `intel/return_pairing/combo.py` (unchanged) |
| Policy unit tests | `tests/test_heartbeat_policy.py` (new, 31 tests) |
| Orchestrator cadence test updated | `tests/test_oakstreet_skeleton.py` |

### Relationship to the existing decay engine

The repo already had **two** heartbeat subsystems:

1. `intel/heartbeat/decay_engine.py` — *age/stage*-driven (ACTIVE 15 min →
   COOLING 1 h → STALE 12 h → ZOMBIE-mute at 48 h), used by the Oak Street
   orchestrator/pipeline.
2. `src/heartbeat_alerts.py` (`HeartbeatManager`) — the scanner's legacy
   RED-only pinger, used by `main.py`.

Phase 2.8 makes the **color policy the authoritative governor** of the
orchestrator path. The decay engine is **retained** for its *stage label*
and *zombie status*, but it **no longer vetoes** an emit: the policy's
fixed per-color cadence is itself the keep-alive and must fire even when
the decay stage's longer interval (e.g. 12 h in STALE) would otherwise
rate-limit it. This is a deliberate policy change; see §6.

`decay_engine.py` and `src/heartbeat_alerts.py` were left untouched.

---

## 3. The decision, precisely

`decide_policy_heartbeat(...)` governs every *follow-up* observation (the
*first* observation always emits a normal alert via the orchestrator, never
a heartbeat). Evaluation order:

1. **GREEN / unknown color** → never emits.
2. **48 h lifetime exceeded** → `stopped`, never emits (even with new info).
3. **Reactivation trigger fires** → emits, bypassing cadence **and** cap.
4. **Reminder cap reached** (16 RED / 4 YELLOW) → suppressed.
5. **Cadence not yet elapsed** (< 3 h RED / < 12 h YELLOW since last
   heartbeat) → rate-limited, suppressed.
6. Otherwise → emits a cadence keep-alive.

---

## 4. Duplicate suppression

`deal_fingerprint(deal_id, route_signature, departure_at, return_date,
total_price)` builds a stable identity key over the **five** required
fields. `is_duplicate(prev_fp, curr_fp)` compares two of them.

Two observations sharing the same fingerprint carry no new information:
**a duplicate is the exact negation of a reactivation** (verified by
`test_duplicate_is_negation_of_reactivation`). In the live orchestrator
path this suppression is already active — an identical re-observation
produces no reactivation, so it can only ever fire a scheduled cadence
keep-alive, never a spurious re-alert. `return_date` participates in the
fingerprint whenever it is available (round-trip combos); one-way legs
pass `None` and it is normalized to `-`.

This is layered on top of the dispatcher's existing safety nets
(`links/telegram_dispatcher.py`): the text-hash dedupe window and the
per-deal cooldown floor remain in place — belt and suspenders.

---

## 5. Round-trip combos respect the policy

Combos are classified by `intel/return_pairing/combo.py`. The policy adds
`combo_heartbeat_color(outbound, return)`:

| Combo (outbound_return) | Qualifies | Heartbeat color | Cadence |
|-------------------------|-----------|-----------------|---------|
| `RED_RED`               | ✅        | RED             | 3 h     |
| `RED_YELLOW`            | ✅        | RED             | 3 h     |
| `YELLOW_RED`            | ✅        | RED             | 3 h     |
| `YELLOW_YELLOW`         | ✅        | YELLOW          | 12 h    |
| anything with GREEN     | ❌        | none            | never   |
| missing / unknown color | ❌        | none            | never   |

A qualifying combo (both legs ≥ YELLOW) heartbeats at the urgency of its
**strongest leg** — RED if either leg is RED, otherwise YELLOW — and then
flows through the exact same `decide_policy_heartbeat` logic as a single
leg. Any combo containing GREEN or missing color data is non-qualifying
and never heartbeats, identical to a GREEN single leg.

> **Scope note.** The combo → cadence *mapping* is implemented and tested.
> Today the desk briefing rides the *outbound* deal's heartbeat color
> through the dispatcher; routing a combo as its own heartbeat entity with
> the combo color is a Phase 3 wiring step. The policy primitive it needs
> (`combo_heartbeat_color`) is now in place.

---

## 6. Tests

New file `tests/test_heartbeat_policy.py` — **31 tests**, covering every
required case plus edges:

- RED heartbeat every 3 h (suppressed before, emits at/after)
- RED stops after 48 h (and alive just before)
- RED caps at 16 reminders
- YELLOW heartbeat every 12 h
- YELLOW stops after 48 h
- YELLOW caps at 4 reminders
- GREEN never heartbeats (and not even on a price drop / unknown color)
- reactivation on material price improvement (and sub-$5 / price-increase
  do **not** reactivate)
- reactivation on color upgrade (and downgrade does **not**)
- reactivation on route / departure-date / return-date change
- reactivation bypasses the cap but **not** the 48 h stop
- 5-field fingerprint distinctness + `is_duplicate` + duplicate ⇔
  ¬reactivation
- combos: qualifying-color → urgency mapping, GREEN/missing → none,
  RED-leg → 3 h cadence, `YELLOW_YELLOW` → 12 h cadence

One existing orchestrator test was updated to the new cadence
(`tests/test_oakstreet_skeleton.py`): the old `…material_change_after_
interval…` asserted a RED heartbeat **20 minutes** after the first alert
(old 15-min ACTIVE stage). Under the new policy that is rate-limited, so it
became `test_red_cadence_heartbeat_emits_after_3h`, asserting an unchanged
RED deal re-observed at 3 h emits a cadence keep-alive. `test_rate_limited_
observation_suppresses` had its comment updated (10-min suppression still
holds under the 3 h interval).

### Results

| Suite | Result |
|-------|--------|
| `tests/test_heartbeat_policy.py` (new) | 31 / 31 ✅ |
| `tests/test_heartbeat_decay.py` (unchanged engine) | 14 / 14 ✅ |
| `tests/test_oakstreet_skeleton.py` | 6 / 6 ✅ |
| `tests/test_layer7b_pipeline_integration.py` | 8 / 8 ✅ |
| **Full regression (all `tests/test_*.py`)** | **338 / 338 ✅** |

Prior baseline was 307; the 31 new policy tests bring the total to 338
with **zero** regressions. (Test runners are standalone — each file is run
with `python3 tests/test_<name>.py`; the environment's `pytest` plugin set
is broken and not used.)

---

## 7. Safety / scope confirmation

- `DRY_RUN=true` — **not** changed.
- `SCANNER_TELEGRAM_ENABLED=false` — **not** changed.
- Service **not** restarted. No Telegram sent. Nothing deployed.
- Phase 3 **not** started.
- Files changed this phase: `intel/heartbeat/policy.py` (new),
  `intel/heartbeat/__init__.py`, `agents/oakstreet/orchestrator.py`,
  `tests/test_heartbeat_policy.py` (new), `tests/test_oakstreet_skeleton.py`.
