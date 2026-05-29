# Colombia Desk — Claude Code Skill Package

**Skill type:** layered-build pattern for country-specific travel-deal bots
**Reference implementation:** this repo at commit `74c4fe9` (Layer 1–5 frozen)
**Authoring date:** 2026-05-28

> This document describes the Colombia Desk as a **transferable
> pattern** — the same five-layer build sequence, the same agent
> taxonomy, the same provider-Protocol seams. Use it as the
> instruction set when starting a new country desk (Costa Rica desk,
> Panama desk, …) so the future architecture is born in this shape
> rather than retrofitted into it.

---

## 1. Project purpose

Build a Telegram bot that surfaces high-confidence travel deals for a
**single destination country / region**, combining:

- **Flight scanning** with positioning analysis
  (origin → gateway → destination)
- **Specialist orchestration** — multiple intelligence agents feed a
  single "voice" to the Telegram channel
- **Lodging price intelligence** that grades observed accommodation
  prices against season-weighted baselines
- **Budget-accommodation recommendation** (hostels, guest houses,
  budget hotels) tied into the lodging brain

The Colombia Desk is the first instance. Future desks follow the same
layered build; only data (region pack, season matrix tuning, hostel
seeds) changes.

---

## 2. Core architectural commitments

These are load-bearing — every layer enforces them and every clone
must inherit them. Violating any of these turns the desk into a
bespoke project rather than an instance of this pattern.

1. **One outbound seam.** Every Telegram message flows through one
   dispatcher (`links/telegram_dispatcher.py`). The dispatcher owns
   the severity gate, dedupe window, per-deal cooldown, and audit
   log. No agent ever calls `bot.send_message` directly.
2. **Pure-logic / orchestration split.** Pure intel lives under
   `intel/`. Agents that wrap I/O live under `agents/`. Pure modules
   never read clocks, env, or network; agents do all of that and
   feed pure inputs. This is what makes the engines trivially
   testable.
3. **Provider Protocol seams.** Every external data source sits
   behind a `Protocol`. A `Mock<X>Provider` drives every test; live
   implementations are added later via the same Protocol without
   changing consumers.
4. **DRY_RUN safety contract.** A single env knob (`DRY_RUN=true`)
   turns the dispatcher hermetic — no network calls, but every
   decision is still recorded on the outbox + audit log. CI, local
   dev, and "watch what would have happened" runs all go through
   this knob.
5. **Scanner kill switch.** The legacy scanner's direct
   Telegram path is gated by `SCANNER_TELEGRAM_ENABLED`. Migration
   from "scanner sends directly" → "Oak Street is the only voice"
   is a single boolean flip per machine.
6. **Typed specialist reports.** Specialists emit
   `SpecialistReport(agent, status, confidence, payload, flags,
   verdict_input)`. `verdict_input` keys must be in `VERDICT_KEYS`
   (rejected at construction). New specialists extend the
   vocabulary deliberately.
7. **Single SQLite file.** All orchestration state lives in one
   SQLite database. Tables are namespaced by domain (`deals`,
   `heartbeat_snapshots`, `specialist_reports`, `lodging_baseline`,
   `lodging_history`). Schema is re-applied on every connection
   open via `CREATE TABLE IF NOT EXISTS` — no migration scripts.

---

## 3. Layer sequence (build order)

| # | Layer | Mission | Hard exit criteria |
|---|---|---|---|
| **0** | Scanner foundation | Existing config-driven scanner ingests a region pack and emits deal events. | Region pack loads; placeholder fetcher runs; smoke suite green. |
| **1** | Infrastructure + heartbeat | Oak Street skeleton; shared logging; SQLite manager + base schema; Telegram dispatcher abstraction; DRY_RUN config; heartbeat decay engine + scanner preservation. | Heartbeat decay + Oak Street skeleton tests green; legacy scanner preserved bit-for-bit. |
| **2** | Live Telegram wiring | Live sender; dispatcher severity gate + dedupe + cooldown + audit; scanner kill switch. | Layer 2 live-send suite green; no live Telegram path reachable when DRY_RUN=true. |
| **3** | First specialist pair | Return-pairing engine (Delta) + price-context engine (Echo); `SpecialistReport` schema; Oak Street typed `ingest_report` + briefing synthesis. | Three Layer 3 suites green; Echo's `lodging_signal` reserved (None); briefing renders. |
| **3+** | Layer 3 enhancement | Configurable return-window modes (`fixed` / `range`). | Window-modes suite green; default behavior unchanged. |
| **4** | Lodging Price Intelligence (shared brain) | `intel/lodging/` — seasons, scoring, baseline, storage, providers, service; SQLite gains `lodging_baseline` + `lodging_history`. | Layer 4 suites green; real providers ship STUB even when configured; brain never touches dispatcher. |
| **5** | India hostel intelligence | `agents/india/` — four accommodation categories, per-axis scoring, MockHostelProvider, integration with Layer 4 brain. | Layer 5 suites green; India never touches dispatcher; Oak Street ingests typed India reports. |
| **6+** | Echo lodging wiring; live providers; dedicated INDIA briefing renderer; VPS deploy | Reserved. | Phase-A freeze blocks any Layer 6 work. |

**Build rule:** never skip a layer. Each layer's tests pin the
contracts the next layer must honor.

---

## 4. Repo structure (target for any new desk)

```
<country>_desk/
├── main.py                                       ← entry point
├── requirements.txt
├── .env.example                                  ← every knob documented
├── .gitignore                                    ← .env, .venv, logs/*, __pycache__
├── README.md
│
├── src/                                          ← scanner (region-pack driven)
│   ├── config.py
│   ├── region.py
│   ├── flight_fetcher.py
│   ├── route_compare.py
│   ├── deal_classifier.py
│   ├── arrival_rules.py
│   ├── alert_formatter.py
│   ├── scheduler.py                              ← kill-switch seam from L2
│   ├── storage.py                                ← JSON layer (preserved)
│   ├── heartbeat_alerts.py
│   └── telegram_handlers.py
│
├── configs/
│   └── <country>.yaml                            ← the region pack
│
├── agents/
│   ├── config.py                                 ← DeskConfig
│   ├── logging_setup.py
│   ├── specialist_report.py                      ← SpecialistReport + VERDICT_KEYS
│   ├── oakstreet/                                ← master orchestrator
│   ├── delta/                                    ← return-pairing specialist
│   ├── echo/                                     ← price-context specialist
│   └── india/                                    ← hostel & budget specialist
│
├── intel/
│   ├── heartbeat/                                ← decay engine + trigger rules
│   ├── return_pairing/                           ← windows + pairing engine
│   ├── price_context/                            ← PriceBand + classifier
│   └── lodging/                                  ← shared brain
│       └── providers/                            ← Mock + AirDNA STUB + Inside Airbnb STUB
│
├── links/
│   ├── telegram_dispatcher.py                    ← single outbound seam
│   ├── telegram_live_sender.py
│   └── live_send_audit.py
│
├── db/
│   ├── sqlite_manager.py
│   └── schema.sql                                ← 5 tables (deals, heartbeat, reports, lodging x 2)
│
├── tests/                                        ← 19+ suites, mirror the layer split
└── docs/
    ├── LAYER_<n>_*.md                            ← one per layer
    ├── ARCHITECTURE_FREEZE_v<n>.md               ← one per freeze point
    ├── CLAUDE_CODE_SKILL.md                      ← this pattern doc
    ├── GITHUB_RELEASE_CHECKLIST.md
    └── COUNTRY_BOT_CLONING_GUIDE.md
```

---

## 5. Required environment variables (target shape)

Inherit the full 33-variable surface from the Colombia Desk
(`docs/ARCHITECTURE_FREEZE_v1.md` §10). New desks override only the
geography-flavored values:

| Var | Inherit | Override per desk |
|---|---|---|
| Telegram (`TELEGRAM_*`) | ☑ | New bot per desk — separate token + chat |
| `REGION_PACK` | ☑ | Point at the new YAML |
| `TIMEZONE` | ☑ | Local TZ for the destination (e.g. `America/Costa_Rica`) |
| Flight provider (`RAPIDAPI_*`, `FLIGHT_API_*`) | ☑ | Same provider; new key per quota |
| Operational cadence (`*_HEARTBEAT_*`, `YELLOW_RECHECK_*`, `GREEN_SUMMARY_HOUR`) | ☑ | Adjust to local hours |
| `DRY_RUN`, `SCANNER_TELEGRAM_ENABLED` | ☑ | Default to safety (true / false) |
| `LIVE_SEND_*` | ☑ | Path may change per machine |
| `RETURN_WINDOW_MODE` + range/list | ☑ | Adjust if traveler profile differs |
| `LODGING_*` thresholds + lookback | ☑ | Adjust if the destination's pricing dynamics differ |
| `AIRDNA_API_KEY` / `INSIDE_AIRBNB_LOCAL_PATH` | ☑ | Provider stays STUB until live wire is implemented per Layer 6+ |

---

## 6. Deployment workflow

**Pre-deploy gate (per machine):**

1. Confirm `DRY_RUN=true` and `SCANNER_TELEGRAM_ENABLED=false`.
2. Run the full test suite (see Phase-A `GITHUB_RELEASE_CHECKLIST`).
3. Run `python tests/dry_run_simulations.py` and visually verify the
   4 scenarios match expectations.
4. Confirm the chat ID is a bare integer (no leading colon, no
   accidental prefix).

**Soft launch:**

5. Flip `SCANNER_TELEGRAM_ENABLED=false` (Oak Street becomes the
   sole live path).
6. Keep `DRY_RUN=true` for one scan cycle. Inspect
   `logs/colombia_desk_live_sends.jsonl` — every outcome should be
   `dry_run`.
7. Flip `DRY_RUN=false`. Inspect `logs/colombia_desk.log` for the
   first live `dispatch outcome=sent ...` line.

**VPS deployment** (reserved for Layer 6+):

- systemd unit per desk (one country = one service).
- `WorkingDirectory` is the cloned repo.
- `EnvironmentFile` is `.env` (chmod 600, owned by the run user).
- `Restart=on-failure` with `RestartSec=10`.
- `journalctl -u <country>-desk -f` for log streaming.

---

## 7. Inheritance guidance for future country bots

When starting a new desk, **do not** scaffold from scratch. Inherit
this repo's shape using one of three modes:

### Mode A — Fork (preferred for fully separate desks)

```
git clone <colombia-desk-repo> <country>-desk
cd <country>-desk
git remote rename origin upstream
git remote add origin <new-remote>
# Then follow COUNTRY_BOT_CLONING_GUIDE.md for the geography swap.
```

Pros: fully independent history; can diverge freely.
Cons: cross-desk bug fixes don't auto-propagate; you must
cherry-pick.

### Mode B — Submodule the shared layers (preferred for multi-desk monorepo)

Extract `agents/`, `intel/`, `links/`, `db/` into a shared
`colombia_desk_core/` package; each desk depends on it via
`requirements.txt`. Per-desk repos hold only `configs/`, `main.py`,
`.env.example`, and country-specific test seeds.

Pros: one fix updates every desk.
Cons: heavier upfront refactor; needs a versioning strategy on the
shared core.

### Mode C — Region-pack only (preferred for closely-related desks)

Keep the Colombia Desk as the *runtime* and add another region
pack: `configs/costa_rica.yaml`. The same process runs against
`REGION_PACK=costa_rica`. Specialists keep their Colombia tuning —
acceptable when destinations are culturally close (Andean / Central
American) and operational risk is low.

Pros: zero new infrastructure.
Cons: specialists are still Colombia-tuned; deal classification may
be off until you fork.

**Decision tree:**

```
Is the destination culturally close to Colombia AND traveler
profile similar?
  YES → start with Mode C; promote to Mode A if specialists drift.
  NO  → start with Mode A; promote to Mode B once you have ≥3 desks.
```

---

## 8. What an LLM agent should remember about this pattern

If you (a future Claude Code session) are asked to start a new
country desk, default to:

1. **Read this file plus `ARCHITECTURE_FREEZE_v1.md` and
   `COUNTRY_BOT_CLONING_GUIDE.md` first.** They are the contract.
2. **Build in layer order.** Don't skip — each layer's tests pin
   the next layer's contracts.
3. **Mock first, live later.** Every provider ships with a hermetic
   mock in the first layer that introduces it. The live wire path
   is a separate later layer, gated behind both `enable_live=True`
   AND credentials.
4. **DRY_RUN by default.** Any new `.env` in a fresh clone starts
   with `DRY_RUN=true`. The operator flips it explicitly.
5. **Don't touch `src/` unless it's the kill-switch seam.** The
   scanner is the L0 surface; everything else is layered on top
   without modifying it.
6. **One outbound seam.** If you find yourself writing
   `await context.bot.send_message(...)` anywhere outside the
   dispatcher's path, stop. Route through Oak Street instead.
7. **Stop at the layer boundary.** When the user asks for "Layer N",
   produce only Layer N's work + tests + report. Do not begin
   Layer N+1.

---

## 9. References

- `docs/ARCHITECTURE_FREEZE_v1.md` — frozen current state
- `docs/LAYER_1_REFACTOR_REPORT.md` … `LAYER_5_INDIA_HOSTEL_INTELLIGENCE_REPORT.md` — per-layer design records
- `docs/COUNTRY_BOT_CLONING_GUIDE.md` — concrete steps per destination
- `docs/GITHUB_RELEASE_CHECKLIST.md` — what to verify before publish
- `REPO_RENAME_MIGRATION.md` — naming + Option 1/2/3 decision still open

---

**End of skill package. Inherit this pattern for every country desk.**
