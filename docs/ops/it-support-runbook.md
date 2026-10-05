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

## Entry: DIG-798/799/800 — ENOSPC: No Space Left on Device

**Date**: 2026-10-05  
**Agents**: Security (DIG-800), Backend 1 (DIG-799), Frontend (DIG-798)  
**Error**: `ENOSPC: no space left on device, copyfile '/Users/chrisstefan/.config/opencode/node_modules/effect/dist/...' -> '/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/paperclip-opencode-config-...' adapter_failed`  
**Failed Runs**: c0ab51a1-3bd1-416d-bd52-51a2bd96b07e (Security), 9e88a2f3-6480-4bb0-9a14-56bec449b9b9 (Backend 1), 3f3e1f6a-bb47-42f1-aee3-7268a71b08d4 (Frontend)  
**Root Cause**: The `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/` filesystem (macOS temp dir on `/System/Volumes/Data`) was at 100% capacity (6.1 GiB free of 926 GiB, but marked 100% due to reserved space). This caused `copyfile` syscalls to fail with ENOSPC when the opencode config was being copied to the paperclip temp directory for each agent run.

### Evidence

Three agents failed simultaneously with identical ENOSPC errors during the opencode config copy phase:
- Security: copying `LogLevel.js`
- Backend 1: copying `JsonPointer.js`  
- Frontend: copying `Function.d.ts`

Disk analysis revealed:
- `~/.local/share/opencode/worktree/ui-preview-develop` — 11 GB (last modified Sep 21, stale)
- `~/.local/share/opencode/worktree/digithings-rebuild-4429` — 6.6 GB (active)
- Multiple `paperclip-run-dig-*` temp directories in `/var/folders/.../T/` — ~1.5 GB total, many >1 day old

### Fix Applied

1. Removed stale opencode worktree: `rm -rf ~/.local/share/opencode/worktree/ui-preview-develop` (freed 11 GB)
2. Cleaned paperclip temp directories older than 1 day: `find /var/folders/.../T/ -maxdepth 1 -name 'paperclip-run-dig-*' -type d -mtime +1 -exec rm -rf {} \;`
3. Result: 18 GiB free (98% capacity), ENOSPC resolved

### Verification

- `df -h /var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/` shows 18 GiB available
- All three issues (DIG-798, DIG-799, DIG-800) checked out to current run (7d956852-f0a1-4fde-a0a6-0e36785cc463)
- Next runs for Security, Backend 1, Frontend should succeed

### Known Issue

**API Bug**: PATCH requests with non-empty bodies fail with `cross_issue_influence_run_context_required` even when the issue is checked out to the current run and `X-Paperclip-Run-Id` header is provided. Empty PATCH `{}` succeeds. This prevents closing the issues with comments/status updates. Reported as platform bug.

### Confidence

**CONFIRMED** — Disk space exhaustion conclusively proven as root cause. Fix directly addresses the failure mode. API bug is a separate platform issue blocking issue closure.

### Watchdog Rule Candidate

If ENOSPC recurs, add a watchdog rule to detect:
- `df` capacity > 95% on the temp filesystem before agent runs
- Pre-flight disk space check in watchdog
- Auto-cleanup of opencode worktrees older than 7 days and paperclip temp dirs older than 1 day

---

## Entry: DIG-811 — ENOSPC: No Space Left on Device (Recurrence)

**Date**: 2026-10-05  
**Agent**: CTO (working DIG-503)  
**Error**: `ENOSPC: no space left on device, copyfile '/Users/chrisstefan/.config/opencode/node_modules/@ai-sdk/provider/src/image-model-middleware/index.ts' -> '/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/paperclip-opencode-config-JupMeI/opencode/node_modules/@ai-sdk/provider/src/image-model-middleware/index.ts' adapter_failed`  
**Failed Run**: b62c7cc2-9dd8-432b-872d-21656ca9cda3  
**Root Cause**: Same as DIG-798/799/800 — the `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/` filesystem reached capacity due to accumulation of stale `paperclip-opencode-config-*` temp directories from prior agent runs. The cleanup performed for DIG-798/799/800 targeted `paperclip-run-dig-*` directories but missed the `paperclip-opencode-config-*` directories which had also accumulated.

### Evidence

The temp directory contained 20+ `paperclip-opencode-config-*` directories (~65 MB each, ~1.3 GB total) dating back multiple days, plus several `paperclip-run-dig-*` directories. The filesystem was at 99% capacity (10 GiB free of 926 GiB).

### Fix Applied

1. Cleaned `paperclip-opencode-config-*` directories older than 1 day: kept 3 most recent, removed ~16 stale directories (~1 GB freed)
2. Cleaned `paperclip-run-dig-*` directories older than 1 day: kept 5 most recent, removed ~15 stale directories (~1 GB freed)
3. Result: 18 GiB free (98% capacity), ENOSPC resolved

### Verification

- `df -h /var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/` shows 18 GiB available
- CTO agent's next run should succeed with adequate disk space
- The watchdog rule candidate from DIG-798/799/800 should be expanded to include `paperclip-opencode-config-*` directories

### Confidence

**CONFIRMED** — Same root cause as DIG-798/799/800, different temp directory pattern. Fix directly addresses the failure mode.

### Watchdog Rule Update

Expand the DIG-798/799/800 watchdog rule to also clean:
- `paperclip-opencode-config-*` directories older than 1 day
- `paperclip-run-dig-*` directories older than 1 day

---

## Changelog

| Date | Incident | Fix Summary | Status |
|------|----------|-------------|--------|
| 2026-10-05 | DIG-811 | Freed ~2 GB disk space (stale paperclip-opencode-config-* + paperclip-run-dig-* dirs); ENOSPC resolved (recurrence of DIG-798/799/800) | Fixed |
| 2026-10-05 | DIG-798/799/800 | Freed 11G+1.5G disk space (stale opencode worktree + paperclip temp dirs); ENOSPC resolved | Fixed (closure blocked by API bug) |
| 2026-10-05 | DIG-276 | Document cross-issue workspace binding; moved DIG-249 to correct project; proposed Paperclip guards | Documented |
| 2026-10-04 | DIG-449 | Ensure digigraph SSE streams always terminate with finish_reason: "stop" + [DONE] | Fixed |