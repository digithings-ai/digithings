# CI queue pressure and org runner starvation

When many PRs push at once, or a large PR fans out many workflows, jobs can sit in
**Queued** for 15+ minutes even though nothing is wrong with the YAML. That blocks merge
(`mergeStateStatus: UNSTABLE`) until checks complete or are cancelled.

## Symptom

- PR shows **Mergeable** but **blocked** / **Checks pending**
- Actions UI: multiple workflows `Queued`, often 10+ per PR
- Same jobs eventually pass when runners free up

Root cause is usually **org-level concurrent job limits** on GitHub-hosted runners (shared
across all repos in `digithings-ai`), not a failing test.

## What runs on every PR (inventory)

| Check / workflow | Required for merge? | Path-filtered? | Notes |
|------------------|--------------------:|----------------|-------|
| `CI` → `changes` + gated jobs | Intended (`ruff-and-scripts`, baseline) — see [BRANCH_PROTECTION.md](../BRANCH_PROTECTION.md) | Yes — `ci.yml` `dorny/paths-filter` gates component installs | Orchestrator only; component tests are `workflow_call`-only |
| `PR hygiene` → `Require Fixes` | Yes (when protection applied) | Linkage: no; TSV coverage: `project_fields.tsv` + workflow only | Merged from former `pr-linkage` + `project-fields-coverage` |
| `gitleaks` → `gitleaks-scan` | Recommended security gate | PR: skips doc-only (`**.md`, `docs/**`) | Full history still scanned on `develop`/`main` push |
| `Docs` | Optional | Yes — markdown, `agents.yml`, agent surface | Single job (link check + agents-init) |
| `Type Check` | Optional | Yes — `digibase/**`, `digikey/**` | |
| `CodeQL` | Org/repo policy | Org-managed | Not defined in this repo; reduce frequency in org settings |
| `Project status automation` | **No** | PR: **merge/close only** (not open/sync) | Board hygiene; skips when `DIGITHINGS_PROJECT_TOKEN` absent |
| `digiquant.io Cloudflare build check` | Optional | Yes — digiquant.io frontend assets + build script | Does not run for backend-only `digiquant/**` changes |
| `Doc auto-merge` | Optional | Label `automerge-docs` only | Triggers on `labeled` / `unlabeled` |

## What we filtered (2026-06 queue remediation)

1. **`ci.yml` orchestrator** — component test workflows are `workflow_call`-only; `changes` job gates digiquant, digisearch, score, e2e, nautilus, atlas, pip-audit, ruff, compose.
2. **`pr-hygiene.yml`** — one workflow instead of two; TSV validation only when `scripts/project_fields.tsv` or the hygiene workflow changes (daily schedule still catches drift).
3. **`project-status-automation.yml`** — dropped `opened` / `reopened` / `ready_for_review` on `pull_request`; still updates **Done** on merge and **In Progress** on task-branch push.
4. **Concurrency** — all lightweight PR workflows use `cancel-in-progress: true` per workflow+PR so superseded pushes release queue slots faster.
5. **`gitleaks`** — doc-only PRs skip the PR diff scan (push to `develop`/`main` still scans full history).
6. **`automerge-docs`** — no longer dispatches on every `synchronize`; only when `automerge-docs` label is added or removed.

## Expected job reduction

| PR profile | Before (approx.) | After (approx.) |
|------------|------------------:|----------------:|
| Doc-only (`**.md`) | 8–12 queued jobs | 3–4 (`CI` changes + hygiene linkage + maybe CodeQL) |
| Single-component code (e.g. digisearch only) | 12–18 | 5–8 (orchestrator + linkage + gitleaks + touched component) |
| Wide audit / multi-component (e.g. #578) | 15–20+ | 10–14 (unavoidable — many paths touched) |

Savings are largest on **doc-only** and **single-component** PRs. Monorepo-wide remediation PRs still fan out legitimately.

## How to merge when checks are queued

1. **Wait** — if jobs are `Queued` (not `Failed`), prefer waiting over bypass.
2. **Cancel stale runs** — Actions → filter by branch → cancel older workflow runs for the same PR (concurrency should do this on new pushes).
3. **Re-push** — empty commit or close/reopen only if runs are stuck >30 min with zero runner assignment.
4. **Admin bypass** — repo admins: *Merge without waiting for requirements* (emergencies only; open a follow-up issue).
5. **Org settings** (human) — GitHub org → Settings → Actions → increase concurrent jobs or add larger runners; CodeQL → reduce PR frequency or scope languages/paths.

### Re-poll merge

```bash
gh pr view <N> --json mergeable,mergeStateStatus,statusCheckRollup \
  --jq '{mergeable, mergeStateStatus, pending: [.statusCheckRollup[] | select(.status != "COMPLETED") | .name]}'
```

Merge when `mergeStateStatus` is `CLEAN` (or `UNSTABLE` only because of optional checks you accept) and required checks are green.

## Path filter source of truth

CI component gates in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) embed filters
generated from [`scripts/ci_paths.yaml`](../../scripts/ci_paths.yaml). After editing the YAML,
run `python3 scripts/generate_ci_path_filters.py` (or `--check` in CI). See
[`scripts/generate_ci_path_filters.py`](../../scripts/generate_ci_path_filters.py).

## Related docs

- [CI_CONVENTIONS.md](CI_CONVENTIONS.md) — full workflow inventory
- [BRANCH_PROTECTION.md](../BRANCH_PROTECTION.md) — required check names and `set-branch-protection.sh`
