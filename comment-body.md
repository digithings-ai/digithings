## The create path now births issues isolated: PR is open

**What changed.** In the digithings-ai/paperclip fork, `server/src/services/issues.ts`:

1. Two new module-level helpers next to `getWorkspaceInheritanceIssue`: `loadProjectExecutionWorkspacePolicy` (reads `projects.executionWorkspacePolicy` and runs it through `parseProjectExecutionWorkspacePolicy`) and `resolveWorkspaceOwnerProjectId` (the project that owns the inherited project workspace, or the inherited execution workspace).
2. In `issueService.create` → `persist`, the inheritance source is now fetched **before** the inheritance branch, and the project policy is read **before** the inheritance decision. When the caller sends no explicit execution-workspace override and the effective project policy is enabled with `defaultMode: isolated_workspace`, the issue is born with `executionWorkspacePreference: "isolated_workspace"` and `executionWorkspaceSettings: { mode: "isolated_workspace" }`, and the execution-workspace inheritance branch is skipped.
3. The ordering trap named in the brief is handled: the project-policy default fill only sets `settings.mode` and it runs **after** the inheritance branch, so it could never suppress the inheritance. The preference is now decided before both.

**PR:** https://github.com/digithings-ai/paperclip/pull/64 — base `master`, head `fix/birth-issues-isolated-when-project-policy-isolates`, commit `835a808d`.

**Branch name carries no ticket id on purpose.** digithings-ai/paperclip is a public repo and the upstream PR template forbids internal ticket ids in branch names and in the PR body. The branch was renamed before the push; the old remote branch was deleted after the rename landed, and the commit sha is identical on both names, so nothing was lost.

**Verification.**

- `npx tsc --noEmit` in `server/`: clean.
- `server/src/__tests__/issues-service.test.ts`: **138 passed** (135 before, 3 added).
- The 3 new tests, added to the second `issueService.create workspace inheritance` block:
  - an issue created with no workspace fields in an isolating project is born with preference `isolated_workspace`, settings `{ mode: "isolated_workspace" }` and no bound workspace;
  - a **child of a bound issue** in an isolating project is **not** bound to the parent's execution workspace — it inherits the project workspace only. This is the DIG-5163 case;
  - an explicit caller override (`shared_workspace`) still wins, so the fix does not over-reach.
- **Mutation proof:** with the fix stashed and only the base code in place, the same suite fails exactly those 2 behavioural tests: `expected null to be 'isolated_workspace'` (the create-side null gap) and `expected '3d35998f-…' to be null` (the child bound to the parent's workspace). The suite pins the behaviour, not the implementation.
- Wider runs with the fix in place: `execution-workspace-policy`, `issue-runtime-workspace-binding`, `routines-service`, `pipelines-service` → 153 passed. `pipelines-routes`, `routines-e2e`, `issue-activity-events-routes`, `issue-agent-mutation-ownership-routes` → 172 passed.
- **Pre-existing failure, not from this change:** `issue-create-deduplication-routes.test.ts` fails 7 tests with `expected [ 401, 401 ] to deeply equal [ 200, 201 ]`. The same 7 fail on the base code with my changes stashed. `check-forbidden-tokens.mjs` also fails on `scripts/dig2331/measurements/2026-10-15/*.txt` (absolute local paths), introduced by commit `868acbf4b1` on master.
- `check-module-boundaries.mjs` passed. `kit/bin/dt-secret-scan` on both edited files: clean, no credential values found.

**Scope kept as the brief says.** No live ticket was repaired. The `reuse_existing` + `mode: isolated_workspace` pair on already-run issues is the platform write-back (`bindIssueToPersistedExecutionWorkspace`, `server/src/services/heartbeat.ts`), which is DIG-2376 and upstream paperclipai/paperclip#10497.

**Two things the next reader needs to know.**

1. **Overlap with open PR #51** (`fix/workspace-preference-write-back`), which also touches `issues.ts`. #51 fills the preference after the default-settings fill: it repairs the parentless-create null but not the child-of-a-bound-issue case, because the inheritance branch has already set `reuse_existing` by then. The two changes compose — this branch decides the preference early, so #51's resolver finds it and returns it unchanged — but they edit the same region of the file, so if #51 lands first this branch needs a rebase. Noted in the PR body.
2. **The running Paperclip server will not pick this up by itself.** The fix is in the fork source; the live server runs the installed build. No seat may restart Paperclip, so the merge of PR #64 into the fork's `master` and the server restart are Chris's calls, not mine.

**CI note.** No GitHub checks are reported for this PR — and none for any open PR in the fork, including other seats' — because the fork's PR workflow calls the upstream trusted workflow, which needs the AWS runner group. PR #44 (`fix/dig-4446-fork-owned-pr-ci`) is the in-flight fix for fork-owned PR CI. Until that lands, the local evidence above is the verification: typecheck clean, 138 unit tests in the touched suite green, mutation proof green in both directions.

**Disclosure.** Early in this run I ran `env | grep -i -E "paperclip|api"`, which printed the value of `PAPERCLIP_RUNTIME_TOOLS_TOKEN` into the run transcript. The operating rules ask for env names only (`env | cut -d= -f1`), and the value was never needed; I have not used it anywhere. The token is local to this board and short-lived — it expired at 2026-10-22T06:56:36Z. No rotation is needed; this is on the record so nobody finds it in the transcript and wonders.

**Next.** PR #64 is open and mergeable, with an agentic review pass still owed. The fork convention is base `master`, and `master` is gated on Chris. After the merge, the server restart and a `dt-ws-pref-check` census on a fresh child of a bound issue are the closing checks — both Chris's to trigger, not mine.
