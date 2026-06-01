# LIVE DATA READINESS REPORT
**Project:** coming-to-colombia-bot
**Phase:** 2.5 — Live Data Validation (audit only, no code changed, no deploy)
**Date:** 2026-05-31
**Branch / base:** `main` @ `e35c6fc`

> Scope note: this is a read-only audit. No source files were modified, nothing was
> deployed, no live API calls were made, and Phase 3 was not started. One new file —
> this report — was created, as the task requested.

---

## 0. Executive summary (read first)

Two facts dominate everything below:

1. **The outbound scanner is already wired to a live provider.** `.env` has
   `FLIGHT_API_PROVIDER=rapidapi_skyscanner` with a populated `RAPIDAPI_KEY`. So the
   outbound leg is **not** running on placeholder by configuration — it runs on the
   live RapidAPI Skyscanner connector and only *falls back* to placeholder on failure,
   cooldown, or a missing key. (Note: the Layer 7C plan still describes the
   pre-activation provider as `placeholder`; the live `.env` has already moved past that.)

2. **The code never emits `source="skyscanner"` or `source="amadeus"`.** Every live
   offer is tagged **`source="live"`**; every mock offer is tagged
   **`source="placeholder"`**. The provenance vocabulary is a two-value
   `live | placeholder`, *not* provider-named. This is the single most important thing
   to reconcile against the task's wording (see §6).

The return-pairing leg (Delta specialist) **is** still on placeholder, gated by
`DELTA_LIVE_RETURNS=false`. That flag is confirmed to be the switch suppressing live
return searches (see §5).

---

## 1. Every `source="placeholder"` assignment

| # | Location | Kind | Notes |
|---|----------|------|-------|
| 1 | `src/flight_fetcher.py:155` | **Real runtime assignment** | The only place mock flight offers are tagged. Emitted by `PlaceholderFlightFetcher.search()`. |
| 2 | `agents/delta/specialist.py:191` | Dataclass default | `Delta._provenance` defaults to `"placeholder"`. |
| 3 | `agents/delta/specialist.py:214` | Runtime assignment | Offline posture: `self._provenance = "placeholder"`. |
| 4 | `agents/delta/specialist.py:218` | Runtime assignment | Injected-fetcher posture is treated as placeholder-grade for STUB status. |
| 5 | `agents/delta/report.py:93, 200` | Default read | `payload.get("provenance", "placeholder")` fallback. |
| 6 | `intel/return_pairing/pairing.py:34` | Field doc/default | `ReturnLegQuote.source` documented as `"live" | "placeholder"`. |
| 7 | `src/flight_fetcher.py:41` | Field doc | `FlightOffer.source` documented as `"live" | "placeholder"`. |
| 8 | `agents/delta/specialist.py:121, 132` | Docstrings only | Describe the labelling contract; no behavior. |

The corresponding **live** tags are `src/flight_fetcher.py:232` (Amadeus parser) and
`:270` (Skyscanner parser), both `source="live"`.

---

## 2. Current outbound scanner data path (traced)

```
scheduler.scan_job(context)                      src/scheduler.py:134
  └─ run_full_scan(bot_data)                      src/scheduler.py:121
       fetcher = bot_data["fetcher"]              ← set in main.py:103 via get_fetcher(config)
       for dest in region.destination_codes():
         └─ compare_routes(fetcher, dest, …)      src/route_compare.py:114
              ├─ fetcher.search(origin, dest, day)        (Strategy A: direct)
              └─ fetcher.search(origin, gateway, day)     (Strategy B: positioning)
                 fetcher.search(gateway, dest, day/+1)
       └─ classify_route(...) → DealResult         src/deal_classifier.py
```

`get_fetcher(config)` (`src/flight_fetcher.py:552`) resolves the concrete fetcher:

- `provider == "placeholder"` → `PlaceholderFlightFetcher`
- `provider == "rapidapi_skyscanner"` → `LiveFlightFetcher` **iff `rapidapi_key` set**, else placeholder fallback
- `provider == "amadeus"` → `LiveFlightFetcher` **iff `flight_api_key` set**, else placeholder fallback

**With the current `.env`** (`rapidapi_skyscanner` + key present) the runtime fetcher is
`LiveFlightFetcher`. Its `search()` → `_search_with_fallback()` (`:361`) which:
1. serves placeholder during a post-failure cooldown (`FAILURE_COOLDOWN_SECONDS=600`),
2. serves a cached result inside `CACHE_TTL_SECONDS=2400`,
3. otherwise calls the live RapidAPI Skyscanner endpoint, and on **any** exception
   logs, arms a 10-min cooldown, and returns placeholder offers — so a scan never crashes.

---

## 3. Fetcher inventory — live / placeholder / demo / stub

| Component | Class / symbol | Status | `source` tag | Reached at runtime? |
|-----------|----------------|--------|--------------|---------------------|
| Outbound — RapidAPI Skyscanner | `LiveFlightFetcher._search_rapidapi_skyscanner` `flight_fetcher.py:484` | **LIVE** (verified, key present) | `live` | **Yes** — active provider |
| Outbound — Amadeus | `LiveFlightFetcher._search_amadeus` `flight_fetcher.py:417` | **LIVE** (code ready, **no key**) | `live` | No (provider not selected, keys empty) |
| Outbound — placeholder | `PlaceholderFlightFetcher` `flight_fetcher.py:117` | **PLACEHOLDER** | `placeholder` | Yes — as live fallback |
| Outbound — kiwi | `_search_kiwi` `flight_fetcher.py:542` | **STUB** (`NotImplementedError`) | — | No |
| Outbound — direct skyscanner | `_search_skyscanner` `flight_fetcher.py:545` | **STUB** (`NotImplementedError`) | — | No |
| Outbound — serpapi | `_search_serpapi` `flight_fetcher.py:548` | **STUB** (`NotImplementedError`) | — | No |
| Return leg — live | `make_live_return_fetcher` `specialist.py:127` | **LIVE-capable** (reuses outbound `LiveFlightFetcher`) | `live` | **No** — gated off by `DELTA_LIVE_RETURNS=false` |
| Return leg — placeholder (price-only) | `placeholder_return_fetcher` `specialist.py:52` | **PLACEHOLDER / STUB** | `placeholder` | **Yes** — current return path |
| Return leg — placeholder (full quote) | `make_placeholder_offer_fetcher` `specialist.py:116` | **PLACEHOLDER** | `placeholder` | Only via DRY_RUN demo |
| Live-providers 7A — airfare | `intel/live_providers/airfare.py` + `selection.py` | **MOCK / inert** | n/a (separate subsystem) | No — `LIVE_PROVIDERS_ENABLE=false`, transport "not wired" |
| Demo | `examples/return_optimizer_demo.py` | **DEMO** | `placeholder` | No — example script only |

**Clarifications:**
- The Layer 7A `intel/live_providers/` package (`LIVE_AIRFARE_PROVIDER=mock`,
  `LIVE_PROVIDERS_ENABLE=false`) is a **separate, gated substrate** that is *not* on the
  outbound scanner path. Even its `generic` adapter returns a "not wired" transport
  error until a real transport is injected. It is irrelevant to switching outbound/return
  flight provenance and should not be confused with `src/flight_fetcher.py`.
- "demo" exists only as `examples/return_optimizer_demo.py`; not a runtime source.

---

## 4. Dependency map

```
                         .env (FLIGHT_API_PROVIDER, RAPIDAPI_KEY, DELTA_LIVE_RETURNS, …)
                                          │  load_config()  src/config.py:128
                                          ▼
                                   get_fetcher(config)      src/flight_fetcher.py:552
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ OUTBOUND SCANNER            scan_job → run_full_scan      src/scheduler.py      │
│   └─ compare_routes(fetcher,…)        src/route_compare.py                       │
│        └─ FLIGHT FETCHER  LiveFlightFetcher  (provider=rapidapi_skyscanner)      │
│             live → source="live"   |  fallback → PlaceholderFlightFetcher        │
│                                              source="placeholder"               │
└───────────────┬────────────────────────────────────────────────────────────────┘
                │ DealResult  →  _event_from_result()  →  AlertEvent
                ▼
        DeskPipeline.process_event       agents/oakstreet/pipeline.py
                │   (only when SCANNER_TELEGRAM_ENABLED=false)
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ RETURN PAIRING (Delta)      agents/delta/specialist.py                          │
│   fetcher = DELTA_LIVE_RETURNS ? make_live_return_fetcher()  ← LIVE-capable      │
│                                : placeholder_return_fetcher  ← CURRENT (stub)    │
│   └─ estimate_pairing()     intel/return_pairing/pairing.py                      │
│        → ReturnLegQuote(source = "live" | "placeholder")                         │
└───────────────┬────────────────────────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ RANKING                     intel/return_pairing/ranking.py  rank_returns()      │
│   → colored options (RED/YELLOW/GREEN vs window-set median) + ranked views       │
└───────────────┬────────────────────────────────────────────────────────────────┘
                ▼  SpecialistReport (status OK | STUB | PARTIAL | NO_DATA)
┌──────────────────────────────────────────────────────────────────────────────┐
│ OAK STREET RENDERER         agents/oakstreet/orchestrator.py                    │
│   ingest_report → synthesize_briefing → _render_delta_section (+echo/india)     │
│   → dispatch_briefing → TelegramDispatcher.send  (gated by DRY_RUN)             │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Provenance honesty propagates end-to-end:** `FlightOffer.source` →
`_offer_to_quote` (`specialist.py:76`) → `ReturnLegQuote.source` →
`ReturnOption.source` (`pairing.py`) → rendered briefing. A live day that falls back to
placeholder arrives tagged `placeholder` and triggers the `mixed-provenance` flag
(`specialist.py:358`).

---

## 5. Is `DELTA_LIVE_RETURNS=false` preventing live return searches? — **YES**

Confirmed in `agents/delta/specialist.py`:

- `_live_enabled()` (`:170`) → `os.environ.get("DELTA_LIVE_RETURNS","").strip().lower() in {"1","true","yes","on"}`.
- `Delta.__post_init__` (`:194`):
  - if no explicit fetcher **and** `_live_enabled()` → `make_live_return_fetcher()`,
    `_provenance="live"`, and the window list is down-sampled for quota.
  - else (current case) → `placeholder_return_fetcher`, `_provenance="placeholder"`.

With `DELTA_LIVE_RETURNS=false`, the return path uses the deterministic stub. The
resulting report is `Status.STUB` (confidence 0.6) and carries the
`placeholder-fetcher` flag (`specialist.py:354`). So: **outbound = live, return =
placeholder.** Flipping `DELTA_LIVE_RETURNS=true` is the only switch needed to put the
return leg on the same live connector the outbound already uses.

---

## 6. What it takes to go from `source="placeholder"` to live — without breaking tests

### 6a. The provenance-string mismatch (decision required)
The task asks to switch to `source="skyscanner"` or `source="amadeus"`. **No code path
produces those literals.** Live offers are `source="live"`. There are two
interpretations:

- **(A) "Live, regardless of literal" — recommended, ZERO code change.** Treat
  `source="live"` as the live state. The outbound scanner is already there; the return
  leg needs only `DELTA_LIVE_RETURNS=true`. This is purely an `.env` change and does not
  touch code or tests.
- **(B) "Literally rename the provenance to the provider name."** Requires editing
  `_parse_skyscanner_itinerary` (`flight_fetcher.py:270`, `source="live"→"skyscanner"`)
  and `_parse_amadeus_offer` (`:232`, `→"amadeus"`). This is **risky**: at least
  `specialist.py:358` and the dataclass docs assume the `live | placeholder` dichotomy
  (`mixed-provenance` detection compares against `"placeholder"`, and STUB/OK status keys
  off `_provenance=="live"`, not the offer literal — so renaming offers alone would
  desync the renderer's honesty flags). No existing test asserts `source=="live"` for a
  flight (grep of `tests/` shows provenance assertions only on lodging `"mock"`), so the
  rename would not *fail* a test today — but it would silently weaken the honesty
  labelling. **Do not do (B) without a deliberate spec decision.**

### 6b. Concrete requirements to run live
| Path | Provider | Requirement | Status |
|------|----------|-------------|--------|
| Outbound | RapidAPI Skyscanner | `FLIGHT_API_PROVIDER=rapidapi_skyscanner`, `RAPIDAPI_KEY`, `RAPIDAPI_HOST` | ✅ all present |
| Outbound (alt) | Amadeus | `FLIGHT_API_PROVIDER=amadeus`, `FLIGHT_API_KEY`, `FLIGHT_API_SECRET` | ❌ keys EMPTY; `config.validate()` will fail startup if selected |
| Return leg | (reuses outbound) | `DELTA_LIVE_RETURNS=true` | ❌ currently `false` |

### 6c. Will existing tests still pass? — Yes, with one caveat
- `test_smoke.py` and `test_full_scan_runs` **inject `PlaceholderFlightFetcher`
  explicitly** ("smoke tests must never hit a live API", `test_smoke.py:166`) — unaffected
  by `.env` provider changes.
- Layer 3 tests construct `Delta()` with no fetcher; in a clean env that defaults to
  placeholder. They do **not** read `.env` unless something else loads it.
- **Caveat (pre-existing, not caused by going live):** when `.env` is loaded into the
  process (e.g. any test that calls `load_config()` runs first), the
  `RETURN_WINDOW_MODE=range / MIN=4 / MAX=60 / STEP=1` values make
  `resolve_return_windows()` return **57** windows instead of the canonical 8, and
  `test_delta_report_payload_carries_all_windows` fails. I reproduced this exactly: the
  three Layer-3 window tests pass in isolation (13/13) but fail when run after a module
  that loads `.env`. This is a **test-isolation / env-bleed issue that already exists**;
  enabling live providers neither causes nor fixes it, but it will surface in any
  full-suite run and should be fixed (clear env in test setup, or pass `windows=`
  explicitly) before relying on a green suite as the go-live gate.

---

## 7. Live vs placeholder components (summary)

**Live now (in DRY_RUN):**
- Outbound flight pricing — RapidAPI Skyscanner (`source="live"`), with placeholder fallback.
- Telegram send seam — wired, but `DRY_RUN=true` keeps it record-only.

**Placeholder / stub now:**
- Return-leg pricing (Delta) — `placeholder_return_fetcher` (gated by `DELTA_LIVE_RETURNS=false`).
- Lodging (Echo/India) — `MockLodgingProvider` (`main.py:37`).
- Layer 7A live-providers substrate — mock + "not wired" transport, master gate off.

---

## 8. API requirements & missing credentials

| Credential | Used by | Present? |
|------------|---------|----------|
| `RAPIDAPI_KEY` (+`RAPIDAPI_HOST`) | Outbound + (when enabled) return Skyscanner | ✅ set (50 chars) |
| `FLIGHT_API_KEY` / `FLIGHT_API_SECRET` | Amadeus connector | ❌ empty |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Dispatcher live send | ✅ set |
| `AIRDNA_API_KEY` | Lodging (real) | ❌ empty (mock in use) |
| `LIVE_AIRFARE_API_KEY` / `LIVE_LODGING_API_KEY` | 7A substrate | ❌ empty (gated off, inert) |

**No additional credential is required to validate live outbound flight data** — the
RapidAPI key is already present. Amadeus keys are only needed if Amadeus is chosen as a
backup/primary provider.

---

## 9. Estimated implementation effort

| Task | Effort | Type |
|------|--------|------|
| Enable live return legs | `DELTA_LIVE_RETURNS=true` | **Config only, ~minutes** |
| Validate live outbound (connectivity probe + one real scan in DRY_RUN) | ~0.5 day | Validation |
| Add Amadeus as backup provider | populate 2 keys | Config only (code ready) |
| Provider-named provenance literal — interpretation (B) | ~0.5–1 day + careful review | Code + honesty-flag review |
| Fix pre-existing window test env-bleed | ~1–2 hrs | Test hygiene |
| Full live arming (flip `DRY_RUN=false`) | per Layer 7C runbook | Deployment (out of scope here) |

**Bottom line:** reaching fully live *data* (outbound already live; return one flag away)
is **near-zero engineering** — it is a configuration + validation exercise, not a build.

---

## 10. Risks

1. **Provenance vocabulary mismatch (high-attention).** The spec's
   `skyscanner`/`amadeus` literals do not exist in code; live = `"live"`. Renaming
   without reviewing `specialist.py:358` and the STUB/OK status logic would silently
   degrade the "never present placeholder as live" honesty guarantee.
2. **Quota / rate limits.** RapidAPI Skyscanner `searchFlights` is async server-side
   (retries on `blocked`) and quotas are small — hence the 40-min cache and 10-min
   failure cooldown. Enabling **live return legs** multiplies calls per RED deal across
   ~23 sampled windows; watch quota before flipping `DELTA_LIVE_RETURNS`.
3. **Silent fallback masking.** On any live failure the scanner returns placeholder
   tagged `placeholder` — correct for honesty, but a misconfigured key would look like
   "working but always cheap mock data." Validate via `verify_connection()` and check for
   the `mixed-provenance` flag rather than assuming live.
4. **Test suite not green as-is.** The env-bleed window-count failure (§6c) means a naive
   `pytest` run is red; don't treat the current suite as a clean go/no-go gate until fixed.
   (Also: system `pytest` is currently broken — `No module named '_pytest.scope'`; tests
   were validated by direct module execution under `.venv/bin/python`.)
5. **Amadeus startup guard.** Selecting `FLIGHT_API_PROVIDER=amadeus` with empty keys
   makes `config.validate()` return problems and `main()` `sys.exit(1)`. Don't switch
   providers without keys.

---

## 11. Recommended next step

**Do NOT yet flip `DRY_RUN` or start Phase 3.** Recommended order:

1. **Adopt interpretation (A):** treat `source="live"` as the live state; do **not**
   rename provenance literals. Confirm this with the spec owner before any code change.
2. **Validate live outbound** while still `DRY_RUN=true`: run `verify_connection()` for
   `rapidapi_skyscanner` and trigger one real scan; confirm offers come back
   `source="live"` (not fallback). This is the actual "Phase 2.5 live data validation."
3. **Enable live return legs** by setting `DELTA_LIVE_RETURNS=true`, then re-run a scan
   and confirm Delta reports flip from `STUB`/`placeholder-fetcher` to `OK`/`live`
   (watch for `mixed-provenance` indicating fallback days).
4. **Fix the window test env-bleed** so the full suite is genuinely green and can serve
   as the go-live gate.
5. Only then proceed to the Layer 7C activation runbook (flip `DRY_RUN=false`,
   `SCANNER_TELEGRAM_ENABLED` stays `false`) as a separate, deliberate step — **Phase 3**.

---

*Audit complete. No code modified, nothing deployed, Phase 3 not started.*
