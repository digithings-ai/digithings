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

**`git rev-list --count <base>..<branch>` is the wrong measure and must not be used
to classify a branch.** It counts every commit reachable from the
branch tip but not from `develop`, including commits whose *patch is already in
`develop`* by another route. Squash merges guarantee such commits exist: a squash
commit has one sha on `develop`, while the branch keeps the original per-commit
shas with no ancestry relationship. A branch whose entire work already shipped by
squash still reports every commit as "not in develop".

The measure is the **unmerged patch**, i.e. the `+` lines of `git cherry`:

```bash
# patches on <remote>/<branch> that are NOT already applied on <remote>/develop
git cherry github/develop github/<branch> | grep -c '^+'
```

Two corrections to how this was previously stated, both measured on
2026-10-15 (DIG-1600).

**`git cherry` is not a landing test, and this is not a squash problem.** It is
patch-*id* based, so a rebase or a reorder does not change its answer — that
part is right. But a squash merge rewrites the patch it lands (new parent
context, new message) while keeping the diff, and patch identity is a function
of the patch. So a branch whose work shipped by squash can still report a `+`
for every commit it carried. Measured: `claude/digithings-web-ui-refactor`
(PR #4791) merged into `develop` and still reads **144 unmerged patches**.
Across the 71 measurable branches of the 2026-10-06 census, **284 patches sit
on branches whose PR had already merged** — 34% of everything the measure
reports.

Counting them is therefore necessary and not sufficient. `git cherry` answers
*"is this patch new?"*, which is the right question for deciding whether a branch
holds work. It does not answer *"did this branch's work already land?"*, and
nothing downstream may treat it as though it did.

The landed signal is **per PR** and squash-aware. All counts below are over the
**42 census PRs with a resolved branch** (35 `merged=true`, 7 `merged=false`).

1. `merged` — the boolean from `gh api repos/O/R/pulls/<n> --jq .merged`. **Not**
   `merge_commit_sha != null`: GitHub publishes the *test* merge commit it
   computed for a PR whether or not the merge happened, and **4 of the 42** read
   `merged=false` with a non-NULL `merge_commit_sha` (#4560, #4908, #4949,
   #4975). Gating on the sha marks shipped work that never shipped, and marks
   work that DID ship as stranded.
2. `merge-base --is-ancestor <merge_commit_sha> <pr.base.ref>` — against the
   PR's **own** base, not `develop`. **8 of the 35** merged PRs targeted a base
   other than `develop` (3 `main`, 4 `module/digiquant`, 1 `module/digichat`). All
   8 are *also* reachable from `develop` today, so on this census the two tests
   agree — but a `main`-targeted or module-targeted PR is not required to reach
   `develop`, and a `develop` ancestry test answers a question nobody asked. Own
   base is the rule; `on_own_base` was `YES` for all 35 merged PRs, which is the
   control that the check fires.
3. The **merge commit**, not the branch head. A squash merge has no second
   parent, so head-ancestry is the wrong question for exactly the case this
   section is about.

Both signals are implemented in `scripts/branch_census.py`, which is the
executable form of this section and of the tier counts in section 3:

```bash
python3 scripts/branch_census.py                  # JSON summary
python3 scripts/branch_census.py --markdown       # table + bounds
python3 scripts/branch_census.py --no-gh          # git only, no landed column
```

A branch whose ref is gone from the remote is reported **unresolvable**, never
as zero patches: `T0` means *measured, nothing unmerged*, and a branch that
cannot be measured has not earned a free-tier deletion licence.

The remote in these commands is `github`, not `origin`. `origin` on
`digithings-ai/digithings` is a cursor mirror: `github/develop` exists and
`origin/develop` does not, so the commands as previously written — against
`origin/develop` — had no base to compare against.

The companion census command, which reproduces the table in section 1:

```bash
git fetch github '+refs/heads/*:refs/remotes/github/*' \
                '+refs/archive/*:refs/remotes/github/archive/*'
gh pr list --state open --limit 500 --json headRefName -q '.[].headRefName' \
  | sed 's|^|github/|' > open-pr-heads.txt        # branches that are NOT stranded
git for-each-ref --format='%(refname:short)' refs/remotes/github \
  | grep -v '^github/\(main\|develop\)$' > branches.txt
# old = last-commit older than 3 days; then require a non-zero patch count above
```

The archive refspec matters: a branch archived per section 4 clause 5 still
resolves, so its patches stay measurable. Without it those branches fall out of
the census entirely.

## 3. Tiers

Every stale branch lands in exactly one tier. The tier decides who may dispose of
it and what evidence is required.

| Tier | Unmerged patches | Action | Owner | Evidence required |
|------|------------------|--------|-------|-------------------|
| **T0 — free** | 0 | Delete. No approval. | Anyone with write access | None. By definition nothing is lost. |
| **T1 — small** | 1–2 | Delete after a snapshot check. | Agent that owns the branch; DevOps for a bulk run | `dt-snapshot check` green, or the branch listed in the run manifest |
| **T2 — decide** | 3–10 | Explicit PR-or-discard decision per branch. | EM (product owner per branch's originating issue) | The decision is written on the issue: ship it as a PR, or discard it |
| **T3 — escalate** | >10 | CTO decision per branch. | CTO | A diff summary showing what the branch carries and whether an equivalent survives elsewhere |

### The 2026-10-06 census, re-measured

The tier populations recorded on 2026-10-06 were **T0 114, T1 111, T2 47, T3 23**
(295 rows) and are unchanged: those counts describe the census rows, and
`docs/ops/2026-10-06-stranded-branch-triage.tsv` still holds 295. What was
inflated is the patch total, because it was measured with the wrong assumption
about which branches exist and about what a `+` means.

Re-measured 2026-10-15 with `scripts/branch_census.py` against `develop` at
`3528cf9f`, after fetching all live **and** archived refs. Every cell except the
last column is generated by that command; the last column is transcribed from
the 2026-10-06 write-up and is **not** re-derivable from the TSV, whose own
`commits_not_in_develop` column sums to 1764 — a third number, and one this
policy rejects as a measure in the first place.

| Recorded tier | Census rows | Measurable | Measured `+` | Landed (br / p) | No PR (br / p) | PR never landed (br / p) | Previously published `+` |
|---|---|---|---|---|---|---|---|
| T0 | 114 | 6 | 0 | 6 / 0 | 0 / 0 | 0 / 0 | — |
| T1 | 111 | 11 | 10 | 6 / 7 | 2 / 2 | 3 / 1 | 172 |
| T2 | 47 | 43 | **162** | 35 / 133 | 1 / 3 | 7 / 26 | 184 |
| T3 | 23 | 11 | 654 | 1 / 144 | 7 / 425 | 3 / 85 | 1035 |
| **Total** | **295** | **71** | **826** | **48 / 284** | **10 / 430** | **13 / 112** | **1391** |

The *No PR* and *PR never landed* columns sum to **542**, not 112: a no-PR
branch is not landed either, so the tool's one-line summary reports the two
together while this table separates them — and they are different problems with
different owners (corrections 2 and 3 below).

Three corrections, in order of how much they move the number.

**1. "Total recoverable patches: 1391" is not measurable and was not
recoverable.** 224 of the 295 census rows — 76% — no longer resolve to any ref,
live or archived. A vanished ref has no patch count to read, so the population
those 224 rows described cannot be re-derived by any tool. Of what *is*
measurable the honest figure is **826 patches across 71 branches**, and that is
a **lower bound**, not a total. The published per-tier figures were also higher
than what the surviving refs yield in every tier (T1 172 vs 10, T2 184 vs 162,
T3 1035 vs 654), because the unresolvable rows were scored as though they
still had content.

**2. Of the 826 measurable patches, 284 are already landed.** `git cherry`
reports them as unmerged because their PRs shipped by squash (§ 2). They are
not recoverable work; they are shipped work wearing a `+`. The number that
disposal can act on is **112 patches across 13 branches** whose PR closed
without merging — those are the T2/T3 candidates, and 26 of the 112 are in T2.

**3. 430 patches across 10 branches have no PR of their own.** Seven are T3.
These are stack bases and unfiled branches: real, substantial, un-landed diffs
with no PR to be landed or discarded through, so they cannot be classified by
the per-PR signal at all. They are the largest single unclassified mass in the
census and § 4 clause 5 does not cover them — there is no decision on the issue
to record, because no issue was ever opened. **This is the largest open
question in the census** and it is not answerable by re-measuring.

Two smaller notes, both measured on the same pass:

- **11 of the 826 measurable patches sit on refs section 5 already excludes**
  (`module/**` ×10, `release/v*` ×1), which are never counted as stranded.
  Including them in a recoverable total contradicts section 5.
- **3 of the 71 measurable branches have dropped a tier** since 2026-10-06 and
  none rose: `fix/4991-fanout-leg-isolation` T2→T1 (2 patches),
  `cursor/langfuse-design-reference-3c6b` T1→T0 and
  `docs/designeer-xyz-reference` T1→T0 (0 patches each). The census
  re-derives the tier from the measured patch count and prints this drift
  against the recorded one, rather than trusting a column written nine days
  ago. Only measurable branches can drift; the 224 unresolvable rows have no
  tier to re-derive and are reported as unmeasured, not as tier 0.

The tier definitions above are unchanged and remain keyed on the **measured**
unmerged patch count. The table above is reproducible:

```bash
python3 scripts/branch_census.py --markdown
```

It prints this table keyed on the recorded tier, a second table keyed on the
measured tier (which is what disposal acts on, and which differs by exactly the
drift listed above), and the drift list.

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

- **Weekly.** The cron worker runs the census from section 2 —
  `python3 scripts/branch_census.py --markdown` is the reference implementation —
  and writes a triage manifest. Any T0 or T1 branch older than 14 days is deleted
  in that run, after the snapshot check. **A branch the census reports as
  unresolvable is never deleted on a T0 verdict**: T0 means *measured, nothing
  unmerged*, and an unmeasurable branch has not been measured.
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