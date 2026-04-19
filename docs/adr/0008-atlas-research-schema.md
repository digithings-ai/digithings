# ADR 0008: Atlas Research — State Model and Output Persistence Schema

**Status:** proposed
**Date:** 2026-04-19

## Context

[ADR-0004](0004-atlas-pricing.md) was accepted on 2026-04-19, unblocking Atlas execution. Epic [#10](https://github.com/digithings-ai/digithings/issues/10) now needs a concrete research subgraph (scaffolding spike in [issue #146](https://github.com/digithings-ai/digithings/issues/146)) that produces outputs the Atlas UI can render across sessions and after process restarts.

Two separate data concerns sit inside "Atlas research":

1. **In-flight state.** The research subgraph is a LangGraph flow with nodes that plan queries, fan out to DigiSearch, collect sources, synthesize findings, and hand off to the persist step. This state is ephemeral execution-context data — it exists to resume a run that crashed mid-flight, not to serve UI reads.
2. **Durable research outputs.** Once a run completes, the artifact (query, domain, sources, findings, synthesis) is an end-user asset: it outlives the execution, it appears in a "my research" list in the Atlas UI, it is referenced from backtest runs, and it must be queryable by tenant and owner for authorization.

The repo already distinguishes these layers for other workflows — `DIGI_CHECKPOINTER` (`memory` / `sqlite` / `postgres`, see project `CLAUDE.md`) drives LangGraph resumability, while business data lives in component-owned Postgres tables (DigiKey's `digikey_api_keys`, DigiChat's Drizzle schema). Atlas needs the same separation made explicit before #146 writes code against either layer.

This ADR fixes: the shape of the in-flight state object, the shape of the durable table, which layer owns what, and how schema changes are versioned.

## Decision

**Two layers, two shapes.** In-flight research state is a Pydantic v2 model serialized by the existing LangGraph checkpointer. Durable outputs live in a new dedicated Postgres table `atlas_research`, owned by DigiGraph.

### In-flight state — `AtlasResearchState` (Pydantic v2, LangGraph checkpointer)

Fields passed between nodes of the Atlas research subgraph. Serialized by the LangGraph checkpointer configured via `DIGI_CHECKPOINTER`. No separate persistence path; it is discarded (or garbage-collected by the checkpointer TTL) once the run reaches the persist node.

| Field | Type | Meaning |
|---|---|---|
| `query` | `str` | The user-submitted research question |
| `domain` | `str` | Atlas research domain (e.g., `"equities.us"`, `"fx.g10"`) — used to route sources and scope persistence |
| `sources` | `list[AtlasSource]` | Raw retrieval hits collected across fan-out nodes |
| `findings` | `list[AtlasFinding]` | Structured findings extracted from sources |
| `synthesis` | `str` | Final narrative synthesis returned to the caller |
| `persisted_id` | `UUID \| None` | Set by the persist node once the row is written; downstream nodes / callers use this as the canonical handle |

`AtlasSource` and `AtlasFinding` are Pydantic v2 sub-models (fields documented alongside the scaffold in #146 — not fixed here, because additive changes to those sub-shapes should not require an ADR amendment).

This matches the TypedDict-vs-Pydantic convention already present in `digigraph/src/digigraph/graph/state.py`: the supervisor-level `WorkflowState` is a LangGraph TypedDict with last-writer-wins reducers, while subgraph-internal state is free to be a Pydantic model where structured validation is worth the cost. Atlas research is subgraph-internal.

### Durable persistence — new `atlas_research` Postgres table

Owned by DigiGraph (same service that runs the subgraph). Written by the `persist_node` at end of a successful run.

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | Generated at persist time; returned as `persisted_id` to in-flight state and to the caller |
| `owner_id` | `TEXT NOT NULL` | From the DigiKey JWT `sub` claim on the originating request |
| `tenant_slug` | `TEXT NOT NULL` | From the DigiKey JWT tenant claim; used for tenant-scoped list queries |
| `query` | `TEXT NOT NULL` | Verbatim user query — indexed for "my recent research" search |
| `domain` | `TEXT NOT NULL` | Atlas research domain; indexed because Atlas UI filters by it |
| `findings_json` | `JSONB NOT NULL` | Serialized `list[AtlasFinding]` |
| `sources_json` | `JSONB NOT NULL` | Serialized `list[AtlasSource]` |
| `synthesis` | `TEXT NOT NULL` | Final narrative |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | — |
| `schema_version` | `SMALLINT NOT NULL DEFAULT 1` | Starts at 1; see Versioning |

Indexes at launch: `(tenant_slug, owner_id, created_at DESC)` for the Atlas UI list view, `(tenant_slug, domain, created_at DESC)` for domain-filtered views. Both are tenant-prefixed so no cross-tenant scan is ever possible from an application query.

### Why not the checkpointer for persistence

The LangGraph checkpointer is built for *resumable execution*. Its contract is "if a run crashes, you can pick up mid-graph"; its schema is graph- and version-coupled; its TTL is whatever fits resumability needs, not retention needs. Treating it as a durable artifact store conflates three concerns that should stay separate:

1. **Retention.** Atlas research outputs need a long retention policy driven by the customer and their plan; checkpoints want a short one driven by resumability (days, not months).
2. **Queryability.** Atlas UI lists research by `owner_id`, `tenant_slug`, `domain`, `created_at`. Checkpointer rows are keyed by LangGraph thread id — wrong index, wrong shape, wrong lifecycle.
3. **Schema stability.** The checkpointer schema is owned by LangGraph and can evolve on library upgrade. A table we own cannot.

The two layers serve different purposes and are cleanest when they stay distinct. This matches the general pattern laid out in project `CLAUDE.md` ("Checkpointing: LangGraph checkpoint backend via `DIGI_CHECKPOINTER`") — the checkpointer is for state, not for artifacts.

### Versioning policy

`schema_version` is a `SMALLINT` column on every row, starting at 1. The policy is:

- **Additive changes** (adding a new optional JSONB key, adding a new nullable column) do **not** bump `schema_version`. Readers tolerate missing fields.
- **Breaking changes** (removing a field, changing a field's meaning, renaming a column) bump `schema_version` and ship with a migration that either backfills the new shape or tags old rows so readers dispatch on version.
- Readers check `schema_version` only when they need a field whose meaning has changed; the common case stays version-agnostic.

This is the cheapest versioning scheme that still gives us a rollback/rollforward story for the handful of times Atlas's artifact shape will change before GA. It does not need to be `JSONB` internal versioning, a `Pydantic` discriminator, or an Event-Sourcing log — any of those would be overengineered for a table that sees low-cardinality shape changes.

## Consequences

**Positive**

- Clear separation: in-flight execution state (checkpointer) versus durable end-user artifacts (Postgres). Each has the right lifecycle, retention, and query shape for its job.
- Atlas UI can list, filter, and retrieve research with tenant-scoped Postgres queries — no LangGraph internals leak into the read path.
- `schema_version` gives a cheap escape hatch for the breaking changes that will inevitably happen before GA, without forcing a migration on every additive change.
- Persistence lives in DigiGraph, which already owns the subgraph — no new service.
- JWT-derived `owner_id` / `tenant_slug` plus compound indexes keep authorization checks simple and cross-tenant reads impossible at the query layer.

**Negative / tradeoffs**

- **New Postgres dependency for DigiGraph.** DigiGraph currently carries a Postgres dependency only via the optional `postgres` checkpointer backend. This ADR makes Postgres a hard dependency for any deployment with Atlas enabled. DigiKey already requires Postgres in production, so the operational pattern exists — but the compose files and deploy docs will need updating.
- **JSONB is flexible but weakly typed.** `findings_json` / `sources_json` are JSONB blobs; schema correctness lives in the Pydantic models, not the database. We trade DB-level validation for iteration speed and tolerate a shape-drift risk mitigated by `schema_version` and by the Pydantic round-trip on every read.
- **Read path not yet defined.** This ADR covers the write shape. Read endpoints (`GET /v1/atlas/research/{id}`, list endpoints, pagination) are intentionally deferred to follow-up issues — a premature read API would lock in details before Atlas UI requirements are firm.
- **One durable shape for all Atlas plans.** Pricing tiers (ADR-0004) differ in metered units, not in artifact shape; persisted research looks the same whether the user is on Free or Enterprise. Plan-gated retention lives in a future retention job, not in this table.

## Alternatives considered

1. **Checkpointer for persistence too.** Rejected. Wrong tool — checkpointer state is execution context, not a user artifact. Retention, queryability, and schema-ownership all point the opposite way. Reusing it would save a table but create a tangle between library-owned state and product-owned data.
2. **One `data JSONB` column, no first-class `query` / `domain` / `owner_id` columns.** Rejected. Loses indexable access to the three fields the Atlas UI filters by most (owner, tenant, domain). A JSONB-only shape is a short-term convenience that creates a read-path refactor as soon as the list view ships.
3. **Fully normalized schema** (`atlas_sources` table, `atlas_findings` table, FK to `atlas_research`). Rejected for launch. Overengineered for an MVP whose write pattern is "insert one complete artifact atomically" and whose read pattern is "render the whole artifact". Normalization becomes worth it only when another table needs to join to sources or findings independently; add then, not now.
4. **Event-sourced log of research events.** Considered. Rejected: the subgraph already emits DigiSmith spans for observability, and there is no second reader for a research event stream today. The persisted row is the artifact the product needs.
5. **Store research in DigiSearch vector store alongside ingest docs.** Rejected. DigiSearch is for retrieval over ingested content; Atlas research outputs are user-owned artifacts with a different authorization model (per-owner, not per-tenant corpus). Cross-referencing a completed research row *into* DigiSearch as a retrievable source is a reasonable future enhancement; storing it there as the primary record is not.

## Implementation sketch

1. **Migration for the `atlas_research` table.** Alembic (or equivalent — match DigiGraph's existing migration tooling once #146 lands). Include the two compound indexes described above.
2. **New file `digigraph/src/digigraph/models/atlas.py`.** Contains:
   - `AtlasResearchRow` — SQLAlchemy ORM model mapped to `atlas_research`.
   - `AtlasResearchPersisted` — Pydantic v2 model for read-side serialization; the read endpoints in follow-up issues return this.
   - `AtlasSource`, `AtlasFinding` — Pydantic v2 sub-models shared with the in-flight state.
   - `AtlasResearchState` — Pydantic v2 in-flight state (the LangGraph subgraph field container).
3. **`persist_node` in the Atlas subgraph** (landing with #146). Takes the final `AtlasResearchState`, extracts `owner_id` and `tenant_slug` from the propagated JWT claims (same pattern DigiQuant uses for the forwarded `digi_bearer` in `WorkflowState`), writes one row, sets `persisted_id` on the returned state.
4. **Read endpoints** (follow-up issues, not this one). `GET /v1/atlas/research/{id}` and tenant-scoped list endpoints. Out of scope for this ADR beyond the statement that they will key on `(tenant_slug, owner_id, id)`.
5. **Tests.** Unit test for the Pydantic round-trip through JSONB; integration test for the persist-node write; a migration test verifying the indexes exist. CI should fail if a new ORM field is added without updating the Pydantic model or vice versa.

## Links

- Related: [issue #10](https://github.com/digithings-ai/digithings/issues/10) (epic), [issue #146](https://github.com/digithings-ai/digithings/issues/146) (scaffolding spike), [issue #147](https://github.com/digithings-ai/digithings/issues/147) (this ADR)
- Related: [ADR-0004](0004-atlas-pricing.md) — Atlas pricing (accepted 2026-04-19)
- Related: [`docs/VISION.md`](../VISION.md) — Atlas tiering
- State-model convention: [`digigraph/src/digigraph/graph/state.py`](../../digigraph/src/digigraph/graph/state.py)
- Checkpointer background: project `CLAUDE.md` → "Checkpointing"
