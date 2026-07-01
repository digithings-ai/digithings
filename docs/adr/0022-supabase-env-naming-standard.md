# ADR 0022: Standardized Supabase Env Naming (`CORE_*` / `TWELVEX_*`)

**Status:** accepted
**Date:** 2026-06-25

## Context

Supabase connection env vars diverged across the codebase:

- digithings (Olympus/Atlas/prices) wrote to the core project via `SUPABASE_URL` /
  `SUPABASE_SERVICE_ROLE_KEY`.
- twelve-x used `SUPABASE_URL` (hardcoded) / `SUPABASE_SERVICE_KEY` (no `ROLE`).
- [#1064](https://github.com/digithings-ai/digithings/issues/1064) added a third pair,
  `SUPABASE_URL_DIGIQUANT` / `SUPABASE_SERVICE_ROLE_KEY_DIGIQUANT`, for the strategy store.

With Olympus and twelve-x now distinct Supabase projects ([ADR 0021](0021-digiquant-supabase-project-topology.md))
and the calendar consolidated into `core` ([#1066](https://github.com/digithings-ai/digithings/issues/1066)),
a single naming scheme is needed so any repo can reference the shared core project and its
own project unambiguously. The org-level core secret was renamed in GitHub already, so code
+ workflows must conform.

## Decision

One scheme, `{PROJECT}_SUPABASE_{URL,SERVICE_KEY}` — drop `ROLE`:

| Env var | Scope | Value |
|---------|-------|-------|
| `CORE_SUPABASE_URL` | GitHub **org** (all repos) | core/Olympus project URL |
| `CORE_SUPABASE_SERVICE_KEY` | GitHub **org** (all repos) | core project service-role key |
| `TWELVEX_SUPABASE_URL` | twelve-x repo only | twelve-x project URL |
| `TWELVEX_SUPABASE_SERVICE_KEY` | twelve-x repo only | twelve-x project service-role key |

The shared core key is an **org** secret (every repo's pipeline can write `core`); each
project's own key is a **repo** secret. Frontend `NEXT_PUBLIC_*` anon keys (public, browser)
are out of scope.

**Transition-safe migration (no pipeline breakage):**

- Code resolves `CORE_SUPABASE_* || <legacy names>` — read-new-fall-back-to-old. The legacy
  chain is `*_DIGIQUANT` (#1064) then `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`.
- Workflows set the new env names from the new secrets **and** keep the legacy env names
  populated from the same secrets, so any not-yet-migrated reader still works.
- Once every reader is on `CORE_*`, the legacy env names + secrets are dropped (follow-up).

## Consequences

**Positive**

- One predictable scheme across repos; the core key is defined once at the org level.
- Migration cannot break live pipelines — every reader has a working fallback and the
  workflows feed both names.

**Negative**

- Temporary redundancy: workflows map one secret to two env names, and code carries a
  fallback chain, until the cleanup pass removes the legacy names.
- `digiquant/scripts/atlas/*` (ruff-exempt legacy ops) carry the same inline fallback; they
  are not lint-enforced, so they're verified by AST-parse + the workflow env.

## Alternatives considered

1. **Keep per-repo names, alias in CI only.** Rejected: the code still reads divergent names;
   the divergence (and the `ROLE` inconsistency) persists.
2. **Hard rename with no fallback.** Rejected: any missed reader or unsynced secret breaks a
   live pipeline run. The fallback chain removes that risk.

## Links

- Implements [#1090](https://github.com/digithings-ai/digithings/issues/1090).
- Builds on [ADR 0021](0021-digiquant-supabase-project-topology.md) (project topology) and
  the #1066 calendar consolidation.
