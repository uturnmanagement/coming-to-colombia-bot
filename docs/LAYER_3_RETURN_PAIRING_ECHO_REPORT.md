# Layer 3 — Return Pairing + Echo Specialist Foundation

**Branch:** `layer-3-return-pairing-echo-foundation`
**Date:** 2026-05-27
**Status:** Layer 3 complete. Awaiting approval before Layer 4 / deploy / push.

> Layer 3 ships *foundations*, not live data sources. Both specialists
> emit typed reports against a shared schema; Oak Street synthesizes
> a single internal briefing from them. No external HTTP, no Apify,
> no scraping. DRY_RUN stays true; SCANNER_TELEGRAM_ENABLED stays false.

---

## 1. Mission and scope

Stand up Colombia Desk's first specialist layer:

- **Delta** — return-pairing specialist. Couples each outbound deal
  with the canonical return-window set (4 / 7 / 10 / 14 / 21 / 30 /
  42 / 50 days) and produces a round-trip estimate per window.
- **Echo** — price-context specialist (lodging hook reserved).
  Classifies an observed price against the destination's typical
  band; emits a labeled position. The lodging slot is wired into
  the schema but explicitly inactive in Layer 3.
- **Shared `SpecialistReport` schema** — agent, status, confidence,
  payload, flags, verdict_input. Every future specialist (India,
  Juliet) plugs into this contract without renegotiation.
- **Oak Street briefing** — `ingest_report(...)` + `synthesize_briefing(deal_id)`
  + `dispatch_briefing(...)`. The briefing is rendered, passed
  through the Layer 2 dispatcher (severity gate, dedupe, cooldown,
  audit), and — under DRY_RUN — recorded but not sent.

Non-goals (per brief): no live sends, no lodging intelligence, no
Apify, no return-leg fetch, no Echo external HTTP, no VPS deploy, no
push, no repo rename, no Layer 4.

---

## 2. Architecture changes (Layer 3 additions vs Layer 2)

### New files (10)

```
agents/
├── specialist_report.py           SpecialistReport + Status + VERDICT_KEYS
├── delta/
│   ├── __init__.py
│   └── specialist.py              Delta(fetcher).analyze(event) -> SpecialistReport
└── echo/
    ├── __init__.py
    └── specialist.py              Echo(typical_prices).analyze(event)

intel/
├── return_pairing/
│   ├── __init__.py
│   ├── windows.py                 RETURN_WINDOWS_DAYS + generate_windows
│   └── pairing.py                 estimate_pairing + ReturnLegFetcher protocol
└── price_context/
    ├── __init__.py
    └── classifier.py              PriceBand + classify_price_position

tests/
├── test_layer3_return_pairing.py  13 tests
├── test_layer3_echo.py            13 tests
└── test_layer3_briefing.py        11 tests
```

### Modified files (2)

- `agents/oakstreet/orchestrator.py` — added typed `ingest_report`,
  per-deal in-memory `_reports_cache`, `synthesize_briefing(deal_id)`,
  `dispatch_briefing(...)`, and per-specialist section renderers.
  Existing `ingest_specialist_report` (untyped legacy path) kept for
  Layer 1 callers.
- `agents/oakstreet/__init__.py` — re-exports `SpecialistReport` and
  `Status` so `from agents.oakstreet import …` covers both the
  orchestrator and the report schema.

### Unmodified

- `src/` (scanner) — untouched. Scanner-preservation tests still 4/4.
- `links/telegram_dispatcher.py` — Layer 2 gate, dedupe, cooldown,
  audit all unchanged.
- `db/schema.sql` — the `specialist_reports` table from Layer 1 is
  what Delta + Echo write into. No schema migration.

---

## 3. SpecialistReport — the shared contract

```python
@dataclass(frozen=True)
class SpecialistReport:
    agent: str                         # "delta" | "echo" | future
    status: Status                     # OK | PARTIAL | NO_DATA | STUB | ERROR
    confidence: float                  # 0.0 .. 1.0
    deal_id: Optional[str]
    observed_at: datetime
    payload: dict[str, Any]            # specialist-specific
    flags: tuple[str, ...]
    verdict_input: dict[str, Any]      # keys must be in VERDICT_KEYS
```

`VERDICT_KEYS` is the *only* surface Oak Street consults to bias its
briefing. Layer 3 ships five:

| Key | Producer | Meaning |
|---|---|---|
| `round_trip_est_usd` | Delta | Best round-trip estimate across windows |
| `best_return_window_days` | Delta | The window that produced the best estimate |
| `price_position_label` | Echo | "great" / "good" / "normal" / "high" |
| `price_position_pct` | Echo | Observed price as % of typical |
| `lodging_signal` | Echo | Reserved for Layer 4 — always `None` in Layer 3 |

`__post_init__` rejects unknown verdict keys at construction time —
adding a new key requires editing `VERDICT_KEYS` first, which makes
schema drift impossible to ship by accident.

---

## 4. Return Pairing (Delta) — what it does

```
AlertEvent  ────►  Delta.analyze(event)
                       │
                       ▼
              intel.return_pairing.estimate_pairing(
                  origin, destination, depart, outbound_price,
                  fetcher, windows=RETURN_WINDOWS_DAYS,
              )
                       │
                       ▼
              PairingEstimate
                ├── 8 ReturnOption rows (one per window)
                ├── per-option round_trip_total_usd | None
                └── best_option
                       │
                       ▼
              SpecialistReport(agent="delta", ...)
                  payload.options = [...]
                  verdict_input  = {
                      round_trip_est_usd, best_return_window_days
                  }
                  flags = ("placeholder-fetcher", ...)
```

**Default fetcher is a placeholder.** Layer 3 uses
`placeholder_return_fetcher` — a deterministic heuristic that prices
returns from a base-by-origin table plus mild Dec/Jan seasonality.
The numbers are *plausible but fictional*. Status is therefore
`STUB` (not `OK`) and the `placeholder-fetcher` flag is always set.

When the fetcher returns `None` for every window, status degrades
to `NO_DATA`, confidence is 0, and `verdict_input` is empty —
Oak Street will then skip the section entirely.

---

## 5. Echo (price-context) — what it does

```
AlertEvent  ────►  Echo.analyze(event)
                       │
                       ▼
              destination = parse_route_tail(event.route_signature)
              typical     = typical_prices.get(destination) or
                            DEFAULT_TYPICAL_PRICE_USD
                       │
                       ▼
              classify_price_position(observed_usd, PriceBand(typical))
                       │
                       ▼
              SpecialistReport(agent="echo", ...)
                  payload = {label, percent_of_typical,
                             lodging_signal: None}
                  verdict_input = {
                      price_position_label,
                      price_position_pct,
                      lodging_signal: None,    # ← Layer 4 hook
                  }
                  flags = ("lodging-hook-reserved",)
```

Typical-price source priority:
1. Explicit `typical_prices` constructor arg (used by tests).
2. Active region pack — `src.region.active().destinations` (live
   path in `main.py`). Loads on first construction.
3. Fallback constant `DEFAULT_TYPICAL_PRICE_USD = 330.0`.

The `lodging_signal` slot is reserved at the schema level
(`VERDICT_KEYS`) AND at the payload level. Layer 4 attaches lodging
data without changing the schema or any other code outside Echo.

---

## 6. Oak Street ingestion + briefing

### `ingest_report(report)`

- Strict type check — `TypeError` on anything other than
  `SpecialistReport`.
- Persists to the existing `specialist_reports` table via
  `db.insert_specialist_report(specialist=report.agent, ...)`.
- Caches the latest report-per-agent in
  `_reports_cache[deal_id][agent]`.
- No Telegram side effects.

### `synthesize_briefing(deal_id, now=...)`

- Pulls the deal row + every cached report for the deal.
- Renders a header + a Delta section + an Echo section + sections
  for any unknown specialists in deterministic order + a footer.
- Returns `None` when no reports have been cached yet.

### `dispatch_briefing(deal_id, *, color, route_signature, now=...)`

- Calls `synthesize_briefing` and routes through
  `dispatcher.send(text, kind="heartbeat", ...)`.
- The dispatcher's Layer 2 rules apply: DRY_RUN suppresses the
  wire, severity gate (heartbeat kind passes), dedupe / cooldown,
  audit log records the outcome.
- Returns the rendered text for the operator to inspect even when
  the dispatcher suppressed the send.

`kind="heartbeat"` is deliberate: the heartbeat channel already has
the right cadence semantics (rate-limited, deal-scoped) for the
briefing's "one-voice" model. The severity gate's allow-list
explicitly admits heartbeats independent of color.

---

## 7. Test results

**Totals: 96/96 tests passing across all suites.**

| Suite | Result | Layer |
|---|---|---|
| `test_heartbeat_decay` | 14/14 | Layer 1 invariant |
| `test_scanner_preservation` | 4/4 | Layer 1 invariant |
| `test_oakstreet_skeleton` | 6/6 | Layer 1 invariant |
| `test_layer2_live_send` | 21/21 | Layer 2 invariant |
| `test_layer3_return_pairing` | **13/13** | **NEW** |
| `test_layer3_echo` | **13/13** | **NEW** |
| `test_layer3_briefing` | **11/11** | **NEW** |
| `test_smoke` (legacy) | 14/14 | Untouched |
| `dry_run_simulations` (4 scenarios) | all complete | Untouched |
| `main.py` import sanity | clean | — |

### Layer 3 invariant coverage

These tests specifically guard the Layer 1/2 protections **through**
the Layer 3 additions:

```
ok  test_heartbeat_suppression_intact_with_specialist_reports
ok  test_zombie_cutoff_intact_with_specialist_reports
ok  test_dispatch_briefing_dry_run_does_not_send_live
ok  test_dispatcher_audit_records_briefing_metadata
```

DRY_RUN, the dispatcher's severity gate, dedupe + cooldown, the
audit log, and the heartbeat decay engine are all still enforced
when a briefing is the payload.

---

## 8. Outstanding items for the operator

These were already pending and remain open:

- The eight non-Colombia region packs (Option 1/2/3 from
  `REPO_RENAME_MIGRATION.md` §2).
- Directory + GitHub repo rename to `coming-to-colombia-bot`.
- Flipping `DRY_RUN=false` — Layer 3 explicitly keeps it true.
- VPS deploy authorization (still deferred).

New Layer 3 surface that will need decisions before going live:

- **Live return-leg fetcher for Delta.** Today's placeholder is
  deterministic but fictional. Wiring Skyscanner/Amadeus for
  return legs is straightforward (the `ReturnLegFetcher` protocol
  is just `(origin, destination, return_date) -> Optional[float]`)
  but is Layer 4 work.
- **Typical-price band tightness for Echo.** The default
  thresholds (great ≤70%, good ≤85%, high >110%) are a starting
  point — adjust once we see what real fares look like over a few
  scans.

---

## 9. Recommended Layer 4 scope (proposal — no action)

The seams Layer 3 introduced point at three natural Layer 4 themes:

1. **Live Delta fetcher.** Plug Skyscanner/Amadeus into the
   `ReturnLegFetcher` protocol. Drop the `placeholder-fetcher` flag
   when a live fetcher is wired. Adds real return-leg data without
   touching the specialist contract or Oak Street.
2. **Echo lodging hook.** Activate the `lodging_signal` slot —
   pull from a placeholder lodging source, then a real one. The
   schema reservation is already in place.
3. **Audit-log analyzer.** A small CLI that summarizes
   `logs/colombia_desk_live_sends.jsonl` — sent vs gated vs
   deduped, by hour, by deal, by specialist contribution. Closes
   the observability loop the Layer 2 audit log opened.

Layer 5+: India, Juliet, return-pairing live in the briefing,
VPS deploy, repo rename, monetization.

---

**End of report. Layer 3 complete. No deploy. No push. No Layer 4.**

---

## Addendum (2026-05-27) — Configurable return-window modes

Layer 3 ships with a single canonical window list. This addendum
adds an env-driven resolver so operators can switch between the
canonical list and an exhaustive day-by-day range without code
changes. Default behavior is unchanged.

### Env surface

| Env var | Mode | Default | Notes |
|---|---|---|---|
| `RETURN_WINDOW_MODE` | both | `fixed` | `fixed` or `range` (case-insensitive). |
| `RETURN_WINDOWS_DAYS` | fixed | unset → canonical | Comma-separated positive integers, e.g. `4,7,10,14`. Whitespace OK. Empty/zero/negative entries rejected. |
| `RETURN_MIN_DAYS` | range | `4` | Inclusive lower bound; must be ≥ 1. |
| `RETURN_MAX_DAYS` | range | `60` | Inclusive upper bound; must be ≥ `RETURN_MIN_DAYS`. |
| `RETURN_WINDOW_STEP_DAYS` | range | `1` | Step ≥ 1. Endpoints inclusive when the step lands; otherwise stops at the largest value ≤ max. |

### New surface

- `intel.return_pairing.resolve_return_windows(env=None)` — picks the
  active tuple from environment (or an injected mapping for tests).
- `intel.return_pairing.range_windows(min_days, max_days, step=1)` —
  pure date math. Validates every input.
- `intel.return_pairing.parse_fixed_list(raw)` — parses
  `RETURN_WINDOWS_DAYS`. Skips empty entries, rejects non-integers
  / non-positives, rejects empty result.
- `intel.return_pairing.ReturnWindowMode` — enum, `FIXED` / `RANGE`.

### Delta integration

`Delta.windows` now resolves at construction (via
`resolve_return_windows()`) unless an explicit `windows=` is passed
to the constructor. A per-call `analyze(event, windows=...)` override
takes precedence over the construction-bound list. The env read
happens **once** at construction so a long-running process cannot
drift mid-loop if the env changes underneath it.

### Test coverage

`tests/test_layer3_return_window_modes.py` — **23 tests**:

- Default and fixed-mode resolution paths (canonical, env override,
  whitespace tolerance, case-insensitive mode token).
- Range-mode resolution including the explicit acceptance case
  `RETURN_WINDOW_MODE=range, MIN=4, MAX=60, STEP=1` producing every
  integer from 4 through 60 inclusive (57 windows).
- Step != 1 (every-other-day mode); step that doesn't land on max.
- Validation: bad mode, bad min, bad min/max ordering, bad step,
  non-integer fixed entry, non-positive fixed entry, empty fixed list.
- Delta construction picks up resolved windows; explicit constructor
  override; per-call `analyze()` override; env-driven range mode
  produces 57 options in the report payload.

### Out of scope for this enhancement

The new modes are purely for window selection. Delta still uses the
placeholder return-leg fetcher; switching to live fetch (Skyscanner /
Amadeus) remains Layer 4 work. DRY_RUN and SCANNER_TELEGRAM_ENABLED
remain unchanged. No deploy. No push.
