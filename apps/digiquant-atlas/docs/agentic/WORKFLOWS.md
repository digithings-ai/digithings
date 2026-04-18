# Workflows Reference

Step-by-step procedures for every recurring workflow.

---

## GitHub Actions (systematic data, no agent)

| Workflow | Schedule | Role |
|----------|----------|------|
| [`daily-price-update.yml`](../../.github/workflows/daily-price-update.yml) | **Mon–Fri 00:00 UTC** (~8:00 PM Eastern during EDT, ~7:00 PM Eastern during EST; after US cash close, per workflow comments) | [`preload-history.py --supabase --supabase-sync`](../../scripts/preload-history.py) → `price_technicals` → macro ingests. Manual dispatch = same as schedule (no inputs). Does **not** run digest, `update_tearsheet.py`, or research. |
| [`ci.yml`](../../.github/workflows/ci.yml), [`deploy.yml`](../../.github/workflows/deploy.yml) | On push / manual | Build and deploy. |

**Weekly digest:** no scheduled GitHub job — use [`scripts/weekly-rollup.sh`](../../scripts/weekly-rollup.sh) when you need the operator prompt. **Sunday baseline** vs weekdays is still defined in [`run_db_first.py`](../../scripts/run_db_first.py).

**Co-work / operator** runs ([`RUNBOOK.md`](../../RUNBOOK.md)): research + portfolio JSON → `run_db_first.py` → Supabase. Cowork setup: [`cowork/README.md`](../../cowork/README.md), project prompt [`cowork/PROJECT-PROMPT.md`](../../cowork/PROJECT-PROMPT.md), task list [`cowork/tasks/README.md`](../../cowork/tasks/README.md).

---

## Daily full digest (DB-first)

**Time:** Before or after market open/close (see [`config/schedule.json`](../../config/schedule.json) for intent).  
**Duration:** 1–3 hours (AI-parallel)

### Steps

```bash
# 1. Entrypoint (prints agent prompt; on full run refreshes metrics + validates DB)
./scripts/new-day.sh
# same as: python3 scripts/run_db_first.py
```

```bash
# 2. Agent: follow skills/orchestrator/SKILL.md (baseline) or skills/daily-delta/SKILL.md (weekday).
#    Publish JSON only: materialize_snapshot.py + publish_document.py (stdin).
#    No repo-local cache required for DB-only runs (see data/README.md).
python3 scripts/run_db_first.py
#    Flags: --skip-execute / --validate-mode research|pm|full / --legacy-markdown-tearsheet — RUNBOOK.md
```

**Manual prompt for full digest:**
```
Today is YYYY-MM-DD.
Read skills/orchestrator/SKILL.md (or weekly-baseline / daily-delta per day type).
Read config/watchlist.md; for portfolio work also preferences + investment-profile.
Load prior context from Supabase daily_snapshots and documents for recent dates.
DB-first: JSON → materialize_snapshot.py / publish_document.py; close with run_db_first.py.
```

```bash
# 3. Commit repo config only (Supabase already holds digest data)
./scripts/git-commit.sh
```

**Output:** Supabase (`daily_snapshots`, `documents`, `positions`, …)

---

## Single Segment Run

Run just one phase or segment without the full pipeline (no dedicated Bash printer; use prompts below).

**Manual prompt pattern:**
```
Read skills/{segment}/SKILL.md (or the appropriate skill package) and run the analysis for {DATE}.
Load prior context from Supabase daily_snapshots or documents for recent dates.
Write JSON artifacts as needed and publish to Supabase (see RUNBOOK.md).
```

**Available segments**: macro, bonds, commodities, forex, crypto, international, equities, earnings, alt-data, institutional, plus any of the 11 sector names.

---

## Phase 7 Synthesis (Digest Only)

After running phases 1-6 manually or partially, use this prompt (DB-first):

**Manual synthesis prompt:**
```
Daily digest is DB-first: load prior context from Supabase (`daily_snapshots`, `documents`).
Produce a digest snapshot JSON (schema: `templates/digest-snapshot-schema.json`) and publish via `scripts/materialize_snapshot.py`. Markdown is rendered from JSON.

Synthesize into snapshot JSON and publish via `scripts/materialize_snapshot.py` (see RUNBOOK.md).
```

---

## Weekly Rollup

**Runs**: Friday evening or Sunday (filesystem rollup); **Supabase weekly baseline** is **Sunday** when using default [`run_db_first.py`](../../scripts/run_db_first.py) detection (`--baseline` on Sunday).
**Purpose**: Synthesize the week's research into one narrative

```bash
./scripts/weekly-rollup.sh
# → prints weekly synthesis prompt
```

**Manual prompt:**
```
Read this week's research from Supabase (`documents`, `daily_snapshots`).
Prefer Supabase only; local JSON mirrors are migration/legacy only (`data/README.md`).
Load bias rows for this week from Supabase daily_snapshots.
Write a weekly JSON artifact (schema: templates/schemas/weekly-digest.schema.json).
If your operator workflow commits weekly rollups, publish per RUNBOOK; otherwise keep as read-only synthesis.
```

---

## Monthly Rollup

**Runs**: Last day of month
**Purpose**: Key themes, sector rotation, thesis evolution

```bash
./scripts/monthly-rollup.sh
# → prints monthly synthesis prompt
```

**Manual prompt:**
```
Query Supabase daily_snapshots for the month's bias rows.
Query Supabase documents for this month's key observations per domain.
(Do not depend on `data/agent-cache/weekly/` — use Supabase documents.)
Write a monthly JSON artifact (schema: `templates/schemas/monthly-digest.schema.json`).
Publish monthly synthesis via RUNBOOK; avoid relying on `data/agent-cache/monthly/` except during migration.
```

---

## Thesis Management

### Adding a New Thesis
```bash
./scripts/thesis.sh add "THESIS_NAME"
# → prints thesis-building prompt
```

**Manual prompt:**
```
Read skills/thesis/SKILL.md.
Build a new research thesis for: [TOPIC/TICKER/THEME]
Read config/preferences.md for context on trading style.
Query Supabase daily_snapshots and documents for existing research on the relevant domain.
Publish the completed thesis to Supabase documents with today's date.
```

### Reviewing Active Theses
```bash
./scripts/thesis.sh review
# → prints thesis review prompt
```

**Manual prompt:**
```
Read skills/thesis-tracker/SKILL.md.
Query thesis data in Supabase documents for all active theses.
Read today's digest context from Supabase (`daily_snapshots`, digest `documents`).
Score each thesis: [Building | Confirmed | Extended | At Risk | Exited]
Publish your review to Supabase documents under today's date.
```

---

## Deep Dive Research

For ad-hoc in-depth research on a specific ticker or topic:

**Prompt:**
```
Read skills/deep-dive/SKILL.md.
Run a deep dive on: {TICKER or TOPIC}
Query Supabase daily_snapshots and documents for prior equity and sector research notes.
Read config/watchlist.md to see if it's a tracked position.
Publish via `scripts/publish_research.py` per RUNBOOK (Supabase research library). Markdown is derived in-app.
```

---

## Watchlist Update

When adding/removing tickers from the watchlist:

```bash
./scripts/watchlist-check.sh
```

**Manual steps:**
1. Edit `config/watchlist.md`
2. If adding a new ticker — publish a context note to Supabase documents for the relevant sector
3. Update `config/portfolio.json` if it's an active position

---

## Research Search

Find prior research on any topic:

```bash
./scripts/memory-search.sh "NVDA"
./scripts/memory-search.sh "China PMI"
./scripts/memory-search.sh "credit spreads"
```

Returns matching content from Supabase `daily_snapshots` and `documents`.

---

## Status Check

```bash
./scripts/status.sh
```

Shows:
- Today's folder status (created or not)
- Which output files exist vs. missing
- Supabase row counts for recent dates
- Active thesis count

---

## Git Workflow

```bash
# After any session with outputs
./scripts/git-commit.sh

# Manual commit (config only — digest data lives in Supabase; see data/README.md)
git add config/
git commit -m "$(date +%Y-%m-%d): config update"
git push
```

CI/CD in `.github/workflows/deploy.yml` publishes the tearsheet on push to master.

---

## Disk migration (rare)

One-off backfills from disk exports: see [`RUNBOOK.md`](../../RUNBOOK.md) (`backfill-historical-daily-to-supabase.sh`, **`LEGACY_ROOT`** or **`SKIP_COPY=1`**).

---

## Error Recovery

**If a published snapshot or document is incomplete:**
```
Re-run or patch the digest snapshot JSON, then republish with scripts/materialize_snapshot.py.
Validate with: python3 scripts/validate_db_first.py --date YYYY-MM-DD
```

**If a Supabase document or snapshot is incorrect:**
```
Recover from Supabase via fetch_research_library.py or query daily_snapshots for the affected date.
Re-publish the corrected document via publish_document.py or materialize_snapshot.py.
```

**If a skill file has a syntax error:**
```
Read docs/agentic/SKILLS-CATALOG.md for the expected format.
Cross-reference with another working skill file.
The YAML frontmatter must remain intact.
```
