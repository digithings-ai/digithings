# Branching model

This repository enforces a specific branch taxonomy **client-side only**, via
`scripts/hooks/pre-push.sh` (installed by `make hooks-install`). Pushes of
branches whose names don't match the taxonomy are rejected before they leave
your machine — but a clone that never ran `make hooks-install` has no name
enforcement at all. There is no branch-naming ruleset on `origin`: the repo's
only ruleset is `module-branch-protection` (on `module/**`). The `Copilot review
for default branch` ruleset this section used to name — left behind by the
Copilot subscription retired in #1904 — is gone; `gh api
repos/digithings-ai/digithings/rulesets?includes_parents=true` returns the one
entry.

Rulesets are not the whole picture. `main` and `develop` also carry **classic
branch protection**, which the rulesets endpoint does not report at all — see the
table below, and query `…/branches/<name>/protection` before concluding a branch
is unguarded.

## Three-tier branching model

```
main  ←  develop  ←  module/<component>  ←  task/<N>-<slug>
```

- **`task/<N>-<slug>`** branches from its module branch (auto-detected from issue's `component:` label by `make task ISSUE=N`). PRs target the module branch.
- **`module/<component>`** accumulates task PRs for a sprint, then PRs into `develop` as one batch. Use `make module-pr MODULE=<component>`.
- **`develop`** is the integration branch. Holds cross-cutting work and module-sprint merges.
- Some components skip the module tier and branch directly from `develop`. `scripts/project_routing.json` is the source of truth for which — read its `branches` map rather than trusting a list in prose (as of 2026-08-01: `component:root`, `component:digivault`, `component:website`, `component:digiquant-web`, `component:design-system`, and the `default` fallback).

**Session start:** `make module-switch MODULE=<component>` then `make task ISSUE=N`.
**Sprint end:** `make module-pr MODULE=<component>` → PR review → merge to develop.
**Sync:** `make module-sync` fast-forwards your **local** `module/*` refs to `develop`. It does not push, so `origin/module/*` is unchanged — and it cannot, because `module-branch-protection` requires a PR and blocks force-push. Refreshing a *remote* module branch means opening a PR into `base=module/<component>`. You do not have to check staleness by hand before branching off one — since #2547 `make task ISSUE=N` fetches `origin` and refuses to cut a task branch from a `module/*` base that is behind `origin/develop`, printing the behind-count and the sync recipe. To check a module branch on its own:

```bash
git fetch origin
git rev-list --count origin/module/<component>..origin/develop   # 0 = current; >0 = stale
```

## Long-lived branches

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | What is actually deployed / released. | PR required (**0** approvals), no force-push, no deletion. One required status check: `Every commit reaching main was reviewed`. Linear history is **not** enforced. |
| `develop` | Integration branch — merge target for module sprints and cross-cutting work. Also the repo's **default branch**. | No force-push, no deletion. **No PR gate** — `required_pull_request_reviews` is `null`, so unlike `main` a pull request is not required server-side. Three required checks, `strict: true` — so a PR that *is* opened must be up to date with `develop` before it can merge. |
| `module/<component>` | Per-module integration branch. One per digithings module. PRs into develop. | No force-push, no deletion, PR required (0 approvals) — the `module-branch-protection` ruleset on `refs/heads/module/**`. |

Local pushes to `main` require `ALLOW_MAIN_PUSH=1` as an environment variable
(belt-and-suspenders on top of the PR gate).

**Module branches managed by the tooling:** `module/digigraph`, `module/digiquant`, `module/digisearch`, `module/digichat`, `module/digikey`, `module/digismith`, `module/digiclaw`, `module/digibase` — this is the `MODULES` array in `scripts/module_branches.sh`, so `make module-status`/`-sync`/`-switch`/`-pr` only know these eight.

Other `module/*` branches exist on `origin` outside that set and are not managed by any
command here. As of 2026-08 that was `module/website`, `module/olympus`,
`module/digiskills` and `module/digiquant-atlas` — **a snapshot, not an invariant**
(`module/digiquant-atlas` was queued for deletion when this was written). Check rather
than trust the list:

```bash
git branch -r --list 'origin/module/*'                       # which ones still exist
git rev-list --no-merges origin/module/<x> ^origin/develop   # empty ⇒ nothing stranded
```

The second was empty for all four at the 2026-08 sync (PRs #2397, #2401, #2402;
`module/digiskills` needed none — it is a plain ancestor of `develop`). Where such a branch
is ahead of `develop` at all, the extra commits are its own `chore/sync-*` merges:
**dormant, not divergent, with no work stranded on any of them.** Don't revive one —
branch from `develop`. `module/digiquant-atlas` was cut in the pre-migration
`apps/digiquant-atlas/` era, and the Wave 1 / Wave 2 plan docs that name it as a PR target
are archival.

Deleting a dormant module branch is **not** a plain `git push origin --delete`. The
`module-branch-protection` ruleset lists `deletion` over `refs/heads/module/**` with an
empty bypass-actor list, and a ruleset grants no implicit admin exemption — both the push
and the web UI's delete button are refused until the ref is excluded or enforcement is
relaxed. That is a repo-settings change, deliberately: the same rule that stops a stale
module branch being force-pushed also stops it being quietly dropped.

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
| `bot/<slug>` | Opened by a repo workflow, not a person — `project-stub-fields.yml` pushes one per issue it fields. | `bot/stub-tsv-2459` |
| `release-please--branches--<target>--components--<component>` | Auto-created by the `release-please-*.yml` workflows to propose a version-bump PR — one per component, against that component's own target branch (digichat → `develop`, digiskills → `module/digiskills`). Not something a human creates; the taxonomy just needs to admit what the bot already pushes, so a maintainer can `git push` a follow-up fix commit onto it (e.g. a lockfile resync) without `--no-verify`. | `release-please--branches--develop--components--digichat` |
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
2. Install your *uncommitted* edit to test it: `HOOKS_REF=WORKTREE make hooks-install`.
   A plain `make hooks-install` installs the copy committed on `origin/develop`,
   so on its own it would not pick your edit up. The override is not durable:
   every worktree shares this one hook file, so the next plain `make
   hooks-install` — or any `make agents-init`, in any worktree — puts
   `origin/develop`'s copy back. Re-run the `HOOKS_REF=WORKTREE` command if so.
3. Merge to `develop`. Other clones pick the new regex up on their next
   `git fetch` followed by `make hooks-install` (or any `make agents-init`).

There is no server-side counterpart to update. `scripts/github-ruleset.json`,
which this section used to point at, does not exist in the repo, and `origin`
has no branch-naming ruleset to edit.

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

`main` and `develop` are protected server-side against deletion. `release/v*` is
**not** — see the gap note below.

**Deletions are exempt from the name check.** The hook validates the branch name
on the way in, not on the way out: a ref that predates a tightening of the
taxonomy, or one a workflow created outside it, must still be deletable — refusing
the delete only strands the branches the rule meant to discourage. Until #2463 the
hook checked the name first and `exit 1`ed before it reached the deletion skip, so
`git push origin --delete bot/stub-tsv-2459` failed with a name-taxonomy error and
no server-side cause, and `bot/*` refs had piled up on `origin` behind it (~100 as
of 2026-08-18; #2465 reaped them on 2026-08-19 and 5 heads remain). The `main`
guard still covers deletions — deleting `main` is at least as serious as pushing
to it, so it needs the same `ALLOW_MAIN_PUSH=1`.

## What is not allowed

- Branch names outside the taxonomy — rejected by the client pre-push hook when
  the branch is created or updated, though not when it is deleted. **Nothing
  enforces this server-side today**: `scripts/github-rulesets/01-branch-naming.json`
  declares the same regex (bar the `main`/`develop` arms, which its
  `conditions.ref_name.exclude` covers instead) and reads `"enforcement":
  "active"`, but that file is desired state that was never applied — the only
  ruleset on `origin` is `module-branch-protection`. Nothing currently proves this
  the way the `release-please--branches--*--components--*` refs used to: those were
  live on `origin` while the taxonomy still rejected them client-side, meaning the
  hook was blocking even a maintainer's own follow-up push (e.g. a lockfile resync)
  onto a branch the bot itself had already pushed with no server-side rule stopping
  it — proof the JSON was never applied, found the hard way. The taxonomy now admits
  that pattern (see the table above), which closes the gap but removes the evidence;
  don't take the absence of a fresh example as proof the JSON ruleset got applied in
  the meantime. (The `bot/*` refs were never proof of anything either way: `bot/<slug>`
  is in the taxonomy, so a server-side rule would have accepted them regardless.) Keep
  the JSON in sync with the table above anyway, so applying it later doesn't reject
  refs this document calls legal.
- Force-pushes to `main` or `develop` — blocked server-side.
- Force-pushes to, or deletion of, `module/**` — blocked by the
  `module-branch-protection` ruleset.

## Enforcement gaps (verified 2026-08-19)

Two protections this document previously asserted are not actually configured.
Both are a human call to close — changing branch protection is a settings
change, not a docs change:

- **`release/v*` has no protection rule.** Only the `main` and `develop`
  patterns exist, so a release branch can be force-pushed or deleted by anyone
  with write access.
- **`main` requires no *approval*.** `required_approving_review_count` is `0`, so
  a PR into `main` can be merged by whoever opened it. Its one required status
  check is `Every commit reaching main was reviewed` — the review-coverage gate in
  `scripts/check_review_coverage.py` — which asserts each commit in the range was
  reviewed at its own task PR, and clears on a label. Nothing requires CI green
  beyond that check.

  (This bullet previously said `main` requires no status checks at all, on the
  strength of `gh api …/rulesets` returning nothing for it. That endpoint does not
  report classic protection; `…/branches/main/protection` does.)
