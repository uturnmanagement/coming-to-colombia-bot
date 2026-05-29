# Architecture Freeze v1 — Coming to Colombia Desk (Coming to Colombia Bot)

**Frozen on:** 2026-05-28
**Branch at freeze:** `layer-5-india-hostel-intelligence`
**Tip commit:** `74c4fe9` — LAYER 5
**Repo on disk:** `C:\Users\uturn\opshub_global_airfare_intelligence_system\` (Windows folder rename pending — see `REPO_RENAME_EXECUTION_REPORT.md`)
**Project identity (in-repo, post-rename):** `coming-to-colombia-bot` (rebrand executed 2026-05-29 on branch `repo-rename-coming-to-colombia-bot`)
**Test totals at freeze:** **235/235 passing** + 4 DRY_RUN simulation scenarios complete

> This document is the authoritative record of what the Colombia Desk
> stack looks like at the end of Layer 5. It is the reference for
> any later layer, any clone, any country fork. The contents reflect
> code on disk — every claim has a file path and (where useful) a
> module symbol.

---

## 1. Layers completed

| # | Layer | Commit | What it shipped |
|---|---|---|---|
| 0 | Initial framework | `b9eddc9` | The original `src/` worldwide airfare scanner |
| **1** | **Colombia Desk infrastructure + heartbeat** | `4c17fff` | `agents/oakstreet/`, `intel/heartbeat/`, `links/telegram_dispatcher.py`, `db/sqlite_manager.py`, shared logging + DRY_RUN config |
| **2** | **Live Telegram wiring + dispatcher hardening** | `e8d4581` | Severity gate, dedupe, cooldown, audit, scanner kill switch (`SCANNER_TELEGRAM_ENABLED`) |
| **3** | **Return Pairing + Echo + Briefing synthesis** | `4c2d9e2` | `agents/delta/`, `agents/echo/`, `agents/specialist_report.py`, Oak Street typed `ingest_report` + `synthesize_briefing` + `dispatch_briefing` |
| **3+** | **Configurable return-window modes** | `f376c38` | `RETURN_WINDOW_MODE=fixed\|range`; `resolve_return_windows()` |
| **4** | **Lodging Price Intelligence (shared brain)** | `8431513` | `intel/lodging/{seasons,scoring,baseline,storage,service}` + providers (`MockLodgingProvider`, `AirDnaProvider` STUB, `InsideAirbnbProvider` STUB); SQLite tables `lodging_baseline` + `lodging_history` |
| **5** | **India hostel intelligence** | `74c4fe9` | `agents/india/{report,scoring,providers,specialist}`; `VERDICT_KEYS` extended; Layer 4 brain integration |

---

## 2. Complete architecture tree (frozen state on disk)

```
coming-to-colombia-bot/                           ← repo (project identity rebranded 2026-05-29;
                                                    Windows folder rename pending — see
                                                    docs/REPO_RENAME_EXECUTION_REPORT.md)
│
├── main.py                                       ← entry point
├── requirements.txt
├── .env.example                                  ← documents every env knob
├── .gitignore                                    ← .env, .venv, logs/*, __pycache__
├── LICENSE                                       (MIT)
├── README.md
├── REPO_RENAME_MIGRATION.md                      ← rename + Option 1/2/3 plan
│
├── src/                                          ← LEGACY scanner (UNTOUCHED since L0)
│   ├── config.py                                 (region pack + env)
│   ├── region.py                                 (RegionPack model + loader)
│   ├── flight_fetcher.py                         (RapidAPI Skyscanner + placeholder)
│   ├── route_compare.py                          (direct vs positioning)
│   ├── deal_classifier.py                        (GREEN/YELLOW/RED on flight side)
│   ├── arrival_rules.py
│   ├── alert_formatter.py
│   ├── scheduler.py                              ← Layer 2 added _send kill switch
│   ├── storage.py                                (JSON logs)
│   ├── heartbeat_alerts.py                       (legacy RED-deal pulse)
│   └── telegram_handlers.py                      (legacy Telegram commands)
│
├── configs/                                      ← region packs (9 included)
│   ├── colombia.yaml                             ← the only "live" pack on this desk
│   └── { backpacker, brazil, europe, japan, luxury,
│         mexico, nomad, southeast_asia }.yaml    ← orphans pending Option 1/2/3
│
├── agents/                                       ← orchestration agents (L1+)
│   ├── __init__.py                               (version)
│   ├── config.py                                 ← DeskConfig — every L1..L4 knob
│   ├── logging_setup.py                          ← colombia_desk.* logger root
│   ├── specialist_report.py                      ← SpecialistReport + Status + VERDICT_KEYS
│   │
│   ├── oakstreet/                                ← L1 master orchestrator
│   │   ├── __init__.py
│   │   └── orchestrator.py                       (OakStreet, AlertEvent;
│   │                                              ingest_alert + ingest_report
│   │                                              + synthesize_briefing
│   │                                              + dispatch_briefing)
│   │
│   ├── delta/                                    ← L3 return-pairing specialist
│   │   ├── __init__.py
│   │   └── specialist.py                         (placeholder fetcher,
│   │                                              env-resolved windows)
│   │
│   ├── echo/                                     ← L3 price-context specialist
│   │   ├── __init__.py
│   │   └── specialist.py                         (lodging_signal still None — RESERVED)
│   │
│   └── india/                                    ← L5 hostel & budget specialist
│       ├── __init__.py
│       ├── report.py                             (AccommodationCategory, HostelOption,
│       │                                          HostelSignal, HostelReport)
│       ├── scoring.py                            (per-axis + ScoreBreakdown +
│       │                                          SCORE_WEIGHTS)
│       ├── providers.py                          (HostelProvider Protocol +
│       │                                          MockHostelProvider — only L5 provider)
│       └── specialist.py                         (India; consults Layer 4 brain)
│
├── intel/                                        ← pure-logic modules
│   ├── __init__.py
│   ├── heartbeat/                                ← L1
│   │   ├── decay_engine.py                       (stage + decision)
│   │   └── trigger_rules.py                      (color/route/price/departure)
│   ├── return_pairing/                           ← L3
│   │   ├── windows.py                            (canonical + range_windows +
│   │   │                                          resolve_return_windows)
│   │   └── pairing.py                            (estimate_pairing + protocol)
│   ├── price_context/                            ← L3 (Echo uses it)
│   │   └── classifier.py                         (PriceBand + classify_price_position)
│   └── lodging/                                  ← L4 the shared brain
│       ├── seasons.py                            (Gauss-Easter + Holy Week +
│       │                                          season matrix)
│       ├── scoring.py                            (LodgingColor + LodgingThresholds +
│       │                                          score_observation)
│       ├── baseline.py                           (compute_baseline — median)
│       ├── storage.py                            (LodgingStorage)
│       ├── service.py                            (LodgingIntelService + LodgingSignal)
│       └── providers/
│           ├── interface.py                      (LodgingObservation +
│           │                                      LodgingProvider Protocol +
│           │                                      ProviderResult + ProviderStatus)
│           ├── mock.py                           (MockLodgingProvider — drives tests)
│           ├── airdna.py                         (AirDnaProvider — STUB)
│           └── inside_airbnb.py                  (InsideAirbnbProvider — STUB)
│
├── links/                                        ← outbound seam (L1+)
│   ├── telegram_dispatcher.py                    (severity gate + dedupe + cooldown
│   │                                              + audit; L2 hardening)
│   ├── telegram_live_sender.py                   (LiveTelegramSender wrapping
│   │                                              telegram.Bot)
│   └── live_send_audit.py                        (append-only JSONL writer)
│
├── db/                                           ← orchestration state
│   ├── sqlite_manager.py                         (SqliteManager, DRY_RUN-aware)
│   └── schema.sql                                (5 tables — see §6)
│
├── tests/                                        ← 19 test files + DRY_RUN sims
│   ├── test_smoke.py                             (legacy — 14/14)
│   ├── dry_run_simulations.py                    (4 scenarios)
│   ├── test_heartbeat_decay.py                   (L1 — 14)
│   ├── test_oakstreet_skeleton.py                (L1 — 6)
│   ├── test_scanner_preservation.py              (L1 — 4)
│   ├── test_layer2_live_send.py                  (L2 — 21)
│   ├── test_layer3_return_pairing.py             (L3 — 13)
│   ├── test_layer3_echo.py                       (L3 — 13)
│   ├── test_layer3_briefing.py                   (L3 — 11)
│   ├── test_layer3_return_window_modes.py        (L3+ — 23)
│   ├── test_layer4_seasons.py                    (L4 — 11)
│   ├── test_layer4_scoring.py                    (L4 — 17)
│   ├── test_layer4_storage.py                    (L4 — 10)
│   ├── test_layer4_providers.py                  (L4 — 14)
│   ├── test_layer4_protections.py                (L4 — 11)
│   ├── test_layer5_india_scoring.py              (L5 — 24)
│   ├── test_layer5_india_classification.py       (L5 — 9)
│   ├── test_layer5_india_integration.py          (L5 — 11)
│   └── test_layer5_india_protections.py          (L5 — 9)
│
├── docs/
│   ├── LAYER_1_REFACTOR_REPORT.md
│   ├── LAYER_2_REFACTOR_REPORT.md
│   ├── LAYER_3_RETURN_PAIRING_ECHO_REPORT.md   (+ window-mode addendum)
│   ├── LAYER_4_LODGING_PRICE_INTELLIGENCE_REPORT.md
│   ├── LAYER_5_INDIA_HOSTEL_INTELLIGENCE_REPORT.md
│   ├── ARCHITECTURE_FREEZE_v1.md               ← this doc
│   ├── GITHUB_RELEASE_CHECKLIST.md             ← Phase A artifact
│   ├── CLAUDE_CODE_SKILL.md                    ← Phase A artifact
│   └── COUNTRY_BOT_CLONING_GUIDE.md            ← Phase A artifact
│
├── logs/                                       ← runtime (gitignored except .gitkeep)
├── skills/                                     ← legacy skill docs from L0
└── examples/                                   (empty)
```

---

## 3. Major agents

### Oak Street — master orchestrator (Layer 1+)

**File:** `agents/oakstreet/orchestrator.py`

The only place new code renders Telegram messages. Owns:
- `ingest_alert(event) -> HeartbeatDecision | None` — runs the
  Layer 1 heartbeat decay engine; persists to `deals` +
  `heartbeat_snapshots`; passes to the dispatcher.
- `ingest_specialist_report(specialist, payload, ...)` —
  untyped legacy path retained for back-compat.
- `ingest_report(report: SpecialistReport)` — typed Layer 3+ path
  Delta / Echo / India all use.
- `synthesize_briefing(deal_id, now)` — pulls every cached
  specialist report, renders DELTA + ECHO sections, falls through
  unknown specialists in deterministic order, appends an internal
  footer.
- `dispatch_briefing(deal_id, color, route_signature, now)` — pushes
  the briefing through the dispatcher with `kind="heartbeat"`.

**Boundary rules:** no external API calls; all outbound goes through
`links/telegram_dispatcher.py`. Persistence goes through
`db/sqlite_manager.py`.

### Delta — return-pairing specialist (Layer 3)

**File:** `agents/delta/specialist.py`

- Default fetcher: `placeholder_return_fetcher` (Layer 3) —
  deterministic, plausible but fictional. Status = `STUB`.
- Windows resolved at construction via
  `intel.return_pairing.resolve_return_windows()` — env-driven:
  `RETURN_WINDOW_MODE=fixed` (default, canonical 8-window list) or
  `RETURN_WINDOW_MODE=range` (every integer day across a range).
- Emits a `SpecialistReport` whose `payload.options[]` carries every
  window's `round_trip_total_usd` and the best one ends up in
  `verdict_input.round_trip_est_usd` + `best_return_window_days`.

### Echo — price-context specialist (Layer 3)

**File:** `agents/echo/specialist.py`

- Per-destination typical prices loaded from
  `src.region.active().destinations` when available; otherwise from a
  constructor override; otherwise the `DEFAULT_TYPICAL_PRICE_USD = 330`
  fallback.
- Classifies the observed fare into `great / good / normal / high`.
- **`lodging_signal` in `verdict_input` is RESERVED — always None.**
  The Echo ↔ `LodgingIntelService` wiring is intentionally deferred
  to a later layer per the long-running brief.

### India — hostel & budget-accommodation specialist (Layer 5)

**File:** `agents/india/specialist.py`

- Provider: `MockHostelProvider` only in Layer 5 — no HTTP, no
  scraping, no third-party APIs.
- Consults the Layer 4 lodging brain via `lodging_service.signal_for`;
  exception-safe (broken service → flag `lodging-signal-unavailable`).
- Scores each option on four axes; emits a `SpecialistReport` with
  `HostelReport` payload + four `verdict_input` keys.
- Status semantics:
  - `NO_DATA` — provider returned no options for the city.
  - `PARTIAL` — options scored but no lodging signal.
  - `STUB` — fully populated; provider still mock, hence not OK.

---

## 4. Lodging Price Intelligence (Layer 4 brain)

**Package:** `intel/lodging/`

Pure-logic + persistence + orchestration. Not an agent — it's a
service Echo and India consume.

- **Season matrix** (`seasons.py`) — Gauss-Easter, Holy Week as a
  PEAK override, per-spec multipliers PEAK 0.75 / HIGH 0.85 / MID 1.00
  / LOW 1.20.
- **Scoring** (`scoring.py`) — `weighted_pct = raw_pct * multiplier`;
  GREEN < 8, YELLOW 8–14.99, RED ≥ 15.
- **Baseline** (`baseline.py`) — median over lookback window; robust
  to scrape outliers.
- **Storage** (`storage.py`) — wraps `SqliteManager`; reads/writes
  `lodging_baseline` + `lodging_history`.
- **Service** (`service.py`) — `LodgingIntelService.signal_for(...)`
  returns a typed `LodgingSignal` (color + season + percentages +
  sample size) that India consumes.
- **Providers**:
  - `MockLodgingProvider` — deterministic, drives every test.
  - `AirDnaProvider` — STUB even when configured + opt-in.
  - `InsideAirbnbProvider` — STUB even when configured + opt-in.

---

## 5. Return pairing engine

**Package:** `intel/return_pairing/`

- `windows.py` — canonical
  `RETURN_WINDOWS_DAYS = (4, 7, 10, 14, 21, 30, 42, 50)`; resolver
  reads `RETURN_WINDOW_MODE` / `RETURN_WINDOWS_DAYS` /
  `RETURN_MIN_DAYS` / `RETURN_MAX_DAYS` / `RETURN_WINDOW_STEP_DAYS`
  from env. Range mode produces every integer from min to max
  (default: 4 through 60, 57 windows).
- `pairing.py` — pure engine; `estimate_pairing(...)` consumes a
  `ReturnLegFetcher` protocol (any `(origin, dest, return_date)
  -> Optional[float]`). Layer 3 ships only the placeholder fetcher;
  live fetching is reserved.

---

## 6. Scoring engines (summary)

| Engine | Module | Output | Used by |
|---|---|---|---|
| Heartbeat decay | `intel/heartbeat/decay_engine.py` | `HeartbeatDecision(should_emit, stage, reason)` | Oak Street |
| Return pairing | `intel/return_pairing/pairing.py` | `PairingEstimate(options, best_option)` | Delta |
| Price context | `intel/price_context/classifier.py` | `PricePosition(label, percent_of_typical)` | Echo |
| Lodging scoring | `intel/lodging/scoring.py` | `LodgingScore(color, weighted_pct_below, season, ...)` | LodgingIntelService → India |
| India per-axis | `agents/india/scoring.py` | `ScoreBreakdown(price, location, season, lodging_signal, overall)` | India |

Each engine is **pure** — no I/O, no clock reads — making them
hermetic-testable. Specialists wrap them, provide I/O, and emit
`SpecialistReport`s.

---

## 7. Provider framework

Three Protocol-typed provider tiers exist across the stack:

| Protocol | File | Status in freeze |
|---|---|---|
| `ReturnLegFetcher` | `intel/return_pairing/pairing.py` | `placeholder_return_fetcher` only (Layer 3 STUB) |
| `LodgingProvider` | `intel/lodging/providers/interface.py` | `MockLodgingProvider` only; AirDNA + Inside Airbnb implementations exist but ship `ProviderStatus.STUB` even with credentials + opt-in |
| `HostelProvider` | `agents/india/providers.py` | `MockHostelProvider` only |

Every Protocol carries a `name` field and a `fetch(...)` method. Every
provider returns a typed result (`ProviderResult.status` for lodging,
tuple for hostels). Real providers can be added in a later layer
without changing any consumer.

---

## 8. Briefing pipeline

```
AlertEvent
   │
   ▼
OakStreet.ingest_alert(event)
   │  ├── Layer 1 heartbeat decay engine — decides emit/suppress
   │  ├── persists to deals + heartbeat_snapshots tables
   │  └── dispatcher.send(text, kind=alert|heartbeat, color, ...)
   │
   ▼
[ Specialists analyze independently and feed Oak Street ]
   Delta(event)   ─► OakStreet.ingest_report(delta_report)
   Echo(event)    ─► OakStreet.ingest_report(echo_report)
   India(event)   ─► OakStreet.ingest_report(india_report)
                       │
                       └── persists to specialist_reports table,
                           caches per (deal_id, agent) in
                           _reports_cache
   │
   ▼
OakStreet.synthesize_briefing(deal_id, now)
   │
   ├── header (deal context: color, route, price, deal_id)
   ├── DELTA section (best round-trip + per-window prices)
   ├── ECHO section (label + percent of typical + reserved lodging)
   ├── India and other specialists (deterministic fall-through)
   └── footer (timestamp + DRY_RUN reminder)
   │
   ▼
OakStreet.dispatch_briefing(deal_id, color, route_signature)
   │
   ▼
TelegramDispatcher.send(text, kind="heartbeat", ...)
   │
   ├── 1. DRY_RUN → outbox + audit only
   ├── 2. Severity gate → only RED alerts / heartbeats / system pass
   ├── 3. Dedupe window (300s default) → same payload blocked
   ├── 4. Per-deal cooldown (60s default) → safety floor
   ├── 5. sender(chat, text) → fire-and-forget on PTB loop
   └── LiveSendAuditor — one JSONL row, 7 outcome types
```

---

## 9. Database schema summary

Single SQLite file at the path resolved by `DeskConfig.sqlite_path`
(default `db/colombia_desk.sqlite`). `SqliteManager` is the only
writer; `LodgingStorage` is the only writer to the lodging tables;
both go through the same connection.

| Table | Owner | Purpose | Indexes |
|---|---|---|---|
| `deals` | L1 — Oak Street | Per-deal heartbeat state | `idx_deals_status`, `idx_deals_first_alert_at` |
| `heartbeat_snapshots` | L1 — Oak Street | Append-only emission history | `idx_hb_deal_emitted` on `(deal_id, emitted_at)` |
| `specialist_reports` | L1 placeholder, L3 typed | Delta / Echo / India reports | `idx_specialist_lookup` on `(specialist, deal_id, report_at)` |
| `lodging_baseline` | L4 — LodgingStorage | Rolling typical price per `(city, neighborhood, beds)` | `idx_lodging_baseline_lookup` |
| `lodging_history` | L4 — LodgingStorage | Append-only raw observations | `idx_lodging_history_lookup` |

Schema is re-applied on every `SqliteManager.__init__` via
`CREATE TABLE IF NOT EXISTS` so an upgrade from L3 to L4+ does NOT
require a migration script.

---

## 10. Environment variable inventory

All knobs that affect runtime behavior. Defaults shown in
parentheses; bold = the local `.env` ships with this value at the
freeze.

| Var | Layer | Default | Notes |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | L0 | (none) | Required for live; harmless in DRY_RUN |
| `TELEGRAM_CHAT_ID` | L0 | (none) | Bare integer — leading colon will fail live |
| `REGION_PACK` | L0 | `colombia` | Picks `configs/<name>.yaml`; **colombia** at freeze |
| `FLIGHT_API_PROVIDER` | L0 | `rapidapi_skyscanner` | `placeholder` for hermetic; **placeholder** in local `.env` |
| `RAPIDAPI_KEY` / `RAPIDAPI_HOST` | L0 | (none / skyscanner host) | RapidAPI Skyscanner creds |
| `FLIGHT_API_KEY` / `FLIGHT_API_SECRET` | L0 | (none) | Amadeus creds |
| `TIMEZONE` | L0 | `America/Bogota` | ZoneInfo |
| `RED_HEARTBEAT_MINUTES` | L0 | `5` | Legacy RED-pulse cadence (scanner-side) |
| `RED_HEARTBEAT_DURATION_HOURS` | L0 | `2` | Legacy RED-pulse duration |
| `YELLOW_RECHECK_MINUTES` | L0 | `45` | Scan recheck cadence |
| `GREEN_SUMMARY_HOUR` | L0 | `9` | Daily digest hour |
| **`DRY_RUN`** | L1 | `false` | **`true`** at freeze. Dispatcher hermetic when true |
| **`SCANNER_TELEGRAM_ENABLED`** | L2 | `true` | **`false`** at freeze. When false, scanner direct-send is muted and routed via Oak Street |
| `LIVE_SEND_AUDIT_LOG` | L2 | `logs/colombia_desk_live_sends.jsonl` | JSONL audit file |
| `LIVE_SEND_COOLDOWN_SECONDS` | L2 | `60` | Per-deal safety floor |
| `LOG_LEVEL` | L1 | `INFO` | colombia_desk.* logger level |
| `RETURN_WINDOW_MODE` | L3+ | `fixed` | `fixed` or `range` |
| `RETURN_WINDOWS_DAYS` | L3+ | unset → canonical | Fixed-mode override (e.g. `4,7,10,14`) |
| `RETURN_MIN_DAYS` / `RETURN_MAX_DAYS` / `RETURN_WINDOW_STEP_DAYS` | L3+ | `4` / `60` / `1` | Range-mode bounds (default → 57 windows) |
| `LODGING_INTEL_ENABLED` | L4 | `true` | Master switch for the lodging brain |
| `AIRDNA_API_KEY` | L4 | (none) | Provider remains STUB even when set |
| `INSIDE_AIRBNB_LOCAL_PATH` | L4 | `/data/insideairbnb` | Provider remains STUB even when set |
| `LODGING_YELLOW_THRESHOLD` | L4 | `8` | pct below typical (weighted) |
| `LODGING_RED_THRESHOLD` | L4 | `15` | pct below typical (weighted) |
| `LODGING_SEASON_WEIGHTING` | L4 | `true` | When false, raw pct drives the color |
| `LODGING_BASELINE_LOOKBACK_DAYS` | L4 | `90` | Baseline aggregation window |

**33 documented env knobs.** Every one has a documented default in
`.env.example`. `agents/config.py` reads every one with the matching
default applied when the env is silent.

---

## 11. SpecialistReport schema (frozen surface)

`agents/specialist_report.py`

```
SpecialistReport
├── agent          str
├── status         Status (OK | PARTIAL | NO_DATA | STUB | ERROR)
├── confidence     float in [0, 1]
├── deal_id        Optional[str]
├── observed_at    datetime
├── payload        dict (agent-specific)
├── flags          tuple[str, ...]
└── verdict_input  dict — keys must be in VERDICT_KEYS

VERDICT_KEYS (frozen at freeze):
  Delta:    round_trip_est_usd, best_return_window_days
  Echo:     price_position_label, price_position_pct, lodging_signal (reserved)
  India:    best_hostel_score, best_hostel_category,
            best_hostel_price_usd, hostel_options_count
```

`__post_init__` rejects unknown verdict keys at construction. Future
specialists must extend `VERDICT_KEYS` deliberately.

---

## 12. Test totals at freeze

| Layer | Suites | Tests passing |
|---|---|---|
| L1 | heartbeat_decay, oakstreet_skeleton, scanner_preservation | 24 |
| L2 | layer2_live_send | 21 |
| L3 | layer3_{return_pairing, echo, briefing, return_window_modes} | 60 |
| L4 | layer4_{seasons, scoring, storage, providers, protections} | 63 |
| L5 | layer5_india_{scoring, classification, integration, protections} | 53 |
| Legacy | smoke | 14 |
| **Total** | **19 suites** | **235** |
| Plus | dry_run_simulations.py | 4 scenarios complete |

---

## 13. Runtime invariants at freeze

These are the load-bearing safety properties every later layer must
preserve. Each is regression-tested by name:

- **DRY_RUN safety** — when `DRY_RUN=true`, every `dispatcher.send`
  records `outcome="dry_run"`; sender callable is never invoked.
- **Severity gate** — only RED initial alerts, heartbeats, and system
  messages can reach the wire; YELLOW/GREEN alerts and digests are
  gated out.
- **Dedupe + cooldown** — identical payloads within 300s suppressed;
  per-deal cooldown 60s default.
- **Heartbeat suppression** — material-trigger heartbeats respect
  stage interval; max silence > 12h forces a keepalive; zombie mute
  is absolute (60h+ deal cannot resurrect even on $100 price drop).
- **Scanner kill switch** — `SCANNER_TELEGRAM_ENABLED=false` routes
  scanner sends through Oak Street; `=true` preserves legacy direct
  send bit-for-bit.
- **Audit log** — every dispatcher decision (sent / dry_run /
  suppressed_gate / suppressed_dedupe / suppressed_cooldown /
  no_sender / send_error) produces one JSONL row.
- **Schema strictness** — `SpecialistReport` rejects unknown
  `verdict_input` keys at construction.
- **STUB safety contracts** — `AirDnaProvider`,
  `InsideAirbnbProvider`, `MockHostelProvider`, and the Delta
  placeholder fetcher all keep the wire path closed even when
  configured/opted-in.

---

**End of freeze. No layer ahead has authorization to violate any of these properties.**
