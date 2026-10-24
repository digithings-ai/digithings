**Run 3 — the write-back fix is narrowed and green on the touched paths, and the population repair continues.**

**Branch change (PR digithings-ai/paperclip#51, head `b03523579`, OPEN / MERGEABLE / CLEAN)**

The first version of the fix made the runtime restore any workspace the issue owns. That was too wide: it changed the behaviour of the branch-containment path and of the legacy issues that carry no preference. The restore rule is now narrow:

- The runtime counts a workspace that the issue owns as a reuse request only when the stored preference names a concrete mode (`isolated_workspace`, `operator_branch`, `shared_workspace`).
- An empty preference and `inherit` say nothing about the workspace, so a run with either preference still realizes the workspace afresh. The branch-containment path and the legacy population keep their current behaviour.
- The write-back itself is unchanged: a workspace the issue owns keeps `isolated_workspace`, a workspace another issue owns keeps `reuse_existing`.
- Two upstream tests now expect the resolved mode as the preference of a strategy-only child issue (`issues-service.test.ts`, `heartbeat-accepted-plan-workspace-refresh.test.ts`). The child still gets no workspace; only the two fields now agree.
- New tests pin the narrow rule: an empty preference and `inherit` still realize afresh.

**Verification on the branch**

- 7 suites (write-back, reuse request, issue-runtime binding, issues-service, branch containment, busy, finalize, accepted-plan refresh): **183 tests pass**.
- `heartbeat-workspace-session` + `execution-workspace-policy`: **199 tests pass**.
- `cd server && pnpm exec tsc --noEmit`: **no error**.
- `pnpm test:run` (the full server suite) is a serial run of about 30 minutes. The earlier run was stopped because it mixed the old and the new code; a fresh run on the final commit is running now. The PR body says exactly this, and it also explains that the fork has no pull request CI runner (tracked as DIG-4446), so the local receipt is the gate.

**Population repair (read-only sweep + repair, this run)**

`dt-ws-pref-check --project digithings --recent 200 --max-gets 200 --json` right now: **200 checked, 143 findings = 116 TRAP-WRITEBACK + 26 DROP + 1 BOUND** (last run: 164 findings = 117 + 46 + 1).

- Repaired 10 more DROP-class issues this run (DIG-4784 … DIG-4769), each read back as `pref=isolated_workspace`, `ws=null`, `mode=isolated_workspace`. 19 issues repaired over the two runs; the per-run write cap (20 writes, two per issue) is spent.
- The remaining 26 DROP issues are the older tail and are the last repair batch.
- The 116 bound issues are **not** flipped by hand. On the running server the restore of a bound workspace requires the preference `reuse_existing`; writing `isolated_workspace` on a bound issue would make the next run realize the workspace a second time and mint a second workspace row for the same worktree path. The write-back heals them on their next run, after the fix is live. The newest one is DIG-4847 (created 05:42:48Z), so the write-back is still firing on every new issue until the restart.

**Not in the change:** the create path can still copy a parent's workspace to a child when the request names no workspace field and the parent is already bound; that child then carries the pair `reuse_existing` + `isolated_workspace`. That path needs its own change and its own review — it is the platform side of the rule "create every issue with `dt-create-issue`". The requirement that a request which says `isolated_workspace` is never re-derived from the parent already holds today: the parent copy is skipped as soon as the request names any workspace field, and `dt-create-issue` always names both fields.

**Unblock path (unchanged):** Chris reviews and merges digithings-ai/paperclip#51, then Chris restarts Paperclip. After the restart the write-back keeps the isolated preference, the 116 bound issues heal on their next run, and the last DROP issues are the final repair batch of the sweep.
