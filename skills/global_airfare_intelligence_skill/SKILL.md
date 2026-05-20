---
name: global-airfare-intelligence
description: >
  Build, clone, configure, deploy, and monetize an OpsHub Global Airfare
  Intelligence System — a config-driven Telegram airfare bot that tracks
  cheap one-way flights for ANY origin/destination market via a YAML
  region pack, compares direct vs gateway-positioning routes, grades
  deals GREEN/YELLOW/RED, and runs live on RapidAPI Skyscanner. TRIGGER
  when the user wants a worldwide/global airfare bot, wants to clone the
  airfare radar to a new country/region, or wants to deploy or monetize
  an airfare deal channel. Flights only.
---

# Global Airfare Intelligence — Super Skill

## Skill name

`global-airfare-intelligence`

## Mission

Turn the verified BWI → Colombia airfare bot into — and operate it as —
a **reusable worldwide airfare intelligence platform**. One config-driven
engine; every market (country, region, city group, travel style) is a
swappable YAML region pack. Clone it for any origin/destination, deploy
it to a VPS, and run paid airfare-alert channels on top of it.

## When to use this skill

- Building a global / multi-region airfare bot.
- Cloning the airfare radar to a new country, region, or city group.
- Adding or tuning a region pack (destinations, gateways, thresholds).
- Deploying to a Hostinger / AWS / Ubuntu VPS.
- Standing up Patreon / Telegram / Discord monetized airfare channels.

Do **not** use it for hotels, weather, safety, or currency features —
this platform is flights only.

## Inputs required

| Input | Source | Required |
|-------|--------|----------|
| `TELEGRAM_BOT_TOKEN` | @BotFather | Yes |
| `TELEGRAM_CHAT_ID` | `/chatid` command | Yes |
| `REGION_PACK` | a `configs/*.yaml` name | Yes (defaulted) |
| `RAPIDAPI_KEY` | RapidAPI Skyscanner subscription | For live fares |

Never hardcode tokens or keys — everything loads from `.env`.

## Core principles

- **Config over code.** Geography lives in region packs, never in `.py`.
- **Graceful fallback.** A missing key or API failure serves placeholder
  data; the bot never crashes.
- **One process, one region.** Run multiple region packs as separate
  services to cover multiple markets.
- **Verified connector.** The RapidAPI Skyscanner parser is proven —
  reuse it, do not rebuild it.

## Documentation index

This skill ships the following documents. Items marked ✅ are included in
this foundation build; ⏳ items arrive in the documentation phase.

| Doc | Purpose | Status |
|-----|---------|--------|
| `QUICKSTART.md` | Run the bot in 5 minutes | ✅ |
| `REGION_SETUP.md` | Region pack YAML schema reference | ✅ |
| `SYSTEM_ARCHITECTURE.md` | Modules + data flow | ✅ |
| `CLONE_NEW_COUNTRY_GUIDE.md` | Clone to a new market | ✅ |
| `AIRPORT_SETUP.md` | Choosing origins, gateways, codes | ⏳ |
| `TELEGRAM_SETUP.md` | Bot token + channel setup | ⏳ |
| `RAPIDAPI_SETUP.md` | Subscribing + key wiring | ⏳ |
| `POSITIONING_LOGIC.md` | How positioning is calculated | ⏳ |
| `URGENCY_SCORING.md` | The GREEN/YELLOW/RED model | ⏳ |
| `RETRY_HANDLING.md` | Async "blocked" retry handling | ⏳ |
| `QUOTA_MANAGEMENT.md` | Protecting API quota | ⏳ |
| `VPS_DEPLOYMENT.md` | Generic Linux VPS deployment | ⏳ |
| `HOSTINGER_DEPLOYMENT.md` | Hostinger-specific steps | ⏳ |
| `AWS_DEPLOYMENT.md` | AWS EC2 deployment | ⏳ |
| `TROUBLESHOOTING.md` | Common failures + fixes | ⏳ |
| `PATREON_MONETIZATION.md` | Patreon VIP airfare tiers | ⏳ |
| `DISCORD_MONETIZATION.md` | Discord airfare rooms | ⏳ |

## Maintenance commands

```bash
python tests/test_smoke.py                  # verify the build
python main.py                              # run locally
sudo systemctl restart airfare-intelligence # restart on a VPS
journalctl -u airfare-intelligence -f       # follow logs
```

## Guardrails

- No hardcoded tokens, keys, origins, or destinations.
- Do not rebuild the verified live connector / parser.
- Do not remove the graceful placeholder fallback.
- Flights only — no hotels, weather, safety, or currency.
