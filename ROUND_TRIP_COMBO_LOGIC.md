# ROUND-TRIP COMBO LOGIC
**Project:** coming-to-colombia-bot
**Phase:** 2.7 — Round-Trip Deal Combo Logic
**Date:** 2026-05-31

> **Safety posture held throughout:** `DRY_RUN=true`, `SCANNER_TELEGRAM_ENABLED=false`.
> No Telegram enabled, no `DRY_RUN` flip, **no service restart**, no deployment, Phase 3
> not started. Code changes are on disk only — the running `coming-to-colombia-bot.service`
> (PID 61389, up since May 30) loaded its modules at startup and will not execute the new
> logic until a deliberate restart (not performed here).

---

## 0. Summary

Added a **round-trip combo classifier** that pairs the OUTBOUND leg color with each RETURN
leg color and decides whether the round trip is an alert-worthy travel opportunity. The
rule: **a round trip qualifies when BOTH legs are at least YELLOW.** The Delta Return
Optimizer now reports the combo category, qualify verdict, and round-trip savings versus
typical for every window, plus a best-combo summary. **16 new tests pass; full suite
307/307 green.**

---

## 1. New combo rules

A leg "qualifies" when its color is **RED** or **YELLOW** (GREEN does not). The combo
category is `"<OUTBOUND>_<RETURN>"` when both legs qualify, else `NON_QUALIFYING`.

| Outbound | Return | `combo_color` | Qualifies? |
|----------|--------|---------------|------------|
| RED | RED | `RED_RED` | ✅ yes |
| RED | YELLOW | `RED_YELLOW` | ✅ yes |
| YELLOW | RED | `YELLOW_RED` | ✅ yes |
| YELLOW | YELLOW | `YELLOW_YELLOW` | ✅ yes |
| RED | GREEN | `NON_QUALIFYING` | ❌ no |
| GREEN | RED | `NON_QUALIFYING` | ❌ no |
| YELLOW | GREEN | `NON_QUALIFYING` | ❌ no |
| GREEN | YELLOW | `NON_QUALIFYING` | ❌ no |
| GREEN | GREEN | `NON_QUALIFYING` | ❌ no |
| (missing / unknown either leg) | — | `NON_QUALIFYING` | ❌ no |

**Color semantics (unchanged from existing logic):**
- **Outbound color** comes from the scanner's deal classifier (`src/deal_classifier.py`):
  RED ≥ $150 under typical, YELLOW ≥ $75, else GREEN. It is carried on the `AlertEvent`.
- **Return color** is assigned by the return-ranking pass (`intel/return_pairing/ranking.py`)
  relative to the **window-set median** round-trip total: ≤ 85% of median → RED,
  ≤ 95% → YELLOW, else GREEN. (The two color axes are independent and intentionally so.)

### `combo_color` categories
`RED_RED · RED_YELLOW · YELLOW_RED · YELLOW_YELLOW · NON_QUALIFYING`

---

## 2. Implementation (files touched)

| File | Change | Risk |
|------|--------|------|
| `intel/return_pairing/combo.py` | **New** pure module: `combo_color()`, `qualifies()`, `COMBO_CATEGORIES`, `QUALIFYING_COLORS`. No I/O. | none (additive) |
| `intel/return_pairing/__init__.py` | Export the four new symbols. | none (additive) |
| `agents/delta/specialist.py` | Compute combo per option; add payload fields `outbound_color`, `round_trip_typical_usd`, `qualifying_count`, `best_qualifying`; per-option `combo_color`, `qualifies`, `outbound_color`, `return_color`, `savings_vs_typical_usd`; add non-breaking `round-trip-combo` flag when ≥1 combo qualifies. | low (additive; `_option_to_dict` kwargs default-compatible) |
| `agents/delta/report.py` | New `ROUND-TRIP COMBO SUMMARY` block + per-option combo / savings / booking lines. | low (render-only) |
| `agents/oakstreet/orchestrator.py` | One combo line added to the Delta briefing section. | low (render-only) |
| `tests/test_round_trip_combo.py` | **New** — 16 tests. | none (test-only) |

**Outbound scanner behavior unchanged:** no edits to `src/scheduler.py`, `src/route_compare.py`,
`src/deal_classifier.py`, or `src/flight_fetcher.py`. The combo layer is purely additive on
top of the Delta return optimizer.

### "Savings versus typical"
There is no separate return-typical in the region pack, and typical fares are treated as
symmetric, so the **round-trip typical baseline = 2 × the pack's one-way typical** for the
destination. `savings_vs_typical_usd = round_trip_typical − round_trip_total`. When no
region pack is active (e.g. some unit tests), the baseline degrades to `None` and the
report prints "— not provided (no typical baseline)" rather than crashing.

---

## 3. Examples

### 3a. Pure classifier
```
combo_color("RED",    "RED")    -> "RED_RED"          qualifies -> True
combo_color("YELLOW", "RED")    -> "YELLOW_RED"       qualifies -> True
combo_color("RED",    "GREEN")  -> "NON_QUALIFYING"   qualifies -> False
combo_color("GREEN",  "YELLOW") -> "NON_QUALIFYING"   qualifies -> False
combo_color("red",    "yellow") -> "RED_YELLOW"       (case-insensitive)
combo_color(None,     "RED")    -> "NON_QUALIFYING"   (missing leg)
```

### 3b. Rendered Delta optimizer output (RED outbound, BOG, synthetic spread)
```
OUTBOUND DETAILS:
Route:          BWI Baltimore → BOG Bogotá
Price:          $285
Color:          🔴 RED

ROUND-TRIP COMBO SUMMARY:
Outbound color:   🔴 RED
Typical (round):  $660
Qualifying combos:2 of 4 windows (both legs ≥ YELLOW)
Best combo:       RED_RED  (QUALIFIES ✅)
  Window:         day 7 (return 2026-06-06)
  Round-trip:     $385  · +$275 vs typical $660
  Airline:        — not provided by source  [direct]  ·  Duration — not provided by source
  Booking link:   — not provided by source
```
Per-window the report now also prints `Outbound color`, `Return color`, `Combo:` (category +
QUALIFIES verdict), `Savings/typical:`, and the return-leg `Booking link:` when the source
supplies one.

### 3c. Required report fields (Task 3) — coverage
| Field | Where shown |
|-------|-------------|
| Outbound color | OUTBOUND DETAILS + per-option + combo summary |
| Return color | per-option `Return color` |
| Combo category | `Combo:` per option + `Best combo` summary |
| Round-trip total | per-option `Total trip` + summary |
| Savings vs typical | per-option `Savings/typical` + summary |
| Best travel window | combo summary `Window: day N` |
| Airlines | per-option + summary |
| Stops | `route_type` (direct / N stops) |
| Duration | per-option + summary |
| Booking URL (if available) | per-option + summary (`— not provided` when absent) |

---

## 4. Testing results

New file `tests/test_round_trip_combo.py` — **16 tests, all pass.**

**Task 4 — combinations that MUST qualify (✅ all pass):**
- `RED + RED` → `RED_RED`
- `RED + YELLOW` → `RED_YELLOW`
- `YELLOW + RED` → `YELLOW_RED`
- `YELLOW + YELLOW` → `YELLOW_YELLOW`

**Task 5 — combinations that must NOT qualify (✅ all pass):**
- `GREEN + YELLOW`, `YELLOW + GREEN`, `GREEN + GREEN`, `RED + GREEN`, `GREEN + RED`
  → all `NON_QUALIFYING`, `qualifies() == False`

**Robustness:** case-insensitive (`red`/`yellow`), and missing/unknown colors
(`None`, `""`, `"BLUE"`) never qualify.

**Integration through `Delta.analyze`:**
- every payload option carries the 6 combo keys, and each option's `combo_color` /
  `qualifies` equals the pure function over the same colors;
- RED outbound + price spread → `qualifying_count ≥ 1`, `best_qualifying` is the cheapest
  qualifying round trip, and the `round-trip-combo` flag is set;
- GREEN outbound → `qualifying_count == 0`, `best_qualifying is None`, all
  `NON_QUALIFYING`, no `round-trip-combo` flag;
- YELLOW outbound → qualifies only on RED/YELLOW returns (`YELLOW_RED` / `YELLOW_YELLOW`).

**Regression — full suite (each module run isolated to avoid a known `.env` window
env-bleed): 307 tests, 0 failures.** No existing Delta, ranking, briefing, scanner-
preservation, or smoke test changed behavior.

> Test runner note: the repo's system `pytest` is broken (`No module named '_pytest.scope'`),
> so tests were executed by direct module invocation under `.venv/bin/python` (each module
> in its own subprocess). The new test file is also directly runnable:
> `python tests/test_round_trip_combo.py`.

---

## 5. Safety confirmation

| Requirement | Status |
|-------------|--------|
| `DRY_RUN` remained `true` | ✅ verified in `.env` |
| `SCANNER_TELEGRAM_ENABLED` remained `false` | ✅ verified in `.env` |
| Telegram enabled | ❌ No |
| `DRY_RUN` flipped to false | ❌ No |
| Service restarted | ❌ No — PID 61389 unchanged (running old code in memory) |
| Deployment performed | ❌ No |
| Phase 3 started | ❌ No |
| Outbound scanner behavior modified | ❌ No — combo layer is additive on the Delta optimizer only |
| Production alerts activated | ❌ No |

**No live API calls were made in this phase** (logic + tests are hermetic; no RapidAPI quota
consumed).

---

## 6. State left behind & next step

- New combo classifier + Delta report fields are on disk and fully tested, but **not live**:
  the running service must be restarted to load them (a Phase-3 / deployment action — not
  taken here).
- `DELTA_LIVE_RETURNS=true` remains staged in `.env` from Phase 2.6 (also dormant until
  restart).
- **Stopping after report generation, as instructed.** Recommended Phase-3 sequencing
  (when you choose to proceed): restart the service to load the combo logic *while still*
  `DRY_RUN=true`, observe combo output in the audit log / briefings, then arm with
  `DRY_RUN=false` only as a final, deliberate step.

---

*Phase 2.7 complete. Code added and tested; DRY_RUN held true, no Telegram, no restart, no deploy.*
