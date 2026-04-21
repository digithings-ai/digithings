# ADR-0010 — Atlas first-class thesis + deliberation tables

- **Status:** Accepted
- **Date:** 2026-04-20
- **Deciders:** Chris Stefan (founder), Atlas Wave 1 worktree agents
- **Related:** [ADR-0008 Atlas research schema](0008-atlas-research-schema.md), [ADR-0011 Atlas Supabase persistence](0011-atlas-supabase-persistence.md)
- **Supersedes:** nothing. Complements ADR-0011.

## Context

Through migration 023 the Atlas Track B pipeline (`market_thesis_exploration`,
`thesis_vehicle_map`, `deliberation_transcript`, `deliberation_session_index`,
`pm_allocation_memo`, `asset_recommendation`) persists exclusively through the
`documents` table as JSONB payload rows. That shape is fine for publish-time
(one upsert per artifact) and for the frontend (one read for the full blob),
but it is expensive for four classes of query we now need:

1. **Dashboards that join theses to vehicles** (e.g. "which tickers are in the
   long-growth thesis over the last 90 days") require repeated JSONB unpacking
   and ticker-level indexing on the `thesis_vehicle_map` payload.
2. **Deliberation analytics** ("average rounds to convergence", "recess-trigger
   rate by sector") require scanning every transcript and parsing rounds.
3. **Historical thesis tracking** across `theses` → vehicles → analyst
   recommendations → rebalance decisions is chained across five JSONB
   payloads with no join keys.
4. **"Which analyst covers AAPL today"** is a 1-row query that today requires
   scanning all `asset_recommendation` documents for the date.

Wave 1 of the Atlas → DigiGraph migration moves the Hermes sub-graph
(deliberation round-loop, deep-dive recess, PM memo) into first-class
LangGraph state. That work creates the natural opportunity to also land
structured persistence alongside the existing documents-only writes.

## Decision

Adopt **dual persistence** for a defined subset of Track B doc_types:
payloads continue to land in `documents` (no regression for frontend, no
schema migration for blob consumers) **and** a structured subset lands in
new first-class tables (migration 024).

### Which doc_types get first-class tables

| doc_type                       | Goes into           | Rationale                                                   |
|--------------------------------|---------------------|-------------------------------------------------------------|
| `thesis_vehicle_map`           | `thesis_vehicles`   | High query volume by `(thesis_id, ticker)` join             |
| `deliberation_session_index`   | `deliberation_sessions` | Needs `(date, kind)` filters for analytics             |
| `deliberation_transcript`      | `deliberation_rounds`   | Per-round convergence + recess analytics               |
| `asset_recommendation`         | `analyst_coverage`  | Denormalized analyst ↔ ticker index                         |
| _(synthetic)_ deep-dive trigger | `deep_dive_triggers` | New audit log — no prior documents payload existed         |

### Which doc_types stay documents-only (for now)

- `market_thesis_exploration` — narrative-heavy; the structured slice we need
  is the vehicle list, which lands in `thesis_vehicles` via its
  `source_exploration_key` back-pointer. The exploration itself stays a
  document because it is read holistically.
- `pm_allocation_memo` — narrative memo with bulk text + targets. Low query
  volume at the sub-structure level; frontend reads the whole payload.
- `rebalance_decision` — already mapped through `position_events` first-class
  table since migration 022.
- `research_delta`, `research_baseline_manifest`, `document_delta`,
  `research_changelog`, `evolution_*`, `sector_report`, `deep_dive`,
  `pipeline_review`, `weekly_digest`, `monthly_digest`, `delta_digest`,
  `master_digest`, `delta_segment` — infrequent query access, bulk-narrative
  content, no denormalization benefit.

### Write path (Wave 2)

The Python adapters are explicitly out of scope for this ADR / migration
(they land in Wave 2, UNIT W2-A). The contract for Wave 2:

- The existing `publish_document` adapter in
  `apps/digiquant-atlas/src/digiquant_atlas/supabase_io.py` remains the single
  entry point for writing Track B artifacts.
- New extractor functions per doc_type read the just-upserted payload, project
  the structured subset, and upsert into the matching first-class table in the
  same logical operation.
- All secondary writes pass through `digibase.audit.redact_mapping` before
  logging, consistent with ADR-0009.

### RLS

Every new table gets `ENABLE ROW LEVEL SECURITY` + a per-table `anon` SELECT
policy named `{table}_anon_select` — matching migrations 005 / 007 / 015 / 023.
Writes require the Supabase service_role key; service_role bypass is grant-
based in Supabase (not a policy), so we do not declare an explicit
`service_role` policy (consistent with every existing Atlas migration).

## Consequences

### Positive

- Two-index-hop for common dashboard queries (vs. JSONB scan).
- Deliberation and deep-dive analytics become tractable.
- Wave 2 implementers get a clean contract: same publish entrypoint, new
  extractor next to each doc_type.
- Frontend is not disrupted — `documents` reads keep working unchanged.
- Rollback is a single commented-out block in migration 024.

### Negative

- Every Track B publish becomes a 2-row write (documents + first-class).
  Mitigated because the writes are serialized within a single Python
  invocation; failure rolls back both (transaction per publish).
- Drift between `documents.payload` and first-class rows is possible if a
  future author forgets to extend both. Wave 2 adds a validation test that
  for every row in the first-class tables there is a matching `documents`
  row at the same `(date, document_key)`.
- Two sources of truth for the structured subset. We treat `documents` as
  the canonical artifact and the first-class rows as a derived projection —
  documents wins in any reconciliation.

### Neutral

- Pre-existing casing conventions are inherited, not re-opened:
  - `documents.doc_type` CHECK constraint uses **Title Case** (e.g.
    `'Deliberation Transcript'`) for human-readable labels.
  - Payload `doc_type` fields use **snake_case** (e.g. `deliberation_transcript`)
    for programmatic matching.
  - Migration 024 does not touch either. First-class tables use neither; they
    reference `documents` by `document_key` strings.

## Alternatives considered

1. **Generated columns on `documents`** — would avoid a second table but
   indexes on JSONB-generated columns don't compose cleanly across rows and
   we'd still have no FK to `theses`.
2. **Materialized views** — readable but refresh latency and cost grow with
   `documents` size; we'd need the same indexes anyway.
3. **Replace documents with first-class tables entirely** — would disrupt the
   frontend and lose the blob-retrieval affordance. Rejected.
4. **Natural PK `(session_id, ticker, round_number)` on `deliberation_rounds`** —
   `deliberation_rounds.id` surrogate `BIGSERIAL` chosen over the natural
   `(session_id, ticker, round_number)` PK for simpler FK-back references
   and ORM ergonomics. The natural triple is preserved as a UNIQUE constraint.

## Implementation

- Migration: `apps/digiquant-atlas/supabase/migrations/024_thesis_deliberation_first_class.sql`
- Schema map: `apps/digiquant-atlas/supabase/SCHEMA.md`
- Test: `apps/digiquant-atlas/tests/test_migration_024.py`
- Rollback: commented-out DROP block at the bottom of migration 024.

## Appendix A — Dead doc_type audit (2026-04-20)

Scan of `apps/digiquant-atlas/` (src/, scripts/, frontend/, tests/, templates/)
for every string literal that appears as a `doc_type` value, compared against
the `chk_documents_doc_type` CHECK constraint (migration 023).

**Decision for this migration: freeze. Do not drop any doc_type.** A follow-up
migration (025) drops any that are still unreferenced after one sprint.

### Live doc_types (referenced in code + allowed by CHECK)

Payload-side snake_case (referenced in `src/digiquant_atlas/` or `scripts/`):
`deliberation_session_index`, `deliberation_transcript`,
`market_thesis_exploration`, `thesis_vehicle_map`, `pm_allocation_memo`,
`asset_recommendation`, `rebalance_decision`, `research_delta`,
`research_baseline_manifest`, `document_delta`, `research_changelog`,
`evolution_sources`, `evolution_quality_log`, `evolution_proposals`,
`pipeline_review`, `weekly_digest`, `monthly_digest`, `master_digest`,
`delta_digest`, `delta_segment`, `deep_dive`, `sector_report`,
`opportunity_screen`, `research_closeout`.

Title-Case labels persisted in `documents.doc_type` column (checked by
`chk_documents_doc_type`):
`'Daily Digest'`, `'Daily Delta'`, `'Weekly Rollup'`, `'Monthly Summary'`,
`'Deep Dive'`, `'Research Delta'`, `'Research Baseline Manifest'`,
`'Document Delta'`, `'Research Changelog'`, `'Rebalance Decision'`,
`'Asset Recommendation'`, `'Deliberation Transcript'`,
`'Deliberation Session Index'`, `'Market Thesis Exploration'`,
`'Thesis Vehicle Map'`, `'PM Allocation Memo'`, `'Sector Report'`,
`'Evolution Sources'`, `'Evolution Quality Log'`, `'Evolution Proposals'`,
`'Pipeline Review'`.

### Potentially orphaned (allowed by CHECK but no live writer)

- `'Daily Delta'` — no producer found in current `src/digiquant_atlas/`; one
  reference in `frontend/lib/queries.ts` as a literal. Likely historical.
  **Freeze for 1 sprint; candidate for drop in 025.**
- `'Weekly Rollup'` vs payload `weekly_digest` — title/payload mismatch; the
  writer uses `weekly_digest`. Likely a legacy label. **Freeze; candidate for
  drop in 025.**
- `'Monthly Summary'` vs payload `monthly_digest` — same pattern as above.
  **Freeze; candidate for drop in 025.**

### Referenced in payloads but not in CHECK constraint

The following payload `doc_type` values appear in scripts/ but are *not* in
the `chk_documents_doc_type` allow-list, so they land with `documents.doc_type
IS NULL` (the CHECK allows NULL):

- `opportunity_screen` — emitted in Track B phase 3 (validate_pipeline_step.py).
  Intentional: the opportunity screen is an intermediate payload, not a
  first-class document label. **No action.**
- `markdown_legacy` — legacy transitional payloads (pre-db-first). **No action.**
- `digest_snapshot`, `delta_request` — classifier kinds, never written as
  `documents.doc_type`. **No action.**

### Not dropped in this migration

Per the plan, doc_types are **frozen for one sprint**. Any drop happens in a
future migration (025) with its own ADR addendum, after Wave 1 lands and we've
verified no backfill scripts still produce the questionable labels.

## Appendix B — Follow-up work

- **Wave 2:** psycopg live round-trip test for migration 024 before any
  adapter writes land. The existing `tests/test_migration_024.py` is hermetic
  (SQL text assertions only); a throwaway Postgres round-trip is needed once
  the Wave 2 adapters start writing to these tables.
- `analyst_coverage.analyst_role` carries a CHECK constraint listing the
  canonical taxonomy (`asset_analyst`, `sector_analyst`, `macro_analyst`) +
  NULL. Canonical role definitions live in `docs/agentic/HERMES_SUBGRAPH.md`;
  a new role requires both an ADR addendum and a migration to extend the
  CHECK list.
