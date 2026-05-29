# Layer 5 — India: Hostel & Budget-Accommodation Intelligence

**Branch:** `layer-5-india-hostel-intelligence`
**Date:** 2026-05-28
**Status:** Layer 5 complete. Awaiting approval before Layer 6 / deploy / push.

> Layer 5 ships **Agent India** — the hostel and budget-accommodation
> specialist. India consumes the same `AlertEvent` every other
> specialist sees, plugs into the Layer 4 lodging brain when one is
> available, scores accommodation candidates on four axes, and emits
> a `SpecialistReport` for Oak Street's typed ingestion path.
> Mock providers only. No HTTP. No scraping. No live Telegram.

---

## 1. Mission and scope

Build **Agent India** as a foundation:

- A specialist (`agents/india/`) that follows the same Layer 3
  contract Delta and Echo use.
- Typed accommodation models: `AccommodationCategory`, `HostelOption`,
  `HostelSignal`, `HostelReport`.
- A pure scoring engine with four axes (price, location, season,
  lodging_signal) and a weighted overall recommendation.
- A single **deterministic** mock provider — no HTTP, no scraping,
  no third-party APIs.
- Wire India into Oak Street's briefing without changing the
  dispatcher, the heartbeat decay engine, or the scanner kill switch.

Non-goals (per brief): no live data sources, no Central America
changes, no VPS deploy, no push, no Telegram, no Layer 6.

---

## 2. Architecture changes (Layer 5 additions vs Layer 4)

### New files (10)

```
agents/india/
├── __init__.py                    re-exports India + scoring helpers
├── report.py                      AccommodationCategory + HostelOption
│                                  + HostelSignal + HostelReport
├── scoring.py                     ScoreBreakdown + per-axis scorers +
│                                  score_option() + SCORE_WEIGHTS
├── providers.py                   HostelProvider protocol +
│                                  MockHostelProvider (only Layer 5 ships)
└── specialist.py                  India.analyze(event) -> SpecialistReport;
                                   consults Layer 4 lodging brain when wired

tests/
├── test_layer5_india_scoring.py        24 tests
├── test_layer5_india_classification.py  9 tests
├── test_layer5_india_integration.py    11 tests
└── test_layer5_india_protections.py     9 tests
```

### Modified files (1)

- `agents/specialist_report.py` — `VERDICT_KEYS` gains four India keys:
  `best_hostel_score`, `best_hostel_category`, `best_hostel_price_usd`,
  `hostel_options_count`. The strict-unknown-key rejection in
  `__post_init__` still holds (regression-tested).

### Unmodified — preservation contract

- `src/` (scanner) — untouched.
- `links/telegram_dispatcher.py` — untouched.
- `agents/oakstreet/orchestrator.py` — untouched. India ingests via the
  same typed `ingest_report(...)` path Delta and Echo use.
- `intel/lodging/` — untouched. India *consumes* the Layer 4 brain
  through `LodgingIntelService.signal_for(...)` but does not modify it.
- DRY_RUN + SCANNER_TELEGRAM_ENABLED — `.env` unchanged.

---

## 3. Accommodation categories (per spec)

```python
class AccommodationCategory(str, Enum):
    HOSTEL_DORM           = "hostel_dorm"
    HOSTEL_PRIVATE_ROOM   = "hostel_private_room"
    BUDGET_HOTEL          = "budget_hotel"
    GUEST_HOUSE           = "guest_house"
```

Each category has its own price anchor (`TYPICAL_PRICE_USD_BY_CATEGORY`)
the price-score axis uses as the typical-rate reference. Defaults
chosen as conservative Colombia-Desk values; the operator can pass a
custom `typical_table` to `India(...)`.

| Category | Default typical USD/night |
|---|---|
| HOSTEL_DORM | 15 |
| HOSTEL_PRIVATE_ROOM | 35 |
| BUDGET_HOTEL | 50 |
| GUEST_HOUSE | 40 |

---

## 4. Scoring axes

Every axis returns a 0–100 score (higher is better). The overall
recommendation is the weighted sum.

| Axis | Function | 100 means | 0 means | Weight |
|---|---|---|---|---|
| `price` | `score_price(observed, category, table)` | observed ≤ 70% of typical | observed ≥ 130% of typical | **0.40** |
| `location` | `score_location(km_to_center)` | 0 km — at the center | ≥ 5 km away | **0.20** |
| `season` | `score_season(Season \| None)` | LOW season | PEAK season | **0.15** |
| `lodging_signal` | `score_lodging_signal(LodgingColor \| None)` | RED (city-wide lodging is significantly cheap) | GREEN (lodging at typical) — None is neutral 50 | **0.25** |

Weights sum to 1.0 (asserted in tests). Linear scoring between the
clamp points. `None` inputs collapse to a neutral 50 so a missing
lodging signal doesn't unfairly tank an option's overall score.

### Worked example — best case

```
observed = $10, typical = $15  → price          = 100
distance = 0 km                → location       = 100
season   = LOW                 → season         = 100
lodging  = RED                 → lodging_signal = 100
overall  = 0.40*100 + 0.20*100 + 0.15*100 + 0.25*100
         = 100.0
```

### Worked example — worst case

```
observed = $25, typical = $15  → price          = 0
distance = 8 km                → location       = 0
season   = PEAK                → season         = 40
lodging  = GREEN               → lodging_signal = 50
overall  = 0.40*0 + 0.20*0 + 0.15*40 + 0.25*50
         = 18.5
```

Both worked examples are direct test assertions.

---

## 5. India specialist flow

```
AlertEvent
    │
    ▼
India.analyze(event)
    │
    ├── city = explicit override OR parse from route_signature
    │
    ├── provider.fetch(city, now) → tuple[HostelOption, ...]   # mock
    │
    ├── season = classify_season(observed_at.date())           # Layer 4
    │
    ├── lodging_color = lodging_service.signal_for(...).color  # Layer 4
    │   (any exception is caught and reported via flag)
    │
    ├── for each option:
    │     score_option(price, distance, season, lodging_color)
    │     -> HostelOption with score_breakdown attached
    │
    ├── HostelSignal = best-scoring option summary
    │
    ├── HostelReport = full payload (options + signal + flags)
    │
    └── SpecialistReport(
          agent="india",
          status=NO_DATA | PARTIAL | STUB,
          confidence=0..0.6,
          payload=serialized HostelReport,
          flags=("mock-provider", "lodging-signal-unavailable"?, ...),
          verdict_input={
            best_hostel_score,
            best_hostel_category,
            best_hostel_price_usd,
            hostel_options_count,
          },
        )
```

### Status semantics

| Status | When |
|---|---|
| `NO_DATA` | Provider returned no options for the city. `verdict_input` is empty; flag `no-options-for-city`. |
| `PARTIAL` | Provider returned scored options but no lodging signal was available (service not wired, exception, or no baseline). Confidence 0.5. |
| `STUB` | Provider returned scored options AND a lodging signal was obtained. Confidence 0.6 — even with full inputs, the provider is mock-only, so the report is foundation-stage. |
| `OK` / `ERROR` | Reserved for live provider layers. Never produced by Layer 5. |

The `mock-provider` flag is *always* set in Layer 5 so the operator
sees, at a glance, that the report is not on live data.

---

## 6. Layer 4 integration

India is fully functional **without** the Layer 4 lodging brain — it
falls through to a neutral `lodging_signal=50` and marks the report
`PARTIAL`. With the brain wired, India calls `signal_for(...)` and
the lodging axis carries the city-wide color:

| Lodging color | India's lodging-signal sub-score |
|---|---|
| RED | 100 |
| YELLOW | 75 |
| GREEN | 50 |
| None | 50 (neutral) |

A `RED` city-wide lodging signal (Layer 4 sees prices 15%+ below
typical) moves the lodging axis from 50 → 100 — a +12.5 point shift
on the overall score (proven by
`test_option_overall_changes_with_lodging_signal`).

Exception safety: a lodging service that raises is caught by India,
the report degrades to `PARTIAL`, and the flag
`lodging-signal-unavailable` is set. Verified by
`test_lodging_service_exception_does_not_propagate`.

---

## 7. SpecialistReport schema extension

```python
VERDICT_KEYS = {
    "round_trip_est_usd",       # Delta  (Layer 3)
    "best_return_window_days",  # Delta  (Layer 3)
    "price_position_label",     # Echo   (Layer 3)
    "price_position_pct",       # Echo   (Layer 3)
    "lodging_signal",           # Echo   (reserved, still None)
    # ----- Layer 5 additions -----
    "best_hostel_score",        # India  (0..100 — overall recommendation)
    "best_hostel_category",     # India  (AccommodationCategory.value)
    "best_hostel_price_usd",    # India  (USD/night)
    "hostel_options_count",     # India  (int — total options considered)
}
```

The Layer 3 `__post_init__` rejection of unknown keys still applies,
so adding a future India sub-signal (`best_hostel_neighborhood`, say)
requires a deliberate vocabulary edit. Regression-guarded by
`test_unknown_verdict_key_still_rejected`.

---

## 8. Test results

**Totals across the project: 235/235 tests passing.**

| Suite | Result | Layer |
|---|---|---|
| `test_heartbeat_decay` | 14/14 | L1 invariant |
| `test_oakstreet_skeleton` | 6/6 | L1 invariant |
| `test_scanner_preservation` | 4/4 | L1 invariant |
| `test_layer2_live_send` | 21/21 | L2 invariant |
| `test_layer3_return_pairing` | 13/13 | L3 invariant |
| `test_layer3_echo` | 13/13 | L3 invariant |
| `test_layer3_briefing` | 11/11 | L3 invariant |
| `test_layer3_return_window_modes` | 23/23 | L3 invariant |
| `test_layer4_seasons` | 11/11 | L4 invariant |
| `test_layer4_scoring` | 17/17 | L4 invariant |
| `test_layer4_storage` | 10/10 | L4 invariant |
| `test_layer4_providers` | 14/14 | L4 invariant |
| `test_layer4_protections` | 11/11 | L4 invariant |
| `test_layer5_india_scoring` | **24/24** | **NEW** |
| `test_layer5_india_classification` | **9/9** | **NEW** |
| `test_layer5_india_integration` | **11/11** | **NEW** |
| `test_layer5_india_protections` | **9/9** | **NEW** |
| `test_smoke` (legacy) | 14/14 | Untouched |
| `dry_run_simulations` (4 scenarios) | all complete | Untouched |
| `main.py` import sanity | clean | — |

### Layer 5 protection suite — what it specifically guards

```
ok  test_india_does_not_touch_dispatcher
ok  test_oakstreet_ingests_india_specialist_report
ok  test_synthesize_briefing_includes_india_section
ok  test_dispatch_briefing_with_india_stays_dry_run
ok  test_heartbeat_suppression_intact_with_india
ok  test_zombie_cutoff_intact_with_india
ok  test_echo_lodging_signal_still_none_after_layer5
ok  test_unknown_verdict_key_still_rejected
ok  test_no_live_telegram_path_with_india_active
```

The strongest guard is the last one:
**every dispatcher message recorded during a Layer 5 ↔ Oak Street
flow has `outcome="dry_run"`** — proving no live Telegram path can
fire while India runs alongside the briefing.

---

## 9. Design calls made during the build

1. **India is the brain's first consumer.** Layer 4 shipped
   `LodgingIntelService.signal_for(...)` and reserved Echo's
   `lodging_signal` slot. Layer 5 wires India into the service (not
   Echo — that hookup stays reserved per the long-running brief)
   because India's scoring legitimately depends on a city-wide
   lodging color, whereas Echo's lodging hookup needs a payload-level
   rewrite that belongs to a later layer.

2. **The proxy-observed-price for `signal_for(...)`.** The Layer 4
   service takes an `observed_usd` to score; India uses the cheapest
   mock option's price as a stand-in so the call deterministically
   returns a signal under tests. In a live layer this becomes the
   median observed from the active scan.

3. **`None` lodging color is neutral, not zero.** A missing signal
   shouldn't penalize an option as much as a literal GREEN signal
   does (GREEN = 50). It currently maps to 50 too — same numeric value,
   different semantic. Future tuning may differentiate them; today the
   collapse keeps the scoring deterministic.

4. **Mock provider is hermetic and deterministic.** No timestamps in
   the data, no randomness, no city outside the seeded set. This is
   the only behavior Layer 5 ships — every "live data" path stays
   closed until a future layer adds it.

5. **Status reports `STUB` even at full coverage.** Even when every
   axis scores and the lodging service is wired, Layer 5 marks the
   report `STUB` and confidence 0.6 because the provider is mock-only.
   This is the safety contract; an operator can never confuse a
   foundation report for live intel.

---

## 10. Outstanding items for the operator

Already pending and still open:

- Repo / directory rename to `coming-to-colombia-bot`.
- The eight non-Colombia region packs (Option 1/2/3 from
  `REPO_RENAME_MIGRATION.md`).
- `DRY_RUN=false` and `SCANNER_TELEGRAM_ENABLED=true` flips.
- VPS deploy.
- Layer 4 follow-ups: live AirDNA and Inside Airbnb fetch paths.
- Echo ↔ LodgingIntelService wiring (reserved).

New decisions introduced by Layer 5:

- **Live hostel data sources.** When ready, replace
  `MockHostelProvider` with a Hostelworld / Booking.com adapter that
  honors the same `HostelProvider` protocol. Layer 5's mock-only
  STUB contract is the safety floor until then.
- **Threshold + weight tuning.** Today: `price 0.40 / location 0.20 /
  season 0.15 / lodging 0.25`. Adjust once live data lets us see
  whether the best option's overall score correlates with operator
  intuition.
- **Per-category typical prices.** Defaults are conservative
  Colombia-Desk values. Layer 6 could load them from the region pack
  or from a configurable JSON.
- **Echo wiring decision.** Layer 4 reserved Echo's `lodging_signal`
  slot; Layer 5 plugged India in. The choice to also wire Echo is now
  a one-file change in `agents/echo/specialist.py` plus a hookup test.

---

## 11. Recommended Layer 6 scope (proposal — no action)

1. **Echo ↔ LodgingIntelService wiring.** Mirror the India hookup in
   Echo so its reserved `lodging_signal` field gets filled.
2. **Live hostel providers.** Implement at least one — Hostelworld or
   Booking.com budget tier — gated by an `enable_live` flag exactly
   like Layer 4's AirDNA / Inside Airbnb providers.
3. **Briefing renderer for India.** Today Oak Street renders Delta
   and Echo as named sections; India falls through to the unknown-
   specialist line. A dedicated renderer would surface the best
   option name, price, category, and score breakdown.
4. **VPS deploy.** All five layers are hermetic; the remaining work
   is operational — Hostinger / EC2 systemd unit, real `.env` on the
   target, monitoring.

Layer 7+: monetization, repo rename, multi-region.

---

**End of report. Layer 5 complete. No deploy. No push. No Layer 6.**
