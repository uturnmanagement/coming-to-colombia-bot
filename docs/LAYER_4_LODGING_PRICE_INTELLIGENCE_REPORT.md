# Layer 4 — Lodging Price Intelligence (shared brain)

**Branch:** `layer-4-lodging-price-intelligence`
**Date:** 2026-05-28
**Status:** Layer 4 complete. Awaiting approval before Layer 5 / deploy / push.

> Layer 4 ships the *brain*, not Echo's wiring into it. Echo and India
> will plug into `LodgingIntelService.signal_for(...)` in a later
> layer to fill the `lodging_signal` slot they reserved in Layer 3.
> Today, Echo still reports `lodging_signal=None`. DRY_RUN stays true;
> SCANNER_TELEGRAM_ENABLED stays false. No HTTP, no scraping, no file
> reads — all integration with AirDNA and Inside Airbnb is via STUB
> adapters that own the interface shape only.

---

## 1. Mission and scope

Stand up the shared **Lodging Price Intelligence** module:

- Provider interface (`LodgingProvider`) + three implementations:
  `MockLodgingProvider` (deterministic, drives tests),
  `AirDnaProvider` and `InsideAirbnbProvider` (both **STUB** in Layer 4).
- Pure intel: season classification + multiplier matrix, RED/YELLOW/GREEN
  scoring engine, baseline aggregation.
- Persistence: two new SQLite tables — `lodging_baseline` and
  `lodging_history` — in the existing Colombia Desk DB file. No
  separate connection.
- `LodgingIntelService` — orchestration shell. Pulls observations,
  persists, computes the baseline, and emits a typed `LodgingSignal`
  for future Echo/India use.
- DeskConfig + `.env.example` plumbing for every Layer 4 env knob.

Non-goals (per brief): no Telegram, no live HTTP, no file reads, no
Echo wiring, no India build, no VPS deploy, no push, no repo rename,
no Layer 5.

---

## 2. Architecture changes (Layer 4 additions vs Layer 3)

### New files (12)

```
intel/lodging/
├── __init__.py
├── seasons.py                       Season enum + multiplier matrix
│                                    + Gauss-Easter + Holy Week
├── scoring.py                       LodgingColor + LodgingThresholds
│                                    + score_observation()
├── baseline.py                      LodgingBaseline + compute_baseline()
├── storage.py                       LodgingStorage wraps SqliteManager
├── service.py                       LodgingIntelService + LodgingSignal
└── providers/
    ├── __init__.py
    ├── interface.py                 LodgingProvider protocol +
    │                                LodgingObservation + ProviderResult
    │                                + ProviderStatus enum
    ├── mock.py                      MockLodgingProvider — drives tests
    ├── airdna.py                    AirDnaProvider — STUB in Layer 4
    └── inside_airbnb.py             InsideAirbnbProvider — STUB

tests/
├── test_layer4_seasons.py           11 tests
├── test_layer4_scoring.py           17 tests
├── test_layer4_storage.py           10 tests
├── test_layer4_providers.py         14 tests
└── test_layer4_protections.py       11 tests
```

### Modified files (3)

- `db/schema.sql` — appended `lodging_baseline` + `lodging_history`
  tables with their lookup indexes. The schema is re-applied on every
  SqliteManager init (`CREATE TABLE IF NOT EXISTS`), so existing
  Layer 1+2+3 deployments pick up the new tables on next start with
  no migration script.
- `agents/config.py` — `DeskConfig` gains 7 Layer 4 fields and
  `load_desk_config()` reads them with the spec defaults.
- `.env.example` — documents every Layer 4 env knob and notes the
  default safety stance.

### Unmodified — preservation contract

- `src/` (scanner) — untouched. Scanner preservation tests still
  4/4 green.
- `links/telegram_dispatcher.py` — Layer 2 gate, dedupe, cooldown,
  audit unchanged.
- `agents/oakstreet/orchestrator.py` — Layer 3 briefing path
  unchanged. The `lodging_signal` slot in `verdict_input` is still
  populated as `None` by Echo (Layer 4 is the brain only).
- Layer 1 heartbeat decay engine — untouched, 14/14 still pass.
- DRY_RUN + SCANNER_TELEGRAM_ENABLED — local `.env` is unchanged.

---

## 3. Season weighting matrix

Spec multipliers exactly as written, applied to the raw pct-below-
baseline before the threshold classifier:

| Window | Season | Multiplier |
|---|---|---|
| Dec 15 — Jan 15 | **PEAK** | 0.75x |
| Jan 16 — Apr 14 | **MID** | 1.00x |
| Apr 15 — May 31 | **LOW** | 1.20x |
| Jun 1 — Aug 31 | **HIGH** | 0.85x |
| Sep 1 — Dec 14 | **LOW** | 1.20x |
| Holy Week (variable) | **PEAK** | 0.75x — overrides surrounding season |

Boundaries are inclusive at both ends. Holy Week is the 7 days ending
the day before Easter Sunday (Palm Sunday through Holy Saturday) and
is computed via the Gauss algorithm — verified against known Western
Easter dates 2024–2030.

### Effect on the GREEN/YELLOW/RED bands

Scoring formula:

```
raw_pct      = (baseline - observed) / baseline * 100
weighted_pct = raw_pct * season_multiplier   (or raw_pct if weighting off)
```

| Season | Multiplier | Raw pct needed for YELLOW (>= 8) | for RED (>= 15) |
|---|---|---|---|
| PEAK | 0.75 | **~10.7%** | **20.0%** |
| HIGH | 0.85 | ~9.4% | ~17.7% |
| MID | 1.00 | 8.0% | 15.0% |
| LOW | 1.20 | **~6.7%** | **12.5%** |

LOW season amplifies: a 7% drop tips into YELLOW. PEAK attenuates:
even a 12% drop only reaches GREEN. This matches the operator
intuition that high-demand seasons need bigger discounts to qualify
as "deals".

---

## 4. RED/YELLOW/GREEN thresholds

Per the spec, classification compares `weighted_pct_below` against:

| Color | Condition |
|---|---|
| GREEN | weighted_pct < 8 |
| YELLOW | 8 <= weighted_pct < 15 |
| RED | weighted_pct >= 15 |

Configurable via `LODGING_YELLOW_THRESHOLD` and `LODGING_RED_THRESHOLD`
in `.env`. The `LodgingThresholds` dataclass rejects malformed input
(`0 < yellow < red`) at construction.

---

## 5. SQLite schema additions

```sql
CREATE TABLE IF NOT EXISTS lodging_baseline (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    city               TEXT    NOT NULL,
    neighborhood       TEXT,
    beds               INTEGER,
    baseline_price_usd REAL    NOT NULL,
    sample_size        INTEGER NOT NULL,
    lookback_days      INTEGER NOT NULL,
    computed_at        TEXT    NOT NULL,
    source_set         TEXT
);
CREATE INDEX IF NOT EXISTS idx_lodging_baseline_lookup
    ON lodging_baseline(city, neighborhood, beds, computed_at);

CREATE TABLE IF NOT EXISTS lodging_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city            TEXT    NOT NULL,
    neighborhood    TEXT,
    beds            INTEGER,
    observed_at     TEXT    NOT NULL,
    stay_date       TEXT    NOT NULL,
    price_usd       REAL    NOT NULL,
    source          TEXT    NOT NULL,
    listing_ref     TEXT,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS idx_lodging_history_lookup
    ON lodging_history(city, neighborhood, beds, observed_at);
```

Lives in the same `colombia_desk.sqlite` file as the deals + heartbeat
+ specialist_reports tables. `LodgingStorage(SqliteManager)` is the
only writer in Layer 4.

---

## 6. Env surface

Added to `.env.example` with the spec defaults:

```
LODGING_INTEL_ENABLED=true
AIRDNA_API_KEY=
INSIDE_AIRBNB_LOCAL_PATH=/data/insideairbnb
LODGING_YELLOW_THRESHOLD=8
LODGING_RED_THRESHOLD=15
LODGING_SEASON_WEIGHTING=true
LODGING_BASELINE_LOOKBACK_DAYS=90
```

`DeskConfig` reads all seven, with the documented defaults applying
when env is silent. `LODGING_INTEL_ENABLED=false` short-circuits the
entire service — every `refresh_observations` returns `[]` and
`signal_for(...)` returns `None`.

---

## 7. Test coverage

**Totals across the project: 182/182 tests passing.**

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
| `test_layer4_seasons` | **11/11** | **NEW** |
| `test_layer4_scoring` | **17/17** | **NEW** |
| `test_layer4_storage` | **10/10** | **NEW** |
| `test_layer4_providers` | **14/14** | **NEW** |
| `test_layer4_protections` | **11/11** | **NEW** |
| `test_smoke` (legacy) | 14/14 | Untouched |
| `dry_run_simulations` (4 scenarios) | all complete | Untouched |
| `main.py` import sanity | clean | — |

### What the Layer 4 protection suite specifically guards

```
ok  test_signal_for_returns_typed_signal_after_refresh_and_baseline
ok  test_signal_for_returns_none_when_disabled
ok  test_signal_for_returns_none_when_no_baseline_yet
ok  test_lodging_service_never_touches_dispatcher
ok  test_echo_lodging_signal_remains_none_in_layer4
ok  test_oakstreet_briefing_dry_run_suppressed_with_lodging_service_present
ok  test_heartbeat_suppression_intact_with_layer4_active
ok  test_zombie_cutoff_intact_with_layer4_active
ok  test_desk_config_documented_defaults
ok  test_lodging_intel_disabled_via_env
ok  test_no_live_telegram_path_can_fire_under_layer4
```

The last case (`test_no_live_telegram_path_can_fire_under_layer4`)
asserts the strongest invariant: **every dispatcher message recorded
during a Layer 4 ↔ Oak Street flow has `outcome="dry_run"`** —
proving no live send is reachable while Layer 4 runs alongside the
briefing path.

---

## 8. Design calls made during the build

1. **Single SQLite file, two new tables.** Adding lodging tables to
   `db/schema.sql` keeps the existing `SqliteManager` lifecycle the
   only writer to disk. `LodgingStorage` is a thin adapter, not a
   second manager.

2. **Median for the baseline.** Mean baselines drift on scrape
   outliers. Median is robust against an Inside Airbnb dump with a
   $10,000/night villa hidden in the middle of a 30-listing city.

3. **AirDNA and Inside Airbnb ship STUB even when configured.**
   Setting `AIRDNA_API_KEY` AND `enable_live=True` still returns
   `ProviderResult(status=STUB, reason="not implemented in Layer 4")`.
   The wire path stays closed until the layer that implements it
   replaces the body of `_fetch_live`. This is the operator safety
   contract — the brain alone cannot make an unexpected HTTP call.

4. **Echo's `lodging_signal` remains None.** The schema slot was
   reserved in Layer 3 and the future hookup is a single
   `LodgingIntelService.signal_for(...)` call inside Echo. Doing the
   wiring NOW would mean shipping Layer 5 work labeled Layer 4 —
   exactly what the brief prohibits.

---

## 9. Outstanding items for the operator

Already pending and still open:

- The eight non-Colombia region packs (Option 1/2/3 from
  `REPO_RENAME_MIGRATION.md` §2).
- Directory + GitHub repo rename to `coming-to-colombia-bot`.
- `DRY_RUN=false` flip — Layer 4 explicitly keeps it true.
- VPS deploy authorization.
- Live Delta return-leg fetcher (Layer 3 enhancement candidate).

New surface introduced by Layer 4 that needs decisions before going live:

- **Real AirDNA wire**: when ready, replace `AirDnaProvider._fetch`
  STUB body with the live HTTP call. Tests should then exercise both
  STUB (no creds) and OK (live) paths.
- **Inside Airbnb local-path reader**: similarly, add the CSV/Parquet
  ingestion under `enable_live=True`. The path knob is already in
  `.env`.
- **Threshold tuning**: defaults are conservative (8% / 15%). Once
  baselines are populated, adjust if alert volume is wrong.
- **Per-city baselines**: today the storage indexes are ready for
  `(city, neighborhood, beds)` keys but the orchestration uses
  city-level only. Wire neighborhood granularity if Inside Airbnb
  data supports it.

---

## 10. Recommended Layer 5 scope (proposal — no action)

1. **Echo ↔ LodgingIntelService wiring.** Replace
   `verdict_input["lodging_signal"] = None` with a real signal from
   `signal_for(...)`. One file change in `agents/echo/specialist.py`
   plus a Layer 5 hookup test.
2. **Real AirDNA + Inside Airbnb providers.** Implement the live
   `_fetch` paths gated by `enable_live`. Keep the STUB fall-through
   so accidental misconfiguration never triggers an HTTP call.
3. **India specialist foundation.** Symmetric to Echo: a separate
   intelligence dimension (event/holiday calendar? air-quality?
   weather windows?) consuming the same brain.
4. **Audit-log analyzer CLI** (already proposed in Layer 3's
   recommendation; still a good candidate).

Layer 6+: VPS deploy, repo rename, monetization, real-time
multi-region brain expansion.

---

**End of report. Layer 4 complete. No deploy. No push. No Layer 5.**
