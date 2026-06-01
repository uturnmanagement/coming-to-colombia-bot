# LIVE RETURN LEG VALIDATION
**Project:** coming-to-colombia-bot
**Phase:** 2.6 — Live Return-Leg Validation
**Date:** 2026-05-31
**Optimizer under test:** Delta Return Optimizer (`agents/delta`) with `DELTA_LIVE_RETURNS=true`

> **Safety posture held throughout:** `DRY_RUN=true`, `SCANNER_TELEGRAM_ENABLED=false`.
> No Telegram message sent or constructed (the validation never imported the dispatcher;
> `Delta.analyze` performs no sends). No deployment, no service restart, no scanner-behavior
> change. Only one config line flipped (`DELTA_LIVE_RETURNS`) and one report added; the
> validation harness ran from `/tmp` and was deleted.

---

## 0. Result — PASS ✅

Live return-leg pricing works end to end. With `DELTA_LIVE_RETURNS=true`, the Delta
optimizer priced every tested return window from the live RapidAPI Skyscanner connector
(`source="live"`), produced real airlines and fares, generated round-trip totals and
color buckets, and **no placeholder fallback occurred**. The report status moved exactly
as the gate intends: **STUB / placeholder-fetcher → OK / live**.

---

## 1. RapidAPI quota / rate-limit check (Task 1) — SUFFICIENT ✅

Measured live from the provider's response headers:

| Metric | Value |
|--------|-------|
| Monthly request limit | **10,000** |
| Remaining before validation | **8,075** |
| Remaining after validation | **8,058** |
| Reset window | ~30 days |
| Cost of one return-deal validation | ~14 live calls (this run) |

8,058 remaining ≫ the ~14–17 calls a single RED-deal validation costs. **Quota is more
than sufficient for one validation** (and for routine operation; the live service has used
only ~1,940 of 10,000 this month across its 45-minute scans).

---

## 2. Config change (Task 2) — applied, config-only

`.env`: `DELTA_LIVE_RETURNS=false` → **`true`**. Single line; `DRY_RUN` and
`SCANNER_TELEGRAM_ENABLED` untouched.

> **Operational note (important):** the live `coming-to-colombia-bot.service` (PID 61389)
> loaded its configuration at startup on **May 30** and does **not** hot-reload `.env`. It
> is therefore **still running with `DELTA_LIVE_RETURNS=false` in memory** and is **not**
> making live return calls. The new value takes effect only on the next deliberate service
> restart (a Phase-3 action — not performed here). This validation ran in an isolated
> process that read the updated `.env` directly.

---

## 3. Selected deal (Tasks 3) — strongest real current deal

**Honest finding on "RED":** the live service has run 12+ scans today and found
**0 RED deals** (`scan complete: 6 deals (0 red, 4 yellow)` every cycle). Current Colombia
inventory simply has no fare ≥ $150 under typical, so **no genuine RED outbound deal
exists to select right now.** I therefore selected the **single strongest real existing
deal** — the closest thing to RED in live inventory:

| Field | Value |
|-------|-------|
| Outbound route | **BWI → SMR** (Santa Marta) |
| Departure date | **2026-06-21** (`today + scan_days_ahead=21`) |
| Outbound price | **$286.00** (real, direct, from the 11:45 live scan) |
| Effective savings | **$144 under typical** ($430) — **$6 short of the $150 RED line** |
| Actual outbound color | **YELLOW** (no RED available; see above) |
| Deal key | `60fed31ea61a7e50` |

The seed `AlertEvent` was labeled `color="red"` to exercise the RED-priority path, but the
deal's true classification is YELLOW. **This does not affect the validity of the result:**
outbound color does not influence return-leg pricing — round-trip totals below use the
**real** $286 outbound fare plus **live** return fares, so every number is real.

---

## 4. Delta Return Optimizer run (Tasks 4–5)

**Return windows tested:** 7, 14, 21, 30, 45, 60 days (a representative spread across the
4–60 day range; a fixed set was used for quota control and reproducibility).
**Return direction:** SMR → BWI on each return date.

| Window | Return date | Airline | Stops | Return $ | Round-trip $ | Source | Color bucket |
|-------:|-------------|---------|------:|---------:|-------------:|--------|--------------|
| 7d  | 2026-06-28 | LATAM Airlines | 2 | $606.00 | $892.00 | **live** | GREEN |
| 14d | 2026-07-05 | JetSmart       | 3 | $368.00 | $654.00 | **live** | GREEN |
| 21d | 2026-07-12 | LATAM Airlines | 2 | $379.00 | $665.00 | **live** | GREEN |
| 30d | 2026-07-21 | LATAM Airlines | 3 | $395.00 | $681.00 | **live** | GREEN |
| 45d | 2026-08-05 | LATAM Airlines | 3 | $383.00 | $669.00 | **live** | GREEN |
| 60d | 2026-08-20 | JetSmart       | 3 | $333.00 | **$619.00** | **live** | YELLOW |

- **Airlines (real):** LATAM Airlines, JetSmart.
- **Cheapest return option / cheapest total:** **60-day window — JetSmart, $333 return,
  $619 round-trip** (also the cheapest-return-leg). This is the YELLOW-bucket pick.
- **Best direct-ish (fewest stops):** 21-day — LATAM, 2 stops, $665 round-trip.
- **Window-set median round-trip:** **$667.00** (basis for the color buckets).
- **Color bucket result:** **0 RED · 1 YELLOW (60d) · 5 GREEN.** (Buckets are the return
  options scored RED/YELLOW/GREEN relative to the window-set median, per the optimizer.)

> Honesty note: SMR ↔ BWI is a thin, small-airport market — all live returns are 2–3 stops
> and relatively expensive ($333–$606). That is real market structure, not a defect. No
> non-stop return inventory exists for this route/date.

### Status transition (Task 5) — CONFIRMED ✅
Same seed, both postures:

| | BEFORE (`DELTA_LIVE_RETURNS=false`) | AFTER (`DELTA_LIVE_RETURNS=true`) |
|---|---|---|
| provenance | `placeholder` | **`live`** |
| status | **`STUB`** | **`OK`** |
| confidence | 0.6 | **0.9** |
| flags | **`['placeholder-fetcher']`** | **`[]`** |
| offer source | none (offline stub) | **`live`** (all windows) |
| outbound enrichment source | — | **`live`** |

All five required checks pass:
- ✅ return prices are LIVE
- ✅ `source` is LIVE (every window + outbound enrichment)
- ✅ no placeholder fallback occurred (`fallback_detected = false`; no `mixed-provenance` flag)
- ✅ status changed STUB → OK
- ✅ flag `placeholder-fetcher` cleared

---

## 5. Source provenance & fallback behavior

| Check | Result |
|-------|--------|
| Distinct sources across all options | `["live"]` only |
| Placeholder fallback detected | **No** |
| `mixed-provenance` flag (live day fell back) | **Not raised** |
| Outbound-leg enrichment source | `live` |
| Delta internal `_provenance` | `live` |

No cooldown, no `blocked`-exhaustion, no 429 fallback was observed on any of the 7 live
searches (6 return windows + 1 outbound enrichment).

---

## 6. API calls consumed & quota impact

| Item | Calls |
|------|------:|
| Delta optimizer (6 return windows + outbound enrichment, incl. server-side retries + 2 airport resolves) | ~14 |
| In-harness quota probes (before/after) | 2 |
| Standalone quota probe (Task 1) | 1 |
| **Total Phase 2.6 spend** | **~17** |
| Remaining quota after | **8,058 / 10,000** |

**Quota impact: negligible** (~0.17% of the monthly limit for the full validation). A clean
production run (without the diagnostic probes) is ~14 calls; the full auto-sampled window
set (~23 windows) would be ~25–30 calls per RED deal — still small against 8,058 remaining,
but it scales per RED deal, so monitor when REDs become frequent.

---

## 7. Safety confirmations (Task 7)

| Requirement | Status |
|-------------|--------|
| `DRY_RUN` remained `true` | ✅ confirmed in `.env` after the run |
| `SCANNER_TELEGRAM_ENABLED` remained `false` | ✅ confirmed in `.env` after the run |
| No Telegram messages sent | ✅ dispatcher never imported/instantiated; `Delta.analyze` has no send path |
| No deployment performed | ✅ no `systemctl`, no service restart, no code change |
| Outbound scanner behavior modified | ✅ No — only the return-leg flag changed |
| Phase 3 started / `DRY_RUN` flipped | ✅ No — neither touched |

---

## 8. Conclusion & state left behind

**Phase 2.6 live return-leg validation: PASS.** The Delta Return Optimizer prices real
return inventory live, with honest `source="live"` provenance, correct STUB→OK / OK-flag
clearing, real airlines and round-trip totals, and zero placeholder fallback — all under
`DRY_RUN=true` with no messages sent.

**Current state:**
- `.env` now has `DELTA_LIVE_RETURNS=true` (as instructed). `DRY_RUN=true`,
  `SCANNER_TELEGRAM_ENABLED=false` unchanged.
- The **running service is unaffected** (still `false` in memory until a deliberate
  restart). No live return quota is being spent right now, and with 0 RED deals in current
  inventory, none would be spent immediately even after a restart.

**Stopping here as instructed — Phase 3 not started, `DRY_RUN` not flipped.**
Optional, your call: if you prefer to keep live returns dormant until Phase 3, revert the
one line to `DELTA_LIVE_RETURNS=false`; otherwise it is staged to activate on the next
service restart.

---

*Validation complete. DRY_RUN held true, no Telegram sent, no deployment, no Phase 3.*
