# Layer 7A Report — Live Provider Integration Foundation

**Branch:** `layer-7a-live-provider-foundation` (off `main` @ `12654b5`)
**Status:** Layer 7A complete. No live Telegram. No VPS. No Layer 7B/7C. No real network transport wired.
**Test totals:** **283/283 passing** (259 prior + 24 new) + 4 DRY_RUN simulation scenarios complete.
**Safe posture verified:** local `.env` keeps `DRY_RUN=true` and `SCANNER_TELEGRAM_ENABLED=false` (untouched).

---

## 1. Files changed

**New package `intel/live_providers/`:**

| File | Role |
|------|------|
| `__init__.py` | Public surface (data + builders only; no sender) |
| `base.py` | `LiveProvider` template: gating + the five failure modes; `LiveProviderStatus`, `LiveResult`, `LiveProviderConfig`, `ProviderTimeout`, `ProviderTransportError` |
| `transport.py` | `not_wired_transport` (default; wire closed) + `InjectableTransport` (offline fake responses/errors) |
| `airfare.py` | `LiveAirfareProvider` + `AirfareQuote` normalization |
| `lodging.py` | `LiveLodgingProvider` + `LodgingQuote` normalization |
| `mock.py` | Deterministic mock providers + transports (offline OK results) |
| `selection.py` | Env-based `build_airfare_provider` / `build_lodging_provider` |

**New tests:** `tests/test_layer7a_live_providers.py`, `tests/test_layer7a_selection.py`, `tests/test_layer7a_safety.py`.

**Modified:** `.env.example` (Layer 7A env block).

**Untouched (intact):** existing STUB providers (`intel/lodging/providers/airdna.py`, `inside_airbnb.py`), `MockHostelProvider`, `MockLodgingProvider`, the Delta placeholder fetcher, dispatcher/scheduler, `src/` scanner, all prior layers.

---

## 2. Provider architecture summary

```
query ─► LiveProvider.fetch(**query)            (base.py — never raises)
            │
            ├─ enable_live? ── no ─────────────► LiveResult(DISABLED)
            ├─ api_key?     ── no ─────────────► LiveResult(NO_KEY)   [wire never touched]
            │
            ├─ _build_request(**query)
            ├─ transport(timeout, **req)          (the ONLY possible network seam)
            │     ├─ raise ProviderTimeout ─────► LiveResult(TIMEOUT)
            │     └─ raise anything else ───────► LiveResult(ERROR)
            │
            ├─ raw is None ────────────────────► LiveResult(EMPTY)
            ├─ _parse(raw)
            │     └─ KeyError/TypeError/Value… ─► LiveResult(MALFORMED)
            ├─ no records ─────────────────────► LiveResult(EMPTY)
            └─ records ────────────────────────► LiveResult(OK, data=…)
```

- **Transport is the single seam** that could ever reach the network. The default is `not_wired_transport`, which raises → so a configured-but-unwired live provider returns `ERROR ("not implemented in Layer 7A")`. No real HTTP client is included in this layer, by design — the foundation cannot reach the internet by accident.
- **Mock mode** wires an in-process deterministic transport, exercising the full gating/parse pipeline and returning `OK` offline with no key.
- **Normalized records** (`AirfareQuote`, `LodgingQuote`) are transport-neutral; bridging them to the Layer 4 `LodgingObservation` / Oak Street pipeline is deferred to **7B**.

---

## 3. Env variables added

| Var | Default | Meaning |
|-----|---------|---------|
| `LIVE_PROVIDERS_ENABLE` | `false` | Master gate for live behavior |
| `LIVE_AIRFARE_PROVIDER` | `mock` | `mock` (offline) \| `generic` (gated live) |
| `LIVE_LODGING_PROVIDER` | `mock` | `mock` \| `generic` |
| `LIVE_PROVIDER_TIMEOUT_SECONDS` | `8` | Per-request budget for a future transport |
| `LIVE_AIRFARE_API_KEY` | *(blank)* | Secret — blank locally, never committed |
| `LIVE_LODGING_API_KEY` | *(blank)* | Secret — blank locally, never committed |

No secrets are stored, printed, or committed. `.env` was not modified.

---

## 4. Tests added (24)

| Suite | Tests | Focus |
|-------|-------|-------|
| `test_layer7a_live_providers.py` | 12 | OK; EMPTY (empty list + None); MALFORMED (missing field + wrong type); TIMEOUT; ERROR (transport + unexpected); NO_KEY; DISABLED; "never raises" sweep; wire-not-touched on NO_KEY/DISABLED |
| `test_layer7a_selection.py` | 6 | mock default/explicit; generic disabled→DISABLED; enabled+no key→NO_KEY; enabled+key→ERROR (not wired); unknown name→mock fallback |
| `test_layer7a_safety.py` | 6 | no links/telegram/dispatcher imports; `LiveResult` data-only; DRY_RUN=true & kill switch=false mapping; AirDNA/InsideAirbnb STUB intact; mock mode no-key/no-network |

---

## 5. Full test result

- **283/283 passing** across 24 `test_*.py` suites (259 prior + 24 Layer 7A). Zero failures.
- **DRY_RUN simulations:** 4/4 complete — "no network, no disk writes."
- One self-inflicted issue found & fixed during implementation: the safety scan first flagged the word "telegram" in docstrings; tightened to inspect `import`/`from` statements only.

---

## 6. Local test command

```powershell
# All Layer 7A suites:
.\.venv\Scripts\python.exe tests\test_layer7a_live_providers.py
.\.venv\Scripts\python.exe tests\test_layer7a_selection.py
.\.venv\Scripts\python.exe tests\test_layer7a_safety.py

# Full regression (every suite):
Get-ChildItem tests\test_*.py | ForEach-Object { .\.venv\Scripts\python.exe $_.FullName }
```

All run offline. Three local modes are covered with no external API:
**mock provider mode**, **missing-key mode**, and **fake provider response mode** (`InjectableTransport`).

---

## 7. Layer 7B readiness report

**Ready.** The foundation gives 7B clean seams:

1. **Real transport** — implement a `requests`-backed transport (separate module) and inject it into the `generic` provider; the gating/parse/failure ladder already exists and is tested. Add live-transport tests with a mocked HTTP client.
2. **Bridge to Layer 4** — map `LodgingQuote` → `LodgingObservation` and adapt `LiveLodgingProvider` to the existing `LodgingProvider` protocol so `LodgingIntelService` consumes it; map `AirfareQuote` into the scanner/Delta flow.
3. **Oak Street live integration (the big 7B piece)** — wire `scan_job` → `ingest_alert` (heartbeat decay) → Delta/Echo/India → `dispatch_briefing`, and construct the specialists + `LodgingIntelService` at the composition root (`main.py`). Specialists still run only in tests today.
4. **Still DRY_RUN** — 7B must remain DRY_RUN with the kill switch off; live arming is 7C.

**Risk note:** Layer 7A opened **no** wire — no Telegram path, no real HTTP, STUB floor intact, every failure mode typed and non-raising. 7B must preserve the `enable_live` gating and re-verify the Phase A freeze §13 invariants when bridging live data into the dispatcher path.

---

**End of report. Layer 7A complete. No live Telegram. No VPS. No 7B/7C.**
