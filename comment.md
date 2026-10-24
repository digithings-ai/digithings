**Root cause found, fix is up as PR digithings-ai/paperclip#51, population swept and partly repaired.**

**1. Where the write-back is**

`server/src/services/heartbeat.ts`, in `bindIssueToPersistedExecutionWorkspace` (the function that binds the issue to the workspace a run just provisioned):

```ts
const shouldSwitchIssueToExistingWorkspace =
  issueRef?.executionWorkspacePreference === "reuse_existing" ||
  requestedExecutionWorkspaceMode === "isolated_workspace" ||   // always true for an isolated issue
  requestedExecutionWorkspaceMode === "operator_branch" ||
  warmReusableExecutionWorkspace || nativeSharedWorkspace;
...
if (shouldSwitchIssueToExistingWorkspace && (pref !== "reuse_existing" || mode !== nextIssueWorkspaceMode)) {
  nextIssuePatch.executionWorkspacePreference = "reuse_existing";   // hardcoded
  nextIssuePatch.executionWorkspaceSettings = { ...settings, mode: nextIssueWorkspaceMode };
}
```

`nextIssueWorkspaceMode` is the mode of the workspace the run just created, so it is `isolated_workspace`. The preference the request asked for is overwritten with `reuse_existing` and the mode stays `isolated_workspace`. That is the trap pair, written by the platform, after the create request and after `dt-create-issue` read its own field back. The exit-0 contract of the script cannot see it, because the write-back lands later.

**2. It is not intermittent**

Of the 40 newest digithings issues, 21 have a bound workspace, and 21 of those 21 carry the trap. 19 have no workspace, and none of those carry it. The rule is exact: the write-back fires on every issue that gets an isolated workspace bound, so it hits every issue after its first run. The 6-issue sample in this ticket was too small to show it.

Census of the 200 newest digithings issues (2026-10-20 04:55Z to 2026-10-21 05:30Z): 164 findings, 117 TRAP-WRITEBACK, 46 DROP (preference null), 1 BOUND.

**3. No cross-issue worktree is happening today**

I compared every bound workspace with its issue. For all 21 in the last 40, `sourceIssueId` is the issue itself, the mode is `isolated_workspace` and the status is `active`. Zero are bound to another issue's workspace. The trap is dormant: the fields lie, the binding is healthy. It bites the moment a bound workspace is not the issue's own, which is exactly what the `reuse_existing` pair invites.

**4. The other half: a null preference at creation**

`server/src/services/issues.ts`, create path. When the platform resolves an isolation mode for a new issue (from the project policy, or from a strategy inherited from the parent) it stores the mode and leaves the preference empty. That is the 46 DROP issues. They are not the write-back, they are a second defect in the same pair.

Requirement 1 already holds for a request that names a field: `hasExplicitExecutionWorkspaceOverride` (issues.ts:9970) skips the parent block, so an explicit `isolated_workspace` is never re-derived from the parent. It does not hold for a request that names nothing, and the platform then writes the mode without the preference.

**5. The fix: PR digithings-ai/paperclip#51** (branch `fix/workspace-preference-write-back`, base `master`)

- The write-back keeps `isolated_workspace` when the bound workspace is the one the issue owns. A workspace owned by another issue keeps `reuse_existing`, so a cross-issue share stays visible.
- The reuse request counts a workspace the issue owns as a reuse request, whatever the stored preference says. Without this, restoring the bound workspace would realize it a second time and mint a second workspace row for the same worktree path. This is also why I did not simply flip the preference on the live population (see 6).
- The create path writes the resolved mode as the preference when the request names no preference and the issue has no workspace of its own.
- New test file with 11 tests. The two existing workspace suites (199 tests) pass. `tsc --noEmit` is clean.

**6. Population repair: what I did, and what I deliberately did not do**

Repaired 9 issues with the null preference: DIG-4827, DIG-4809, DIG-4808, DIG-4807, DIG-4806, DIG-4805, DIG-4804, DIG-4803, DIG-4796. Each one now reads `pref=isolated_workspace`, `ws=null`, `mode=isolated_workspace`, verified by read-back. The per-run cross-issue write cap is 20 and an issue takes two writes, so 9 is the ceiling for one run. 37 DROP issues remain in the 200-issue window.

I did not flip the preference on the 117 bound issues. On the running server the preference is what makes the next run restore the bound workspace (`resolveExecutionWorkspaceReuseRequestForIssue`). Flipping it now would make the next run realize a second workspace row for the same worktree path, and the occupancy guard from PR #45 would then see two live rows on one path. That repair belongs to the write-back, and PR #51 makes it durable: after the merge and the restart, each bound issue writes `isolated_workspace` back on its next run.

Live proof that a field repair is not durable. I repaired DIG-4840 to `pref=isolated_workspace`, `ws=null`. Minutes later the re-read shows DIG-4840 as TRAP-WRITEBACK with `pref=reuse_existing` and a bound workspace. The platform overwrote my repair in the same run that provisioned the workspace.

**7. What I need**

- A review and a merge of PR #51. I opened it, I own it to merged.
- Chris to restart Paperclip after the merge. I do not restart it.
- After the restart the 117 bound issues heal themselves, and the remaining 37 DROP issues are the last repair batch.

Status: blocked on the merge and the restart. The sweep continues in the next run.
