# Prompt patterns

Copy-paste prompts for ad-hoc sessions. Replace `{DATE}` with today (YYYY-MM-DD).

## How production runs (use this first)

- **Scheduled work:** attach one task from [`cowork/tasks/README.md`](../../cowork/tasks/README.md), read [`cowork/PROJECT.md`](../../cowork/PROJECT.md), then follow [`RUNBOOK.md`](../../RUNBOOK.md). That path is the default; the snippets below are for **manual / partial** runs.
- **Canonical state:** Supabase `daily_snapshots` and `documents` (JSON payloads). Tasks do not use a repo-local agent cache — see [`data/README.md`](../../data/README.md).
- **Close-out:** `python3 scripts/run_db_first.py` after publishes (see RUNBOOK).

---

## DB-first defaults (all tracks)

- **Track A (blind research):** paste from [`scripts/cowork-research-prompt.txt`](../../scripts/cowork-research-prompt.txt).
- **Track B (portfolio):** paste from [`scripts/cowork-daily-prompt.txt`](../../scripts/cowork-daily-prompt.txt).
- **Validate / publish:** `scripts/validate_artifact.py`, `scripts/materialize_snapshot.py`, `scripts/publish_document.py` — details in RUNBOOK.

---

## Full daily digest (manual)

```
Today is {DATE}.

Read skills/orchestrator/SKILL.md (9 phases; see docs/agentic/ARCHITECTURE.md).

Setup:
- Read config/watchlist.md; for portfolio layer read config/preferences.md and config/investment-profile.md
- Load prior context from Supabase daily_snapshots and documents

Execute phases; emit JSON per skill; materialize digest and publish to Supabase (RUNBOOK.md).
No local daily folder required when publishing to Supabase.
```

---

## Single segment — Macro

```
Today is {DATE}.

Read skills/macro/SKILL.md.
Load prior macro context from Supabase daily_snapshots or documents for recent dates.
Read config/preferences.md only if this run feeds portfolio (Track B).

Run the macro analysis.
Publish segment JSON to Supabase per RUNBOOK.md.
```

---

## Single segment — Crypto

```
Today is {DATE}.

Read skills/crypto/SKILL.md.
Load prior crypto context from Supabase daily_snapshots or documents for recent dates.
Read config/watchlist.md for tracked crypto assets.

Run crypto analysis.
Publish to Supabase per RUNBOOK.md.
```

---

## Single sector

```
Today is {DATE}.

Read skills/sector-{SECTOR}/SKILL.md (replace {SECTOR} with: technology, healthcare, energy, financials,
consumer-disc, consumer-staples, industrials, materials, utilities, real-estate, or comms)

Load prior sector research from Supabase daily_snapshots or documents for recent dates.
Load today's macro segment from Supabase documents for {DATE} if present.

Publish sector payload to Supabase per RUNBOOK.md.
```

---

## All 11 sectors (parallel)

```
Today is {DATE}.
Macro context: [paste regime summary from Supabase daily_snapshots / documents, or describe]

Run all 11 sector analyses in parallel. For each sector:
- Read skills/sector-{sector}/SKILL.md
- Load prior context from Supabase daily_snapshots or documents for recent dates
- Publish findings to Supabase per RUNBOOK.md

Sectors: technology, healthcare, financials, energy, consumer-disc,
consumer-staples, industrials, materials, utilities, real-estate, comms
```

---

## Alternative data sweep (Phase 1)

```
Today is {DATE}.

Run Phase 1 alternative data:
1. skills/alt-sentiment-news/SKILL.md
2. skills/alt-cta-positioning/SKILL.md
3. skills/alt-options-derivatives/SKILL.md
4. skills/alt-politician-signals/SKILL.md

Load prior alt-data context from Supabase daily_snapshots or documents.
Publish each segment to Supabase per RUNBOOK.md.
```

---

## Institutional flows (Phase 2)

```
Today is {DATE}.

Run Phase 2 institutional analysis:
1. skills/inst-institutional-flows/SKILL.md
2. skills/inst-hedge-fund-intel/SKILL.md
3. Read config/hedge-funds.md for tracked funds

Load prior institutional context from Supabase daily_snapshots or documents.
Publish to Supabase per RUNBOOK.md.
```

---

## Synthesis / digest only (Phase 7)

Use after segment work for {DATE} is in Supabase:

```
Today is {DATE}.

Load completed segment context from Supabase documents and daily_snapshots for {DATE}
(load segment context from Supabase only).

Produce a digest snapshot JSON (schema: templates/digest-snapshot-schema.json) and publish via scripts/materialize_snapshot.py per RUNBOOK.md.
Load prior bias context from Supabase daily_snapshots.

Canonical digest row: daily_snapshots for {DATE}; narrative digest document per RUNBOOK.
```

---

## Ticker deep dive

```
Run a deep dive on: {TICKER}

1. Read skills/deep-dive/SKILL.md for the research framework
2. Query Supabase daily_snapshots and documents for any prior notes on {TICKER}
3. Read config/watchlist.md — tracked? size?
4. Check config/preferences.md for relevant biases or theses

Produce structured research; publish to Supabase research library via scripts/publish_research.py (RUNBOOK.md).
```

---

## Portfolio / thesis review

```
Today is {DATE}.

Load active theses from Supabase documents.
Read config/preferences.md for portfolio positioning and risk tolerance.
Load recent bias rows from Supabase daily_snapshots (last 5 entries).

Load today's digest context from Supabase daily_snapshots (and documents digest for {DATE}).

For each active thesis:
- Assess evidence For vs Against
- Update status: Building | Confirmed | Extended | At Risk | Exited

Publish updates to Supabase documents.
```

---

## Weekly synthesis

```
Week ending: {DATE}

Read this week's digests from Supabase (documents + daily_snapshots).
Load bias rows for this week from Supabase daily_snapshots.

Produce weekly JSON (schema: templates/schemas/weekly-digest.schema.json).
Publish per RUNBOOK if your workflow commits weekly_digest to Supabase; otherwise keep as operator-only artifact.
Publish weekly rollup per RUNBOOK if your workflow stores it in Supabase.
```

---

## Historical context load

```
Before we begin, load relevant context for today's session.

Read:
- config/watchlist.md
- config/preferences.md

Query Supabase:
- daily_snapshots: last 10 entries (regime + biases)
- documents: active theses and recent segment notes

Summarize:
1. Macro regime and bias trend
2. Key equity observations from recent sessions
3. Active theses and status
4. Watchlist developments

Use as foundation for today's analysis.
```

---

## Adding a new skill

```
I want to add a new skill for: {SKILL_NAME}

Purpose: {description}

Please:
1. Read docs/agentic/SKILLS-CATALOG.md
2. Read skills/macro/SKILL.md as a format reference
3. Create skills/{skill-slug}/SKILL.md with YAML frontmatter, numbered steps, Output Format, Supabase Publish
4. Reference in skills/orchestrator/SKILL.md if it is a pipeline phase
5. Add to docs/agentic/SKILLS-CATALOG.md
```

---

## Editing conventions

```
- Supabase (daily_snapshots, documents) is canonical — publish there first
- macOS sed: sed -i "" (BSD)
- Skill YAML name:/description: — cascading updates if renamed
- Do not hand-edit JSON meant for Supabase outside the publish scripts — no local cache folder is authoritative
- Use {DATE} / YYYY-MM-DD in examples, not hardcoded dates
```
