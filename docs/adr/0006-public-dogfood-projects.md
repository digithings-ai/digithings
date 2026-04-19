# ADR 0006: Public Dogfood Projects in `docs/projects/`

**Status:** accepted
**Date:** 2026-04-18

## Context

DigiThings maintains two distinct categories of project directories:

1. **`projects/`** — confidential client pilots and engagements (e.g. `projects/sitaas/`). These contain connection strings, client secrets, and proprietary config. They are excluded from version control via the root-anchored `.gitignore` pattern `/projects/` so they are never committed or pushed to public remotes.

2. **`docs/projects/`** — committed public dogfooding projects used to demonstrate or validate the DigiThings stack. For example, `docs/projects/digithings-guide/` is the ecosystem RAG project indexed at `chat.digithings.ai`.

This split became explicit during PR #94, which introduced the `digithings-guide` project as a committed reference implementation. The Claude Code guardrail enforced the distinction: writing under `projects/` is blocked on non-`task-N-*` branches, while `docs/projects/` is an unrestricted documentation path. The `.gitignore` anchor already carried a comment marking the intent, but no ADR recorded the convention.

## Decision

- **`projects/` (repo root)** is strictly private. The `/projects/` root-anchored `.gitignore` pattern ensures nothing under this directory is ever committed. Agents must never commit files here.
- **`docs/projects/` is the canonical home for committed public DigiThings projects** — reference implementations, dogfood stacks, and demo projects that are safe to ship in the public repo.
- The `.gitignore` file anchors `/projects/` (root-only) so that `docs/projects/` is not captured by the exclusion.

### Rule for agents

When creating or referencing a DigiThings project that will be committed to the repo:
- Use `docs/projects/<project-name>/` as the destination.
- Never write under `projects/` expecting it to be committed — it will be silently excluded.

## Consequences

**Positive:**
- Clear, enforced separation between confidential client work and committed public demos.
- `.gitignore` root-anchor means the rule is machine-enforced, not documentation-only.
- Claude Code guardrail blocks writes to `projects/` on non-task branches, adding a second layer of protection.
- Agents have an unambiguous location (`docs/projects/`) for any committed reference implementation.

**Negative / tradeoffs:**
- The nested `docs/projects/` path is slightly counterintuitive — a project that lives under `docs/` feels like documentation rather than a runnable stack. The trade-off is accepted because: (a) these are reference/demo projects, (b) `docs/` is the unrestricted committed path, and (c) the guardrail enforces correctness mechanically.

## Links

- Context: PR #94 (digithings-guide project indexing ecosystem docs)
- Related: ADR-0001 (DigiThings Project Spec — defines what a project directory contains)
- Related: ADR-0002 (Domain Unification — `docs/projects/digithings-guide/` serves `chat.digithings.ai`)
- `.gitignore` lines 16–17 (root-anchor comment and pattern)
- `docs/projects/digithings-guide/` — first committed public dogfood project
