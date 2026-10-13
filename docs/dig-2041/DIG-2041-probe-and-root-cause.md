# DIG-2041 — allowIssueOverride probe, and the real root cause of `reuse_existing`

Author: Platform (d80f78b8). Date: 2026-10-07. All measurements on the live API at
`http://127.0.0.1:3100`, company `3d7a91f3-c674-4a9e-862b-11b9698f6686`.

## Summary

Two results, both verified by read-back rather than by HTTP status:

1. **`allowIssueOverride: false` is accepted and persisted, and it changes nothing.**
   It is not a gate. Rolling it back was correct.
2. **The inflow is not caused by an absent enum value resolving wrongly.** It is caused by
   the create route *silently injecting* the calling agent's own run issue as a workspace
   inheritance source. The `reuse_existing` stamp is a deliberate inheritance write, not a
   bad default. The project policy is never consulted on this path at all.

Part 2's hypothesis (absent value should default to `inherit`) is therefore **not the defect**.
The correct upstream fix is to stop the silent inheritance injection on create.

---

## Part 1 — the probe

### Starting state, all three product projects

```json
{"enabled": true, "defaultMode": "isolated_workspace", "allowIssueOverride": true,
 "workspaceStrategy": {"type": "git_worktree", "baseRef": "develop"}}
```

`datatap` is identical except `baseRef: "main"`.

### A correction to the brief

The brief says the OpenAPI spec "documents no body" for `PATCH /api/projects/{projectId}`.
It does document one. The real spec is at **`/api/openapi.json`**; `/openapi.json` serves
the SPA HTML shell and returns a 200 with `<!DOCTYPE html>`, which is almost certainly how
the "no body" reading arose.

`executionWorkspacePolicy` is a documented property of the PATCH request body, and
`allowIssueOverride` is a documented `boolean` inside it. So the write is supported, not
undocumented. This lowered the risk of the probe and is worth correcting on DIG-1951.

### Result: the write takes, and is inert

```
PATCH /api/projects/0ae7b608...  {"executionWorkspacePolicy": {..., "allowIssueOverride": false}}
  -> HTTP 200
GET  /api/projects/0ae7b608...  (read-back)
  -> allowIssueOverride: true -> false          TAKEN
  -> all other policy fields byte-identical      no collateral change
```

The setting persisted. It had no behavioural effect:

| # | project | create body | read-back pref | read-back settings.mode | workspace |
|---|---------|-------------|----------------|--------------------------|-----------|
| A | digithings | *(bare, no field)* | `reuse_existing` | `isolated_workspace` | **BOUND** |
| B | digithings | *(bare, no field)*, `allowIssueOverride=false` | `reuse_existing` | `isolated_workspace` | **BOUND** |
| C | digithings | `executionWorkspacePreference: reuse_existing`, `allowIssueOverride=false` | `reuse_existing` | `isolated_workspace` | `null` |

A and B are byte-identical outcomes. C shows the gate is not merely ineffective but
**unenforced**: an explicit `reuse_existing` is accepted and stored while
`allowIssueOverride` is `false`.

### Why: `allowIssueOverride` is write-only

Counted across the whole server tree:

```
server/src/services/issues.ts                      13716 lines   allowIssueOverride: 0
server/src/services/heartbeat.ts                   30821 lines   allowIssueOverride: 0
server/src/services/pipelines.ts                    5180 lines   allowIssueOverride: 0
server/src/services/routines.ts                     3391 lines   allowIssueOverride: 0
server/src/routes/issues.ts                        19350 lines   allowIssueOverride: 0
server/src/routes/projects.ts                       1016 lines   allowIssueOverride: 0
server/src/services/execution-workspace-policy.ts     449 lines   allowIssueOverride: 3
```

All three occurrences are in the parser. It is read from the policy blob, normalised, and
returned. Nothing consumes it. It is persisted configuration that no code path ever reads —
so no setting can be made true or false on it, and no operator can rely on it.

This is an independent, separately-reportable defect from the inheritance bug.

---

## Part 2 — the actual root cause

### What the brief assumed

> An absent value is not in that enum, and it resolves to `reuse_existing` rather than to
> `inherit`. A default of `inherit`, or a rejection of an absent value, fixes all 56 agents.

### What the code does

`server/src/routes/issues.ts:12059-12062`, inside the `POST /api/companies/{id}/issues` handler:

```ts
const runWorkspaceInheritanceSourceIssueId =
  hasExplicitIssueWorkspaceCreateSelection(rawCreateBody)
    ? null
    : await resolveRunIssueWorkspaceInheritanceSource(companyId, actor);
```

and in the create body:

```ts
...(runWorkspaceInheritanceSourceIssueId
  ? { inheritExecutionWorkspaceFromIssueId: runWorkspaceInheritanceSourceIssueId }
  : {}),
```

`resolveRunIssueWorkspaceInheritanceSource` reads `heartbeatRuns.contextSnapshot` for the
caller's own run. If the run has a non-empty `executionWorkspaceId`, it returns
`context.issueId` — the issue the caller is already running.

So when an agent creates an issue and names **no** workspace field at all, the server adds
the agent's own current issue as the inheritance source. The guard is:

```ts
function hasExplicitIssueWorkspaceCreateSelection(input: Record<string, unknown>) {
  return input.parentId !== undefined ||
    input.inheritExecutionWorkspaceFromIssueId !== undefined ||
    input.projectWorkspaceId !== undefined ||
    input.executionWorkspaceId !== undefined ||
    input.executionWorkspacePreference !== undefined ||
    input.executionWorkspaceSettings !== undefined;
}
```

That lands in `server/src/services/issues.ts:10086-10115`:

```ts
if (inheritsSourceProject && isolatedWorkspacesEnabled &&
    !hasExplicitExecutionWorkspaceOverride && workspaceSource.executionWorkspaceId) {
  ...
  if (sourceWorkspace) {
    executionWorkspaceId = sourceWorkspace.id;
    executionWorkspacePreference = "reuse_existing";          // <-- line 10107
    executionWorkspaceSettings = {
      ...workspaceSource.executionWorkspaceSettings,
      mode: issueExecutionWorkspaceModeForPersistedWorkspace(sourceWorkspace.mode),
    };
  }
}
```

`executionWorkspacePreference = "reuse_existing"` is a hardcoded literal on line 10107. It is
the only assignment of that string in `issues.ts`.

### This explains every measured row, including the contradictory ones

- **Row A/B** — my bare create returned `pref=reuse_existing`, `settings.mode: isolated_workspace`,
  bound. The bound workspace was `1cc98d9a-902d-473b-9d44-62bfa64b4196`, whose
  `sourceIssueId` is **DIG-2041 itself** — my own run. `mode: isolated_workspace` is copied
  from that workspace's own mode. Nothing was "invented"; it was inherited from me.
- **Rows C/D** — `digithings-business` returned `pref=null`. That run had no
  `executionWorkspaceId` in its context snapshot, so the resolver returned `null` and no
  inheritance happened. Same code, different run context.
- **Row F** — `inherit` returned `pref=inherit` and no binding, because
  `hasExplicitIssueWorkspaceCreateSelection` saw the explicit field and suppressed the
  injection.

So the behaviour is not enum-dependent at all. It is **run-context-dependent**. That is why
`defaultMode: isolated_workspace` in the project policy is never read on this path: the
policy is only consulted at `issues.ts:10169-10181`, and only to derive
`executionWorkspaceSettings` — never to choose a preference, and `allowIssueOverride` is not
consulted there either.

### The blast radius is exactly the reported damage

An agent that creates a child issue with no workspace field shares its **own live worktree**
with the new issue. Two issues, one `cwd`, one branch. That is precisely
"133 already sit on a workspace another issue holds", and it is why it recurs at ~95/day
across 13+ agents: every one of them triggers the same silent injection on a bare create.

It also explains why `dt-create-issue` works. It always sends
`executionWorkspacePreference` explicitly, which trips
`hasExplicitIssueWorkspaceCreateSelection`, which suppresses the injection. The script was
right; the server-side default it compensates for is the bug.

### Why "default to `inherit`" is the wrong upstream fix

An absent value already behaves as intended once inheritance stops. Rows C/D show `pref=null`
and `ws=null` when there is no run workspace to inherit. Changing the terminal fallback to
`inherit` would not address the path that actually produces the damage, which is the explicit
injection at `routes/issues.ts:12059`, and it would not stop the silent binding.

---

## Corrections to DIG-1951's root cause

DIG-1951 (DIG-1636 lineage) concluded: "there is no server-side default; create an issue with
no preference field and it comes back `null`; the field must be on the request."

That measurement is correct **for a run with no execution workspace** and wrong as a general
claim. For an agent running in an isolated worktree — which is every agent on these three
projects — the server *does* supply a value, and it supplies the dangerous one. The practical
consequence is the same, which is why the conclusion held operationally, but the mechanism is
different and the fix is different:

| | DIG-1951's model | What the code does |
|---|---|---|
| Cause | client omits a field | server injects the caller's own run issue as inheritance source |
| Default supplied | none (`null`) | `reuse_existing`, bound to the caller's worktree |
| Project policy | not read at creation | still not read on this path |
| Fix | server must refuse / default to `inherit` | server must not silently inject |

---

## What we can do on our side, with no server change

The injection only happens when the create body names no workspace field. Every caller can opt
out by naming one. `dt-create-issue` already does this and is the whole mitigation. The
practical recommendation for DIG-1951 stands and is now better founded: route bare creates
through `dt-create-issue`, which is lane 1 and lane 3 of that brief.

Setting `allowIssueOverride: false` is not a mitigation and should not be attempted again.

---

## Rollback

`digithings` policy restored to the exact original object and verified by read-back:

```json
{"enabled": true, "defaultMode": "isolated_workspace", "allowIssueOverride": true,
 "workspaceStrategy": {"type": "git_worktree", "baseRef": "develop"}}
```

- `twelve-x` and `datatap`: never written. Verified still `allowIssueOverride: true`.
- Probe issues A, B, C: created, then deleted. All three verified `404` afterwards.
- Throwaway project `DIG2041-probe-ws`: `DELETE` returned `500 Internal server error` twice.
  Per the two-failure rule I stopped retrying and archived it via `PATCH archivedAt`
  (`2026-10-07T21:21:26Z`). It no longer appears in `GET /api/companies/{id}/projects`.
  Its `DELETE` 500 is itself a small defect worth noting.
- My own execution workspace `1cc98d9a-902d-473b-9d44-62bfa64b4196` re-verified `active`,
  `closedAt: null`, worktree present and git-clean afterwards.

## Confidence

- **CONFIRMED** — the write takes and is inert (read-back, live).
- **CONFIRMED** — `allowIssueOverride` is never consumed (grepped across the server tree).
- **CONFIRMED** — the injection at `routes/issues.ts:12059` and the literal at
  `issues.ts:10107` (read the source at `master`).
- **CONFIRMED** — the bound workspace's `sourceIssueId` is DIG-2041 (read-back, live).
- **LIKELY** — that rows C/D differ only by run context. The resolver requires a
  non-empty `executionWorkspaceId` in `contextSnapshot`, which explains it, but I did not
  read the specific historical runs.

## Not verified

- I did not run the create path with `isolatedWorkspacesEnabled` off, so I have not seen
  whether the injection is gated by it in a way that changes the picture. The source shows
  it is read in the same condition, so the gate is likely shared.
- I did not test the `PATCH` create path, where the same injection presumably applies to
  updates.
- Upstream issue not yet filed: publishing outside the company is Chris-only. Draft ready.