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
| `gitleaks-scan` | `security-gitleaks.yml` | Secrets scan over the PR diff (full history on `develop`/`main` push). Added to the required set in #3922. **Not yet applied live** — see the pre-apply note below. |

> **Pre-apply note (#3922):** `security-gitleaks.yml` currently skips markdown/doc-only
> PRs with a workflow-level `paths-ignore`. A workflow skipped by path filtering leaves
> its required check in a **Pending** state, so GitHub would block docs-only PRs from
> merging ("Waiting for status to be reported"). Before applying the updated script,
> relocate that skip to a **job-level** conditional — a skipped *job* reports Success —
> or drop the PR trigger filter. Do not apply `gitleaks-scan` as a required context
> while the workflow can be skipped by path filtering.

`strict: true` — the PR branch must be up-to-date with `develop` before merging.
`scripts/set-branch-protection.sh` applies exactly this payload (once the
[pre-apply note](#on-develop) above is resolved) and refuses `--branch main`
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

## The policy-gate drift guard

`ci.yml`'s own "Verify needs list covers every job in this file" step only sees
`ci.yml`, so it cannot fail on a policy check that lives in another workflow file — it
would stay green no matter which one that was. `scripts/check_required_policy_checks.py`
is the corrected inventory ([DIG-1982](https://github.com/digithings-ai/digithings/issues/1982)).
It reconciles:

| set | against | catches |
|---|---|---|
| `.github/policy-checks.yml` | the jobs the workflows actually define | a renamed or dropped check; a policy surface nobody declared |
| `.github/policy-checks.yml` | develop's required contexts | a check the gate does not hold, and a gate the inventory does not own |
| every context the gate holds **or** the inventory declares | whether each can report on every develop PR | **the stall** — a required check that never arrives hangs every merge |

That third row covers both sets on purpose, and the second half of it is
[DIG-2237](https://github.com/digithings-ai/digithings/issues/2237), because the original
guard only asked about the live gate. A workflow whose checks are all `advisory` reports
nothing that anyone is waiting for, so a workflow-level `paths-ignore` added to one was a
**false green**: no failing check, and a PR shape the check would never cover. The moment
DIG-1952 child B promotes such an entry, every PR it skips hangs. The guard now reports that
as a finding before the promotion, not after.

"Whether it can report" is decided from the `pull_request:` trigger alone, and all four
filters matter, not two of them:

| trigger filter | why it can stop the check arriving |
|---|---|
| `paths:` / `paths-ignore:` | a skipped **workflow** reports nothing — only a skipped *job* reports Success |
| `branches:` | the workflow never starts for a PR into another branch |
| `branches-ignore:` | the same filter spelled as an exclusion; matching globs |
| `types:` | **required contexts are evaluated against the PR's head SHA**, and `synchronize` is the only event that re-reports on a new push. A workflow on `types: [opened]` reports for the opening SHA and never again, so after the first push the PR waits on "Waiting for status to be reported" forever with no failing check to explain it. |

An **absent** `types:` key is GitHub's default (`opened`, `synchronize`, `reopened`), which
includes `synchronize` and is therefore reachable. A `types:` key that is present but
unreadable is treated as empty, so the rule fails closed rather than passing on a value
nobody could read.

`ci.yml`'s in-file `needs` staleness check is **kept**, not replaced. The reconciliations do
not overlap; dropping the old one would leave a real hole.

### Completeness: `tracked_workflows` is an allowlist, not the scope

`.github/policy-checks.yml` tracks 8 of the 53 workflow files — the ones with policy
surfaces. That is the right size, but an allowlist nobody checks for completeness is not an
inventory: a brand-new workflow carrying a real gate would be out of scope by construction,
and `policy.untracked-producer` would never be raised.

So the guard also scans every `*.yml` under `.github/workflows/` for a named job matching a
live or declared context, and fails when the producer is untracked — including when the
producer is untracked *and* cannot report, which previously drew `policy.undeclared-gate`
and then stopped, giving the wrong diagnosis on exactly the case `gitleaks-scan` exists to
exercise. Adding a workflow is therefore not free: either name it in `tracked_workflows`, or
do not give any of its jobs a `name:`. Migrating all 53 is not the answer and is not
required.

An untracked file that will not parse is reported (`policy.unreadable-workflow`), not
raised — otherwise any of the 45 untracked workflows could take the guard down with an
unreadable error instead of a diagnosis. A **tracked** file that will not parse still
raises, because a tracked file is a declared surface.

**Check the gate, at any time:**

```bash
python3 scripts/check_required_policy_checks.py                    # committed snapshot (what CI runs)
python3 scripts/check_required_policy_checks.py --live \
    --repo digithings-ai/digithings --branch develop               # the live gate
```

CI reads `.github/required-contexts.txt`, not the API: reading branch protection needs
`administration: read`, which **cannot be granted to `GITHUB_TOKEN`** at all, so no
workflow can read it. The snapshot is only trustworthy if it is updated in the same
change as the protection itself — run `--live` after any manual branch-protection edit
and commit the difference, or the guard is checking a fiction.

### Re-verifying the snapshot on a clock

Doing that by hand leaves one gap: nothing catches a branch-protection edit that nobody ran
`--live` after. The PR path cannot close it, because `GITHUB_TOKEN` cannot read branch
protection at all, so putting the read on the PR path would mean putting a human-only
credential in front of every merge.

So it runs on a schedule instead. The `policy-gate-live` job in
[`ci-pr-hygiene.yml`](../.github/workflows/ci-pr-hygiene.yml) mints a
[`policy-check-reader`](../docs/ops/policy-check-credential.md) installation token, exports
it as `GH_TOKEN`, and runs the guard with `--live`, failing when the snapshot and the live
gate disagree. Three deliberate choices:

- **It rides the existing `digithings-cron` dispatch** (`jobs.ts`, daily 06:21 UTC,
  `workflow_dispatch` against `develop`) rather than adding an `on.schedule:` trigger, which
  `tests/scripts/test_no_gha_schedules.py` forbids.
- **The job is unnamed.** A job with a `name:` is a policy surface that the inventory must
  list, and a check that reads branch protection must never appear on the PR path.
- **`environment: cron` is declared on it.** Without that, `secrets.*` resolves to empty
  rather than to the key, so the read would fail as "no key" and never as "permission
  denied".

An **absent credential is reported as unvalidated, never as a failure** — the job posts
`::notice` and exits 0. A canary that starts red because it cannot read its own secret is
how a check becomes a silent stop, which is what happened to the token canary in #2541. A
present credential that disagrees with the snapshot *is* a failure.

> **Not yet provisioned.** The `policy-check-reader` App, the `cron`-scoped
> `POLICY_CHECK_APP_PRIVATE_KEY` secret and the `POLICY_CHECK_APP_ID` /
> `POLICY_CHECK_INSTALLATION_ID` variables do not exist yet (the `cron` environment holds
> no secrets at all), and creating the App needs `Administration: write`, which is
> Chris-only on this one-member org. Until they exist the job notices and exits 0 on every
> run. Provisioning is tracked on DIG-2237; nothing else here depends on it.

### Declaring a new policy check

Add it to `.github/policy-checks.yml` with one of three `enforcement` values:

- `required` — must be in develop's contexts *and* must report on every develop PR.
  The guard fails both if it is absent and if it could be skipped.
- `advisory` — runs and reports but deliberately does not gate. **Requires a `reason`.**
- `other-branch` — gates another branch (`main`), not develop.

### Every non-`required` entry needs an owner

A `reason` records what was true when it was written. On its own it is indistinguishable
from what is true now, forever — which is what makes `advisory` an escape hatch nobody owns
([DIG-2237](https://github.com/digithings-ai/digithings/issues/2237)). So:

| field | required on | meaning |
|---|---|---|
| `owner:` | every non-`required` entry | who answers for it. Missing → `GuardError` |
| `review_by:` | *or* one of the two below, on `advisory` | a date to revisit the decision |
| `issue:` | | the issue tracking the gap (`DIG-NNNN`) |
| `gated_by:` | | a context that is `required` in this inventory **and** present in the live gate |

`gated_by:` is validated, not trusted: naming a context the inventory does not declare is a
`GuardError`, and naming one that is declared but not actually in the live gate is a
`policy.bad-gated-by` finding. Otherwise "it is gated by the aggregator" would be a citation
rather than a fact. `advisory` with none of the three raises.

There is a separate, narrower field for a gap that is **accepted on purpose**: `known_gap:`.
It suppresses the reachability finding for that entry while the entry is ungated, and stops
applying the moment the entry reaches the live gate — at that point the check really does
have to report, so the accepted gap has expired. `gitleaks-scan` is the only entry with one
today.

A job counts as a policy surface when it has an explicit `name:`. A job without one
reports under its job id and is folded into an aggregator instead. Naming a job makes it
a policy surface; leaving it unnamed keeps it internal.

**`gitleaks-scan` is the worked example of why `required` is not free.** Its entry is
`advisory`, and promoting it to `required` is refused while `security-gitleaks.yml` keeps
its workflow-level `paths-ignore`: a docs-only PR never starts the workflow, the check
never reports, and requiring the name hangs those PRs on "Waiting for status to be
reported" forever. Move the skip to a job-level `if:` (a skipped *job* reports Success; a
skipped *workflow* does not) or drop the filter first. That is the pre-apply note above,
enforced in CI instead of only in prose.

## How to apply protection

Re-apply `develop`'s checks (idempotent — safe to re-run any time the contexts in the
script match what's actually live). Read the [pre-apply note](#on-develop) first:
`gitleaks-scan` must not be applied while `security-gitleaks.yml` can be skipped by path
filtering.

```bash
bash scripts/set-branch-protection.sh
```

Then update `.github/required-contexts.txt` to match what was applied, and prove the
snapshot against the live gate:

```bash
python3 scripts/check_required_policy_checks.py --live \
    --repo digithings-ai/digithings --branch develop
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

Look at `required_status_checks.contexts`: on `develop` it should list the checks in
[On `develop`](#on-develop) with `strict: true`; on `main` it should list only
`Every commit reaching main was reviewed` per [On `main`](#on-main).

`scripts/enable_branch_protection.py status` reports the same state in a form meant for
reading, and is what [the policy-gate guard](#the-policy-gate-drift-guard) uses:

```bash
python3 scripts/enable_branch_protection.py status \
    --repo digithings-ai/digithings --branch develop
```

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

## Scope: this applies to `digithings`, not to `twelve-x`

Everything above is about `digithings-ai/digithings`, and only that repo has the protection
described here. `digithings-ai` is on the GitHub Free plan, and **protected branches on a
private repository require GitHub Pro**. `twelve-x` and `digithings-ops` are private, so
branch protection, rulesets and the native merge queue are all refused on them with:

```
Upgrade to GitHub Pro or make this repository public to enable this feature.
```

This is a plan limit, not a misconfiguration — the identical API call succeeds on the
public `digithings` and is refused on private `twelve-x` in the same org, with the same
token and the same admin permission.

`scripts/enable_branch_protection.py status` reports the gate for any repo:

```bash
python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
```

Until the plan changes, the merge path for `twelve-x` is
[the merge queue](MERGE_QUEUE.md), which governs merges but — say this plainly — **cannot
stop a direct push to the branch.** Only branch protection can do that. The full repo
survey is in [MERGE_QUEUE.md § Repo survey](MERGE_QUEUE.md#repo-survey).
