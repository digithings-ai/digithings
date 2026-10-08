# Dependency freshness radar — design note

- **Issue:** DIG-1515, cadence changed by DIG-2277
- **Status:** Shipped. Merged to `develop` as PR #5242 and dispatched by hand
  once on 2026-10-07 — the only `workflow_dispatch` it has needed, because the
  Worker's clock row took over from the start.
- **Date:** 2026-10-06, revised 2026-10-07, cadence amendment 2026-10-08
- **Author:** Architect
- **Supersedes:** the first draft of this note, which shipped a workflow that
  could not work. See "Correction" below — it had six defects, not three.
- **Amendment (DIG-2277, 2026-10-08):** the clock moved from `23 6 1 * *`
  (monthly) to `23 6 * * MON` (weekly). The radar edits one standing issue in
  place, so weekly adds no issues; and `security-pip-audit` / `security-npm-audit`
  already read the same `uv.lock` every Monday, so monthly reported new versions
  at a lower rate than it reported known vulnerabilities in them. Everything
  below that describes the *monthly* clock is a record of what DIG-1515 shipped,
  not of the current schedule.

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

- **Trigger:** `workflow_dispatch` only. The clock is **not** on GitHub: develop
  carries no `on.schedule` for any workflow
  (`tests/scripts/test_no_gha_schedules.py`), because every clock for this repo
  lives on the digithings-cron Worker and a GitHub cron would double-fire with
  it. The monthly clock is the `dependency-freshness` `wd()` row at
  `23 6 1 * *` in `apps/digithings-cron/src/jobs.ts` plus its `[triggers] crons`
  entry in `wrangler.toml`. `secret-staleness` is the precedent.
- **Input:** `uv export --frozen --all-packages --all-extras` against the
  checked-in `uv.lock`. 284 pinned packages today.
- **Comparison:** PyPI JSON API per package, 16-way concurrent; newest
  non-prerelease release.
- **Classification:** major 🔴 / minor 🟡 / patch 🟢 / current ✅ /
  no stable release 🟣 / unknown ⚠️. The last two are deliberately different:
  "no stable release" means PyPI answered and has only ever shipped prereleases,
  "unknown" means we could not read PyPI at all.
- **Output:** one deduplicated GitHub issue, searched by title, updated in place.
- **Permissions:** `contents: read`, `issues: write`. No lock mutation.

### Correction (2026-10-07)

The first implementation was reported as done on 2026-10-06. It could not have
worked. Six defects, all found by running it rather than reading it:

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
4. **A GitHub cron this repo cannot carry.** The shipped workflow used
   `on: schedule`. develop fails `tests/scripts/test_no_gha_schedules.py` on any
   workflow whose `on` contains `schedule` — every clock here lives on the
   digithings-cron Worker, and a GitHub cron on the default branch double-fires
   with it. The monthly clock moved to the Worker's `wd()` row.
5. **A sequential fetch slow enough to fake its own failures.** Measured on the
   real lock: **8m06s** for 284 packages, of which 6 `unknown` rows were our own
   10s read timeout firing under load rather than PyPI being unreachable. A row
   that reads "could not compare" because the radar was slow is the radar lying
   about its own gaps. Now a 16-way `ThreadPoolExecutor`: **36s**, and three
   consecutive runs at `0 unknown`. That narrows the window, it does not remove
   the mechanism — the 10s read timeout is unchanged, and a review reproduced 6
   self-inflicted `unknown`s at the same 16 workers under local load. See Risks.
6. **Six packages mislabelled.** All six `opentelemetry-instrumentation*` we lock
   have never shipped a non-beta on PyPI — every one of their 75 releases is a
   prerelease. Calling that `unknown` blamed our own network for PyPI's release
   policy. They now carry their own `no stable release` 🟣 label, so `unknown`
   keeps meaning exactly one thing: we could not read PyPI.

Also: the logic moved out of the YAML into `scripts/dependency_freshness.py` so
it is testable without Actions, and dedup searches by title — the run creates
the `radar` label it uses rather than assuming one already exists.

Both prior claims — that the design note and workflow were "in place" — were
wrong about the repository as well: both files were untracked on disk in the
main checkout and had never been committed to any branch. They exist only in
local `dt-snapshot` commits.

### Verification

- 38 tests green across three files: 21 in `test_dependency_freshness.py` (the
  script), 15 in `test_dependency_freshness_clock.py` (the clock wiring), and the
  2 pre-existing `test_no_gha_schedules.py` guard tests the radar must not break.
- `apps/digithings-cron` vitest: 71 passed across 7 files, including
  `uniqueEnabledCrons()`, which asserts the enabled cron set by exact ordered
  equality — the new `23 6 1 * *` had to be added at its `JOBS` position, not
  appended.
- Three full live runs against the real `uv.lock`: exit 0, all 284 packages
  parsed, no crash, 36s.
- Live result independently reproduces the original finding and widens it:
  `cryptography 49.0.0 → 50.0.2` 🔴, `mcp` 1.29.0 → 2.3.0 🔴, `optuna` 4.9.0 →
  5.0.0 🔴, plus 13 further majors visible only in the full closure
  (`openai`, `kubernetes`, `websockets`, `plotly`, `filelock`, `huggingface-hub`,
  `multidict`, `oauthlib`, `polars`, `polars-runtime-32`, `xxhash`, `pyee`,
  `uuid-utils`). Each pair re-verified against PyPI on 2026-10-07.
  The issue filed 3 majors because it listed direct dependencies; the radar reads
  the whole closure, so 16 is the honest number.
- `ruff check` and `ruff format --check` clean.
- **The one manual dispatch**, run 37636863094 on 2026-10-07 against the merged
  `develop`: exit 0 in 51s. `Parsed 284 pinned packages`, the guard step saw a
  non-empty `TABLE`, and the report landed as issue #5243 with the `radar`,
  `component:root` and `priority:low` labels applied — `radar` created by the
  run itself, which is the part that had never executed. `unknown` was 0.
  This is the first time the workflow has ever run, and it is the whole reason
  the review fixed `if: always()` first: before that fix, any upstream failure
  would have posted a blank table and called it success.

## Risks

- **284 HTTPS calls to PyPI**, now 16-way concurrent, measured at 36s. The pool
  is deliberately capped at 16 rather than one-thread-per-package: PyPI is a free
  public service and a monthly radar should not become someone else's rate-limit
  incident. If the closure grows past ~600 packages, revisit the worker count
  before revisiting the cadence.
- **A throttled run still degrades, and now visibly so.** The 16-way pool made
  self-inflicted timeouts rare (three consecutive runs at 0; a review reproduced 6
  under load at the same worker count), not impossible — the mechanism is a 10s
  read timeout, and concurrency only shrinks how often it fires. A throttled run
  therefore still posts `unknown` rows instead of comparisons. That is why the
  issue body spells out that `unknown` should be 0 and that a non-zero count means
  the scan itself was degraded — the failure mode is legible from the artifact
  rather than needing the reader to know the script.
- **Posting 284 rows monthly** is a lot of issue body. The summary line is the
  signal; the table is the evidence. Acceptable, and it is what the R&D Lead
  asked for.
- **The 2026-11-01 run is unattended.** GitHub disables scheduled workflows on
  repos with no activity, so the first Worker's `23 6 1 * *` firing may no-op
  until the repo is active again. Nothing in this job is time-critical — a
  missed month costs one stale report — but if the December issue does not
  appear, check repo activity rather than the workflow.
- **One thing the dispatch did not prove.** It created the report issue, so the
  dedup path (title search → `gh issue edit`) has still never executed. It
  fires on the first *second* run. If that path is wrong, the symptom is a
  duplicate radar issue rather than a missing one.

## Not doing

- Not touching any bound. The floors may well be deliberate and correct.
- Not touching the `mcp` `<2` cap — that is DIG-1514, separate owner.
- Not running `uv lock --upgrade` as a dry-run diff. That is a real branch
  change and a separate half-day ask.