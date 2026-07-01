# ADR-0014 — Atlas belongs in `digiquant/`, not `apps/`

**Status:** Accepted
**Date:** 2026-04-23
**Related epic:** [#297](https://github.com/digithings-ai/digithings/issues/297) (closed 2026-04-27)
**Amends:** [ADR-0009](0009-frontend-umbrella.md) (un-defers the Atlas frontend relocation item)
**Amended by:** [ADR-0015](0015-atlas-vs-hermes.md) (2026-04-28) — splits the Atlas package into research (`digiquant.olympus.atlas`) and analysis (`digiquant.olympus.hermes`) sub-packages. The "Atlas in `digiquant/`" decision stands; this ADR's "Atlas package" references should now be read as "the research half of the Atlas package."

## Context

Atlas — the DigiQuant research pipeline and frontend — currently lives under
`apps/digiquant-atlas/`. That placement made sense when Atlas was an
experimental standalone project, but it now creates three concrete problems:

1. **Tooling duplication.** `apps/digiquant-atlas/` carries its own
   `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, and CI workflows independent
   of the `digiquant/` module. Every tooling change (ruff config, pytest
   setup, Docker base image) must be applied in two places.

2. **Package namespace mismatch.** The Python package is `digiquant_atlas`
   (importable as `import digiquant_atlas`), which is disconnected from the
   `digiquant.*` namespace that owns the rest of the quant stack. Introspection,
   type checking, and dependency graphs all see it as a separate top-level
   package.

3. **Frontend umbrella misalignment.** ADR-0009 established that all DigiThings
   web frontends live under `frontend/`. It explicitly deferred the physical
   relocation of `apps/digiquant-atlas/frontend/` to `frontend/atlas/` with
   the note "keeping it nested under the research project is fine for now."
   That deferral is no longer appropriate: Atlas is a first-class DigiQuant
   product, its frontend is actively maintained, and keeping it outside
   `frontend/` creates a persistent exception to an otherwise clean rule.

Atlas is not a research prototype anymore. It runs a scheduled LangGraph
sub-graph inside DigiGraph (landed in [PR #243](https://github.com/digithings-ai/digithings/pull/243)),
persists to the same Supabase schema as every other DigiQuant surface
(ADR-0011), and carries first-class deliberation tables (ADR-0010). Treating
it as an `apps/` side-project understates its role in the product family and
makes it harder to evolve as an integrated part of `digiquant/`.

## Decision

Atlas is a DigiQuant product. Its Python code becomes `digiquant.olympus.atlas`
(namespace package inside `digiquant/src/digiquant/olympus/atlas/`) and its frontend
moves to `frontend/atlas/`, consistent with ADR-0009.

Specifically:

- **Python package:** `apps/digiquant-atlas/src/digiquant_atlas/` becomes
  `digiquant/src/digiquant/olympus/atlas/`. The top-level `digiquant_atlas` distribution
  is retired; `digiquant` becomes the sole installable for the quant stack.
  Import paths change from `digiquant_atlas.*` to `digiquant.olympus.atlas.*`.

- **Frontend:** `apps/digiquant-atlas/frontend/` moves to
  `frontend/atlas/`. The root `package.json` workspaces already cover
  `"frontend/*"`, so no glob change is needed; the now-empty
  `"apps/*/frontend"` entry is dropped.

- **Supabase migrations:** The migrations under
  `apps/digiquant-atlas/supabase/migrations/` are the canonical source for
  Atlas schema. They are not relocated in this ADR — a follow-up issue (#TBD
  after #315 and #300 land) will decide whether to consolidate them into a
  top-level `supabase/` directory or keep them in `digiquant/supabase/`.

- **CI:** The four workflow files under `apps/digiquant-atlas/.github/workflows/`
  (`ci.yml`, `deploy.yml`, `daily-price-update.yml`, `pipeline-meta-review.yml`)
  are deleted. Atlas is covered by the root `.github/workflows/` CI,
  with path filters updated to `digiquant/**` and `frontend/atlas/**`.

- **Ancillary artefacts** (`agents/`, `cowork/`, `data/`, `docs/`, `config/`,
  `scripts/`, `templates/`, `skills/`) that currently sit alongside the Python
  source in `apps/digiquant-atlas/` move to `digiquant/` in the same phase as
  the Python package, or are archived if no longer needed.

## Consequences

**Positive:**

- One `pyproject.toml` and one `CLAUDE.md` govern the entire quant stack.
  Ruff, pytest, Docker, and agent configuration are no longer duplicated.
- `import digiquant.olympus.atlas` reads as a natural extension of the module; tooling
  that understands Python namespaces (mypy, pyright, dependency scanners)
  sees Atlas as part of `digiquant` automatically.
- The `frontend/` umbrella holds every DigiThings web surface with no
  exceptions. ADR-0009's deferred `frontend/atlas/` relocation item is resolved.
- The product family narrative is clean: `digiquant/` owns the full quant
  engine — strategies, backtesting, Atlas research sub-graph, and the
  Atlas frontend.

**Negative / tradeoffs:**

- `apps/digiquant-atlas/` import paths (`digiquant_atlas.*`) appear throughout
  DigiGraph sub-graph wiring, Supabase adapter references, and the frontend's
  API client. All callers must be updated in the Python-move phase (#315).
- The `"apps/*/frontend"` workspace glob must be dropped atomically with the
  frontend move (#300), not before, to avoid a broken-workspace window. CI
  path-filter updates for `frontend/atlas/**` also land in #300.
- Supabase migration paths embedded in CI scripts and `RUNBOOK.md` references
  will need updating when migrations are eventually consolidated (deferred).
- `apps/digiquant-atlas/` carried standalone `RUNBOOK.md`, `SETUP_GUIDE.md`,
  and `skills/` that are Atlas-specific. These are migrated into
  `digiquant/docs/` during the cleanup phase; contributors who have bookmarked
  the old paths will need to update their references.

## Migration phases

| Phase | Issue | Description |
|-------|-------|-------------|
| 1 | [#315](https://github.com/digithings-ai/digithings/issues/315) | Python package move — `digiquant_atlas` → `digiquant.olympus.atlas`; update all import sites in DigiGraph, tests, and CI |
| 2 | [#300](https://github.com/digithings-ai/digithings/issues/300) | Frontend move — `apps/digiquant-atlas/frontend/` → `frontend/atlas/`; drop `apps/*/frontend` glob, update CI path filters |
| 3 | TBD | Supabase migration consolidation — decide canonical home for `supabase/migrations/`; update CI and RUNBOOK paths |
| 4 | TBD | `apps/digiquant-atlas/` cleanup — delete shell, migrate ancillary docs/scripts into `digiquant/`, remove stale CI workflows |

Phases 1 and 2 are independent and may land in either order; they must both
be complete before phase 4.

## Links

- Related epic: [#297](https://github.com/digithings-ai/digithings/issues/297) — Migrate Atlas from `apps/` into `digiquant` module
- Child issues: [#315](https://github.com/digithings-ai/digithings/issues/315) (Python move), [#300](https://github.com/digithings-ai/digithings/issues/300) (frontend move)
- Amends (un-defers): [ADR-0009](0009-frontend-umbrella.md) — frontend umbrella (Atlas frontend relocation was explicitly deferred)
- Cross-reference: [ADR-0010](0010-atlas-first-class-thesis-deliberation.md) — Atlas first-class deliberation tables
- Cross-reference: [ADR-0011](0011-atlas-supabase-persistence.md) — Atlas Supabase persistence
