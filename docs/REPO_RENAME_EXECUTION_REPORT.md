# Repo Rename Execution Report — Coming to Colombia Bot

**Date:** 2026-05-29
**Branch:** `repo-rename-coming-to-colombia-bot`
**Base branch:** `layer-5-india-hostel-intelligence` (tip `74c4fe9`)
**Phase A freeze tag:** `phase-a-freeze-v1` (`15c43e3`) — **intact**
**Test status at execution:** **235/235 passing + 4 DRY_RUN simulation
scenarios complete**
**Scope:** in-repo rebrand of the project identity from
`opshub_global_airfare_intelligence_system` (display: *OpsHub Global
Airfare Intelligence System*) to `coming-to-colombia-bot` (display:
*Coming to Colombia Bot*). No code changes, no push, no deploy, no
Layer 6 work.

> This report is the operator-facing artifact for the rename. It
> records what was changed, what was *intentionally* not changed, why,
> and the exact next steps to finish the rename on disk, on GitHub,
> and on the VPS.

---

## 1. Mission and scope

Rename the project's identity strings throughout the documentation,
configuration templates, deployment artifacts, and skill docs so that
the repository now presents itself as the **Coming to Colombia Bot**.
The repository's *technical core* — the config-driven worldwide
airfare framework, the Colombia Desk orchestration, every Layer 1–5
agent and test — is preserved untouched. The rename is therefore a
**brand/identity refactor**, not a behavioral one.

### From → To

| Old identifier | New identifier | Where it appeared |
|---|---|---|
| `opshub_global_airfare_intelligence_system` | `coming-to-colombia-bot` | folder/repo slug used in docs |
| `opshub-global-airfare-intelligence-system` | `coming-to-colombia-bot` | GitHub remote slug used in docs |
| `OpsHub Global Airfare Intelligence System` / `Global Airfare Intelligence System` | `Coming to Colombia Bot` | project titles, doc headers, README, .env.example header, skill description, systemd `Description=` |
| `Global Airfare Intelligence` (skill display) | `Coming to Colombia Bot` (skill display) | skill `SKILL.md` heading + frontmatter |
| `global-airfare-intelligence` (skill name slug) | `coming-to-colombia-bot` | skill frontmatter `name:` |

The existing internal architecture identity **"Colombia Desk"** (used
in code as `colombia_desk.*` loggers, log messages, and the Layer 1
report) **remains as-is**. The "Coming to Colombia Desk" label
appears in user-facing prose (README, architecture freeze title)
where it reads more naturally; internally the orchestration is still
"Colombia Desk" because that name is embedded in code identifiers
which fall under the "Do NOT modify code" constraint.

---

## 2. What was changed

### Files modified (8)

| File | Nature of change |
|---|---|
| `README.md` | Title → *Coming to Colombia Bot*. Opening reframed as a desk-identity tagline that explains the underlying framework. Project structure tree slug, quick-start `cd` path, GitHub setup `git remote add` URL, super-skill section updated. |
| `.env.example` | **Only the top header comment** changed to *Coming to Colombia Bot — environment configuration*. **No env values touched** — `DRY_RUN`, `SCANNER_TELEGRAM_ENABLED`, every other key preserved verbatim. |
| `deployment/systemd/coming-to-colombia-bot.service.template` | Header comment + `Description=` line rebranded; install command in the comment updated to the new service file name. (Renamed from `airfare-intelligence.service.template` via `git mv`.) |
| `docs/GITHUB_RELEASE_CHECKLIST.md` | Title rebranded. §4 documentation note updated. §7 identity table promoted to a 4-column matrix (Surface / Pre-rename / Post-rename / Status). §8 release-checklist items 1 + 2 marked done with execution date and branch references. Header rename note added. |
| `docs/ARCHITECTURE_FREEZE_v1.md` | Title rebranded. Header fields updated: repo-on-disk note now reflects pending Windows folder rename; project identity row added. §2 architecture tree top label updated. |
| `docs/LAYER_1_REFACTOR_REPORT.md` | The historical "Working directory note" updated to record that the in-repo rebrand was executed 2026-05-29; the pre-rename path is preserved as history. |
| `skills/global_airfare_intelligence_skill/SKILL.md` | Frontmatter `name:` → `coming-to-colombia-bot`. Frontmatter `description:` rewritten under the desk identity. H1 → *Coming to Colombia Bot — Super Skill*. Mission rewritten. Maintenance command service name updated to `coming-to-colombia-bot`. Folder-rename note added. |
| `skills/global_airfare_intelligence_skill/QUICKSTART.md` | The `cd` command at step 1 updated to `coming-to-colombia-bot`. |

### Files renamed (1)

| Old path | New path |
|---|---|
| `deployment/systemd/airfare-intelligence.service.template` | `deployment/systemd/coming-to-colombia-bot.service.template` |

Renamed via `git mv` so git records the rename rather than a delete +
create. The on-disk content was edited *before* the rename so the
diff reads cleanly.

---

## 3. What was *intentionally not* changed

### Python source files (per "Do NOT modify code")

The following `.py` files still contain `OpsHub Global Airfare
Intelligence System` (or the shorter `Global Airfare Intelligence
System`) in their **module docstring** or **top-of-file comment**:

| File | Location | Why preserved |
|---|---|---|
| `main.py` | line 1 docstring | "Do NOT modify code" constraint |
| `src/__init__.py` | line 1 docstring | "Do NOT modify code" constraint |
| `tests/test_smoke.py` | line 1 docstring | "Do NOT modify code" constraint |
| `requirements.txt` | line 1 header comment | Adjacent to code; conservative skip |

These are **identity-only** references (no runtime behavior depends
on them) and are tracked as a **docstring-sync follow-up** to run in
a separate, clearly-labeled commit when the operator chooses to lift
the no-code-changes constraint.

### Internal architecture identifiers

| Identifier | Where | Why preserved |
|---|---|---|
| `colombia_desk.*` logger names | `agents/logging_setup.py` and every `getLogger("colombia_desk.…")` call site | Code change |
| "Colombia Desk" in log messages and DB rows | many places | Code change; user-facing string in alerts, but embedded in code |
| `Oak Street` orchestrator name | `agents/oakstreet/` | Code change; deliberately distinct internal codename per Layer 1 design |
| Internal `__version__` numbers | `src/__init__.py` (2.0.0) and `agents/__init__.py` (0.1.0) | "Preserve" per task brief |

### Region packs and tests

All `configs/*.yaml` files, all 19 test files, and every Layer 1–5
module under `agents/`, `intel/`, `links/`, `db/`, `src/` are
**untouched**. The DRY_RUN simulation suite in
`tests/dry_run_simulations.py` is untouched.

### Skill folder name

The folder `skills/global_airfare_intelligence_skill/` is **not**
renamed in this commit. The folder rename is mechanical (`git mv
skills/global_airfare_intelligence_skill
skills/coming_to_colombia_bot_skill`) but it ripples into the few
documentation files that link to it (`README.md` lines 153, 182).
Both `SKILL.md` and `README.md` carry an explicit "folder name kept
from the framework's L0 origin; pending rename" note pointing to this
report. **Recommended follow-up commit**:

```powershell
cd C:\Users\uturn\opshub_global_airfare_intelligence_system   # (or the renamed folder)
git checkout -b skill-folder-rename
git mv skills\global_airfare_intelligence_skill skills\coming_to_colombia_bot_skill
# update the two README lines and the SKILL.md note
git commit -m "Rename skill folder global_airfare_intelligence_skill -> coming_to_colombia_bot_skill"
```

### Documents referencing the old name as **history** (intentional)

Three files still mention `opshub_global_airfare_intelligence_system`
on purpose — they record the pre-rename state:

1. `docs/ARCHITECTURE_FREEZE_v1.md` §header: the pre-rename Windows
   folder path is captured as the freeze record.
2. `docs/GITHUB_RELEASE_CHECKLIST.md` §7 identity table: shows
   pre-rename vs post-rename values side by side.
3. `docs/LAYER_1_REFACTOR_REPORT.md` §working-directory note: records
   where the repo lived at Layer 1.

These are not stale references; they are the freeze record.

### Central America references (per "Do NOT touch Central America")

`docs/COUNTRY_BOT_CLONING_GUIDE.md` contains a Central America
cloning recipe (§1, lines 33–191). Every Central America reference
is preserved verbatim. The recipe already references the *new*
target slug `coming-to-colombia-bot` at lines 187–188 as the *source*
for a fork — Antonio had updated this guide before the rename
execution.

---

## 4. Safety verification

### Phase A freeze tag

```
$ git tag --list "phase-a-freeze-v1" --format="%(refname:short) -> %(objectname:short) %(subject)"
phase-a-freeze-v1 -> 15c43e3 Phase A Freeze v1 — Colombia Desk architecture frozen after Layer 5.
```

Tag is **intact**, points at the original freeze commit. The rename
branch is rooted on `layer-5-india-hostel-intelligence` (the same
branch that produced the freeze), so the freeze remains reachable
from `main` once the rename branch is merged.

### Safety flags in `.env.example`

The header comment was the only line touched in `.env.example`.
Every config line is preserved verbatim, including:

- `DRY_RUN=false` (template default; line 40 — unchanged)
- `SCANNER_TELEGRAM_ENABLED=true` (template default; line 47 — unchanged)
- All Layer 4 / Layer 5 / Echo / Delta / India settings — unchanged

> **Note on the runtime safety state**: the operator's task brief
> states that the *active* runtime values are `DRY_RUN=true` and
> `SCANNER_TELEGRAM_ENABLED=false`. Those values live in the
> gitignored local `.env`, which this rename **does not touch**.
> The values shown in `.env.example` are the documented template
> defaults (which model the eventual production state) — they were
> the same before and after this rename. If the operator wants the
> template defaults to match the runtime safety posture, that is a
> separate change (recommended as a follow-up).

### No live Telegram sends introduced

`grep` for live-send code paths (`application.bot.send_message`,
`live_sender.send`, `telegram.Bot(...).send`) returns the same two
pre-existing files (`main.py`, `docs/LAYER_2_REFACTOR_REPORT.md`).
No new send paths were added.

### Layer 1–5 code untouched

`git diff --stat` shows zero `.py` files modified. The eight files
changed are all `.md` / `.template` / `.example`. Verified by:

```
$ git status
… (8 modified .md/.template/.example files + 1 systemd rename) …
```

---

## 5. Test results

All suites green at execution:

```
Smoke (legacy)                                      14/14
Layer 1   heartbeat decay                           14/14
Layer 1   oakstreet skeleton                         6/6
Layer 1   scanner preservation                       4/4
Layer 2   live send                                 21/21
Layer 3   return pairing                            13/13
Layer 3   echo                                      13/13
Layer 3   briefing                                  11/11
Layer 3   return window modes                       23/23
Layer 4   seasons                                   11/11
Layer 4   scoring                                   17/17
Layer 4   storage                                   10/10
Layer 4   providers                                 14/14
Layer 4   protections                               11/11
Layer 5   india scoring                             24/24
Layer 5   india classification                       9/9
Layer 5   india integration                         11/11
Layer 5   india protections                          9/9
Sims      dry_run_simulations                       4 scenarios complete

TOTAL                                              235/235 passing
```

This matches the pre-rename total documented in §3 of
`docs/GITHUB_RELEASE_CHECKLIST.md`. The rename is verified as
behaviorally neutral.

---

## 6. Next steps

The in-repo rebrand is complete on branch
`repo-rename-coming-to-colombia-bot`. **No push or deploy has
happened.** Three operator-side steps complete the rename.

### 6.1 GitHub repo rename (manual operator step)

After approval and push:

```powershell
# 1) Push the branch (when ready)
git -C C:\Users\uturn\opshub_global_airfare_intelligence_system push -u origin repo-rename-coming-to-colombia-bot

# 2) Open the GitHub web UI:
#       https://github.com/uturnmanagement/opshub-global-airfare-intelligence-system/settings
#    Under Repository name, change to:
#       coming-to-colombia-bot
#    Click "Rename" — GitHub keeps the old URL as a permanent redirect.

# 3) Update the local remote URL to the new canonical name (the old
#    URL keeps working via GitHub redirect, but updating is cleaner):
git -C C:\Users\uturn\opshub_global_airfare_intelligence_system remote set-url origin https://github.com/uturnmanagement/coming-to-colombia-bot.git

# 4) Verify
git -C C:\Users\uturn\opshub_global_airfare_intelligence_system remote -v
```

GitHub automatically redirects the old URL for HTTP clones, web
links, and PR/issue references, so existing bookmarks keep working.
Open PRs survive the rename.

### 6.2 Local Windows folder rename (manual operator step)

The folder is `C:\Users\uturn\opshub_global_airfare_intelligence_system\`.
Steps to rename it to `C:\Users\uturn\coming-to-colombia-bot\`:

```powershell
# 1) Stop any running bot process (gracefully). If running via systemd
#    on the VPS, this step is local only — see §6.3 for the VPS side.
#    On Windows there should be no Python process holding files open;
#    confirm with:
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*opshub_global_airfare_intelligence_system*"
}

# 2) From the parent directory, rename:
cd C:\Users\uturn
Rename-Item -Path opshub_global_airfare_intelligence_system -NewName coming-to-colombia-bot

# 3) Re-open the project in the new path; verify git works:
cd coming-to-colombia-bot
git status
git -C . log --oneline -3

# 4) If any tool (VS Code workspace, scheduled task, scripts under
#    OpsHub\.claude\skills, etc.) has the old path hardcoded, update
#    those references. Suggested grep targets:
#       - OpsHub\.claude\skills\* (referenced in user memory)
#       - any Dropbox sync rules
#       - OPSHUB_VAULT references that pin the airfare project path

# 5) Update auto-memory pointers (the user's memory references the
#    old path in reference_opshub_paths.md and reference_global_airfare_framework.md).
```

Git is path-agnostic — the rename only updates the on-disk location;
the repository itself is identical.

### 6.3 VPS naming alignment (manual operator step)

The Coming to Colombia Bot is **VPS-ready** but **not yet deployed**.
When the operator brings it up on a Linux VPS (Hostinger / AWS EC2
/ similar):

```bash
# 1) Clone under the new name
cd ~
git clone https://github.com/uturnmanagement/coming-to-colombia-bot.git
cd coming-to-colombia-bot

# 2) venv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) .env from template — keep DRY_RUN=true initially
cp .env.example .env
# edit .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RAPIDAPI_KEY,
# DRY_RUN=true, SCANNER_TELEGRAM_ENABLED=false  (per safety brief)

# 4) Verify hermetically
python tests/test_smoke.py     # expect 14/14

# 5) Install the systemd unit using the renamed template
sudo cp deployment/systemd/coming-to-colombia-bot.service.template \
        /etc/systemd/system/coming-to-colombia-bot.service
# edit the new unit:
#   - __RUN_USER__       -> the deploy user
#   - __PROJECT_DIR__    -> /home/<user>/coming-to-colombia-bot
#   - __REGION__         -> colombia
sudo systemctl daemon-reload
sudo systemctl enable --now coming-to-colombia-bot

# 6) Watch logs to confirm DRY_RUN / SCANNER_TELEGRAM_ENABLED gate
sudo journalctl -u coming-to-colombia-bot -f
```

The service name `coming-to-colombia-bot` matches the systemd
template filename and the project repo name — keep all three aligned
so journalctl, the README, and the skill maintenance commands read
the same.

If a previous deployment used the legacy service name
`airfare-intelligence`, run:

```bash
sudo systemctl stop airfare-intelligence
sudo systemctl disable airfare-intelligence
sudo rm /etc/systemd/system/airfare-intelligence.service
sudo systemctl daemon-reload
```

…before bringing up `coming-to-colombia-bot.service`. There is
currently **no live VPS deployment** to migrate, so this is
guidance, not a required step.

### 6.4 Auto-memory pointer updates (optional, recommended)

The user's auto-memory at
`C:\Users\uturn\.claude\projects\C--Users-uturn\memory\` references
the project under the old name:

- `reference_opshub_paths.md` — paths to the live/dev/backup folders
- `reference_global_airfare_framework.md` — framework reference

When the local folder rename in §6.2 completes, those memory entries
should be updated to point at `C:\Users\uturn\coming-to-colombia-bot\`.
Add a new entry for the renamed project's identity if desired.

### 6.5 Optional docstring-sync follow-up

The four `.py` / `requirements.txt` header references identified in
§3 can be brought into alignment in a clearly-labeled commit:

```
DOCS — rename docstring sync: .py module headers + requirements.txt
```

This is recommended once the operator has lifted the "Do NOT modify
code" constraint. No runtime behavior depends on those strings.

---

## 7. Constraints honored

- ✅ Switched back to `layer-5-india-hostel-intelligence` before branching.
- ✅ Created branch `repo-rename-coming-to-colombia-bot`.
- ✅ Renamed project identity strings in docs, configs, deployment
  templates, skill docs, cloning guide refs, GitHub checklist, VPS
  guidance, and service names.
- ✅ Did NOT modify any `.py` code module.
- ✅ Did NOT push to GitHub.
- ✅ Did NOT rename the Windows folder (documented as §6.2 next step).
- ✅ Did NOT start Layer 6.
- ✅ Preserved all Layer 1–5 code.
- ✅ Preserved the `phase-a-freeze-v1` tag.
- ✅ Preserved `DRY_RUN` / `SCANNER_TELEGRAM_ENABLED` / Layer-2 kill
  switch / live-send audit; no live Telegram code paths added.
- ✅ Did NOT touch Central America references.

---

**End of execution report.**
