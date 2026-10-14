<!-- in-session-review -->
## Review: digithings PR #4815

| PR | Tip SHA | Verdict | Critical | Major | Minor | Nit |
|----|---------|---------|----------|-------|-------|-----|
| #4815 | `7d8d08fd` | **approve** | 0 | 0 | 0 | 1 |

**Scope reviewed:** `apps/digiquant-runner/src/runner-session.ts`, `apps/digiquant-runner/src/runner.test.ts` (diff vs `develop`).

**Reviewer:** fresh-context subagent (not the authoring session). Tip at review time: `7d8d08fd`.

### Verification performed
- Full diff vs `origin/develop`.
- Traced each new test against `RunnerSession` accept/alarm/pollLock/promote/rollback/applyRemote.
- `npm run test --workspace digiquant-runner` ×4 — 20/20, deterministic (injected clock).
- `tsc --noEmit` clean for digiquant-runner.

### Findings

No critical / major / minor findings.

**Nit:** Post-start seed path where `readStatus` returns `null` (vs throw) is untested; the `if (remote)` guard already makes that path safe.

### Risk coverage

| Risk | Covered |
|------|---------|
| Accept seed before first heartbeat | yes |
| Seed `readStatus` throw soft-path | yes |
| Watchdog `timed_out` + exit 124 | yes |
| Poll keeps lock on `readStatus` throw | yes |
| `startRun` rollback + idem retry | yes |
| `MAX_INFLIGHT` queue + promote | yes |

Production change is export-only (`WATCHDOG_GRACE_SECONDS`); no behavior change.
