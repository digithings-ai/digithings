---
name: research-daily
description: Track A — generic market research (macro, crypto, sectors, sentiment) without portfolio or user preference bias. Produces research_delta JSON and publishes to Supabase (stdin or temp file) with a unique document_key per run.
---

# Research Daily (Track A)

## Purpose

Produce **positioning-blind** research for the run date. **Do not** read:

- `config/preferences.md`
- `config/investment-profile.md`
- `config/portfolio.json`

You may read `config/watchlist.md` only as a **universe list** (tickers to mention), not for weights or goals.

## Cadence

Track A is **project-level** (shared across users). Operators may schedule it **every 8 hours, 12 hours, or once per day** — see `config/schedule.json` → `research_cadence`. Multiple runs on the **same calendar date** are allowed: each publish must use a **distinct** `document_key` so history is preserved (see below).

**Anchor:** `baseline_date` still points at the latest Sunday (or last baseline) on or before `date`. On baseline/anchor days you may set `"run_type": "baseline"` and a fuller segment scope; intra-day reruns are usually `"run_type": "delta"`.

## Outputs (Supabase only — no committed repo paths)

Produce one JSON object that validates as **`research_delta`**. **Do not** treat `data/agent-cache/` as the system of record; hosted runs may have no writable project tree.

- Schema: `templates/schemas/research-delta.schema.json`  
- `doc_type` must be `research_delta`  
- `baseline_date`: latest Sunday baseline on or before `date` (from Supabase `daily_snapshots`).  
- Set **`published_at`** (RFC3339 UTC, e.g. `2026-04-11T14:30:22Z`) so payloads sort consistently with Supabase rows. **`run_id`** (optional UUID) is an alternative disambiguator.

**Validate and publish** (preferred — stdin, no disk path):

- **Pattern:** `document_key` = `research-delta/{{RUN_SUFFIX}}.json` where `RUN_SUFFIX` matches `published_at` in compact form without colons, e.g. `20260411T143022Z`, **or** a short UUID. Never reuse the same key on the same `date`.

```bash
# Pipe the single JSON object (replace heredoc with your payload)
python3 scripts/validate_artifact.py - <<'EOF'
{ ... valid research_delta JSON ... }
EOF
python3 scripts/publish_document.py \
  --payload - \
  --document-key research-delta/RUN_SUFFIX.json \
  --title "Research delta" \
  --category output \
  --doc-type-label "Research Delta"
```

If your environment only supports a scratch file, you may write a **local temp** path, validate/publish that file, then delete it — **do not** rely on `data/agent-cache/` in git or in production layout.

**Daily snapshot row:** If you do **not** run a full digest, ensure `daily_snapshots` has a row for `date` (e.g. upsert via `materialize_snapshot.py` from an empty delta, or operator backfills). `validate_db_first.py --mode research` allows a row with nullable `snapshot` when at least one `research_delta` document exists for that date.

## Optional: issuer filings (SEC)

The watchlist is **ETF-heavy**; there is **no** daily `sec_recent_filings` table. When the delta materially involves a **sector** or **specific operating companies**, you may **ad hoc** check EDGAR for recent **8-K** / **10-Q** / **10-K** on names that drive the theme (or use the **`sec-edgar`** MCP with **`SEC_EDGAR_USER_AGENT`**). Cite filing type and date if you lean on them in the narrative.

## No-change days

Set `"no_change": true` and keep `segments` fields as short strings (e.g. "No material change vs baseline.") so the day is still indexed.

## After publish

```bash
python3 scripts/run_db_first.py --skip-execute --validate-mode research --date {{DATE}}
```

**Digest (research overview):** this skill publishes **`research_delta`** only. The **`digest`** — single summary of all segments for the date — is produced at **research task close-out** via [`skills/daily-delta/SKILL.md`](../daily-delta/SKILL.md) **Phase 7B** (weekdays) or the full [`skills/weekly-baseline/SKILL.md`](../weekly-baseline/SKILL.md) / orchestrator **Phase 7** (Sunday). See [`cowork/tasks/research-daily-delta.md`](../../cowork/tasks/research-daily-delta.md) and [`cowork/tasks/research-weekly-baseline.md`](../../cowork/tasks/research-weekly-baseline.md).

## Related

- Track B (portfolio): `skills/daily-delta/SKILL.md`, `skills/portfolio-manager/SKILL.md`, `cowork/tasks/portfolio-pm-rebalance.md`
- Cowork task routing: `cowork/tasks/recurring-scheduled-run.md`, `cowork/tasks/research-weekly-baseline.md`, `cowork/tasks/research-daily-delta.md`
- Runbook: `RUNBOOK.md` (two tracks, schedules)
