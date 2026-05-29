# Coming to Colombia Bot

The **Coming to Colombia Bot** is a Telegram airfare-and-intelligence
desk for travelers heading from the US to Colombia. Under the hood it
runs a **config-driven worldwide airfare framework** — point it at any
origin airport and destination region via a single YAML region pack,
and it tracks cheap one-way flights, compares direct routes against
gateway-positioning routes, grades every deal **GREEN / YELLOW / RED**,
and pushes alerts to a Telegram channel.

> Evolved from a verified, live BWI → Colombia deployment (live
> Skyscanner fares, positioning engine, urgency scoring, async retry —
> all confirmed in production). The active desk identity is
> **Coming to Colombia Desk**; the live region pack is
> `configs/colombia.yaml`. The other 8 region packs ship as a reusable
> framework for future country desks.

---

## Why a framework

The same engine serves any market — only the region pack changes:

| Market | Region pack |
|--------|-------------|
| USA → Colombia | `configs/colombia.yaml` |
| New York → Europe | `configs/europe.yaml` |
| LA → Southeast Asia | `configs/southeast_asia.yaml` |
| LA → Japan | `configs/japan.yaml` |
| Miami → Brazil | `configs/brazil.yaml` |
| Dallas → Mexico | `configs/mexico.yaml` |
| Backpacker hops | `configs/backpacker.yaml` |
| Premium-cabin deals | `configs/luxury.yaml` |
| Digital-nomad hubs | `configs/nomad.yaml` |

Nothing geographic is hardcoded — origin, destinations, gateways,
positioning rules, thresholds, and arrival-time rules are all data.

---

## How it works

1. For each destination in the active region pack, the scanner searches:
   - **Strategy A — Direct:** `origin → destination`
   - **Strategy B — Positioning:** `origin → gateway → destination`
2. It computes the positioning total, compares it to the direct fare,
   and calculates the savings.
3. It classifies the best option as a **GREEN / YELLOW / RED** deal.
4. It alerts a Telegram channel for YELLOW and RED deals, runs a 5-minute
   heartbeat on RED deals, and posts a daily digest.

### Deal colors

| Color | Meaning | Action |
|-------|---------|--------|
| 🟢 GREEN  | Normal / average | Logged; appears in the daily digest |
| 🟡 YELLOW | Strong deal | Telegram alert; rechecked each cycle |
| 🔴 RED    | Rare urgent deal | Immediate alert + heartbeat pings |

Thresholds are per-region-pack, so a backpacker pack fires on a $50 drop
while a luxury pack waits for $1,200.

---

## Parser architecture

`src/flight_fetcher.py` exposes one interface, three implementations:

- **PlaceholderFlightFetcher** — deterministic mock data, zero keys.
- **LiveFlightFetcher** — verified live connectors:
  - **RapidAPI Skyscanner** — `searchAirport` resolves airport codes to
    Skyscanner `skyId`/`entityId`; `searchFlights` returns itineraries
    parsed into normalized `FlightOffer` objects. The search is async
    server-side, so it retries the "blocked" state up to 3×.
  - **Amadeus** — OAuth2 client-credentials + Flight Offers Search.
- Every live call degrades gracefully: a failure logs a warning, serves
  placeholder data, and enters a cooldown — the bot never crashes.

### Airfare scan flow

```
region pack ─▶ for each destination ─▶ compare_routes()
                                         ├─ direct search
                                         └─ positioning (origin→gateway→dest)
                                       ─▶ classify (GREEN/YELLOW/RED)
                                       ─▶ arrival-time rules
                                       ─▶ alert + heartbeat + storage
```

### Async retry handling

RapidAPI `searchFlights` runs asynchronously: early calls return
`status: blocked`. The connector retries (3 attempts, 4 s apart) and a
40-minute response cache plus a post-failure cooldown keep quota usage
sane. See the skill doc `RETRY_HANDLING.md` and `QUOTA_MANAGEMENT.md`.

### Telegram polling loop

`python-telegram-bot` long-polls; the scheduler registers a recheck
scan, a RED heartbeat, and a daily digest on the JobQueue. A central
error handler labels conflicts and network blips and keeps polling.

### Positioning calculations

For each destination the engine prices `origin→gateway` and
`gateway→destination` (same day and next day), builds every valid
connection within the layover limit, and recommends positioning only
when it beats the direct fare by the pack's `min_savings_usd`.

### Quota management

Live API quota is finite. The framework protects it with a response
cache, a failure cooldown, and per-pack `scan.days_ahead`. For
continuous multi-region operation, use a paid API tier or stagger scans.

---

## Project structure

```
coming-to-colombia-bot/
├── main.py                  # entry point
├── src/                     # config-driven engine
│   ├── region.py            # region pack model + loader (the core)
│   ├── config.py            # env + region wiring
│   ├── flight_fetcher.py    # placeholder + live connectors
│   ├── route_compare.py     # direct vs positioning
│   ├── deal_classifier.py   # GREEN/YELLOW/RED
│   ├── arrival_rules.py     # generic arrival-time rules
│   ├── alert_formatter.py   # Telegram messages
│   ├── scheduler.py         # scan / heartbeat / digest jobs
│   ├── storage.py           # JSON logs + content dedupe
│   ├── heartbeat_alerts.py  # RED-deal heartbeat
│   └── telegram_handlers.py # dynamic per-region commands
├── configs/                 # region packs (9 included)
├── skills/                  # reusable Claude Code super skill
├── deployment/              # systemd templates
├── tests/                   # hermetic smoke suite
└── docs/  examples/  logs/
```

---

## Quick start

```powershell
cd coming-to-colombia-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # then fill in tokens + REGION_PACK
python tests\test_smoke.py           # verification suite
python main.py
```

Pick a market by setting `REGION_PACK` in `.env` (e.g. `japan`). See
`skills/global_airfare_intelligence_skill/QUICKSTART.md` (legacy skill
folder name; the contents are part of the Coming to Colombia Bot
super-skill).

---

## GitHub setup

```powershell
git init
git add -A
git commit -m "Initial Coming to Colombia Bot"
git remote add origin https://github.com/<you>/coming-to-colombia-bot.git
git branch -M main
git push -u origin main
```

`.env` and `logs/` are git-ignored.

---

## Deployment

Runs on any Linux VPS (Hostinger, AWS EC2, …) via systemd — one service
per region pack. See `deployment/` and the skill's `VPS_DEPLOYMENT.md`,
`HOSTINGER_DEPLOYMENT.md`, and `AWS_DEPLOYMENT.md`.

---

## The reusable super skill

`skills/global_airfare_intelligence_skill/` (folder name kept from the
framework's L0 origin; pending rename — see
`docs/REPO_RENAME_EXECUTION_REPORT.md`) is a Claude Code skill that
documents how to clone, configure, deploy, and monetize the Coming to
Colombia Bot — see `SKILL.md` for the index.

---

## Live deployment status

The framework's engine is proven in production: the BWI → BOG route
returned real Skyscanner itineraries (Delta, American, LATAM — live
fares), positioning comparisons computed correctly, urgency scoring
verified, and async retry handling confirmed. Full write-up in
`docs/LIVE_DEPLOYMENT_SUCCESS.md` (added in the documentation phase).

## License

MIT — see `LICENSE`.
