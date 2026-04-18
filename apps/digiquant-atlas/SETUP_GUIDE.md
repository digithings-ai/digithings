# Setup Guide — digiquant-atlas

> Complete this guide once. After that, your daily workflow is just two commands and a paste.

---

## Part 1: Local Setup (5 minutes)

### 1.1 Extract and enter the project

```bash
tar -xzf digiquant-atlas.tar.gz
cd digiquant-atlas
```

After clone you may have **no** `data/` folder, or only **`data/README.md`** (tracked). Scripts create other paths under **`data/`** locally (gitignored) for price CSV cache and optional scratch—**Supabase** holds canonical state ([RUNBOOK.md](RUNBOOK.md)).

### 1.2 Create a private GitHub repo

Go to github.com → New repository → **Private** → name it `digiquant-atlas`

Then connect your local repo:

```bash
git remote add origin https://github.com/YOUR_USERNAME/digiquant-atlas.git
git branch -m master main
git push -u origin main
```

### 1.3 Make scripts executable (if not already)

```bash
chmod +x scripts/*.sh
```

---

## Part 2: Personalize Your Config (10 minutes)

This is the most important step. Claude reads these files at the start of every session.

### 2.1 Edit `config/watchlist.md`

Replace the example tickers with your actual:
- Holdings and high-priority watchlist stocks
- Crypto positions and watchlist
- Bond ETFs you track
- FX pairs relevant to your portfolio (especially if you hold non-USD assets or trade FX)
- Commodities that matter to your thesis

The more specific this is, the more focused your digests will be.

### 2.2 Edit `config/preferences.md`

Fill in every section honestly:
- **Trading style**: Are you swinging, positioning, or investing? What's your typical hold time?
- **Risk profile**: Position sizing, stop approach, leverage limits
- **Active theses**: What are you currently positioned around? What are you watching to enter?
- **What to filter**: What noise do you want excluded from the digest?

The preferences file is what makes the digest *yours* rather than generic market commentary.

---

## Part 3: Set Up the Claude Project (5 minutes)

### 3.1 Create a new Project in Claude

In Claude.ai: **New Project** → name it `digiquant-atlas` (or similar)

### 3.2 Set the Project Instructions

Copy the full contents of `cowork/PROJECT-PROMPT.md` (and optionally the short stub in `CLAUDE_PROJECT_INSTRUCTIONS.md`) and paste into the Project's **Instructions** field.

Canonical behavior and skill routing live in `AGENTS.md` and `docs/agentic/SKILLS-CATALOG.md`; the paste block stays focused on session workflow.

### 3.3 Upload your files to the Project

In the Project's **Knowledge** section, upload:
- `config/watchlist.md`
- `config/preferences.md`
- All `skills/**/SKILL.md` files (all skill packages)
- `templates/digest-snapshot-schema.json` (daily canonical JSON)

> **Note on session context**: Pipeline outputs (digests, segment analyses, thesis state) are stored in Supabase (`daily_snapshots`, `documents`). Config files in `config/` are the operator's working copy. The git repo is your source of truth for config and skill files; Supabase is canonical for pipeline data.

### 3.4 Workflow for keeping Project Knowledge current

After each digest session:
1. Pipeline JSON is published to Supabase automatically via `scripts/materialize_snapshot.py`
2. Run `./scripts/git-commit.sh` to commit any updated config files
3. Re-upload changed config files to Project Knowledge if needed

This takes ~2 minutes once you have the habit.

---

## Part 4: Your First Session (15 minutes)

### 4.1 Run the new-day script

```bash
./scripts/new-day.sh
```

This prints a ready-made prompt to paste into Claude.

### 4.2 Paste the prompt into your digiquant-atlas Claude Project

Claude will:
1. Read all your config files and prior Supabase context
2. Search the web for current market data across all segments
3. Produce structured JSON artifacts and publish to Supabase
4. Produce the master digest

### 4.3 Review the digest

Read it. The first one is calibration — if anything is wrong in focus, tone, or coverage, edit `config/preferences.md` to correct it.

### 4.4 Commit

```bash
./scripts/git-commit.sh
```

---

## Part 5: Daily Rhythm

### Every morning (~15-20 min)

```bash
./scripts/new-day.sh        # detects run type (baseline/delta) + prints prompt
# → paste prompt into Claude Project
# → Claude runs digest (takes 5-10 min)
# → read the digest
./scripts/git-commit.sh     # commits config updates
```

### Every Friday

```bash
./scripts/weekly-rollup.sh  # creates weekly file + prints prompt
# → paste prompt into Claude Project
# → Claude generates weekly synthesis
./scripts/git-commit.sh
```

### End of each month

```bash
./scripts/monthly-rollup.sh
# → paste prompt into Claude Project
./scripts/git-commit.sh
```

### When you want to add a new thesis

Tell Claude in the Project: *"Add a new thesis: [your view]"*
Claude will use `skills/thesis/SKILL.md` to structure it properly and publish it to the thesis tracker in Supabase `documents`.

### When you want a deep dive

Tell Claude: *"Deep dive on NVDA"* or *"Full breakdown of the Treasury curve right now"*
Claude will use `skills/deep-dive/SKILL.md` for a standalone research note.

### Quick morning scan (before full digest)

Tell Claude: *"Pre-market pulse"*
Claude will use `skills/premarket-pulse/SKILL.md` for a fast 5-minute read.

---

## Part 6: Maintenance

### Keeping Supabase data current

Pipeline outputs accumulate in Supabase over time. The `daily_snapshots` and `documents` tables are the canonical record. Use `python3 scripts/update_tearsheet.py` if you need to recover or resync Supabase from local scratch files.

### Updating your theses

Review active theses in Supabase `documents` (thesis entries) weekly. Close theses that have resolved. This is the discipline that makes the system valuable over time.

### Archiving / migration

New runs are DB-first (Supabase). Disk backfill and migration flows live in [`RUNBOOK.md`](RUNBOOK.md) (no separate archive tree in this repo).

---

## Troubleshooting

**Claude produces generic market commentary instead of focused digest**
→ Check that `config/preferences.md` is uploaded to Project Knowledge and has your specifics filled in.

**Pipeline output isn't appearing in Supabase**
→ Explicitly ask: *"Publish today's findings to Supabase using scripts/materialize_snapshot.py"* at the end of the session.

**Digest is too long / too short**
→ Edit the "Format preferences" section of `config/preferences.md` to specify length and depth.

**Claude doesn't know about a recent event**
→ Normal — ask Claude to search for it: *"Search for [event] and incorporate into the digest."*
