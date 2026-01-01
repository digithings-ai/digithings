# 0024. Drop PR-linkage enforcement, keep it as a convention

## Status

Accepted — 2026-08-13

## Context

`ci-pr-hygiene.yml` ran a `check-linkage` job ("Require Fixes #N or
task/N-* branch") on every PR, requiring one of: a `task/<N>-slug` branch, a
`module/*` / promotion / `docs/*` / `chore/*` bypass, or an explicit
`Fixes/Closes/Resolves #N` keyword in the PR body or title.

Auditing the last 100 PRs against this gate surfaced two things:

1. **It was never a required status check.** `main`'s branch protection lists
   only `Every commit reaching main was reviewed`; `develop` has no required
   checks at all. A failing `Require Fixes` run could not, and never did,
   block a merge.
2. **It still cost nothing to fail, so failing changed nothing.** PR #2227
   failed **twice** and merged anyway. PR #2296 is a second instance of the
   same outcome, not a rework case: its `ci-pr-hygiene` runs on the same head
   SHA went success (20:46) → success (20:48) → **failure** (21:58), and it
   merged at 22:01 — three minutes after the failing run, with the check
   still red and no `Fixes/Closes/Resolves` keyword in the body. Both PRs
   show the same thing: the check could go red and the merge happened anyway,
   because nothing consumed its result.

Replaying the gate's own bypass logic over 142 historical `main` PRs (see the
prior CLAUDE.md text, preserved below) had already shown the gate was
inconsistent even on its own terms — 38 of 83 direct `develop`-headed
promotions would have failed it. That inconsistency plus the "never actually
blocks anything" finding removed the case for keeping it as CI.

The historical replay text, preserved for the record:

> Of 142 PRs merged into `main`, 50 were promotions opened from a
> `chore/promote-develop-to-main-*` head and passed automatically via the
> `docs/chore` bypass, while 83 were opened from `develop` directly. Replaying
> the gate over those 83: 38 failed, 45 passed — 35 of the 45 by a deliberate
> standalone `Fixes #N` line and 10 by a keyword that merely appeared
> somewhere in the prose. So the gate was not blind to promotions; it was
> inconsistent about them, and a bare `develop` head was the case it had no
> rule for.

## Decision

- Remove the `check-linkage` job from `ci-pr-hygiene.yml` entirely (the
  `coverage`/TSV job in the same workflow is unaffected — different
  invariant, kept).
- Keep issue linkage as a **convention**, not a gate: prefer
  `task/<N>-slug` branches (created by `make task ISSUE=N`), or a `Fixes #N`
  line in the PR body for everything else. Nothing in CI checks this anymore.
- Collapse the ~49-line branching/linkage explanation in `CLAUDE.md` down to
  the essential branch-tier diagram and this convention, since the bypass
  taxonomy that justified most of that length no longer needs justifying.

## Consequences

- One fewer CI job per PR; `issues: read` permission dropped from the
  workflow since nothing in it reads issues anymore.
- `develop` and `main` can genuinely accumulate commits with no backlog
  link — this was already true in practice (the gate never blocked it), so
  nothing observable changes; it's now just honestly reflected in CLAUDE.md
  instead of implied to be enforced.
- `ci-review-coverage.yml` (the "every commit reaching main was reviewed"
  gate) is unaffected — it never depended on linkage and remains the one
  gate on `main` that's actually required.
- If backlog-traceability enforcement is wanted again later, do it as a
  non-blocking report (e.g. a scheduled job that lists unlinked merged PRs)
  rather than a per-PR check with no bite — a report can't produce the
  fail-twice-and-merge-anyway outcome this ADR is closing out.
