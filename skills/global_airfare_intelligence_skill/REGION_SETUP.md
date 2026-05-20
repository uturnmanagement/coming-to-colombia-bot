# REGION_SETUP — region pack schema reference

A **region pack** is a single YAML file in `configs/` that fully
describes one airfare market. The engine reads it and nothing else for
geography — origin, destinations, gateways, thresholds, and rules are all
data. Select the active pack with `REGION_PACK` in `.env`.

## Full schema

```yaml
region:
  name: Colombia                    # display name, used in messages
  slug: colombia                    # short id (usually the filename)
  description: One-line summary.

origin:
  primary: BWI                      # origin airport IATA code
  label: Baltimore/Washington       # human label for the origin

destinations:                       # one entry per tracked destination
  BOG:
    city: "Bogotá"                  # display city name
    typical_price_usd: 330          # baseline fare — the "is this low?" anchor
  MDE:
    city: "Medellín"
    typical_price_usd: 350
    arrival_rules:                  # OPTIONAL — per-destination timing
      preferred_start: 10           # hour: start of the preferred window
      preferred_end: 15             # hour: end of the preferred window
      late_night_start: 21          # hour: late-night arrivals penalized

gateways:                           # US/region hub codes -> city names
  MIA: "Miami"
  JFK: "New York JFK"

positioning:
  min_savings_usd: 100              # positioning must beat direct by >= this
  max_layover_hours: 12             # reject connections longer than this
  preferred_gateways:               # ranked gateways per destination
    BOG: [MIA, FLL, JFK]
    MDE: [MIA, FLL]

thresholds:
  red_min_savings_usd: 150          # effective savings >= this -> RED
  yellow_min_savings_usd: 75        # effective savings >= this -> YELLOW

scan:
  days_ahead: 21                    # how far out to search fares

preferred_airlines: [Avianca, LATAM]   # optional, informational
budget_label: standard                 # standard | budget | luxury
```

## Field notes

- **`typical_price_usd`** anchors the value-savings calculation: a fare
  far below it is a deal even with no positioning gain. Set it from real
  observed averages for the route.
- **`arrival_rules`** are optional and per-destination. A destination
  with arrival rules whose flight lands late-night can never be RED — it
  is capped at YELLOW with a warning. Use it for airports far from the
  city or with poor late-night transport.
- **`preferred_gateways`** lists, per destination, which gateways to try
  for the positioning leg. Omit a destination to fall back to all
  gateways.
- **`thresholds`** are per-pack on purpose — a backpacker pack fires on
  $50, a luxury pack on $1,200.
- **`scan.days_ahead`** trades freshness for quota — longer-haul markets
  usually search further out.

## Validation

`python tests/test_smoke.py` runs `test_all_region_packs_parse`, which
loads every `configs/*.yaml` and checks it has an origin, destinations,
and gateways. Add your pack, run the suite, and it is verified.

## Telegram commands

Per-destination commands are generated from `city` (accents stripped) and
the destination code — `"Bogotá"` → `/bogota` and `/bog`. No handler code
changes are needed when you add or change destinations.
