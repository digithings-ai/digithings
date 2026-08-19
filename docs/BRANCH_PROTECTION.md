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

The set the script below applies (and re-applies if you re-run it):

| Check name | Workflow | What it validates |
|---|---|---|
| `baseline / tests` | `ci.yml` (job added by #291) | Cross-module smoke tests: import health, config loading, known regressions |
| `ruff-and-scripts` | `ci.yml` | Ruff lint across all source trees + `tests/scripts/` unit tests |
| `Require Fixes` | `ci-pr-hygiene.yml` | Issue linkage, unless a bypass applies — promotion (`develop` → `main`, same repo), `module/*`, `docs/*`, `chore/*`, or `task/<N>-*` head. Otherwise the body **or title** needs `Closes/Fixes/Resolves #N`. See CLAUDE.md § Check linkage for the full order. |

`strict: true` is set, meaning the PR branch must be up-to-date with the base branch before
merging. This prevents "works on my branch" situations where a passing PR would introduce a
regression when integrated.

**Current live state (verified 2026-08-19):** `develop`'s branch protection has no
`required_status_checks` configured at all — the key is absent from the API response. This
has drifted from the table above; not addressed by this doc update. If the gap turns out to
be intentional, this section should say so instead; if not, re-apply with
`bash scripts/set-branch-protection.sh --branch develop` (open a follow-up issue rather than
just re-running it, since something removed the checks and that cause is still unknown).

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
