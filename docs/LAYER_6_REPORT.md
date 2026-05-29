# Layer 6 Report — Echo Lodging Wiring, India Briefing Renderer, Config Typicals

**Branch:** `layer-6-echo-lodging-wiring` (off `main` @ `be7a692`)
**Status:** Layer 6 complete. No deploy. No push. No live providers. No external API activation.
**Test totals:** **259/259 passing** (235 prior + 24 new) + 4 DRY_RUN simulation scenarios complete.
**Scope authority:** `docs/LAYER_5_INDIA_HOSTEL_INTELLIGENCE_REPORT.md §11` (recommended Layer 6 scope), approved 2026-05-29.

---

## 1. Objectives delivered

| # | Objective | Outcome |
|---|-----------|---------|
| **O1** | Echo ↔ `LodgingIntelService` wiring | The reserved `lodging_signal` slot is now populated when the Layer 4 brain is injected. Mirrors India's degrade-quietly contract. |
| **O2** | Dedicated INDIA briefing section | Oak Street renders a real INDIA section (best option, price, score, options, city lodging color); Echo's lodging line now shows the live signal. India removed from the generic fall-through. |
| **O3** | Config-driven per-category typicals | India loads an optional typical-price table from `INDIA_TYPICAL_PRICES_JSON`; unset/invalid env falls back to the built-in defaults. |

**Explicitly deferred to Layer 7** (per approval): all live providers (AirDNA, Inside Airbnb, Hostelworld/Booking), VPS deployment, production integrations, and any external API activation. No new outbound or network path was opened in Layer 6.

---

## 2. Design decisions

### O1 — Echo lodging wiring
- Echo gains two optional fields: `lodging_service` and `lodging_observed_usd`.
- **Echo has no native lodging observation** (its domain is flights), so the representative nightly price is *injected* rather than scraped. Sourcing it from live nightly data is a Layer 7 concern; Layer 6 stays hermetic.
- Behavior matrix (`Echo._consult_lodging`):
  | Condition | `lodging_signal` | flag |
  |-----------|------------------|------|
  | No service injected | `None` | `lodging-hook-reserved` *(exact Layer 3-5 behavior)* |
  | Service, but no observed price / no baseline / it raises | `None` | `lodging-signal-unavailable` |
  | Service yields a signal | compact dict | `lodging-wired` |
- The lodging wiring **does not change Echo's status/confidence** — those still track the flight price band, preserving every prior Echo test.

### Serializable signal projection
- Added `LodgingSignal.as_verdict_dict()` (`intel/lodging/service.py`). The `SpecialistReport` contract requires every `verdict_input` value to survive `json.dumps`; `LodgingSignal` carries enums + a `date`, so consumers drop in the compact dict (`color`, `weighted_pct_below`, `raw_pct_below`, `baseline_price_usd`, `observed_price_usd`, `season`, `sample_size`, `on_date`).

### O2 — Briefing renderer
- New `OakStreet._render_india_section`; `synthesize_briefing` now renders India between Echo and the unknown-specialist fall-through, and excludes `india` from that fall-through loop.
- The INDIA header uses "hostels and budget stays" (no bare `&`) to stay safe under Telegram HTML parse mode.
- `_render_echo_section` renders the live lodging line when present, else `lodging signal: <i>not available</i>`.
- **Backward compatibility:** a future-hook India report with no `signal` payload still renders `INDIA` and echoes its status (the Layer 3 `test_synthesize_briefing_with_unknown_specialist` contract holds).

### O3 — Config typicals
- `load_category_typicals_from_env()` (`agents/india/scoring.py`) reads a JSON object mapping category value → USD/night. Unknown keys ignored; non-numeric/non-positive values skipped; missing/malformed/non-object file → `None`. Never raises.
- `India.__post_init__` calls it only when `typical_prices is None`; an explicit constructor table always wins. Env unset → `None` → scoring-module defaults (identical to Layer 5).

---

## 3. Files modified

| File | Change |
|------|--------|
| `intel/lodging/service.py` | Added `LodgingSignal.as_verdict_dict()` |
| `agents/echo/specialist.py` | Optional `lodging_service` + `lodging_observed_usd`; `_consult_lodging`; fills lodging_signal; flags |
| `agents/oakstreet/orchestrator.py` | New `_render_india_section`; India wired into `synthesize_briefing` + removed from fall-through; Echo lodging line rendered |
| `agents/india/scoring.py` | `load_category_typicals_from_env()` + `TYPICAL_PRICES_ENV_VAR` |
| `agents/india/specialist.py` | `__post_init__` loads config typicals when none supplied |
| `.env.example` | Documented `INDIA_TYPICAL_PRICES_JSON` |

**Untouched (frozen):** `intel/lodging/{scoring,seasons,baseline,storage}`, dispatcher gate/dedupe/cooldown, `src/` legacy scanner, all STUB provider safety contracts, `SpecialistReport` schema (no new VERDICT_KEYS needed — `lodging_signal` was already reserved).

---

## 4. Tests added (24)

| Suite | Tests | Focus |
|-------|-------|-------|
| `tests/test_layer6_echo_lodging_wiring.py` | 8 | Backward compat (no service); wired fills serializable dict; unavailable paths; broken service swallowed; status unchanged |
| `tests/test_layer6_briefing_india.py` | 7 | Dedicated INDIA section; not in fall-through; future-hook back-compat; Echo lodging line wired/unwired; section ordering; DRY_RUN dispatch with India does not send |
| `tests/test_layer6_config_typicals.py` | 9 | Loader unset/valid/unknown-keys/missing/non-object/empty; India defaults vs env override vs explicit override |

---

## 5. Test results

- **Full suite: 259/259 passing** across 21 `test_*.py` suites (235 prior + 24 Layer 6). Zero failures.
- **DRY_RUN simulations:** all 4 scenarios complete — "no network, no disk writes."
- **Phase A freeze invariants (§13) re-verified by name** — all green:
  - DRY_RUN safety, severity gate, dedupe + cooldown, heartbeat/zombie suppression, scanner kill switch, audit-row-per-decision, schema strictness, STUB safety contracts.
  - `test_dry_run_dispatch_with_india_does_not_send` proves the new India path opens no wire.

---

## 6. Backward compatibility

- Default `Echo(...)` (no service) is byte-for-byte unchanged: `lodging_signal=None`, flag `lodging-hook-reserved`. The Layer 3 echo suite (13/13) confirms.
- Default `India(...)` with no env is identical to Layer 5 (defaults table). Layer 5 suites (53/53) confirm.
- Briefing output for prior callers unchanged except India is now a richer named section instead of a generic line — the existing assertion contract (`INDIA`, `stub`) still holds.

---

## 7. Layer 7 readiness assessment

**Ready.** The reserved seams are now closed in a hermetic, test-backed way, and the natural Layer 7 work plugs into existing protocols:

1. **Live providers** — `AirDnaProvider`, `InsideAirbnbProvider`, and a live `HostelProvider` already exist as STUBs behind `enable_live`. Layer 7 implements `fetch(...)` only; no consumer changes.
2. **Live nightly price for Echo** — replace the injected `lodging_observed_usd` with a real per-city median from the active scan. Echo's `_consult_lodging` already accepts it.
3. **VPS deploy** — `deployment/systemd/coming-to-colombia-bot.service.template` is path-agnostic and renamed; remaining work is operational (real `.env`, `DRY_RUN=false`/`SCANNER_TELEGRAM_ENABLED=true` flips, monitoring).
4. **Runtime composition root** — *note:* specialists (Delta/Echo/India) are still instantiated only in tests; `main.py` wires the legacy scanner + Oak Street + dispatcher. Wiring specialists into the live event flow is a Layer 7 prerequisite for any real briefing to fire.
5. **Monetization / multi-region** — unchanged from the L5 roadmap.

**Risk note:** no live data path was activated; the STUB safety floor remains intact. Layer 7 must keep `enable_live` gating and re-verify the §13 invariants when wiring real providers.

---

**End of report. Layer 6 complete. No deploy. No push. No live providers.**
