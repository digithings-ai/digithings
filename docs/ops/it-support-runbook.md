# IT Support Runbook

This runbook documents fixes for recurring agent failures. When the same fix works twice, promote it to a watchdog rule.

---

## Entry: DIG-449 — OpenAI Chat Stream Ended Without Finish_Reason

**Date**: 2026-10-04  
**Agent**: Counsel (digichat AI-SDK backend)  
**Error**: `OpenAI Chat stream ended without finish_reason adapter_failed`  
**Failed Run**: 976e4756-e409-469f-8d97-65f433a8527a  
**Root Cause**: LIKELY — digigraph streaming worker exits without "done" event, causing the SSE stream to end without a terminal `finish_reason: "stop"` chunk and `[DONE]` marker.

### Evidence

The digigraph streaming code in `digigraph/src/digigraph/http_api/streaming.py` had a code path (lines 217-222) where if the workflow worker thread died without enqueueing a "done" event, it would yield an error message with `finish_reason: null` and then `break` without sending the final `finish_reason: "stop"` chunk and `[DONE]` marker.

The Vercel AI SDK's `@ai-sdk/openai-compatible` provider (used by digichat's AI-SDK backends) strictly requires the stream to end with a chunk containing a non-null `finish_reason` followed by `data: [DONE]`. When this doesn't happen, it throws "OpenAI Chat stream ended without finish_reason" which surfaces as `adapter_failed` in the @assistant-ui/ai-sdk integration.

### Fix Applied

Modified `digigraph/src/digigraph/http_api/streaming.py` in the error handler for "worker exited without a done event" to:
1. Yield the error message chunk (with `finish_reason: null`)
2. Yield a final chunk with `finish_reason: "stop"`
3. Yield `data: [DONE]`
4. `return` (instead of `break`) to avoid duplicate emission from the `finally` block

```python
# Before (lines 217-222):
logger.error("workflow stream worker exited without a done event")
yield (
    "data: "
    f"{_sse_chunk(cid, created, model, 'Error: workflow stream ended before completion', None)}\n\n"
)
break

# After:
logger.error("workflow stream worker exited without a done event")
yield (
    "data: "
    f"{_sse_chunk(cid, created, model, 'Error: workflow stream ended before completion', None)}\n\n"
)
# Ensure the stream ends with a proper finish_reason and [DONE] marker
# so OpenAI-compatible clients don't fail with "stream ended without finish_reason"
yield f"data: {_sse_chunk(cid, created, model, '', 'stop')}\n\n"
yield "data: [DONE]\n\n"
return
```

### Verification

- All 1364 digigraph unit tests pass (`tests/dg/`)
- Specific test `test_dead_worker_does_not_leave_the_sse_poll_running` verifies the stream ends with `[DONE]`
- Manual verification confirms the SSE output now correctly includes:
  1. Error content chunk (`finish_reason: null`)
  2. Final stop chunk (`finish_reason: "stop"`)
  3. `[DONE]` marker

### Confidence

**LIKELY** — The error message matches exactly the failure mode when an OpenAI-compatible stream ends without a terminal finish_reason. The fix ensures spec-compliant stream termination in all code paths.

### Watchdog Rule Candidate

If this error recurs, add a watchdog rule to detect:
- SSE streams from digigraph that don't end with `finish_reason: "stop"` + `[DONE]`
- Auto-retry the request (the worker failure is often transient)

---

## Entry: DIG-276 — Workspace Reuse Hands an Issue Another Issue's Worktree

**Date**: 2026-10-05  
**Agent**: FDE twelve-x (working DIG-249)  
**Error**: DIG-249 (scoped to `digithings-ai/twelve-x`) was handed an execution workspace for `digithings-ai/digithings` on DIG-47's branch  
**Failed Run**: DIG-249 wake payload  
**Root Cause**: Two factors combined:
1. **Issue misfiled** — DIG-249 sat in the `digithings` project (projectId `0ae7b608-...`) while twelve-x issues belong in the `twelve-x` project (`5ea37430-...`). Workspace selection is project-scoped, so the wrong project meant the wrong repo.
2. **No cross-issue workspace guard** — `reuse_existing` + `mode: isolated_workspace` selected an active worktree belonging to a different issue (DIG-47, sourceIssueId `0eeac433-...`) in the same project, instead of creating a worktree for DIG-249. Nothing warned the agent.

### Evidence

Wake payload for DIG-249 showed:
```
projectId                    = 0ae7b608-...  (project "digithings")
projectWorkspaceId           = 2a8a0379-...  (digithings project workspace)
executionWorkspacePreference = "reuse_existing"
executionWorkspaceSettings   = {"mode": "isolated_workspace"}
executionWorkspaceId         = 20f53ad3-1a15-442e-8d6c-21e5e3ae3084
```

Workspace `20f53ad3`:
```
repoUrl       = https://github.com/digithings-ai/digithings
branchName    = DIG-47-digithings-cron-twelve-x-dispatch-counts-...
sourceIssueId = 0eeac433-5e50-4698-ac22-caa6c1cd0924   (= DIG-47)
strategyType  = git_worktree
mode          = isolated_workspace
status        = active
```

The assigned worktree contained none of the files DIG-249 changes (all four absent: `scripts/refresh_session_cookie.sh`, `scripts/ingest_market_context.py`, `nodes/scrape.py`, `docs/PRIMEMARKET_DESK_API.md`). No `twelve_x` package exists in digithings repo.

### Fix Applied

1. **Moved DIG-249** to the `twelve-x` project (`5ea37430-...`) and pointed `projectWorkspaceId` at `/Users/chrisstefan/Code/twelve-x`
2. **Moving DIG-266** the same way
3. **Note**: The other five twelve-x-titled issues in the `digithings` project (DIG-20, DIG-22, DIG-47, DIG-57, DIG-76) are `digithings-cron` issues that genuinely belong there, so project placement alone is not a reliable signal.

### Suggested Guards (for Paperclip platform)

- `reuse_existing` under `mode: isolated_workspace` should reuse an existing worktree **for that issue**, never an arbitrary active worktree in the project. If none exists, create one.
- Refuse or warn when a resolved `executionWorkspaceId` has a `sourceIssueId` that is a different issue.
- When an issue's text names a repository scope that disagrees with the project workspace `repoUrl`, surface a warning on the wake instead of silently handing over the wrong tree.
- Reusing a worktree updates its `lastUsedAt`, so the wrong-repo reuse leaves a trace with no error attached to it (DIG-47's workspace shows `lastUsedAt: 2026-10-04T17:29:23Z`).

### Verification

- DIG-249 moved to correct project; next wake should resolve to twelve-x workspace
- DIG-47's worktree unchanged (clean, `ahead 10, behind 2` of `origin/develop`)
- Sweep of 63 twelve-x/PrimeMarket-titled issues: 47 with execution workspace, 16 without; not audited for correct pairing

### Confidence

**CONFIRMED** — The wake payload data conclusively shows cross-issue workspace binding. The fix (project move) addresses the immediate cause; the guards address the missing safety net.

### Watchdog Rule Candidate

If cross-issue workspace binding recurs, add a watchdog rule to detect:
- Wake payloads where `executionWorkspaceId` resolves to a workspace with `sourceIssueId` ≠ current issue
- Project/repo mismatch between issue scope text and `projectWorkspaceId` repoUrl

---

## Changelog

| Date | Incident | Fix Summary | Status |
|------|----------|-------------|--------|
| 2026-10-05 | DIG-276 | Document cross-issue workspace binding; moved DIG-249 to correct project; proposed Paperclip guards | Documented |
| 2026-10-04 | DIG-449 | Ensure digigraph SSE streams always terminate with finish_reason: "stop" + [DONE] | Fixed |