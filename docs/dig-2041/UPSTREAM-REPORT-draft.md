# Upstream report — draft, NOT YET FILED

Target: `github.com/paperclipai/paperclip` issues (declared in the `@paperclipai/server`
package `bugs` field: `https://github.com/paperclipai/paperclip/issues`).
Status: **awaiting Chris's approval to publish.** Publishing outside the company is
Chris-only under the digithings operating rules.

Filed against: `@paperclipai/server` `2026.1005.0`, source at `master`.

---

## Title

`reuse_existing` is silently injected into issues created by an agent, sharing the agent's live worktree; `allowIssueOverride` is never enforced

---

## Body

Two related defects in the execution-workspace resolution path. The second makes the first
unfixable by configuration, which is why they belong in one report.

### Defect 1 — create silently inherits the calling agent's own worktree

When an **agent** creates an issue via `POST /api/companies/{companyId}/issues` and the
request body names **no** execution-workspace field at all, the server injects the calling
agent's own current run issue as the workspace inheritance source.

`server/src/routes/issues.ts:12059-12062`:

```ts
const runWorkspaceInheritanceSourceIssueId =
  hasExplicitIssueWorkspaceCreateSelection(rawCreateBody)
    ? null
    : await resolveRunIssueWorkspaceInheritanceSource(companyId, actor);
```

which is spread into the create body at `server/src/routes/issues.ts:12089-12094`:

```ts
...(runWorkspaceInheritanceSourceIssueId
  ? { inheritExecutionWorkspaceFromIssueId: runWorkspaceInheritanceSourceIssueId }
  : {}),
```

`resolveRunIssueWorkspaceInheritanceSource` reads `heartbeatRuns.contextSnapshot` for the
caller's run and returns `context.issueId` when the run has a non-empty
`executionWorkspaceId`.

That drives the hardcoded literal in `server/src/services/issues.ts:10107`:

```ts
if (sourceWorkspace) {
  executionWorkspaceId = sourceWorkspace.id;
  executionWorkspacePreference = "reuse_existing";
  executionWorkspaceSettings = {
    ...workspaceSource.executionWorkspaceSettings,
    mode: issueExecutionWorkspaceModeForPersistedWorkspace(sourceWorkspace.mode),
  };
}
```

The trigger is the omission guard `hasExplicitIssueWorkspaceCreateSelection`
(`server/src/routes/issues.ts`), which treats the request as "no selection" when *none* of
these are present:

```ts
input.parentId !== undefined ||
input.inheritExecutionWorkspaceFromIssueId !== undefined ||
input.projectWorkspaceId !== undefined ||
input.executionWorkspaceId !== undefined ||
input.executionWorkspacePreference !== undefined ||
input.executionWorkspaceSettings !== undefined
```

**Observed result.** A bare create by an agent running in an isolated worktree returns:

```
executionWorkspacePreference : "reuse_existing"
executionWorkspaceSettings   : { "mode": "isolated_workspace" }
executionWorkspaceId         : <the agent's own worktree>
```

`mode: isolated_workspace` is copied from the source workspace's own mode, so the settings
object appears to describe isolation while the preference binds the caller to a workspace
another issue already holds.

**Why this is a defect rather than a default.** The value is not a resolution of an absent
enum member. It is a deliberate write of a specific workspace belonging to a different
issue. The issue's own `executionWorkspaceSettings` then describes a mode that contradicts
its `executionWorkspacePreference` in the same row.

**Blast radius.** Every agent that creates a child issue without naming a workspace field
shares its own live worktree — branch and working directory — with the new issue. Two
issues, one `cwd`, uncommitted changes visible across both. We measured this recurring at
roughly 95 new issues per day across 13+ distinct agents, of which ~133 were already bound
to a workspace another issue holds.

**Reproduction** (project policy `enabled: true, defaultMode: isolated_workspace,
allowIssueOverride: true`, caller is an agent with a live worktree):

| create body | resulting `executionWorkspacePreference` | `executionWorkspaceSettings.mode` | `executionWorkspaceId` |
|---|---|---|---|
| *(no workspace fields)* | `reuse_existing` | `isolated_workspace` | **bound to caller's workspace** |
| `executionWorkspacePreference: "inherit"` | `inherit` | `isolated_workspace` | `null` |
| `executionWorkspacePreference: "isolated_workspace"` | `isolated_workspace` | — | `null` |
| no workspace fields, caller run has no `executionWorkspaceId` | `null` | `isolated_workspace` | `null` |

The fourth row is why this reads inconsistently across tenants: the behaviour depends on the
caller's run context, not on the project configuration.

**Proposed fixes**, in order of preference:

1. **Do not inject silently.** If the create body names no workspace field, leave
   `executionWorkspacePreference` absent and let `resolveExecutionWorkspaceMode`
   (`server/src/services/execution-workspace-policy.ts`) apply the project policy's
   `defaultMode`. That function already resolves `defaultMode: isolated_workspace` to
   `isolated_workspace` correctly — it is simply never reached on this path.
2. **Reject the self-inheriting write**, or at minimum require the caller to opt in
   explicitly, when the resolved source workspace belongs to the calling run's own issue.
3. **Reject an absent value** rather than defaulting it, so the failure is loud. The current
   behaviour makes the dangerous value the easy one: a correct create requires the caller to
   remember a field, and an incorrect one requires nothing.

Note that fix 1 is the smallest change that closes the inflow for all callers with no client
change anywhere.

### Defect 2 — `allowIssueOverride` is parsed, persisted, and never enforced

`ProjectExecutionWorkspacePolicy.allowIssueOverride` is read in
`parseProjectExecutionWorkspacePolicy` (`server/src/services/execution-workspace-policy.ts`),
normalised, and returned — but **no other code path consumes it**. Occurrence counts across
the server tree:

```
server/src/services/issues.ts                    13716 lines   allowIssueOverride: 0
server/src/services/heartbeat.ts                 30821 lines   allowIssueOverride: 0
server/src/services/pipelines.ts                  5180 lines   allowIssueOverride: 0
server/src/services/routines.ts                   3391 lines   allowIssueOverride: 0
server/src/routes/issues.ts                      19350 lines   allowIssueOverride: 0
server/src/routes/projects.ts                     1016 lines   allowIssueOverride: 0
server/src/services/execution-workspace-policy.ts   449 lines   allowIssueOverride: 3
```

All three occurrences are within the parser itself.

The field is documented in the `PATCH /api/projects/{id}` request body
(`executionWorkspacePolicy.allowIssueOverride`, `boolean`), so operators can set it, and it
round-trips through `GET /api/projects/{id}` as though it took effect.

**Observed.** With a project policy of `allowIssueOverride: false`, an agent create with
`executionWorkspacePreference: "reuse_existing"` is accepted with `201` and stored as
`reuse_existing`. The gate does not reject, downgrade, or warn.

**Consequence.** An operator who reads the field as a safety switch has no safety switch. The
only reliable guard today is that the caller sends an explicit preference. Either enforce the
flag in `resolveExecutionWorkspaceMode` and in the create path, or remove it from the policy
schema so it cannot be mistaken for a control.

### Environment

- Package: `@paperclipai/server` `2026.1005.0`
- Server source read at `master`
- Measured against a self-hosted instance, company with 3 projects under
  `executionWorkspacePolicy.defaultMode: isolated_workspace`
- Repo is MIT-licensed and public; reporting under those terms.

Happy to provide issue IDs, a full enumeration, or to test a patch.