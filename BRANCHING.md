# Branching model

This repository enforces a specific branch taxonomy **client-side only**, via
`scripts/hooks/pre-push.sh` (installed by `make hooks-install`). Pushes of
branches whose names don't match the taxonomy are rejected before they leave
your machine — but a clone that never ran `make hooks-install` has no name
enforcement at all. There is no branch-naming ruleset on GitHub.
`module-branch-protection` (id 15270439, on `module/**`) is absent from the
ruleset list; it went with the retired module tier (#6751).

One ruleset is live. `Public CI` (id **26699837**), created 2026-11-06, targets
`refs/heads/main` and `refs/heads/develop` with enforcement `active`. Read it
with:

```
gh api repos/digithings-ai/digithings/rulesets?includes_parents=true
gh api repos/digithings-ai/digithings/rules/branches/develop
gh api repos/digithings-ai/digithings/rules/branches/main
```

Classic `GET …/branches/<name>/protection` is a separate API. A token without
administration scope gets HTTP 403, which does not prove the classic rule is
absent. The table below is the ruleset the rules API returned on 2026-11-06.
Re-read both endpoints before treating the table as the whole policy.

## Origin drafts

Agent iterations use a local branch named `origin/<slug>` and `origin push local`. Those refs live only on the Origin `/local` endpoint and do not sync to GitHub. They are not part of the taxonomy below. Promoting a draft means copying its tip onto a `task/` or `release/` branch and pushing that branch. See [AGENTS.md](AGENTS.md#origin-iteration-github-promotion).

## Two-tier branching model

```
main  ←  develop  ←  task/<N>-<slug>
```

- **`task/<N>-<slug>`** branches from `develop` (`make task ISSUE=N` reads the base from `scripts/project_routing.json`, which routes every component to `develop`). PRs target `develop`.
- **`develop`** is the integration branch and the default branch. Every change lands here first.
- **`main`** is what is released. `develop` promotes to `main` through a reviewed PR.

Per-component releases do not need their own branches: release-please versions each component from `develop` by path and tags the release.

The `module/<component>` integration tier was retired in November 2026 (#6751). It drifted behind `develop`, added a review-and-merge hop to every change, and gave release-please nothing it lacked. Do not recreate `module/*` branches; the pre-push taxonomy rejects them.

## Long-lived branches


**Org production clocks** live in the Cloudflare Worker `digithings-cron` (`apps/digithings-cron`); the default branch stays `develop`.

| Branch | Purpose | Protection |
|--------|---------|------------|
| `main` | What is actually deployed / released. | Ruleset `Public CI`: pull request required, **0** approving reviews, `require_extra_approval_for_unattributed_changes: true`. Required checks `lint`, `secrets`, `unit`, **`strict_required_status_checks_policy: true`**. No force-push, no deletion. Linear history is **not** a rule on this ruleset. |
| `develop` | Integration branch — merge target for every task PR. Also the repo's **default branch**. | The same ruleset, including a required pull request and strict up-to-date checks. |
| `release/vX.Y.Z` | One per **released** version, cut from `main` at the release commit and tagged there. The maintenance line for that exact version — features accumulate on `develop`, not here, and the branch is never deleted. | Not included in `Public CI`. No ruleset in the list covers `release/**`, so force-push and deletion are possible; see [Enforcement gaps](#enforcement-gaps). Treat them as append-only regardless. |

Local pushes to `main` require `ALLOW_MAIN_PUSH=1` as an environment variable
(belt-and-suspenders on top of the ruleset, which requires a pull request).

Local pushes to `develop` require `ALLOW_DEVELOP_PUSH=1` as an environment
variable. `Public CI` applies the same `pull_request` rule to `develop` as to
`main` (zero approving reviews). The hook is the client-side guard; the ruleset
is the server-side one. The usual accident is a branch tracking `develop`
upstream, so a bare `git push` lands there — repair it with
`git branch --set-upstream-to=github/<branch> <branch>`, then push that branch.

## Short-lived branches

| Pattern | Use | Example |
|---------|-----|---------|
| `task/<N>-<slug>` | A backlog task tied to GitHub Issue #N. `make task ISSUE=N` creates this branch from `develop`. | `task/42-latency-metric` |
| `claude/<slug>` | Work driven by Claude Code outside the task system. | `claude/guardrail-hooks` |
| `codex/<slug>` | Work driven by ChatGPT Codex. | `codex/refactor-rag-chunker` |
| `cursor/<slug>` | Work driven by Cursor Agent. | `cursor/docs-migration` |
| `copilot/<slug>` | Work driven by GitHub Copilot. | `copilot/fix-import-order` |
| `bot/<slug>` | Opened by a repo workflow, not a person. Live publishers are `agent-backlog-snapshot.yml` (`bot/agent-backlog-snapshot`) and `pipeline-provider-review.yml` (`bot/provider-review-*`). `project-stub-fields.yml` used to push `bot/stub-tsv-*` and was removed in #4919; those leftover refs stay deletable. | `bot/agent-backlog-snapshot` |
| `release-please--branches--<target>--components--<component>` | The pattern stays so a leftover release-please ref can still be pushed. The `release-please-*.yml` workflows that used to create these branches were removed in #4919; none remain under `.github/workflows/`. | `release-please--branches--develop--components--digichat` |
| `<handle>/<slug>` | Direct human commits by a named contributor (GitHub login). | `chrizefan/vision-pass` |
| `feat/<slug>` | Feature work not bound to a single Issue. | `feat/model-picker` |
| `fix/<slug>` | Bug fix not bound to a single Issue. | `fix/auth-retry` |
| `docs/<slug>` | Docs-only change (eligible for auto-merge via the `automerge-docs` label). | `docs/vision-update` |
| `chore/<slug>` | Tooling, CI, config. | `chore/bump-pydantic` |
| `revert/<slug>` | Reverting or rolling back an earlier change (e.g. a `git revert` of a merged PR, or restoring paths to a known-good commit). Name what is being undone. | `revert/digiquant-to-7de39ec9a` |
| `rescue/<issue>-<date>` | The branch `kit/bin/dt-worktree-rescue` pushes onto when it retires a worktree that still holds work. Not a human-created name — the helper produces it, so the taxonomy admits it or the push is refused and the worktree is kept. The issue key is uppercase and a `-2`/`-3` suffix is added when the name is taken, so the arm is `rescue/[A-Za-z0-9-]+`. | `rescue/DIG-1234-2026-10-21` |
| `DIG-<n>-<slug>` | A Paperclip **execution workspace**. Paperclip checks the workspace out on `DIG-<n>-<title-slug>`, so this is not a branch a human creates — the taxonomy has to admit what the harness already produces, or every commit made there is unpushable. See [Execution-workspace branches](#execution-workspace-branches-never-blanket-push) before pushing one. | `DIG-1122-pre-push-taxonomy-has-no-dig-slug-rule` |

Slugs: lowercase, dashes, no underscores. Numbers permitted.

### Execution-workspace branches: never blanket-push

A `DIG-<n>-<slug>` branch is a **workspace**, not a unit of work. It accumulates
whatever commits the agents working in it produce, which routinely includes
commits belonging to other issues, merges of other people's PRs, and copies of
changes that already landed on `develop` by another route.

So `git push` on such a branch is not a save operation — it publishes the whole
accumulation. Concretely, on the DIG-47 workspace (snapshot taken 2026-10-04,
DIG-1122): one of its commits, `6d3789d9a` (a DIG-361 docs change), was a *stale
duplicate* — the same change had reached `develop` by another route, squash-merged
as `6c0de7e89` through PR #5094, so the two copies do not share a sha or a
patch-id. The stale copy *deleted* the DIG-258 inventory row and the entire
DIG-526 section that `develop` had gained since. Measured against `develop` at
that point, the workspace branch deleted 166 lines and added 19 to
`docs/ops/SECRETS_INVENTORY.md` — 185 changed lines carrying nothing but the loss
of what `develop` already had.

Two safe shapes:

- **Re-home the commits** onto a branch whose whole history is yours — normally
  `task/<N>-<slug>` or `feat/<slug>` — and push that. This is the normal path.
- **Push an explicit per-commit refspec** when you only want to preserve a
  specific commit on the workspace branch without moving its tip, e.g.
  `git push origin <sha>:refs/heads/<taxonomy-legal-name>`.

Avoid the third path: cherry-picking the same commits onto a legal branch
*without* dropping the local ones is how a patch ends up on two refs with
different SHAs. That happened on DIG-47.10 (`b6a3154d6`/`9b90f2a1c` locally,
`99e3d8618`/`8cc861931` remotely, identical patch-ids). Two patch streams mean
"which ref holds this fix?" has two answers and the contract review is in no
ref at all.

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

> **Parked modules** (see [docs/PARKED_MODULES.md](docs/PARKED_MODULES.md)) stay on `develop` and are never cut into `main` or a `release/` branch.

`develop` accumulates features; `main` is production. A release is **promoted to
`main` first**, and only then gets its own branch — one per version, cut from
`main` at the released commit:

```bash
git checkout develop
git pull
# the version bump lands on develop first: merge the release-please PR (or, for
# a hand bump, commit it on develop together with the tag — see RELEASES.md).
# Merging it is what makes release-please cut `digichat-v2.3.2` on develop.
gh pr create --base main --head develop --title "chore: promote develop to main"
gh pr merge --merge                              # PR into main: human on the cutover
git checkout main
git pull
git checkout -b release/v2.3.2                   # this version's maintenance line
git push -u origin release/v2.3.2
```

The tag already exists by this point — release-please cuts `digichat-vX.Y.Z` on
`develop` when the bump lands there, and that is the release moment (it is also
what dispatches the digichat image publish). Promoting `develop` brings the
tagged commit into `main`'s history, so the release branch is cut from `main`
while being tree-identical to the tag.

The branch is **not** where the release is stabilised: by the time it exists,
that version is already on `main` and deployed. Its job is to keep carrying
fixes for *that* version after `main` has moved on — pinned clients (self-host
stacks, clients pinned on `ghcr.io/digithings-ai/digichat:v0.9.3`) keep consuming it.

Do not delete the branch when the next release ships. There is one branch per
released version, and the older ones are the reason you can still patch them.

## Patching a release

A patch release continues the chain of its version — a new branch off the
previous one, so the branch name always equals the version it carries:

```bash
git checkout -b release/v2.3.3 release/v2.3.2
# apply the fix, bump the version to 2.3.3, commit
git tag digichat-v2.3.3
git push origin release/v2.3.3 digichat-v2.3.3   # a human-pushed digichat tag publishes the image
```

The fix then has to reach `develop`, in every case — release-please reads
`develop`, so a fix that only lives on the release branch is clobbered by the
next promotion:

```bash
git checkout develop
git cherry-pick <fix-sha>                        # the fix, never the version bump
```

Never merge the release branch into `main`: its version bump would take
production backwards (or fork the version line). Production picks the fix up the
normal way, through the next `develop` → `main` promotion, which now carries the
cherry-pick.

If production has to be patched before that promotion — only meaningful while
`main` is still on the same line, `2.3.x` — cherry-pick the *fix* into a
`fix/<slug>` branch off `main`, PR it into `main` (human on the cutover), and
cherry-pick the same fix onto `develop`. Still never the version bump.

A caveat on images: a human-pushed `digichat-vX.Y.Z` tag publishes the digichat
image, but the Python service images publish only on a push to `main`
(`publish-service-images.yml`), so a patch that is never promoted ships no
service image.

## Deleting a stale branch

Any contributor can delete their own short-lived branches after the PR lands:

```
git push origin --delete <branch>
git branch -d <branch>                          # local
```

**Branches with no PR are not covered by this section.** A branch that nobody
merged and nobody referenced is *stranded*, and it is disposed of under a separate
policy: `docs/ops/branch-hygiene-policy.md`.
That policy measures the branch by `git cherry` (unmerged patches, not commit
count), assigns it a tier, and names the agent allowed to delete it. It also turns
on the prevention side — `delete_branch_on_merge`, a branch-age guard, and a
pre-push age warning. Read it before deleting anything that never had a PR.

`main` and `develop` are protected server-side against deletion. Release
branches are policy-protected — one per released version, and an old one is the
only way to patch a client still pinned to it — but that is not yet enforced
server-side; see the gap note below.

**Deletions are exempt from the name check.** The hook validates the branch name
on the way in, not on the way out: a ref that predates a tightening of the
taxonomy, or one a workflow created outside it, must still be deletable — refusing
the delete only strands the branches the rule meant to discourage. Until #2463 the
hook checked the name first and `exit 1`ed before it reached the deletion skip, so
`git push origin --delete bot/stub-tsv-2459` failed with a name-taxonomy error and
no server-side cause, and `bot/*` refs had piled up on the GitHub repo behind it
(~100 as of 2026-08-18; #2465 reaped them on 2026-08-19 and bot/* heads remained).
The `main`
guard still covers deletions — deleting `main` is at least as serious as pushing
to it, so it needs the same `ALLOW_MAIN_PUSH=1`. The `develop` guard works the
 same way: deleting `develop` needs `ALLOW_DEVELOP_PUSH=1`.

## What is not allowed

- Branch names outside the taxonomy — rejected by the client pre-push hook when
  the branch is created or updated, though not when it is deleted. **Nothing
  enforces this server-side today**: `scripts/github-rulesets/01-branch-naming.json`
  declares the same regex (bar the `main`/`develop` arms, which its
  `conditions.ref_name.exclude` covers instead) and reads `"enforcement":
  "active"`, but that file is desired state that was never applied (`origin` is
  the Cursor mirror, not the GitHub repo). Nothing currently proves this
  the way the `release-please--branches--*--components--*` refs used to: those were
  live on GitHub while the taxonomy still rejected them client-side, meaning the
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

## Release-please and strict up-to-date

Issue #19 (private monorepo #32) asked whether branch protection should change
so a release-please pull request would stop sitting `BEHIND` on `develop`.
Leave ruleset `Public CI` (26699837) as it is. Strict up-to-date stays on for
`main` and `develop`. Merging an `autorelease: pending` pull request stays a
human release decision ([AGENTS.md](AGENTS.md#release-cadence-release-please)).

Read-only check on 2026-11-06:

- `strict_required_status_checks_policy` is `true` on **both** `main` and
  `develop`. A release pull request retargeted at `main` still has to be up to
  date. The 2026-09-24 snapshot in #19, where `main` had `strict: false`, does
  not describe this ruleset.
- `release-please-digichat.yml` and `release-please-digiskills.yml` were removed
  in #4919 ([CI_CONVENTIONS.md](docs/agents/CI_CONVENTIONS.md)). Nothing under
  `.github/workflows/` opens those pull requests. `AGENTS.md` still says to keep
  any future release-please target on `develop`: a squash promotion of a bump
  that landed only on `main` reads as a no-op and the changelog empties.
- `GET /git/matching-refs/heads/release-please` returned no refs, and the open
  pull request list was empty. Nothing is parked `BEHIND` by this ruleset today.
- `bypass_actors` on 26699837 is empty (`current_user_can_bypass: never`).
- Ruleset 15270439 (`module-branch-protection`) is not in the list, so it does
  not block the retired `module/*` path.

These options were considered and declined. None of them were sent to the API:

| Option | Why it stays declined |
|--------|------------------------|
| Retarget release-please at `main` | Strict is on there too, the workflows are gone, and `AGENTS.md` forbids that retarget. |
| Clear strict on `develop`, or on ruleset 26699837 | One flag covers `main` and `develop`. Clearing it drops up-to-date for every pull request, and no release-please actor remains to benefit. |
| Bypass the release-please app or `release-please--branches--*` | The app no longer pushes those refs. |
| A scheduled workflow that updates the release branch | There is no such branch, and this dispatch does not add workflows. |
| Automerge on `autorelease: pending` | A release merge stays Chris's decision. |

Before reopening the question, re-read the live ruleset and the refs:

```
gh api repos/digithings-ai/digithings/rulesets/26699837 \
  --jq '{strict: [.rules[] | select(.type=="required_status_checks") | .parameters.strict_required_status_checks_policy], bypass: .bypass_actors, refs: .conditions.ref_name.include}'
gh api repos/digithings-ai/digithings/git/matching-refs/heads/release-please --jq '.[].ref'
```

Settings UI: **Rules → Rulesets → Public CI**. Leave strict required status
checks enabled and the bypass list empty. Save nothing from that screen for
this issue. Classic protection, if it still sits beside the ruleset, was not
re-read (HTTP 403). Leave `…/branches/develop/protection` unpatched.

## Enforcement gaps

Two protections this document previously asserted are not actually configured.
Both are a human call to close — changing branch protection is a settings
change, not a docs change. Re-checked against the rules API on 2026-11-06:

- **`release/v*` has no protection rule.** `Public CI` includes only `main` and
  `develop`, so a release branch can be force-pushed or deleted by anyone
  with write access. A release branch is a shipped version's only maintenance
  line, so losing one means a pinned client can no longer be patched at all.
  Protecting `release/**` (no force-push, no deletion) is intended, and the
  payload already exists in `scripts/github-rulesets/04-protect-releases.json`.
  Applying it is a repo-settings change, so it needs a human, not this document.
- **`main` requires no *approval*.** `required_approving_review_count` is `0`
  on `Public CI`, so a pull request into `main` can be merged by whoever opened
  it. The same ruleset does require `lint`, `secrets`, and `unit`, all strict.
  An older classic-protection read (issue #19, 2026-09-24) named a different
  check, `Every commit reaching main was reviewed`, and recorded `strict: false`
  on `main`. That classic endpoint returned 403 on 2026-11-06 and was not
  re-verified. `require_extra_approval_for_unattributed_changes` is `true`.
