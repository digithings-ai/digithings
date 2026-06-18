# Branching model

This repository enforces a specific branch taxonomy client-side (via
`scripts/hooks/pre-push.sh`) and server-side (via a GitHub ruleset on
`origin`). Pushes of branches whose names don't match the taxonomy are
rejected before they leave your machine.

## Three-tier branching model

```
main  ←  develop  ←  module/<component>  ←  task/<N>-<slug>
```

- **`task/<N>-<slug>`** branches from its module branch (auto-detected from issue's `component:` label by `make task ISSUE=N`). PRs target the module branch.
- **`module/<component>`** accumulates task PRs for a sprint, then PRs into `develop` as one batch. Use `make module-pr MODULE=<component>`.
- **`develop`** is the integration branch. Holds cross-cutting work (component:root, component:website) and module-sprint merges.
- Cross-cutting tasks (component:root/website) skip the module tier and branch directly from `develop`.

**Session start:** `make module-switch MODULE=<component>` then `make task ISSUE=N`.
**Sprint end:** `make module-pr MODULE=<component>` → PR review → merge to develop.
**Sync:** `make module-sync` keeps all module branches up to date with develop.

## Long-lived branches

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | What is actually deployed / released. | PR required, linear history, no force-push, no deletion. |
| `develop` | Integration branch — merge target for module sprints and cross-cutting work. | PR required, no force-push, no deletion. |
| `module/<component>` | Per-module integration branch. One per DigiThings module. PRs into develop. | No force-push. |

Local pushes to `main` require `ALLOW_MAIN_PUSH=1` as an environment variable
(belt-and-suspenders on top of the PR gate).

**Module branches:** `module/digigraph`, `module/digiquant`, `module/digisearch`, `module/digichat`, `module/digikey`, `module/digismith`, `module/digiclaw`, `module/digibase`.

## Short-lived branches

| Pattern | Use | Example |
|---------|-----|---------|
| `release/vX.Y.Z` | A versioned release candidate cut from `develop` for final testing, then merged to `main` and tagged. | `release/v0.1.0` |
| `module/<component>` | Per-module integration branch — accumulates task PRs for a sprint, then PRs to develop. `make module-switch MODULE=<x>`. | `module/digiquant` |
| `task/<N>-<slug>` | A backlog task tied to GitHub Issue #N. `make task ISSUE=N` auto-creates this branch from the correct module branch. | `task/42-latency-metric` |
| `claude/<slug>` | Work driven by Claude Code outside the task system. | `claude/guardrail-hooks` |
| `codex/<slug>` | Work driven by ChatGPT Codex. | `codex/refactor-rag-chunker` |
| `cursor/<slug>` | Work driven by Cursor Agent. | `cursor/docs-migration` |
| `copilot/<slug>` | Work driven by GitHub Copilot. | `copilot/fix-import-order` |
| `<handle>/<slug>` | Direct human commits by a named contributor (GitHub login). | `chrizefan/vision-pass` |
| `feat/<slug>` | Feature work not bound to a single Issue. | `feat/model-picker` |
| `fix/<slug>` | Bug fix not bound to a single Issue. | `fix/auth-retry` |
| `docs/<slug>` | Docs-only change (eligible for auto-merge via the `automerge-docs` label). | `docs/vision-update` |
| `chore/<slug>` | Tooling, CI, config. | `chore/bump-pydantic` |

Slugs: lowercase, dashes, no underscores. Numbers permitted.

## Adding a human contributor

Human branches use the contributor's GitHub handle as the namespace. To add a
new contributor:

1. Edit `scripts/hooks/pre-push.sh` and add the handle to `CONTRIBUTOR_HANDLES`
   (pipe-separated: `chrizefan|alice|bob`).
2. Update the branch-naming ruleset on `origin` (see `scripts/github-ruleset.json`
   or the GitHub UI under **Settings → Rules → Rulesets**).
3. Re-run `make hooks-install` in every developer's clone so the new regex lands.

## Cutting a release

```
git checkout develop
git pull
git checkout -b release/v0.1.0
# freeze: bug-fix commits only on this branch
# when ready:
git checkout main
git merge --no-ff release/v0.1.0
git tag v0.1.0
git push origin main v0.1.0
git checkout develop
git merge --no-ff release/v0.1.0                # bring fixes back
git push origin develop
git branch -d release/v0.1.0
git push origin --delete release/v0.1.0
```

## Deleting a stale branch

Any contributor can delete their own short-lived branches after the PR lands:

```
git push origin --delete <branch>
git branch -d <branch>                          # local
```

`main`, `develop`, and any `release/v*` are protected server-side against
deletion.

## What is not allowed

- Branch names outside the taxonomy — rejected by the client pre-push hook and
  by the server ruleset.
- Force-pushes to `main`, `develop`, or any `release/v*` — blocked server-side.
- PRs without at least one passing CI check — blocked on `main`.
