# SYSTEM_ARCHITECTURE

## Design principle

**Config over code.** One engine; every market is a YAML region pack.
The active pack is loaded once at startup and held as the process-wide
"active region" (`src/region.py`), so every module reads geography from
data — nothing about Colombia, BWI, or any destination is hardcoded.

## Module map

| Module | Responsibility |
|--------|----------------|
| `region.py` | Region pack model + loader; the active-region singleton |
| `config.py` | Loads `.env`, loads + activates the region pack |
| `flight_fetcher.py` | `FlightOffer` model; placeholder + live connectors |
| `route_compare.py` | Direct vs gateway-positioning comparison |
| `arrival_rules.py` | Generic per-destination arrival-time scoring |
| `deal_classifier.py` | GREEN / YELLOW / RED + urgency score |
| `alert_formatter.py` | Telegram HTML message formatting |
| `scheduler.py` | Scan, heartbeat, and daily-digest jobs |
| `storage.py` | JSON logs + content-based alert dedupe |
| `heartbeat_alerts.py` | RED-deal heartbeat manager |
| `telegram_handlers.py` | Static + region-generated commands |
| `main.py` | Wires everything; runs long polling |

## Data flow

```
.env ─▶ load_config() ─▶ load_region_pack() ─▶ region.set_active()
                                                      │
main.py builds: fetcher, storage, heartbeat, Telegram Application
                                                      │
scheduler jobs ──▶ run_full_scan()
                     └─ for each destination in the region pack:
                          compare_routes(fetcher, dest, config, day)
                            ├─ direct:      origin → destination
                            └─ positioning: origin → gateway → destination
                          classify_route()
                            ├─ effective savings vs thresholds
                            └─ arrival rules (late-night cap)
                     ──▶ GREEN: log · YELLOW/RED: alert · RED: heartbeat
```

## Dependency layering

Pure modules (no `telegram` import) — `region`, `config`,
`flight_fetcher`, `route_compare`, `arrival_rules`, `deal_classifier`,
`alert_formatter`, `storage`, `heartbeat_alerts`, `scheduler`. Only
`telegram_handlers` and `main` import `telegram`. This keeps the whole
engine unit-testable without the Telegram dependency.

## The flight fetcher

`FlightFetcher` is the interface. `get_fetcher(config)` returns:

- `PlaceholderFlightFetcher` — deterministic mock data (no keys).
- `LiveFlightFetcher` — RapidAPI Skyscanner (verified) or Amadeus, with
  a response cache, a post-failure cooldown, and an automatic fallback
  to placeholder data on any error.

The live connector is **verified and stable** — extend it, do not
rebuild it.

## Resilience

- Graceful fallback: missing key or API failure → placeholder data.
- Async retry: RapidAPI `searchFlights` "blocked" → up to 3 retries.
- Central error handler: conflicts and network blips are logged, polling
  continues.
- Content-based dedupe: a deal is alerted at most once per 12 h.
- Heartbeat safety cap: RED pings stop after 24 h regardless.

## Scaling to many markets

One process serves one region pack. To cover several markets, run one
service per pack (separate `.env` with a different `REGION_PACK`, a
separate bot token, a separate `logs/` dir). See `VPS_DEPLOYMENT.md`.
