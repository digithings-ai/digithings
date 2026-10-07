# Dependency freshness radar — design note

- **Issue:** DIG-1515
- **Status:** Implemented (fix landed, awaiting first dispatch)
- **Date:** 2026-10-06, revised 2026-10-07
- **Author:** Architect
- **Supersedes:** the first draft of this note, which shipped a workflow that could not work. See "Correction" below.

## Problem

Every dependency floor in this monorepo is `>=`, not `==` or `~=`. The floor is
therefore not what we run. At develop `8de942f` we already resolve to
`cryptography 49.0.0` against a `>=42` floor, and `redis 8.0.1` against `>=5` —
seven and three majors past what anyone approved.

The issue is not drift. It is **invisibility**. Lock refreshes are reactive
(commit record: 2026-09-09, 2026-09-14 — both "regenerate uv.lock" after the
fact). Nobody refreshes to find out what changed, so a major arriving is
discovered mid-incident rather than on purpose.

This is visibility only. It changes no bound and bumps nothing.

## Options considered

**Option A — extend `pipeline-maintenance.yml`.** Add a job to the existing
maintenance workflow, which already runs dependency audits and creates labelled
issues. Cheapest in file count.

*Against:* that workflow is a broad grab-bag of unrelated maintenance checks.
The radar needs a schedule, a per-run issue, and a long PyPI fetch; folding it
in couples the radar's run history to unrelated maintenance failures and makes
the first dispatch hard to interpret in isolation.

**Option B — a dedicated workflow.** (chosen) Separate file, separate schedule,
separate issue. Costs one more workflow file; buys a clean run history and an
isolated `workflow_dispatch` that can be tested without touching maintenance.

**Option C — no code; a recurring human scan.** The R&D Lead already does this
ad hoc and filed the idea because it was not being asked for.

*Against:* a human scan is exactly the reactive-but-late pattern the issue
complains about. It works only while someone remembers.

Chose **B**. Confidence: medium-high. The A/B tradeoff is close; B is
preferred for testability, not because A is wrong.

## Design

- **Trigger:** `cron: "0 6 1 * *"` (monthly, 1st, 06:00 UTC) plus
  `workflow_dispatch`.
- **Input:** `uv export --frozen --all-packages --all-extras` against the
  checked-in `uv.lock`. 284 pinned packages today.
- **Comparison:** PyPI JSON API per package; newest non-prerelease release.
- **Classification:** major 🔴 / minor 🟡 / patch 🟢 / current ✅ / unknown ⚠️.
- **Output:** one deduplicated GitHub issue, searched by title, updated in place.
- **Permissions:** `contents: read`, `issues: write`. No lock mutation.

### Correction (2026-10-07)

The first implementation was reported as done on 2026-10-06. It could not have
worked. Three defects, all found by running it rather than reading it:

1. **Step outputs never written.** The report step `print`ed JSON to stdout but
   wrote nothing to `$GITHUB_OUTPUT`, so `steps.report.outputs.table` and
   `.summary` were empty. The issue would have been created with an empty table.
   Every other workflow in this repo uses `>> "$GITHUB_OUTPUT"`.
2. **It crashed on the first platform-conditional dependency.** `uv export`
   writes `colorama==0.4.6 ; os_name == 'nt' or sys_platform == 'win32'` — 26 of
   the 284 lines carry a PEP 508 marker. The regex captured the marker as part
   of the version and `packaging.version.parse` raised `InvalidVersion`, killing
   the step with exit 1 and zero output. Reproduced locally.
3. **`packaging` was not importable.** It is a transitive dependency, never a
   declared direct one, and the step ran a bare `python3` with no install. Fixed
   per the repo's existing #1715 rule — sync from the lock, no unpinned
   `pip install`.

Also: the logic moved out of the YAML into `scripts/dependency_freshness.py` so
it is testable without Actions, and dedup now searches by title instead of by a
`radar` label that does not exist in the repo.

Both prior claims — that the design note and workflow were "in place" — were
wrong about the repository as well: both files were untracked on disk in the
main checkout and had never been committed to any branch. They exist only in
local `dt-snapshot` commits.

### Verification

- 9 unit tests in `tests/scripts/test_dependency_freshness.py`, all passing.
- Full live run against the real `uv.lock`: exit 0, all 284 packages parsed,
  no crash.
- Live result independently reproduces the original finding:
  `cryptography 49.0.0 → 50.0.2`, `mcp` 1.29.0, `optuna` 4.9.0.
- `ruff check` and `ruff format --check` clean.

## Risks

- **284 sequential HTTPS calls to PyPI.** Roughly 2-4 minutes, and PyPI rate
  limits are the likely first failure. A `unknown` row now degrades gracefully
  instead of failing the run, but a heavily throttled run would post a noisy
  table. Acceptable for monthly; revisit if the closure grows much larger.
- **Posting 284 rows monthly** is a lot of issue body. The summary line is the
  signal; the table is the evidence. Acceptable, and it is what the R&D Lead
  asked for.
- **Not yet dispatched.** `workflow_dispatch` has never fired. The first
  production run is scheduled 2026-11-01, at which point GitHub disables
  scheduled workflows on repos with no activity, so it would likely no-op
  anyway until the repo is active. A manual dispatch is required.

## Not doing

- Not touching any bound. The floors may well be deliberate and correct.
- Not touching the `mcp` `<2` cap — that is DIG-1514, separate owner.
- Not running `uv lock --upgrade` as a dry-run diff. That is a real branch
  change and a separate half-day ask.