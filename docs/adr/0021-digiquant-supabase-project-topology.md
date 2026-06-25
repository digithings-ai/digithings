# ADR 0021: DigiQuant Supabase Topology — Consolidate the Shared Backend into the "core" Project

**Status:** accepted
**Date:** 2026-06-25

## Context

Epic [#1063](https://github.com/digithings-ai/digithings/issues/1063) introduces a
**strategy store** (per-strategy config, fitted calibration, executed trades, tearsheets,
live signals) to back DB-driven live tearsheets ([#1069](https://github.com/digithings-ai/digithings/issues/1069)),
and treats the market datasets (`price_history`, `price_technicals`, `trading_calendar`,
`economic_calendar`) as a **shared DigiQuant data layer** repurposable across the suite
(Olympus, twelve-x, the Slapper book).

[#1064](https://github.com/digithings-ai/digithings/issues/1064)'s first acceptance
criterion originally read *"new Supabase project, separate from the Olympus project."* On
inspection that is not feasible: the `digiquant.io` Supabase org is on the **free tier
(2-project limit)** and both slots are used — the Olympus/Atlas project (`project_id
"digiquant-atlas"`) and the **twelve-x** project (kept separate; it holds confidential
data). A third dedicated project cannot be provisioned without a paid upgrade.

Two facts make consolidation the pragmatic choice rather than a compromise:

- The shared market data **already lives in the Olympus project** (`price_history` 555k+
  rows, `price_technicals`, `trading_calendar`, `macro_series_observations`). It was never
  elsewhere — so the "shared data layer" already exists there.
- The strategy store is **net-new**: its tables reference only each other, so adding them
  to that project touches nothing that exists.

## Decision

**Repurpose the existing Olympus/Atlas project as the unified DigiQuant shared backend,
renamed `core`** (Supabase display name; `config.toml` keeps the stable local alias
`project_id "digiquant-atlas"`). twelve-x stays a separate project.

- **Add** the strategy store via an **additive-only** migration in this project's existing
  sequence: [`digiquant/supabase/migrations/046_strategy_store.sql`](../../digiquant/supabase/migrations/046_strategy_store.sql)
  — `CREATE TABLE IF NOT EXISTS` + `CREATE POLICY` on the five new tables, with **no**
  `DROP`/`ALTER`/`TRUNCATE` and zero references to existing objects.
- **No data migration.** The market datasets already reside here; nothing is moved or
  copied. This obviates [#1065](https://github.com/digithings-ai/digithings/issues/1065)'s
  cross-project copy (superseded — there are no longer two projects to copy between).
- **Logical separation preserved in code.** The accessor
  ([`digiquant.data.store`](../../digiquant/src/digiquant/data/store/)) resolves
  `SUPABASE_URL_DIGIQUANT` / `SUPABASE_SERVICE_ROLE_KEY_DIGIQUANT` and **falls back** to the
  shared `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`. Today both resolve to `core`; if the
  store ever graduates onto its own project (post free-tier), setting the `_DIGIQUANT` vars
  splits it off with **zero code change**.
- **RLS.** Public reference + tearsheet tables grant `anon SELECT`; the private
  `strategy_calibrations` sidecar gets no anon policy (RLS-on, zero-policy → empty reads for
  anon, full access for the service role; the migration-033 idiom).

## Consequences

**Positive**

- Works within the free tier — no new billing, no new CI connection, no data movement, and
  the riskiest epic step (#1065's price copy) disappears.
- The accessor's env-var indirection keeps the separation *design* intact: a future split is
  a config change, not a refactor.
- The prod touch is minimal and provably safe: new empty tables only.

**Negative**

- The strategy store and Olympus operational data share one project — one blast radius, one
  credential set, one RLS surface. The privacy boundaries (`strategy_calibrations`
  service-role-only; per-table RLS) are within-project rather than cross-project.
- `config.toml`'s `project_id` (`digiquant-atlas`) no longer matches the Supabase display
  name (`core`). The alias is kept for historical continuity (ADR-0011/0014 reference it);
  the mismatch is documented here and in `SCHEMA.md`.

## Alternatives considered

1. **A dedicated third Supabase project** (the original #1064 wording). Rejected: blocked by
   the free-tier 2-project limit; would require a paid upgrade. This was the initial plan
   until the constraint surfaced.
2. **Drop twelve-x to free a slot for a dedicated DigiQuant project.** Rejected: twelve-x
   holds confidential data and is a deliberately separate project.
3. **A separate Postgres schema inside `core`** (e.g. `strategy.*`). Rejected as needless:
   `public` + per-table RLS already gives the isolation the strategy store needs, and a
   second schema complicates PostgREST exposure and the accessor for no gain at this scale.

## Links

- Epic: [#1063](https://github.com/digithings-ai/digithings/issues/1063).
- Implements [#1064](https://github.com/digithings-ai/digithings/issues/1064); supersedes the
  cross-project copy in [#1065](https://github.com/digithings-ai/digithings/issues/1065);
  consumed by [#1066](https://github.com/digithings-ai/digithings/issues/1066),
  [#1069](https://github.com/digithings-ai/digithings/issues/1069).
- Migration: [`digiquant/supabase/migrations/046_strategy_store.sql`](../../digiquant/supabase/migrations/046_strategy_store.sql).
- Accessor: [`digiquant/src/digiquant/data/store/`](../../digiquant/src/digiquant/data/store/).
- RLS idiom precedent: [migration 033](../../digiquant/supabase/migrations/033_revoke_anon_run_diagnostics.sql).
