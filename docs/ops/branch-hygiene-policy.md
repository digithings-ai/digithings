# Branch hygiene policy

Status: **adopted 2026-10-06** by the CTO, in response to
`docs/ops/2026-10-06-stranded-work-and-backup-report.md` (DIG-1550).
Issue: DIG-1561. Triage data: `docs/ops/2026-10-06-stranded-branch-triage.tsv`.

This document is the normative source for what happens to a stale branch and for
the tools that stop stale branches from accumulating. `BRANCHING.md` describes
the branching *model*; this document describes branch *disposal* and the
*prevention* side. Where the two overlap, this document wins on disposal.

## 1. The problem, measured

At the 2026-10-06 census, `digithings-ai/digithings` had **512** non-protected
`origin/*` branches. Of those:

| Set | Count |
|-----|-------|
| Older than 3 days (cutoff 2026-10-03) | 327 |
| …with commits not in `origin/develop` | 295 |
| …and no open PR | **288** |
| Currently covered by an open PR | 95 |

288 unmerged, unreferenced branches is not an incident. It is a missing policy.
Ad-hoc rescue does not scale past the first hundred, which is why this document
exists instead of another cleanup run.

## 2. The measure: unmerged patches, not commit count

**`git rev-list --count origin/develop..origin/<branch>` is the wrong measure and
must not be used to classify a branch.** It counts every commit reachable from the
branch tip but not from `develop`, including commits whose *patch is already in
`develop`* by another route. Squash merges guarantee such commits exist: a squash
commit has one sha on `develop`, while the branch keeps the original per-commit
shas with no ancestry relationship. A branch whose entire work already shipped by
squash still reports every commit as "not in develop".

The measure is the **unmerged patch**, i.e. the `+` lines of `git cherry`:

```bash
# patches on origin/<branch> that are NOT already applied on origin/develop
git cherry origin/develop origin/<branch> | grep -c '^+'
```

This is patch-id based, so it is invariant to squash, rebase and reordering. All
thresholds in this policy are in unmerged patches.

The companion census command, which reproduces the table in section 1:

```bash
git fetch origin --prune
gh pr list --state open --limit 500 --json headRefName -q '.[].headRefName' \
  | sed 's|^|origin/|' > open-pr-heads.txt        # branches that are NOT stranded
git for-each-ref --format='%(refname:short)' refs/remotes/origin \
  | grep -v '^origin/\(main\|develop\)$' > branches.txt
# old = last-commit older than 3 days; then require a non-zero patch count above
```

## 3. Tiers

Every stale branch lands in exactly one tier. The tier decides who may dispose of
it and what evidence is required.

| Tier | Unmerged patches | Action | Owner | Evidence required |
|------|------------------|--------|-------|-------------------|
| **T0 — free** | 0 | Delete. No approval. | Anyone with write access | None. By definition nothing is lost. |
| **T1 — small** | 1–2 | Delete after a snapshot check. | Agent that owns the branch; DevOps for a bulk run | `dt-snapshot check` green, or the branch listed in the run manifest |
| **T2 — decide** | 3–10 | Explicit PR-or-discard decision per branch. | EM (product owner per branch's originating issue) | The decision is written on the issue: ship it as a PR, or discard it |
| **T3 — escalate** | >10 | CTO decision per branch. | CTO | A diff summary showing what the branch carries and whether an equivalent survives elsewhere |

The 2026-10-06 census populates these as **T0 114, T1 111, T2 47, T3 23** (295
branches, including the 17 `module/*` and `chore/sync-module-*` refs excluded from
the 288). Total recoverable patches: **1391** — T1 172, T2 184, T3 1035.

## 4. Deletion preconditions

No branch is deleted, by an agent or in bulk, until all of the following hold.

1. **Snapshot green.** `dt-snapshot check` passes, or the ref is present in the
   run manifest with its sha. The snapshot is the recovery path for everything
   that follows, so it is checked first, not last.
2. **No open PR.** A branch with an open PR is never stranded by definition.
3. **Correct tier evidence recorded.** T0 needs nothing; T1 needs the manifest
   entry; T2 and T3 need the decision on the issue.
4. **Not excluded.** The exclusions in section 5 do not apply.
5. **Patches preserved somewhere for T2/T3.** A T2 or T3 branch that is *discarded*
   rather than shipped must first be pushed to an archive ref —
   `refs/archive/<branch>` — so the work is recoverable without being on the
   branch list. This is the difference between discarding and destroying.

Deletion is `git push origin --delete <branch>`. The client pre-push hook exempts
deletions from the name-taxonomy check by design, so a stale ref stays deletable
even after the taxonomy tightens.

## 5. Exclusions

Never delete, never count as stranded:

- `main`, `develop`.
- `module/**` — the `module-branch-protection` ruleset already blocks deletion.
- `chore/sync-module-*` — long-lived module integration syncs.
- `release/v*` — a shipped version's only maintenance line. An old release branch
  is the only way to patch a client still pinned to it. Not yet protected
  server-side; see the gap note in `BRANCHING.md`.
- Any branch with an open PR.
- Any branch touched in the last 3 days.

## 6. Prevention

Disposal is the tail end. The front end is where branches stop being created.

1. **`delete_branch_on_merge` must be `true`.** It is `false` today on
   `digithings-ai/digithings`, and `allow_auto_merge` is `false` as well. Every
   merged PR that leaves its branch behind is a branch that has to be disposed of
   by hand later. This is the single largest lever in this document and it is a
   repo-settings change, not a code change.
2. **Branch-age guard in CI.** A PR or branch whose head is older than **10 days**
   must not trigger a rebuild. It gets a labelled warning and a stop. Rebuilding
   288 stale branches on every push is what makes cleanup expensive. Drive the
   check from the `digithings-cron` Cloudflare Worker (`apps/digithings-cron`) —
   the repo removed `schedule:` triggers in #3579, so a new `schedule:` is not the
   house pattern.
3. **Pre-push age warning.** `scripts/hooks/pre-push.sh` already enforces the
   branch taxonomy. Add a non-blocking warning when a branch being pushed is
   older than 10 days, so an agent gets told at push time instead of at deletion
   time.
4. **One PR per attempt, no restarts, enforced at push time.** The digiquant
   dashboard family (d8c5) was rebuilt from scratch five times and the cause was
   not the number of branches. Every one of those branches was cut from
   `task/4895-dqweb-3910-message` (`9e53df904`), which is 40 commits ahead of
   `develop` and not in it — PR #4900 carried that base and was closed on
   2026-10-03 without merging. On 2026-10-03/04 five of the resulting PRs were
   closed in one action while the branches were kept, which removed the only
   liveness marker on the work. Each later agent then saw no in-flight attempt and
   rebuilt the stack. The root cause, the evidence and the per-family tallies are
   in `docs/ops/2026-10-06-d8c5-restart-root-cause.md`.

   Two corrections to the earlier reading of this family: `dashboard`,
   `pipeline` and `integrations` are **one leaf split into three parallel bands**,
   not three restarts (same parent, same committer, same commit timestamp
   2026-10-02T02:12:22Z, one band file plus one test each), and
   `cursor/digiquant-dashboard-skeleton-mocks-67ef` is a **docs** fork under
   `docs/dashboard-mocks/`, not an agent rebuild.

   "Abandon the existing branch with a written reason" below is the rule; the
   enforcement is a pre-push guard on new branches that refuses a push when 3 or
   more of the candidate's unmerged patch-ids already exist on another unmerged
   branch, unless the push carries `RESUME_FROM=<branch>` or `RESTART_REASON`.
   Implemented by Platform under DIG-1589. A written reason that no tool reads is
   a reminder, and a reminder does not survive a restart.
5. **Artifacts do not go on branches.** `chore/rescue-4804-gold-artifacts` carries
   4,149,332 artifact lines across 105 JSON files and almost no code. Generated
   data belongs in object storage or in `develop`, not in a 4-million-line branch
   diff.

## 7. Cadence

- **Weekly.** The cron worker runs the census from section 2 and writes a triage
  manifest. Any T0 or T1 branch older than 14 days is deleted in that run, after
  the snapshot check.
- **Monthly.** T2 branches older than 30 days are escalated to the EM with the
  decision request; unanswered after 14 more days they are archived per section 4
  clause 5.
- **Quarterly.** The tier counts are reported. A rising T2 or T3 count is a signal
  that prevention is failing, and section 6 gets tightened.

## 8. Exception process

Any agent may request an exception from a deletion on the branch's own issue. An
exception needs the requester's name, the reason, and the date the branch becomes
deletable again. The EM grants exceptions under 30 days; the CTO grants longer
ones. No exception is open-ended.

## 9. Ownership

| Item | Owner |
|------|-------|
| Weekly census + T0/T1 deletion run | DevOps |
| T2 PR-or-discard decisions | EM |
| T3 decisions | CTO |
| `delete_branch_on_merge` repo setting | Platform |
| Branch-age guard in CI, driven from `digithings-cron` | Platform |
| Pre-push age warning | Platform |
| Pre-push duplicate-work guard (section 6 clause 4) | Platform, DIG-1589 |
| Closing a PR without merging while keeping its branch | requester, on the issue |
| This document | CTO |

## 10. What this policy does not do

- It does not protect `release/v*`. That gap is documented in `BRANCHING.md` and
  needs a human to apply `scripts/github-rulesets/04-protect-releases.json`.
- It does not set a required approval count. `main` still requires 0 approvals.
- It does not decide the fate of any individual T2 or T3 branch. That is a
  per-branch decision by the tier owner in section 3, on the issue.