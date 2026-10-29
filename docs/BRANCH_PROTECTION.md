# Branch protection (`digithings-ai/digithings`)

> **PENDING ROLLOUT.** The "Target state" below is not live. It is the target decided for the dev-flow upgrade (2026-10-29). Applying it is a repository-settings change that only Chris makes. Until then, "Live settings" is what GitHub enforces.

## Target state (PENDING ROLLOUT)

### `develop`

- Required status checks: `local-ci` and `merge-queue`. `merge-queue` is a commit status that `scripts/merge_queue.py` posts on a PR head in `run` mode (`success` right before it merges that head, `failure` on a refused head, `pending` when not reached). It is added by [#6558](https://github.com/digithings-ai/digithings/pull/6558), which is open and unmerged as of the read below.
- Pushes to `develop` are restricted to the promotion identity: agents reach `develop` only through a promotion PR. The promotion identity (a GitHub App or bot account) does not exist yet; creating it is Chris's step.
- Everything else (up-to-date strictness, review count) stays as it is today.

### `main`

- Required status check: `Every commit reaching main was reviewed` (from `.github/workflows/ci-review-coverage.yml`, `scripts/check_review_coverage.py`).
- Enforced for admins (`enforce_admins: true`): an admin can no longer merge past a failing required check.

### Rollout order

1. Merge #6558 and watch one queue `run` tick post `merge-queue` on open PR heads.
2. Add `merge-queue` to develop's required contexts (the command recorded in #6558):

   ```
   gh api -X PATCH repos/digithings-ai/digithings/branches/develop/protection/required_status_checks \
     --input - <<<'{"strict":false,"contexts":["local-ci","merge-queue"]}'
   ```

3. Create the promotion identity, then restrict pushes on `develop` to it.
4. Turn on `enforce_admins` for `main`.
5. Re-read the settings and replace "Live settings" below with the new read.

Note that a commit status can be posted by anyone with a write token, so `merge-queue` stops accidental bypass, not deliberate bypass; the push restriction is the stronger control.

## Live settings as of 2026-10-29 14:38 CET (UTC+1)

Read-only, through the GitHub branches and repository API (`GET /repos/digithings-ai/digithings/branches/{branch}` and `GET /repos/digithings-ai/digithings`). Nothing was changed.

| Setting | `develop` | `main` |
|---|---|---|
| Protected | yes | yes |
| Head at read | `67310448` | `986051dc` |
| Required status checks | `local-ci` (commit status, no app bound) | `Every commit reaching main was reviewed` (bound to the GitHub Actions app, id 15368) |
| Required checks apply to admins (`enforcement_level`) | yes (`everyone`) | no (`non_admins`) |

Repository: public; default branch `develop`; merge commits, squash and rebase merges all allowed; auto-merge off; head branches deleted on merge; "update branch" suggestion off.

**Not readable in this read** (the branch summary does not expose them, and there was no read path for the full protection or rulesets endpoints): `strict` (up-to-date requirement), required approving reviews, push restrictions, rulesets (including the `module-branch-protection` ruleset AGENTS.md describes), and GitHub's native merge queue. Secondary reports, not verified here: PR #6558 (27 Oct) records develop as `strict: false`, `enforce_admins: true`, no rulesets; the dev-flow plan (29 Oct) records develop strict off with 0 approvals and main with admins not enforced and 0 approvals. Verify with:

```
gh api repos/digithings-ai/digithings/branches/develop/protection
gh api repos/digithings-ai/digithings/branches/main/protection
gh api repos/digithings-ai/digithings/rulesets
```

## Gap: live vs target

| Setting | Live | Target |
|---|---|---|
| `develop` required checks | `local-ci` | `local-ci`, `merge-queue` |
| `develop` push restriction | not readable in this read | promotion identity only |
| `main` admins | not enforced | enforced |

## Known drift in the tooling

- `.github/required-contexts.txt`, which `scripts/set-branch-protection.sh` applies and `scripts/check_required_policy_checks.py` reads, still lists the Actions-era contexts `Required checks passed`, `doc-links + agents-init` and `mypy — digibase + digikey`. Live develop requires `local-ci` only. Running `scripts/set-branch-protection.sh` as-is would not produce the live or the target state; do not run it until the snapshot is updated in the same change as the protection.
- Previous versions of this doc described those three contexts with `strict: true` as live; that is no longer true.

## Ownership of develop's required contexts

The context set is `.github/required-contexts.txt`; the only writer is `scripts/enable_branch_protection.py` (develop entrypoint `scripts/set-branch-protection.sh`, which refuses `--branch main`); the check is `scripts/check_required_policy_checks.py`. `main`'s protection is a one-off `gh api` call, not tracked by a script.

## Keeping the snapshot true

CI cannot read branch protection (`GITHUB_TOKEN` cannot get `administration: read`), so update the snapshot in the same change as any protection edit and run `python3 scripts/check_required_policy_checks.py --live --repo digithings-ai/digithings --branch develop`. `.github/workflows/policy-gate-live.yml` carries that read on `workflow_dispatch` only, and skips until its `POLICY_CHECK_READER_TOKEN` is provisioned.

## Path-filtered required checks

A workflow skipped by `paths` / `paths-ignore` / `branches` filters reports no check at all, so requiring its name hangs every PR it skips on "Waiting for status to be reported". Prove a new required check reports on a docs-only PR before requiring it.

## Emergency bypass

Today admins can merge `main` past its required check, because the check is not enforced for admins. Use that only for a genuine emergency and open a follow-up issue linked to the bypassed PR. Once the target state lands there is no admin bypass on `main`. Never disable protection; fix the check instead.

## Other repos

Everything above is about `digithings-ai/digithings`. The org's private repos listed in [MERGE_QUEUE.md § Repo survey](MERGE_QUEUE.md#repo-survey) are on the GitHub Free plan, where branch protection and rulesets are refused ("Upgrade to GitHub Pro or make this repository public"). There the merge path is [the merge queue](MERGE_QUEUE.md), which cannot stop a direct push.
