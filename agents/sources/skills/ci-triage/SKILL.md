---
name: ci-triage
description: Use when the user wants to diagnose why a PR's CI is red, bucket the failures by type, and get minimal fix commands. Triggers on "triage PR", "why is CI failing", "/triage <N>", "fix CI on PR <N>".
---

# CI triage

Diagnose a red PR, bucket failures by type, and produce one fix command per bucket.

## Step 1 — Get the failure log

Fetch the CI output for the PR. Options:
- Ask the user to paste the failing step's log.
- Use `gh run view --log-failed` if gh CLI is available.
- Read the summary from the GitHub Checks UI.

## Step 2 — Bucket the failures

| Bucket | Pattern | Minimal fix |
|---|---|---|
| **Lint** | `ruff`, `eslint`, `mypy`, `tsc` errors | `ruff check --fix .` / `npm run lint -- --fix` |
| **Format** | `ruff format`, `prettier` diff | `ruff format .` / `npx prettier --write .` |
| **Broken links** | `make doc-check` failures | Fix or remove the dead markdown link |
| **Unit tests** | `pytest` / `vitest` failures | Run the failing test locally; fix the code |
| **PR linkage** | "Require Fixes" check fails | Add `Fixes #N` to PR body; create backing issue if needed |
| **Scoring gate** | `make score` exits non-zero | Run `score-and-fix` skill |
| **Docker / compose** | `make up` / service health failures | Check `docker compose logs <service>` |
| **Other** | Anything else | Read the raw log; escalate if unclear |

## Step 3 — Output

For each failing bucket:

```
### <Bucket name>
Failure: <one-line summary>
Fix: <exact command to run>
```

## Step 4 — Apply fixes

Apply the minimal fix for each bucket. Do not touch code outside the failing scope.

After fixes:
```bash
git add <changed files>
make score          # re-run gate if scoring was a bucket
git push            # re-triggers CI
```

## PR linkage failures

The "Require Fixes" check fails only when **none** of the gate's bypasses apply. In the order `.github/workflows/ci-pr-hygiene.yml` tests them: a promotion PR (head `develop` → base `main`, from this repo); a `module/*` head; a `docs/*` or `chore/*` head; a `task/<N>-*` head; or a `Fixes/Closes/Resolves #N` keyword in the PR body **or title**.

So a red `Require Fixes` means the head is something else — typically `feat/<slug>`, `fix/<slug>`, or an agent namespace like `claude/<slug>` — with no keyword. Fix:

1. Create a backing issue if none exists:
   ```bash
   gh issue create --title "[agent] <short description>" --label "agent-task"
   ```
2. Add to PR body:
   ```
   Closes #<N>
   ```
3. Push any trivial change (or amend + force-push) to re-trigger checks.
