# CLONE_NEW_COUNTRY_GUIDE

How to point the framework at a brand-new market. No Python changes are
needed — you write one region pack and one `.env`.

## Example: clone for "Toronto → Thailand"

### 1. Create the region pack

Copy the closest existing pack and edit it:

```bash
cp configs/southeast_asia.yaml configs/thailand.yaml
```

Edit `configs/thailand.yaml`:

```yaml
region:
  name: Thailand
  slug: thailand
  description: Cheap one-way flights from Toronto to Thailand.

origin:
  primary: YYZ
  label: Toronto Pearson

destinations:
  BKK: { city: "Bangkok", typical_price_usd: 780 }
  HKT: { city: "Phuket", typical_price_usd: 860 }
  CNX: { city: "Chiang Mai", typical_price_usd: 840 }

gateways:
  YVR: "Vancouver"
  JFK: "New York JFK"
  ICN: "Seoul Incheon"
  DOH: "Doha"

positioning:
  min_savings_usd: 150
  max_layover_hours: 18
  preferred_gateways:
    BKK: [YVR, JFK, ICN, DOH]
    HKT: [ICN, DOH]
    CNX: [ICN, DOH]

thresholds:
  red_min_savings_usd: 250
  yellow_min_savings_usd: 130

scan:
  days_ahead: 35
```

See `REGION_SETUP.md` for every field.

### 2. Point `.env` at it

```
REGION_PACK=thailand
TIMEZONE=America/Toronto
```

### 3. Verify

```bash
python tests/test_smoke.py
```

`test_all_region_packs_parse` now also loads `thailand.yaml`. A typo in
the YAML fails here, before you ever start the bot.

### 4. (Optional) separate Telegram channel

For a dedicated channel, create a new bot with @BotFather, set its
`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, and the framework's commands
(`/bangkok`, `/phuket`, `/chiangmai`) are generated automatically.

### 5. Run

```bash
python main.py
```

## Checklist for any new market

- [ ] Pick the origin airport (IATA code) and a human label.
- [ ] List destinations with realistic `typical_price_usd` anchors.
- [ ] List gateway hubs that actually connect to those destinations.
- [ ] Map `preferred_gateways` per destination.
- [ ] Tune `thresholds` to the price band (budget vs luxury).
- [ ] Set `scan.days_ahead` (longer-haul → search further out).
- [ ] Add `arrival_rules` to any destination with a tricky airport.
- [ ] Run the smoke suite.
- [ ] Set `REGION_PACK` + `TIMEZONE` in `.env`.

## Running several markets at once

Each market is its own service: a separate checkout (or a shared one
with separate `.env` files), a separate bot token, a separate region
pack, and a separate systemd unit. See `VPS_DEPLOYMENT.md` for the
multi-region layout.

## What you never have to touch

`src/*.py` — the engine is fully config-driven. Cloning a market is a
YAML + `.env` task only.
