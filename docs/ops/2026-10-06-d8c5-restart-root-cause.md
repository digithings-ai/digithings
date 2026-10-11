# Root cause: the d8c5 digiquant-web stack never merged its base

Issue: DIG-1582. Follows DIG-1550 (census) and DIG-1561 (policy).
Evidence as of `origin/develop` @ `8f389a439`, 2026-10-06.

## 1. The cause, in one paragraph

The dashboard was not rebuilt five times; **the stack it sat on was never merged, so
every branch after it was a rebuild of the stack rather than of the dashboard.** All
eight branches in the family — `cursor/brief-panes-slice-c-d8c5`,
`cursor/dashboard-digiquant-web-d8c5`, `cursor/pipeline-digiquant-web-d8c5`,
`cursor/integrations-digiquant-web-d8c5`, `cursor/digiquant-hero-slice-i-d8c5`,
`cursor/digiquant-web-finalize-d8c5`, `cursor/ui-surfaces-d8c5` and the sixth attempt
`origin/cursor/ui-surfaces-d8c5` — share one merge-base with each other:
`9e53df904`, which is the **tip of `task/4895-dqweb-3910-message`**, a branch that sits
40 commits ahead of `develop` and whose PR **#4900 was closed unmerged** on 2026-10-03.
Nothing downstream of an unmerged base can land, and no branch in the family has a
merged patch in `develop` (`git cherry origin/develop origin/<branch>` reports `0`
`-` lines for all seven). The agent session after that therefore found an open issue
(#4895 / #4975), a branch full of work, no PR, and nothing anywhere recording that the
work was live — and started a new branch off the same unmerged tip. What turned one
attempt into five was the missing merge-back owner, not a missing plan.

## 2. The three "siblings" are one leaf split, not three restarts

The census reads `dashboard`, `pipeline` and `integrations` as near-identical rebuilds
one commit apart. They are one Cursor session's leaf decomposition, committed in the
same second:

| Branch | Parent | Tip | Date | Commit | Files |
|--------|--------|-----|------|--------|-------|
| `cursor/dashboard-digiquant-web-d8c5` | `9e53df904` | `0b0ed2343` | 2026-10-02T02:12:22Z | `fix(digiquant-web): use the empty dashboard walkthrough frame` | `app/_bands/dashboard.tsx` + its test |
| `cursor/pipeline-digiquant-web-d8c5` | `9e53df904` | `e1c4792ce` | 2026-10-02T02:12:22Z | `fix(digiquant-web): drop the sample pipeline timeline` | `app/_bands/pipeline.tsx` + its test |
| `cursor/integrations-digiquant-web-d8c5` | `9e53df904` | `0cc8b8d15` | 2026-10-02T02:12:22Z | `fix(digiquant-web): wire the local LuxAlgo lookup into integrations` | `app/_bands/integrations.tsx` + its test |

Same parent, same second, same committer (`Cursor Agent <cursoragent@cursor.com>`),
three different band files, one commit and one test each. That is the decompose step
working. The Census's "four near-identical siblings" reading is wrong, and policy
section 6.4 clause 4 inherits that error.

## 3. The blanket close is what removed the in-flight signal

Every PR in the family was closed in one action, with one comment, and the branch was
deliberately kept:

| PR | head → base | opened | closed | merged | closing comment |
|----|-------------|--------|--------|--------|-----------------|
| #4900 | `task/4895-dqweb-3910-message` → `develop` | — | 2026-10-03 | **never** | — |
| #4978 | `cursor/brief-panes-slice-c-d8c5` → `develop` | 2026-10-02T01:24Z | 2026-10-04T04:00Z | never | "Closed as superseded by the UI refactor. Branch kept." |
| #4979 | `cursor/pipeline-digiquant-web-d8c5` → `task/4895-…` | 2026-10-02T02:15Z | 2026-10-04T04:00Z | never | same |
| #4980 | `cursor/dashboard-digiquant-web-d8c5` → `task/4895-…` | 2026-10-02T02:15Z | 2026-10-04T04:00Z | never | same |
| #4981 | `cursor/integrations-digiquant-web-d8c5` → `task/4895-…` | 2026-10-02T02:15Z | 2026-10-03T01:36Z | never | "Closing as superseded. The integrations-band changes … are already in #4986." |
| #4984 | `cursor/digiquant-hero-slice-i-d8c5` → `task/4895-…` | 2026-10-02T02:41Z | 2026-10-04T04:00Z | never | same as #4978 |
| #4985 | `cursor/digiquant-web-finalize-d8c5` → `cursor/digiquant-hero-slice-i-d8c5` | 2026-10-02T04:10Z | 2026-10-04T04:00Z | never | same as #4978 |
| #4986 | `cursor/ui-surfaces-d8c5` → `develop` | 2026-10-02T11:47Z | **still open** | — | `mergeable: CONFLICTING`, `mergeStateStatus: DIRTY` |

Before 2026-10-03 an open PR was the in-flight marker, and the marker was correct.
After the blanket close, five branches carried live work with **no PR, no issue
comment, and no branch metadata** saying they were live. The next session's only
evidence was a branch name and an open issue. That is the moment "restart this"
became indistinguishable from "start a parallel attempt", and 6.4 stopped being
enforceable.

## 4. `skeleton-mocks-67ef` is not in this story

`cursor/digiquant-dashboard-skeleton-mocks-67ef` is a **documentation fork, not an agent
rebuild**. Its tip commits are Chris Stefan, 2026-10-01 21:15–23:05 +02:00:

- `docs(dashboard): dense canvas remock — seven craft locks from 051f13ec`
- `docs(dashboard): Claude implement brief — SoT 051f13ec`
- `docs(dashboard-mocks): lock handoff — no live digiquant as design ref`

Its merge-base with the d8c5 family is `751bdcd3d` (`feat(web): footer pixel wordmark`,
PR #4898, merged), it carries no `apps/` change in its own commits, and its last line
explicitly rules out the live digiquant app as a design reference. It should be
classified as docs, not as a sixth rebuild. Policy section 6.4 clause 4 should drop it
from the list.

## 5. The other two families do not share this cause

Measured against `docs/ops/2026-10-06-stranded-branch-triage.tsv`, column `pr_state`:

| Family | rows | merged | closed | open | NO-PR | cause |
|--------|------|--------|--------|------|-------|-------|
| `*3d52` (kaios, house, olympus, stripe) | 35 | **31** | 4 | 0 | 0 | `delete_branch_on_merge: false` on the repo. PRs #3412, #3390, #3431 all carry `mergedAt`. Nothing is lost; the branches are pure litter. Already covered as prevention item 1 in [branch-hygiene-policy.md](branch-hygiene-policy.md), owner Platform. |
| `*sdca` | 15 | 2 | 8 | 1 | 4 | **mixed.** The 8 `closed` rows are the d8c5 shape (PR 3202, 3219, 3220, 3235, 3245, 3249, 3282 closed unmerged). The 4 `NO-PR` rows are a distinct shape: `claude/sdca-rsi-confluence-and-period-search` (99 commits), `claude/sdca-full-recalibration` (31), `claude/sdca-develop-sync` (3), `claude/sdca-index-curve-mismatch-fix` (1) — a Claude session committing straight to `claude/*` branches with no PR at all, so no marker ever existed. |

So **one cause covers the d8c5 family and the 8 closed sdca branches**: an unmerged
stack base with no merge-back owner, whose only liveness signal (the PR) was removed
in a blanket close. It does **not** cover `3d52` (merged branches — a repo setting,
already owned) and it does not fully cover `sdca` (the `NO-PR` rows are work that was
never proposed for merge at all).

## 6. Why section 6.4 is not enforceable today

[branch-hygiene-policy.md](branch-hygiene-policy.md) § 6.4 says: when work needs a
restart, abandon the existing branch with a written reason rather than forking again.

Two things are missing, and both are mechanical, not cultural:

1. **No lookup.** The rule requires the agent to *know* that an existing branch is the
   same work. Nothing in the repo answers that question. There is no registry of
   in-flight branches; `grep -ril 'in-flight' scripts/ .github/workflows/` returns
   nothing branch-related.
2. **No gate.** Even an agent that knew would still fork freely. `scripts/hooks/pre-push.sh`
   (209 lines) enforces remote allow-list, branch-name taxonomy, `main` push gating and
   live-trading trailers. It has no arm about duplicate work. `tests/scripts/test_pre_push_hook.py`
   and `.sh` are the harness where a new arm would be pinned.

An unenforceable rule is a reminder to be careful, which is what the issue asked us not
to ship.

## 7. The control

**Resume before create, enforced at the pre-push hook, with the reason as the
escape.** A new arm in `scripts/hooks/pre-push.sh` (plus `scripts/branch_restart_check.py`
for the logic) that runs on every push of a **new** branch:

1. Compute the candidate's unmerged patch-ids: `git cherry origin/develop <candidate>`.
2. Compare them against every non-protected `origin/*` branch not reachable from
   `develop`.
3. If **3 or more** of the candidate's patch-ids already exist on another unmerged
   branch, refuse the push and print the sibling branches, their tips, and their patch
   overlap.
4. The push proceeds only with one of:
   - `RESUME_FROM=<branch>` — cut the new branch from that branch instead. The hook
     re-runs the check against the parent so a resume of a resume cannot loop.
   - `RESTART_REASON: <one line>` in the tip commit message, or
     `RESTART_REASON=<one line>` in the push environment. The reason is written to the
     run scratch log and returned in the refusal text so the next session can read it.
5. A branch whose only overlap is with branches already in `develop` never triggers.

Why 3 and not 1: the d8c5 siblings share a whole 40-commit base, and two legitimate
parallel leaves in the same area will share one patch. A threshold of 3 separates "I am
about to redo work that is still in flight" from "I am working next to someone".

Why the hook and not a document: `make hooks-install` already puts one copy of
`pre-push.sh` in every worktree, so every agent on every adapter passes through it. A
policy section is read by the session that already forgot; a refusal is read by the
session that is about to fork.

Why `RESUME_FROM` beats a registry: a registry is a second source of truth that drifts
and needs an owner. Git already holds the answer — patch-ids on unmerged branches. The
hook asks git, and the reason travels with the commit.

## 8. Ownership

| Part | Owner | Note |
|------|-------|------|
| Hook arm + `scripts/branch_restart_check.py` + tests | Platform, EM-decomposed | DIG-1583 |
| Correct § 6.4 clause 4 (drop `skeleton-mocks-67ef`, describe the unmerged-base shape, point at § 7) | EM | this doc's follow-up edit |
| `delete_branch_on_merge: true` for `3d52` | Platform | already prevention item 1, DIG-1561 |
| The blanket close that removed the liveness marker | **Chris** | not engineering. Five branches were closed in one action on 2026-10-03/04 with "Branch kept" and no per-branch decision on the issue. That call was correct on the merits — the UI refactor did supersede them — but it left 190 commits of live work with no marker, and that is what produced the sixth attempt. |

The cause is engineering, and so is the fix. One step of it is not: closing five live
branches in a single action without recording a decision per branch is a call only the
owner can make, and it is the step that made the rest possible.