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
| `gitleaks-scan` | `security-gitleaks.yml` | Secrets scan over the PR diff (full history on `develop`/`main` push). **Not required** — the inventory declares it `advisory`. Added to the writer's payload in #3922 and never applied live; DIG-2223 removed it from the writer. |

> **Why `gitleaks-scan` is still not required (blocker resolved 2026-10-10, #5318).** It was
> blocked on a workflow-level `paths-ignore: ["**.md", "docs/**"]` in `security-gitleaks.yml`.
> A workflow skipped by path filtering reports **no check run at all** — not a skipped job —
> so requiring the name would hang every docs-only PR on "Waiting for status to be reported".
> #5318 deleted that filter, so the workflow now reports on every PR and the stall hazard is
> gone.
>
> What is *not* gone is the promotion decision itself. The check stays `advisory` until
> DIG-1983's branch-protection write is sequenced, which is a human-only repo-settings change.
> Until then the snapshot lists three contexts and the writer applies three.

`strict: true` — the PR branch must be up-to-date with `develop` before merging.
`scripts/set-branch-protection.sh` applies exactly this payload and refuses `--branch main`
(its contexts are develop-specific — see [On `main`](#on-main)). It reads the context list
from `.github/required-contexts.txt` rather than carrying one of its own — see
[Ownership](#ownership-of-develops-required-contexts).

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
| develop's required contexts | whether each can report on every develop PR | **the stall** — a required check that never arrives hangs every merge |

`ci.yml`'s in-file `needs` staleness check is **kept**, not replaced. The three
reconciliations do not overlap; dropping the old one would leave a real hole.

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

### Declaring a new policy check

Add it to `.github/policy-checks.yml` with one of three `enforcement` values:

- `required` — must be in develop's contexts *and* must report on every develop PR.
  The guard fails both if it is absent and if it could be skipped.
- `advisory` — runs and reports but deliberately does not gate. **Requires a `reason`.**
- `other-branch` — gates another branch (`main`), not develop.

A job counts as a policy surface when it has an explicit `name:`. A job without one
reports under its job id and is folded into an aggregator instead. Naming a job makes it
a policy surface; leaving it unnamed keeps it internal.

**`gitleaks-scan` is the worked example of why `required` is not free.** Its entry is
`advisory`, and for six days it was also the fourth context hardcoded into the writer — a
gate you could apply with one command, declared nowhere in the inventory, recorded in no
snapshot. Two things had to be true before promoting it, and only the first now holds:

* **The check reports on every PR shape.** It did not, until #5318 removed the
  workflow-level `paths-ignore` — a skipped *workflow* reports nothing, while a skipped *job*
  reports Success, which is why the filter could not simply be moved to a job-level `if:`
  (GitHub expressions cannot test "changed files match this path glob"). `policy.stall` in
  `scripts/check_required_policy_checks.py` now enforces this in CI instead of only in prose.
* **Someone promotes it on purpose.** That is DIG-1983's branch-protection write, which is
  human-only. Until it happens the snapshot lists three contexts and the writer applies three.

## Ownership of `develop`'s required contexts

Two files decide what `develop` requires, and exactly one of each kind, so there is nothing
left to compare by hand (DIG-2223):

| Role | File | Owns |
|---|---|---|
| The context **set** | `.github/required-contexts.txt` | Which check names `develop` requires. Comment lines are prose, not gates. |
| The **write** | `scripts/enable_branch_protection.py` | The only script that PUTs protection. Owns the preflight, the plan-blocked diagnosis, and the union that stops a narrower apply from dropping a live gate. |
| The **develop entrypoint** | `scripts/set-branch-protection.sh` | Nothing but the branch name. Reads the set from the snapshot, then delegates. Holds no list of its own. |
| The **check** | `scripts/check_required_policy_checks.py` | Executes the writer (`--print-contexts`) and fails on any difference from the snapshot, then reconciles the snapshot against the inventory and the workflows. |

`scripts/check_required_policy_checks.py` executes the writer rather than scanning its
source, because a source scan goes blind the moment the payload is built any other way — a
generated list, a heredoc, a variable — and a scan that finds no literals then reads exactly
like "the writer is in sync".

**Adding a gate is therefore:** edit the snapshot, declare it in `.github/policy-checks.yml`,
prove its workflow reports on a docs-only PR, then run the writer. Editing the writer is not
a step, because it holds no list to edit.

## How to apply protection

Re-apply `develop`'s checks (idempotent — safe to re-run any time the snapshot matches what's
actually live). The snapshot is the **input**, not a record of what was applied: edit
`.github/required-contexts.txt` first, then run the writer, which applies exactly that list.

```bash
bash scripts/set-branch-protection.sh
```

By default the writer *unions* the live contexts, so a stale snapshot cannot quietly weaken
the branch. To make the snapshot authoritative — which is what you want immediately after
editing it — pass `--replace-checks`, and then prove the result against the live gate:

```bash
bash scripts/set-branch-protection.sh --replace-checks
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
