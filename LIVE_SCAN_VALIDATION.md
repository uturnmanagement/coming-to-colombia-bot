# LIVE SCAN VALIDATION
**Project:** coming-to-colombia-bot
**Phase:** 2.5 — Live Outbound Validation
**Date:** 2026-05-31
**Provider under test:** `rapidapi_skyscanner` (RapidAPI Skyscanner Flights & Travel API)

> **Posture held throughout:** `DRY_RUN=true`, `SCANNER_TELEGRAM_ENABLED=false`.
> No Telegram message was sent or constructed (the dispatcher was never imported).
> No code changed, no deployment changed, no `.env` value changed. The validation
> harness ran from `/tmp` (outside the repo) and was deleted after the run.

---

## 0. Result — PASS ✅

Real flight inventory **is retrievable** from the live RapidAPI Skyscanner provider.
Connectivity confirmed, every returned offer carried `source="live"`, and airline
names, prices, schedules, and booking deep links are all real. The system is ready to
proceed to enabling `DELTA_LIVE_RETURNS` (return-leg pricing), subject to the quota note
in §6.

---

## 1. What was run

A single, quota-conscious live outbound validation:

1. **Connectivity probe** — `LiveFlightFetcher.verify_connection()` (one `searchAirport`
   round trip).
2. **Direct outbound legs** — live `searchFlights` for three representative routes from
   the configured origin **BWI**, departing the real scan day **2026-06-21**
   (`today + scan_days_ahead=21`): `BWI→BOG`, `BWI→MDE`, `BWI→CTG`. Called through the
   live connector so any provider error would surface honestly rather than being masked
   by the placeholder fallback.
3. **Scan path confirmation** — the normal scanner entry point
   `LiveFlightFetcher.search()` (the same call `compare_routes` makes) for `BWI→BOG`, to
   prove the production scan path — not just a raw method — returns live data.

**Deliberately NOT run:** the full `run_full_scan()` positioning matrix (6 destinations ×
direct + up to 7 gateways × 3 leg-searches ≈ 100+ API calls). That would exhaust the
small RapidAPI quota needed for live return-leg pricing and is unnecessary to answer the
validation question. Direct outbound legs are the core inventory check.

---

## 2. Provider connectivity — CONFIRMED ✅

| Field | Value |
|-------|-------|
| Provider | `rapidapi_skyscanner` |
| Host | `skyscanner-flights-travel-api.p.rapidapi.com` |
| RapidAPI key | present (50 chars) |
| Resolved fetcher class | `LiveFlightFetcher` (`is_live_fetcher = true`) |
| `verify_connection()` | **OK** — *"RapidAPI Skyscanner reachable (airport lookup OK)."* |

The runtime fetcher is the live connector (not a placeholder fallback), and the airport
resolution endpoint responded successfully.

---

## 3. `source` provenance — CONFIRMED LIVE ✅

Every offer on every route returned `source="live"`. No placeholder fallback occurred on
any route (no cooldown, no failure, no `blocked` exhaustion).

| Route | Offers returned | `source` values | All live? | Error |
|-------|-----------------|-----------------|-----------|-------|
| `BWI→BOG` | 10 | `["live"]` | ✅ yes | none |
| `BWI→MDE` | 46 | `["live"]` | ✅ yes | none |
| `BWI→CTG` | 38 | `["live"]` | ✅ yes | none |
| `BWI→BOG` (via `search()` scan path) | 10 | `["live"]` | ✅ yes | none |

---

## 4. Airline names & prices — CONFIRMED REAL ✅

Cheapest live offer per route (departing 2026-06-21):

| Route | Airline | Price (USD) | Depart → Arrive | Stops | Duration | Booking link |
|-------|---------|-------------|-----------------|-------|----------|--------------|
| `BWI→BOG` | American Airlines | **$226.00** | 06-21 18:39 → 06-22 11:20 | 1 | 17h41 | real Skyscanner deeplink |
| `BWI→MDE` | Frontier Airlines | **$235.00** | 06-21 19:27 → 06-23 23:12 | 3 | 52h45 | real Skyscanner deeplink |
| `BWI→CTG` | Frontier Airlines | **$230.00** | 06-21 19:27 → 06-22 23:00 | 2 | 28h33 | real Skyscanner deeplink |

Additional real carriers observed across the sample sets: **LATAM Airlines, Delta,
American Airlines, Frontier Airlines**. Prices are non-round, realistic fares
(e.g. $308.39, $367.27, $234.61, $278.60), schedules are concrete date-times, and each
itinerary carries a genuine `https://www.skyscanner.net/transport_deeplink/4.0/...`
booking URL. These are not the deterministic mock airlines (`Avianca/American/JetBlue/
Spirit/Delta/United/Frontier` round-number fares) the placeholder fetcher generates.

> Honesty note: per the connector's documented contract, the Skyscanner `searchFlights`
> endpoint returns **leg-summary only** — flight numbers and connection-city detail are
> genuinely absent from this provider and are left empty (never synthesized). Price,
> airline, schedule, stop count, duration, and booking URL are real.

---

## 5. Observations

- **No truly non-stop inventory on these routes for the test date.** The cheapest BWI→BOG
  itinerary is one-stop; MDE/CTG cheapest are 2–3 stops. This is real market structure
  (BWI is not a Colombia gateway), not a defect — it is exactly the signal the
  positioning-vs-direct logic in `route_compare.py` exists to evaluate.
- **MDE/CTG returned large result sets** (46 / 38 itineraries), confirming the provider is
  returning full live inventory, not a thin/sampled response.
- **The production `search()` path matched the raw-method result** for BWI→BOG (10 live
  offers, same $226 American cheapest) — the scanner's real code path retrieves live data,
  not just the internal method.

---

## 6. Quota & cost note (read before enabling DELTA_LIVE_RETURNS)

- This validation consumed roughly **~7–8 RapidAPI calls** (1 connectivity + airport
  resolutions + 3 direct `searchFlights` + 1 scan-path `searchFlights`, with airport
  lookups cached in-process).
- A **full outbound scan** across all 6 destinations with the positioning matrix is
  ~100+ calls per scan, and the scheduler reruns every `YELLOW_RECHECK_MINUTES=45`.
- **Live return-leg pricing (`DELTA_LIVE_RETURNS=true`) multiplies calls** by ~23 sampled
  return windows **per RED deal**. Confirm the RapidAPI plan's monthly quota and rate
  limit before enabling it. The existing 40-min response cache and 10-min failure cooldown
  in `LiveFlightFetcher` mitigate but do not eliminate this.

---

## 7. Conclusion & recommended next step

**Phase 2.5 outbound validation: PASS.** Live, real flight inventory is confirmed
retrievable via `rapidapi_skyscanner`, tagged `source="live"`, with real airlines, fares,
schedules, and booking links — all while `DRY_RUN=true` and Telegram disabled.

**Recommended next step (Phase 2.5 → return-leg enablement):**
1. Verify the RapidAPI plan quota/rate limit against the per-RED-deal call multiplier in §6.
2. Set `DELTA_LIVE_RETURNS=true` (config only) and run one RED deal through the Delta
   specialist in DRY_RUN; confirm the report flips from `STUB`/`placeholder-fetcher` to
   `OK`/`live`, and watch for the `mixed-provenance` flag (indicates live→placeholder
   fallback days).
3. Keep `DRY_RUN=true` and `SCANNER_TELEGRAM_ENABLED=false` until the separate Phase 3
   activation runbook (Layer 7C) is deliberately executed.

---

*Validation complete. DRY_RUN held true, no Telegram sent, no code or deployment changed.*
*Validation harness ran from `/tmp` and was removed; only this report was added to the repo.*
