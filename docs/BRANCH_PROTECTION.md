# Branch Protection Policy

## Why branch protection matters

PRs have landed on `develop` and `main` while CI was red or while no baseline tests ran.
Branch protection makes the most important status checks required gates — a PR cannot merge
until they pass. `develop` and `main` require different checks for different reasons (see
below); together they eliminate silent failures and keep both branches always releasable.

## Required status checks

Required checks are branch-specific — `develop` and `main` are gated by entirely different
mechanisms (see below) and are managed by different tooling. Verify live state with the
commands in [Verify the configuration](#verify-the-configuration) rather than trusting this
doc blindly; it has drifted from reality before (that's the story this section tells).

### On `develop`

**Current live state (applied 2026-08-19, #2469):**

| Check name | Workflow | What it validates |
|---|---|---|
| `Required checks passed` | `ci.yml` aggregator job | Fans in every path-gated component job (`digibase`, `digikey`, `digiquant`, `score`, `pip-audit`, `ruff-and-scripts`, `actionlint`, `compose-validate`, etc.) — tolerates `skipped`, fails only on real `failure`/`cancelled` **except advisory `score`** (#3528: optional rubric; red `score / score` is visible but non-blocking). Includes `changes` in its `needs` list as of `2825a57d3`, a CodeRabbit finding on #2341 (without it, a broken change-detector produced a false-green result). |
| `doc-links + agents-init` | `ci-docs.yml` | Internal markdown link validation + `agents-init --check`. Not path-filtered on `pull_request`, so it posts on every PR. |
| `mypy — digibase + digikey` | `ci-type-check.yml` | Type checking for `digibase`/`digikey`. Not path-filtered on `pull_request`, so it posts on every PR. |

`strict: true` — the PR branch must be up-to-date with `develop` before merging.
`scripts/set-branch-protection.sh` applies exactly this payload and refuses `--branch main`
(its contexts are develop-specific — see [On `main`](#on-main)).

Verified before applying: a throwaway PR touching no component path (the worst case for
`ci.yml`'s per-job path gating) confirmed all three checks post a real conclusion rather
than sitting `pending` forever — see #2469 and the closed [PR #2471](https://github.com/digithings-ai/digithings/pull/2471).

**History — this was a known, paused migration, not unexplained drift.** Until 2026-08-19,
`develop` had *zero* required status checks (the `required_status_checks` key was absent
from the API entirely) — two of the three checks this doc used to describe here
(`baseline / tests`, `Require Fixes`) no longer existed as check names by the time anyone
looked: `Require Fixes` was deleted outright in `c0cdd8d1b` (#2341, "drop unenforced
PR-linkage gate"), and `baseline / tests` was folded into `ruff-and-scripts` as a step, not
a separate job. On 2026-08-13, `fd6de617f` ("ci: make CI/type-check/docs checks safe to
require on develop") found and recorded the zero-required-checks state, then did the prep
work needed to safely require checks without a false "waiting forever" merge block: dropped
the `pull_request` path filters on `ci-docs.yml` and `ci-type-check.yml` (a path-filtered
check never posts on a PR outside its paths, and GitHub then blocks merge forever waiting on
a status that will never arrive once the name is required), and added the
`required-checks` aggregator job to `ci.yml` — every job there is individually path-gated
via a `changes` job, so no single existing job name was stable across every PR shape. That
commit stopped short of the branch-protection API call itself on purpose: *"This commit only
changes what CI reports; it does not touch branch protection."* #2469 made that follow-up
call, six days later, after the throwaway-PR verification above.

### On `main`

`main`'s only required status check is **`Every commit reaching main was reviewed`**, from
[`ci-review-coverage.yml`](../.github/workflows/ci-review-coverage.yml) — a different
mechanism from `develop`'s, not a subset or superset of it. `scripts/set-branch-protection.sh`
does not touch `main` at all (it refuses `--branch main`); `main`'s protection was set up as
a one-off `gh api` call, not tracked by any script.

This check does not require a live approving review on the promotion PR
(`required_approving_review_count: 0`, `require_code_owner_reviews: false` — verified via
API). Instead, `scripts/check_review_coverage.py` walks every commit in the PR's range
(merge and bot commits exempt) and requires each one to already carry review evidence from
its own task PR. The walker batches GitHub GraphQL (PR hatch state + associated SHAs)
instead of sequential `gh pr view`; hatch rules are unchanged, satisfied by any one of:

| hatch | claim | self-grantable? |
|-------|-------|-----------------|
| `Cursor Bugbot` concluded success | a machine reviewed it | no |
| an **APPROVED** review | someone else read it | no |
| a completed agent-tool review (CodeRabbit, Claude, …) | a PR-review bot finished a pass | no |
| label `reviewed:agent` + a findings comment | an in-session review ran | yes, but costs a real review |
| label `reviewed:owner` | "I read this myself" | yes |
| label `risk:low` | "this didn't warrant a review" | yes |

Full rationale — why reviewing the promotion diff itself is the wrong moment, and why this
is deliberately *not* a required `Cursor Bugbot` check on `main` — is in
[`AGENTS.md` § Review coverage](../AGENTS.md#review-coverage-the-gate-before-production).

**Why not a live reviewer-request instead?** [#1612](https://github.com/digithings-ai/digithings/issues/1612)
proposed auto-requesting a non-author reviewer on every promotion PR to work around
`CODEOWNERS` listing only the sole maintainer — the same failure mode that forced an admin
bypass on #1610. That approach was superseded by the per-commit check above: the Copilot
review-request job was retired (2026-08-05, account unsubscribed) and Bugbot proved
unreliable as a *required* check (it reports `neutral` on a usage-limit skip, which would
have blocked all ten promotions on 2026-08-05 had it been required). #1612 was closed as
not planned; see its closing comment for the full comparison.

## How to apply protection

Re-apply `develop`'s three checks (idempotent — safe to re-run any time the contexts in the
script match what's actually live):

```bash
bash scripts/set-branch-protection.sh
```

`--branch main` is refused on purpose — see [On `main`](#on-main) for how `main`'s
protection is actually managed.

Preview what would be applied without calling the API:

```bash
bash scripts/set-branch-protection.sh --dry-run
```

**Before adding a new check name to `develop`'s required set:** confirm with a throwaway PR
that it actually posts a status on a PR shape that doesn't exercise it — a path-filtered
workflow that never fires on some PRs will hang those PRs' merge button forever once
required. See #2469's verification (a closed throwaway PR, #2471) for the pattern.

The script requires the `gh` CLI to be installed and authenticated (`gh auth login`).

## Verify the configuration

```bash
gh api repos/digithings-ai/digithings/branches/develop/protection | python3 -m json.tool
gh api repos/digithings-ai/digithings/branches/main/protection    | python3 -m json.tool
```

Look at `required_status_checks.contexts`: on `develop` it should list the three checks in
[On `develop`](#on-develop) with `strict: true`; on `main` it should list only
`Every commit reaching main was reviewed` per [On `main`](#on-main).

## Emergency bypass procedure

`enforce_admins` is intentionally set to `false`. Repository admins can merge a PR even
when checks fail by clicking "Merge without waiting for requirements" on GitHub.

Use this sparingly and only for genuine emergencies (e.g., a broken check infrastructure
blocking a hotfix). After any admin bypass, open a follow-up issue and link it to the
bypassed PR.

Do **not** disable branch protection entirely — adjust it or fix the failing check instead.

## Updating required checks

If a check is renamed or replaced, re-run the script after updating the `contexts` array in
`scripts/set-branch-protection.sh`. The `gh api PUT` call is idempotent — it replaces the
full protection config each time.
