# Branch Protection Policy

## Why branch protection matters

PRs have landed on `develop` and `main` while CI was red or while no baseline tests ran.
Branch protection makes the three most important status checks required gates — a PR cannot
merge until all of them pass. This eliminates silent failures and keeps the default branch
always releasable.

## Required status checks

| Check name | Workflow | What it validates |
|---|---|---|
| `baseline / tests` | `ci.yml` (job added by #291) | Cross-module smoke tests: import health, config loading, known regressions |
| `ruff-and-scripts` | `ci.yml` | Ruff lint across all source trees + `tests/scripts/` unit tests |
| `Require Fixes` | `pr-linkage.yml` | Every PR body must contain `Closes #N`, `Fixes #N`, or `Resolves #N` |

`strict: true` is set, meaning the PR branch must be up-to-date with the base branch before
merging. This prevents "works on my branch" situations where a passing PR would introduce a
regression when integrated.

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

Look for `required_status_checks.contexts` to confirm the three checks are listed and
`required_status_checks.strict` is `true`.

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
