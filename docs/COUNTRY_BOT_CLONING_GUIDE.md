# Country Bot Cloning Guide — Replicating the Colombia Desk

**Companion to:** `docs/CLAUDE_CODE_SKILL.md` (pattern) and
`docs/ARCHITECTURE_FREEZE_v1.md` (frozen reference)
**Authoring date:** 2026-05-28
**Scope:** how to spin up a new country / region / city desk on the
Layer 1–5 architecture.

> This guide is concrete and actionable. Where multiple cloning
> modes exist (per `CLAUDE_CODE_SKILL.md` §7), each section here
> picks one mode and walks through the literal steps. Promote to a
> different mode later if traffic or specialization demands it.

---

## 0. Decision flow before you start

```
Where does the destination sit?
│
├── Whole country / multi-country region        → Mode A (fork)
├── Closely related to Colombia (Andean / CA)   → Mode C (region pack)
├── Single city inside an existing desk          → Region-pack restriction
└── Three or more desks already running          → Mode B (shared core)
```

The Mode-A fork is the default below — it produces the cleanest
mental model and is the easiest to reason about. The shorter recipes
at the end cover Mode C and city-level desks.

---

## 1. Central America (multi-country regional desk)

**Mode:** A — fork
**Target name:** `central_america_desk` (project), `@central_america_bot` (Telegram)
**Origin airport profile:** US gateway-anchored, mid-Atlantic friendly

### Step 1. Clone the repo

```powershell
cd C:\Users\uturn
git clone <colombia-desk-remote-url> central_america_desk
cd central_america_desk
git remote rename origin upstream
git remote add origin <new-remote-url>
git checkout -b layer-0-region-pack-central-america
```

### Step 2. Author the region pack

Create `configs/central_america.yaml`. Use `configs/colombia.yaml` as
the literal template; replace the geography fields. Reference:
`src/region.py` for the pack schema.

```yaml
region:
  name: Central America
  slug: central_america
  description: Cheap one-way flights from the US to Central America.

origin:
  primary: BWI
  label: Baltimore/Washington

destinations:
  SJO: { city: "San José", typical_price_usd: 320 }
  PTY: { city: "Panama City", typical_price_usd: 290 }
  GUA: { city: "Guatemala City", typical_price_usd: 380 }
  SAL: { city: "San Salvador", typical_price_usd: 400 }
  MGA: { city: "Managua", typical_price_usd: 430 }
  TGU: { city: "Tegucigalpa", typical_price_usd: 460 }
  BZE: { city: "Belize City", typical_price_usd: 510 }

gateways:
  MIA: "Miami"
  FLL: "Fort Lauderdale"
  IAH: "Houston"
  JFK: "New York JFK"
  ATL: "Atlanta"
  MCO: "Orlando"

positioning:
  min_savings_usd: 100
  max_layover_hours: 12
  preferred_gateways:
    SJO: [MIA, FLL, IAH, ATL]
    PTY: [MIA, FLL, IAH, JFK]
    GUA: [MIA, IAH, ATL]
    SAL: [MIA, IAH]
    MGA: [MIA, FLL]
    TGU: [MIA]
    BZE: [MIA]

thresholds:
  red_min_savings_usd: 150
  yellow_min_savings_usd: 75

scan:
  days_ahead: 21

preferred_airlines: [Copa, Avianca, United, Spirit, American, Delta]
budget_label: standard
```

### Step 3. Re-tune the lodging brain (Layer 4)

Open `intel/lodging/seasons.py`. Colombia's matrix puts LOW seasons
in Apr–May and Sep–early-Dec; Central America's seasonality is
**different** (rainy May–Nov, dry Dec–Apr — but with PEAK over
Christmas + Holy Week + spring-break overlap). Author a parallel
`central_america_seasons` matrix if behaviors diverge, or override
via the `LODGING_SEASON_WEIGHTING=false` env knob until you have a
baseline.

Edit decisions to make per desk:
- Holy Week is still PEAK (overrides everything) — keep Gauss-Easter.
- Recommended starting matrix for Central America:
  - PEAK: Dec 15 – Jan 5, Holy Week (`0.75x`)
  - HIGH: Jan 6 – Apr 14 (dry season) (`0.85x`)
  - MID: Apr 15 – May 31 (transition) (`1.00x`)
  - LOW: Jun 1 – Nov 30 (rainy) (`1.20x`)
  - PEAK: Dec 1 – Dec 14 (early holiday creep) — optional refinement
- Confirm by writing fresh tests in `tests/test_layer4_seasons.py`
  that cover the new boundaries.

### Step 4. Re-seed India's mock provider (Layer 5)

Open `agents/india/providers.py`. Replace the `_MOCK_OPTIONS_BY_CITY`
seeds for BOG / MDE / CTG with seeds for the new destinations:

```python
_MOCK_OPTIONS_BY_CITY = {
    "SJO": (...),
    "PTY": (...),
    "GUA": (...),
    ...
}
```

Each city should seed at least one option per category
(HOSTEL_DORM / HOSTEL_PRIVATE_ROOM / BUDGET_HOTEL / GUEST_HOUSE) so
India can demonstrate per-category coverage in tests. Adjust
`TYPICAL_PRICE_USD_BY_CATEGORY` in `agents/india/scoring.py` if
Central American hostels run materially cheaper / more expensive
than Colombia.

### Step 5. Update `.env.example`

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
REGION_PACK=central_america
TIMEZONE=America/Costa_Rica
# Carry over every other knob from Colombia's .env.example.
```

### Step 6. Update tests

For each Layer 4 / Layer 5 test that hard-codes a city (`BOG`,
`MDE`, `CTG`), substitute the new seeds. The structural assertions
(weights sum to 1.0, categories enumerate to the four spec values,
etc.) are unchanged.

### Step 7. Update DeskConfig defaults

`agents/config.py` reads from env. Adjust *defaults* if the desk's
operational cadence differs (e.g. `GREEN_SUMMARY_HOUR=8` for a
desk centered on US Central time).

### Step 8. Verify

```
./.venv/Scripts/python.exe tests/test_smoke.py
./.venv/Scripts/python.exe tests/test_layer4_seasons.py   # rewritten
./.venv/Scripts/python.exe tests/test_layer5_india_classification.py
# ... and the full suite
```

Expect **all suites to pass** before any deploy.

### Step 9. Identity

| Surface | Old | New |
|---|---|---|
| Local dir | `colombia_desk` | `central_america_desk` |
| GitHub repo | `coming-to-colombia-bot` | `central-america-desk-bot` |
| Telegram bot identity | `coming_to_colombia_bot` | new BotFather bot |
| Internal orchestration | "Colombia Desk" | "Central America Desk" |
| Internal master orchestrator | "Oak Street" | choose a new street name (e.g. "Pine Street") |

---

## 2. Costa Rica (single-country focus)

**Mode:** A — fork (independent desk)
**Why a separate fork from Central America:** Costa Rica has unique
tourism dynamics (eco-tourism, distinct dry/wet season boundaries,
Pacific vs Caribbean coast pricing). A focused desk produces
sharper signals than a CA-wide one.

### Differences vs Central America fork

1. **Region pack — one country only:**
   ```yaml
   region:
     name: Costa Rica
     slug: costa_rica
   destinations:
     SJO: { city: "San José",        typical_price_usd: 320 }
     LIR: { city: "Liberia (Guanacaste)", typical_price_usd: 360 }
     PVT: { city: "Pavones (closest: SJO)", typical_price_usd: 320 }
   ```
2. **Season matrix:**
   - PEAK: Dec 15 – Apr 15 (dry season + Christmas + Holy Week)
   - LOW: May 1 – Nov 30 (green season — true LOW window)
   - MID: Apr 16 – Apr 30 (transition)
   - Holy Week overlays PEAK regardless.
3. **India seeds:** Costa Rica is hostel-rich; seed dorms,
   private rooms, and guesthouses across SJO + LIR. Avoid Budget
   Hotel seeds in beach towns where hostels dominate.
4. **Per-category typical USD:** raise BUDGET_HOTEL anchor to ~$70
   if your sample suggests it; HOSTEL_DORM stays ~$15–20.

### Step list

Identical to Central America §1 Step 1–9; substitute the values
above and rename to `costa_rica_desk` / `@costa_rica_bot`.

---

## 3. Panama (single-country focus)

**Mode:** A — fork
**Why a separate fork:** Panama is an airline hub (Copa) with its
own positioning math; the gateway concept inverts because Panama City
itself is a gateway for the region.

### Differences vs Central America

1. **Region pack — Panama-only:**
   ```yaml
   region:
     name: Panama
     slug: panama
   destinations:
     PTY: { city: "Panama City",  typical_price_usd: 290 }
     BOC: { city: "Bocas del Toro", typical_price_usd: 350 }
     DAV: { city: "David",         typical_price_usd: 330 }
   gateways:
     MIA: "Miami"
     IAH: "Houston"
     # Notably: PTY itself can be a positioning gateway for OTHER
     # destinations in a future region; for the Panama desk, PTY is
     # the primary destination.
   ```
2. **Season matrix:** similar to Costa Rica — dry Dec–Apr, wet
   May–Nov, but Bocas del Toro has microclimate exceptions worth
   noting in flags rather than scoring.
3. **India seeds:** Panama City has strong hostel + guesthouse
   coverage; Bocas is hostel-heavy. Seed accordingly.

### Step list

Same Mode A workflow. Adjust the operational cadence — Panama's UTC
offset matches Colombia (UTC-5), so `TIMEZONE=America/Panama` keeps
the digest hour aligned.

---

## 4. Medellín (single-city desk inside Colombia)

**Mode:** Region-pack restriction (lightest touch — no fork needed)
**Why not a fork:** Medellín is already a destination in the
Colombia region pack. A "Medellín desk" is a *channel restriction*,
not an architecture change.

### Steps

1. Author `configs/medellin.yaml`:
   ```yaml
   region:
     name: Medellín
     slug: medellin
     description: BWI -> MDE only — single-city focused.
   origin:
     primary: BWI
   destinations:
     MDE:
       city: "Medellín"
       typical_price_usd: 350
       arrival_rules:
         preferred_start: 10
         preferred_end: 15
         late_night_start: 21
   gateways:
     MIA: "Miami"
     FLL: "Fort Lauderdale"
     JFK: "New York JFK"
     EWR: "Newark"
     ATL: "Atlanta"
     MCO: "Orlando"
   positioning:
     min_savings_usd: 80
     max_layover_hours: 12
     preferred_gateways:
       MDE: [MIA, FLL, JFK, EWR, ATL, MCO]
   thresholds:
     red_min_savings_usd: 120
     yellow_min_savings_usd: 60
   scan:
     days_ahead: 21
   preferred_airlines: [Avianca, LATAM, American, JetBlue, Delta]
   budget_label: standard
   ```
2. Set `REGION_PACK=medellin` in a per-channel `.env`.
3. Configure a **separate Telegram bot** via BotFather:
   `coming_to_medellin_bot` / `@medellin_deals_bot` (or similar).
4. Configure a separate SQLite path so the Medellín desk's heartbeat
   state doesn't collide with the Colombia desk's:
   `COLOMBIA_DESK_DB=db/medellin_desk.sqlite`.
5. Re-seed India for MDE specifically if you want richer per-
   neighborhood signals (Poblado vs Laureles vs Envigado).
6. Run as a **separate process** with the same codebase — different
   `.env`, different bot identity.

This gives you a fully independent Medellín channel with zero code
divergence and minimal operational overhead. Promote to a fork if
you later want Medellín-specific scoring weights.

---

## 5. Cartagena (single-city desk inside Colombia)

**Mode:** Region-pack restriction (same as Medellín)

### Differences vs Medellín

1. **Region pack** — `configs/cartagena.yaml`:
   ```yaml
   destinations:
     CTG:
       city: "Cartagena"
       typical_price_usd: 300
       arrival_rules:
         preferred_start: 9
         preferred_end: 17       # Caribbean coast — early arrivals also OK
   ```
2. **Season matrix override**: Cartagena pricing peaks Dec–Mar
   (dry season + beach tourism overlap) and again briefly in
   June–July (school holiday). Consider running
   `LODGING_SEASON_WEIGHTING=false` initially and re-tuning once
   you have a baseline, OR fork to ship a Cartagena-specific matrix.
3. **India seeds:** Getsemaní + Centro Histórico + Manga, all
   hostel-rich and walkable to the historic center. Per-category
   typical USD anchors trend higher than the rest of Colombia
   (BUDGET_HOTEL ~$65, GUEST_HOUSE ~$50).
4. **Bot identity:** `coming_to_cartagena_bot` /
   `@cartagena_deals_bot`. Separate process, separate DB path.

---

## 6. Future country desks — generalized recipe

For any new destination not covered above:

1. **Decide the mode** (use §0 decision flow).
2. **If Mode A (fork):** clone the repo, rename, swap the region
   pack, retune the lodging season matrix, reseed India, update
   `.env.example`, write fresh seasons/scoring/seeds tests,
   rebrand the agent (the master orchestrator's "Oak Street" name
   is part of the Colombia Desk identity — pick a new street name
   for the new desk: e.g. "Cedar Street" for Costa Rica, "Pine
   Street" for Central America, "Beech Street" for Panama).
3. **If Mode C (region pack):** author a new YAML, set
   `REGION_PACK=<name>` in a per-channel `.env`, run as a separate
   process pointing at a separate SQLite file.
4. **Always:**
   - Start with `DRY_RUN=true` and `SCANNER_TELEGRAM_ENABLED=false`.
   - Re-run the full test pass.
   - Verify the first 4 DRY_RUN simulation scenarios produce
     sensible output for the new geography.
   - Soft-launch by flipping `SCANNER_TELEGRAM_ENABLED=false` and
     watching `colombia_desk_live_sends.jsonl` (rename the audit
     path per desk).

---

## 7. What never changes across desks

These are the spine. Don't fork them — inherit them verbatim:

- The five-layer build order (L0 → L5).
- The agent taxonomy (Oak Street + Delta + Echo + India).
- The provider Protocol shape (`name` + `fetch(...)`).
- The dispatcher pipeline (DRY_RUN → severity gate → dedupe →
  cooldown → sender → audit).
- The SpecialistReport schema and `VERDICT_KEYS` strict-validation.
- The heartbeat decay engine, scoring formula, and zombie cutoff.
- The single-SQLite-file orchestration model.
- The mock-first / live-later contract for providers.

---

## 8. What always changes across desks

- The region pack (`configs/<country>.yaml`).
- The timezone (`TIMEZONE=America/<city>`).
- The Telegram bot identity (token + chat + BotFather brand).
- The lodging season matrix (Holy Week is universal; everything
  else is local).
- India's `_MOCK_OPTIONS_BY_CITY` seeds.
- The orchestrator nickname (Oak Street → ...).
- The audit-log filename (`colombia_desk_live_sends.jsonl` →
  `<country>_desk_live_sends.jsonl`).
- The SQLite file path (`COLOMBIA_DESK_DB`).

---

## 9. Hand-off to a future Claude Code session

If you (a future agent) are reading this to start a new desk:

1. Read `CLAUDE_CODE_SKILL.md` first — it's the pattern.
2. Read `ARCHITECTURE_FREEZE_v1.md` — it's the frozen state.
3. Read THIS file — it's the recipe.
4. Pick the mode for the operator's target destination.
5. Build in layer order — don't skip.
6. Stop at the layer boundary the operator names.
7. Never deploy / push without explicit operator approval.

---

**End of cloning guide. Five recipes (Central America, Costa Rica, Panama, Medellín, Cartagena) plus the generalized recipe for any future country desk.**
