# ADR 0009: Atlas Persistence — Reuse Existing Supabase Schema

**Status:** accepted
**Date:** 2026-04-20
**Supersedes:** [ADR-0008](0008-atlas-research-schema.md)

## Context

ADR-0008 (2026-04-19) proposed a dedicated Postgres table `atlas_research` owned by DigiGraph to hold Atlas research outputs. Issue [#176](https://github.com/digithings-ai/digithings/issues/176) then landed the actual Atlas → DigiGraph migration, and during implementation it became clear that:

- The existing `apps/digiquant-atlas/` system already writes every segment research document to Supabase `documents` (keyed by `(date, document_key)`) and digest snapshots to `daily_snapshots` (keyed by `date`). Those tables carry a year of production data and are read by the deployed DigiQuant Atlas frontend.
- ADR-0008's proposed `atlas_research` table duplicates what `documents` already stores, with a different shape and ownership. Shipping it would fork Atlas persistence across two tables and force every downstream reader (frontend, Phase 9 evolution, BI queries) to know which bucket to read from.
- The DigiQuant Atlas frontend at `digiquant.io` reads from `documents` today; migrating it to `atlas_research` is out of scope for #176.

## Decision

Reuse the existing Supabase schema (`documents`, `daily_snapshots`, `price_technicals`, `macro_series_observations`, `positions`, etc.) for Atlas persistence. Do not create a new `atlas_research` table.

The sub-graph's Supabase adapter (`digiquant_atlas/supabase_io.py`, landed in commit 3 of the #176 migration) writes to these existing tables via `publish_document(..., on_conflict="date,document_key")` and `publish_daily_snapshot(..., on_conflict="date")`. Legacy operator scripts (`scripts/publish_document.py`, `scripts/materialize_snapshot.py`) wrote to the same tables with the same unique keys and are frozen in commit 9 of the migration so the two paths never write concurrently.

ADR-0008 is **superseded**: its `atlas_research` schema is not created, and its `AtlasResearchState` recommendation is still in force (that part was about the in-flight Pydantic state model, which is the right call and lives in `src/digiquant_atlas/state.py`). Only ADR-0008's durable-persistence decision is overturned by this ADR.

## Consequences

**Positive**

- One system of record for Atlas artifacts — no schema fork, no duplicate-write risk, no reader migration required.
- The existing DigiQuant Atlas frontend keeps working unchanged; it reads live from `documents` / `daily_snapshots`.
- Sub-graph writes and legacy scripts share `(date, document_key)` unique keys, so replays and concurrent writes are deterministic (last-writer-wins on the specific key).
- Supabase migrations `009` (documents_db_first), `014` / `019` (doc_type extensions), `020` (track_b_thesis), `023` (pipeline_review) stay authoritative; no new migrations for Atlas core.

**Negative**

- `documents` carries a wider schema than a dedicated `atlas_research` table would (phase, category, segment, sector columns that are relevant for only some doc_types). This is a mild denormalization cost — same cost the legacy system already pays.
- Adding a richer provenance field for carry-vs-fresh (`segment_freshness` on the digest snapshot) is still a schema change but a small additive one; handled inside commit 7 of the migration rather than by ADR.
- When we eventually want per-tenant row-level access control on Atlas research (ADR-0008's `owner_id` / `tenant_slug` motivation), we'll add those columns to `documents` instead of creating a new table — the work is similar in scope to the `atlas_research` path ADR-0008 proposed.

## Alternatives considered

1. **Ship both tables in parallel for a transition period.** Rejected. Parallel writes to different tables with different keys creates a reconciliation problem. The operational risk is worse than the cleanup cost of just not forking.
2. **Build `atlas_research` per ADR-0008 and migrate `documents` into it.** Rejected for #176. Out of scope — the migration's job is to land a scheduled sub-graph equivalent of the legacy pipeline, not to reshape the persistence layer.
3. **Keep ADR-0008 as-is, document-only, and never implement it.** Rejected — the stale ADR would mislead future readers about the intended schema. An explicit supersedes relationship is cleaner.

## Links

- [ADR-0008](0008-atlas-research-schema.md) — superseded by this ADR.
- Implementation: `apps/digiquant-atlas/src/digiquant_atlas/supabase_io.py`, [PR #243](https://github.com/digithings-ai/digithings/pull/243).
- Migration plan: `~/.claude/plans/1-yes-use-the-crispy-sky.md` (approved 2026-04-20).
- Related Supabase migrations: `apps/digiquant-atlas/supabase/migrations/009_documents_db_first.sql` and onward.
