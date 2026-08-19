# Branch Protection Policy

## Why branch protection matters

PRs have landed on `develop` and `main` while CI was red or while no baseline tests ran.
Branch protection makes the three most important status checks required gates — a PR cannot
merge until all of them pass. This eliminates silent failures and keeps the default branch
always releasable.

## Required status checks

Required checks differ by branch and have drifted from `set-branch-protection.sh`'s
original single-payload design — verify live state with the commands in
[Verify the configuration](#verify-the-configuration) rather than trusting this doc blindly.

### On `develop`

**Current live state (verified 2026-08-19):** zero `required_status_checks` — the key is
absent from the API response entirely. Nothing merging into `develop` is actually gated on
CI passing.

This table is what `set-branch-protection.sh` still applies if run today — it is **stale,
not aspirational**: `Require Fixes` was deleted outright in `c0cdd8d1b` (#2341, "drop
unenforced PR-linkage gate"), and `baseline / tests` no longer exists as a check name (its
tests were folded into the `ruff-and-scripts` job as a step, not a separate job). Do not run
the script against `develop` expecting this table's effect.

| Check name (stale) | Workflow | What it validated |
|---|---|---|
| ~~`baseline / tests`~~ | `ci.yml` (job added by #291) | No longer a distinct job — its tests are now a step inside `ruff-and-scripts`. |
| `ruff-and-scripts` | `ci.yml` | Still a real job/check name. Ruff lint across all source trees + `tests/scripts/` unit tests. |
| ~~`Require Fixes`~~ | `ci-pr-hygiene.yml` | Removed 2026-08-13 (#2341) — issue linkage is now a documented convention only, not a CI check. See `docs/adr/0024-drop-pr-linkage-enforcement.md`. |

**This is a known, paused migration, not unexplained drift.** On 2026-08-13, `fd6de617f`
("ci: make CI/type-check/docs checks safe to require on develop") found and recorded this
exact zero-required-checks state, then did the prep work needed to safely require checks
without a false "waiting forever" merge block: it dropped the `pull_request` path filters
on `ci-docs.yml` and `ci-type-check.yml` (a path-filtered check never posts on a PR outside
its paths, and GitHub then blocks merge forever waiting on a status that will never arrive
once the name is required) and added a `required-checks` aggregator job to `ci.yml` — every
job there is individually path-gated via a `changes` job, so no single existing job name was
stable across every PR shape. The commit is explicit that it stops short of the branch
protection API call itself: *"This commit only changes what CI reports; it does not touch
branch protection."* That follow-up call was never made — six days later, live state is
still zero required checks.

**The three checks now safe to require, ready to apply:**

| Check name | Workflow | What it validates |
|---|---|---|
| `Required checks passed` | `ci.yml` aggregator job | Fans in every path-gated component job (`digibase`, `digikey`, `digiquant`, `score`, `pip-audit`, `ruff-and-scripts`, `actionlint`, `compose-validate`, etc.) — tolerates `skipped`, fails only on real `failure`/`cancelled`. Includes `changes` in its `needs` list as of `2825a57d3`, a CodeRabbit finding on #2341 (without it, a broken change-detector produced a false-green result). |
| `doc-links + agents-init` | `ci-docs.yml` | Internal markdown link validation + `agents-init --check`. No longer path-filtered on `pull_request`, so it posts on every PR. |
| `mypy — digibase + digikey` | `ci-type-check.yml` | Type checking for `digibase`/`digikey`. No longer path-filtered on `pull_request`, so it posts on every PR. |

Applying this needs its own `gh api` call with these three exact context strings — **not**
`scripts/set-branch-protection.sh`, which still carries the stale trio above. See
[#2469](https://github.com/digithings-ai/digithings/issues/2469) for the actual apply step
(deliberately left for explicit sign-off rather than done as part of this doc fix).

### On `main`

`main`'s only required status check today is **`Every commit reaching main was reviewed`**,
from [`ci-review-coverage.yml`](../.github/workflows/ci-review-coverage.yml) — not the
`develop` table above. `scripts/set-branch-protection.sh` was never updated for this: it
still applies the `develop`-era three-context payload to whichever `--branch` you pass it.
**Do not run it against `main`** without first updating the script's `contexts` array —
doing so would silently replace the review-coverage check with the stale set and break the
main gate.

This check does not require a live approving review on the promotion PR
(`required_approving_review_count: 0`, `require_code_owner_reviews: false` — verified via
API). Instead, `scripts/check_review_coverage.py` walks every commit in the PR's range
(merge and bot commits exempt) and requires each one to already carry review evidence from
its own task PR, satisfied by any one of:

| hatch | claim | self-grantable? |
|-------|-------|-----------------|
| `Cursor Bugbot` concluded success | a machine reviewed it | no |
| an **APPROVED** review | someone else read it | no |
| label `reviewed:agent` + a findings comment | an in-session review ran | yes, but costs a real review |
| label `reviewed:owner` | "I read this myself" | yes |
| label `risk:low` | "this didn't warrant a review" | yes |

Full rationale — why reviewing the promotion diff itself is the wrong moment, and why this
is deliberately *not* a required `Cursor Bugbot` check on `main` — is in
[`CLAUDE.md` § Review coverage](../CLAUDE.md#review-coverage-the-gate-before-production).

**Why not a live reviewer-request instead?** [#1612](https://github.com/digithings-ai/digithings/issues/1612)
proposed auto-requesting a non-author reviewer on every promotion PR to work around
`CODEOWNERS` listing only the sole maintainer — the same failure mode that forced an admin
bypass on #1610. That approach was superseded by the per-commit check above: the Copilot
review-request job was retired (2026-08-05, account unsubscribed) and Bugbot proved
unreliable as a *required* check (it reports `neutral` on a usage-limit skip, which would
have blocked all ten promotions on 2026-08-05 had it been required). #1612 was closed as
not planned; see its closing comment for the full comparison.

## Dependency

**This script must be run after issue #291 (baseline CI suite) is merged and the
`baseline / tests` check appears green on at least one PR.** Running it before #291 lands
will register a required check that can never pass, blocking all merges.

## How to apply protection

Apply to `develop` (the default integration branch):

```bash
bash scripts/set-branch-protection.sh --branch develop
```

Apply to `main` (production):

```bash
bash scripts/set-branch-protection.sh --branch main
```

> **Stale for `main` — see [On `main`](#on-main).** This command applies the `develop`-era
> three-context payload and would overwrite the live `Every commit reaching main was
> reviewed` check. Update the script's `contexts` array first if you actually need to
> re-apply `main`'s protection.

Preview what would be applied without calling the API:

```bash
bash scripts/set-branch-protection.sh --dry-run
bash scripts/set-branch-protection.sh --branch main --dry-run
```

The script requires the `gh` CLI to be installed and authenticated (`gh auth login`).

## Verify the configuration

```bash
gh api repos/digithings-ai/digithings/branches/develop/protection | python3 -m json.tool
gh api repos/digithings-ai/digithings/branches/main/protection    | python3 -m json.tool
```

Look at `required_status_checks.contexts`: on `develop` it should list the three checks in
[On `develop`](#on-develop) with `strict: true` (currently doesn't — see the drift note
there); on `main` it should list only `Every commit reaching main was reviewed` per
[On `main`](#on-main).

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
