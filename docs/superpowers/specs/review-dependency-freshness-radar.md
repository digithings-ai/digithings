# Review — DIG-1515 dependency freshness radar (PR #5242)

- **Reviewer:** fresh-context subagent (did not write the code)
- **Subject:** PR #5242, `DIG-1515-dependency-freshness-radar` → `develop`, base tip as fetched
- **Date:** 2026-10-07
- **Verdict:** ship after fixes
- **Severity counts:** blocker 0 · major 1 · minor 5 · nit 6
- **Disposition (2026-10-07, Architect):** all 1 major, 5 minor and 6 nit
  findings addressed on this branch. Resolutions are in "Resolution" below.

Every finding below was verified with a command or by reading the exact lines.
Commands are listed at the bottom.

## Findings

| severity | file:line | what is wrong | why it matters |
|---|---|---|---|
| major | `.github/workflows/pipeline-dependency-freshness.yml:70` (+`:108`) | `if: always()` on the create/update step, feeding `gh issue edit --body "$BODY"` from `steps.report.outputs.*` | When any earlier step fails the outputs are empty, so the step overwrites the standing radar issue with a blank table **and reports success**. The fragile step is the 2.4 GB `uv sync` at `:48`. Rendered degraded body verified in a `bash -e` simulation. |
| minor | `scripts/dependency_freshness.py:69-82` | `latest_stable` filters prerelease/dev but **not yanked** releases | Verified live: the radar reports `narwhals → 2.27.0`, every file of which is yanked on PyPI (`2.26.0` is the installable latest). One permanently wrong row today; it accumulates. |
| minor | `tests/scripts/test_dependency_freshness.py` (whole file) | `main()` has **zero** coverage — the only workflow↔script contract | Mutation: wrong input filename **and** `print()` instead of `json.dump()` → 16/16 tests still pass. Same for dropping the dev-release filter, breaking epoch/local version semantics, and flipping duplicate-name resolution. Composes with the major above: a `main()` bug produces exactly the blank artifact that gets posted. |
| minor | `scripts/dependency_freshness.py:85-90`, `:150-151` | A PyPI **404** (package absent from PyPI) is classified `unknown`, which the issue body defines as "we could not read PyPI" | Verified: `HTTPError 404` → key dropped → `unknown`. Two different facts collapse into one label, and the body asserts `unknown` "should be 0" — which such a package would break permanently. |
| minor | `scripts/dependency_freshness.py:110-113`; design note `:90-94` | Concurrency is claimed to have eliminated self-inflicted `unknown`s | It narrowed the window; it did not remove the mechanism (10 s timeout unchanged). Reproduced 6 self-inflicted `unknown`s at the same 16 workers under local load; 3 later runs at the same settings gave 0. |
| minor | `.github/workflows/pipeline-dependency-freshness.yml` (job level) | No `timeout-minutes`, no `concurrency:` | 27 repo workflows set `timeout-minutes` (`secret-staleness-check.yml` uses 5); this job does a 2.4 GB install and 284 HTTPS calls. Two overlapping dispatches (the note itself says a manual dispatch is required) can each create an issue. |
| nit | `scripts/dependency_freshness.py:127` | `{name: version for result in results if result for name, version in [result]}` | Correct, but reads like a typo. `filter(None, results)` + a plain comprehension is clearer. |
| nit | design note `:70` | Says "Three defects", then lists six; `:7` says six | Internal contradiction inside the section whose whole purpose is the correction record. |
| nit | design note `:122-124` | Says "13 further majors", lists 12 | Omits `polars-runtime-32`. The count of 16 is right. |
| nit | design note `:102-103` | Justifies title-search dedup with "a `radar` label that does not exist in the repo" | Stale: `:116-122` now creates and applies `radar`. |
| nit | `.github/workflows/pipeline-dependency-freshness.yml:80` | `<!-- dependency-freshness-radar -->` written but never read | Dedup is by title (`:104`). Dead marker. |
| nit | `tests/scripts/test_dependency_freshness_clock.py:67-70` | `test_the_clock_is_monthly` compares a module literal to itself; reads nothing from the repo | Harmless — `:73-96` pin the real strings in `jobs.ts` / `wrangler.toml` (mutation-verified). |

## Refuted

Checked, and **not** a problem:

- **Markdown / `@mention` injection into the issue body via PyPI metadata.** Package names
  come only from `read_pinned` (`PIN_RE` restricts to `[A-Za-z0-9._-]+`). The only PyPI string
  reaching the body is `str(Version(...))`, which is PEP 440-normalised. Seven adversarial
  release keys (`1.0.0+evil|hi`, `2.0.0+@user`, `1.0.0+\`id\``, embedded newline, `9!1.0`, …)
  all rejected. `env:` + quoted `echo` means no re-expansion.
- **`environment:` needed for the token.** `DIGITHINGS_PROJECT_TOKEN` is repo-scoped;
  the `cron` environment holds 0 secrets. No gate required.
- **`gh issue create --label` dying on a missing label.** `radar` genuinely does not exist
  yet, but `:116` creates it first; `component:root` and `priority:low` both exist.
- **The dedup search string.** Multi-word `in:title` works against the live repo (probe: 1
  match); the em-dash in the title is not a problem.
- **`uv sync` needing a build toolchain.** All 297 lock entries have wheels. Real
  `--frozen --all-packages --all-extras` sync: exit 0 in 60 s, 2.4 GB.
- **Internally inconsistent summary numbers.** 16 + 110 + 43 + 109 + 6 + 0 = 284 = `len(rows)`.
- **The scan mutating `uv.lock` or a bound.** `git diff --name-only` shows no lock/pyproject
  change; `--frozen` writes nothing.
- **`fetch_all`'s nested comprehension being a bug.** Valid and correct (mutation M2 is caught).
- **Design note numbers.** 30 pytest, 15 vitest in `jobs.test.ts`, 16 majors, `ruff` clean,
  6 `no stable release`, 284 packages — all reproduced.
- **`jobs.ts` ↔ `wrangler.toml` drift.** Mutating `wrangler.toml` alone fails
  `test_the_cron_is_in_the_wrangler_trigger`.
- **AGENTS.md compliance.** Naming rule clean; DCO `Signed-off-by` on all 3 commits; PR title
  `ci(root): …` has a valid scope; `ruff` line length ≤ 100. The branch-name deviation is the
  known accepted one and blocks nothing.

## What I could not verify

- **The workflow end-to-end on a runner.** It does not exist on `develop`, so it cannot be
  dispatched. Every step was instead extracted from the YAML and executed locally under
  `bash -e` (GitHub's Linux default, per `secret-staleness-check.yml:94`).
- **Whether `DIGITHINGS_PROJECT_TOKEN` carries the org/project scope `gh project item-add`
  needs.** Secret values are unreadable by design. Guarded with `|| true`, and six other
  call sites in `pipeline-maintenance.yml` use the identical pattern.
- **Timeout behaviour on GitHub's own runners.** My six `unknown`s came from local contention
  (a concurrent 2.4 GB download), not from GitHub infrastructure.
- **Post-merge.** `deploy-digithings-cron.yml` auto-deploys the Worker on a push to `develop`;
  I verified the row's workflow filename and `ref: DEVELOP` are consistent, not that the deploy
  succeeds.

## Commands

```
git diff --stat github/develop...HEAD
.venv/bin/python -m pytest tests/scripts/test_dependency_freshness.py \
  tests/scripts/test_dependency_freshness_clock.py tests/scripts/test_no_gha_schedules.py -q
# -> 30 passed
.venv/bin/python -m ruff check + format --check  (3 files)        # -> clean
uv export --frozen --all-packages --all-extras --format requirements-txt \
  --no-emit-project --no-emit-workspace --no-hashes -o freshness-requirements.txt
# -> exit 0; 1088 lines, 284 non-comment, 284 matched, 0 unmatched, 0 dup versions
UV_PROJECT_ENVIRONMENT=/tmp/dfs-venv uv sync --frozen --all-packages --all-extras
# -> EXIT=0  real 59.52s   2.4G
bash -e <extracted "Compute freshness report" step>  (GITHUB_OUTPUT=/tmp/GH_OUT)
# -> exit 0; GITHUB_OUTPUT 13486 bytes; summary=**16 major**, 110 minor, 43 patch,
#    109 current, 6 no stable release, 0 unknown (of 284 packages)
bash -e <degraded simulation: step fails, outputs empty>  # -> blank table body
gh api repos/digithings-ai/digithings/actions/secrets   # DIGITHINGS_PROJECT_TOKEN present (repo scope)
gh api repos/digithings-ai/digithings/environments/cron/secrets  # -> total_count 0
gh label list --search <l>  # radar: none; component:root, priority:low: present
gh issue list --search "Dependency freshness report in:title" --state all   # -> none (first run)
gh issue list --search "L5: client must in:title" --state all                # -> 1 match (search works)
mutation M2 sequential fetch   -> 1 failed
mutation M3 collapsed states   -> 2 failed
mutation M4 broken main()      -> 16 passed   <-- gap
mutation M5 no dev filter       -> 16 passed   <-- gap
mutation M6 epoch/local broken -> 16 passed   <-- gap
mutation M7 first-wins dup     -> 16 passed   <-- gap
mutation M8 daily clock everywhere -> test_the_clock_is_monthly failed (literal-vs-literal)
mutation M9 wrangler-only drift -> test_the_cron_is_in_the_wrangler_trigger failed
yarn/npm test (apps/digithings-cron)   # -> 71 passed (jobs.test.ts alone: 15)
yanked-release sweep over all 284      # -> 1 hit: narwhals 2.27.0 (all files yanked)
7 adversarial PyPI version keys through latest_stable -> all rejected
2 concurrent live scans -> 0 unknown; 1 under load -> 6 self-inflicted unknown
```

## Resolution

Every finding, and where it closed. Fixed on `DIG-1515-dependency-freshness-radar`.

| severity | finding | resolution |
|---|---|---|
| major | `if: always()` let an upstream failure overwrite the standing issue with a blank table and report success | `always()` removed from the publish step; a new `if: always()` guard step reads `steps.report.outputs.table` and `exit 1`s when it is empty. Pinned by `test_a_failed_scan_cannot_blank_the_standing_report`. |
| minor | yanked releases not filtered | `_all_files_yanked()` in `latest_stable`; empty file list is not a yank. narwhals now reports 2.26.0. 3 tests. |
| minor | `main()` had zero coverage | 5 tests added, including `test_main_writes_the_contract_the_workflow_reads` (filename + `json.dump` on stdout). The M4/M5/M6/M7 mutations now fail. |
| minor | a PyPI 404 collapses into `unknown` | Not split into a new state — it is one reader-visible fact, "we have no comparable latest", and a fourth label would be read as a defect. The issue body glossary now says `unknown` means "a read timeout, or no such project on PyPI at all". Fixed the comment in `build_report` that claimed three meanings. |
| minor | concurrency claimed to have eliminated self-inflicted `unknown`s | Narrowed, not removed. Both the design note (:92-96, Risks) and the `fetch_all` docstring now say so, with the review's under-load reproduction quoted as the reason. |
| minor | no `timeout-minutes`, no `concurrency` | `timeout-minutes: 20` and `concurrency: {group: pipeline-dependency-freshness, cancel-in-progress: false}`, both pinned by `test_the_job_is_bounded_and_single_flighted`. |
| nit | nested comprehension reads like a typo | `dict(result for result in filter(None, results))`. |
| nit | note says "Three defects", lists six | "Six defects". |
| nit | "13 further majors" lists 12 | `polars-runtime-32` added. All 13 locked→latest pairs re-verified against PyPI on 2026-10-07. |
| nit | title-search dedup justified by a label that does not exist | Reworded: the run creates the `radar` label it uses. |
| nit | dead `<!-- dependency-freshness-radar -->` marker | Removed. |
| nit | `test_the_clock_is_monthly` compared a literal to itself | Now reads the cron out of `jobs.ts` and asserts it against the pinned constant. Mutation-verified: changing `CRON` fails the test. |

Verification after the fixes: 38 pytest passed, `ruff check` + `format --check` clean, `actionlint` clean.