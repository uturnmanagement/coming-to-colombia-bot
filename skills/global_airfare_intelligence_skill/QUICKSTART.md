# QUICKSTART — run the bot in 5 minutes

## 1. Install

```bash
cd coming-to-colombia-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and set, at minimum:

```
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<see step 4>
REGION_PACK=colombia
```

Leave `RAPIDAPI_KEY` blank to start on **placeholder** (mock) data — the
bot runs fine and you can wire live fares later.

## 3. Verify

```bash
python tests/test_smoke.py
```

Expect every check to `PASS`. The suite is hermetic — no API calls.

## 4. Start + find your chat ID

```bash
python main.py
```

In Telegram, open your bot and send `/chatid`. Copy the number into
`TELEGRAM_CHAT_ID` in `.env`, then restart the bot so alerts land there.

## 5. Use it

| Command | Shows |
|---------|-------|
| `/start`, `/help` | Overview and command list |
| `/deals` | All destinations, latest scan |
| `/red`, `/yellow`, `/green` | Deals filtered by color |
| `/positioning` | Direct vs positioning comparison |
| `/<city>` | One destination in detail |
| `/status` | Region, data source, cadence |

Per-destination commands are generated from the region pack — load
`japan` and you get `/tokyo`, `/osaka`, … automatically.

## 6. Go live (optional)

Subscribe to the RapidAPI Skyscanner API, then in `.env`:

```
FLIGHT_API_PROVIDER=rapidapi_skyscanner
RAPIDAPI_KEY=<your key>
```

Restart. The bot now scans real fares; on any failure it falls back to
placeholder data automatically.

## Switch markets

Change one line in `.env` — `REGION_PACK=europe` — and restart. To run
several markets at once, deploy each as its own service (see
`VPS_DEPLOYMENT.md`).
