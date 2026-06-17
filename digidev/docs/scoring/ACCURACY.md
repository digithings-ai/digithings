# Accuracy rubric

Default minimum: **9/10**

This is the highest-threshold dimension. Correctness is non-negotiable. Score one point per criterion satisfied.

---

## Criteria

1. **Matches the issue spec** — The implementation satisfies all acceptance criteria in the linked GitHub issue. If an acceptance criterion is not met, the PR is not ready.

2. **Matches ARCHITECTURE.md** — New endpoints, models, flow order, and data shapes match what `{component}/ARCHITECTURE.md` describes. If the spec changed, update the doc and note the divergence.

3. **Error paths handled, not silenced** — No bare `except: pass`, no silently discarded errors. Every error is either surfaced to the caller, logged with context, or explicitly documented as intentionally ignored.

4. **API contracts unchanged or versioned** — Breaking changes to existing public APIs use a new version path (`/v2/`, module rename, etc.). Non-breaking additions are fine. Removing or renaming a parameter without a version bump is a contract violation.

5. **State transitions correct** — If the component uses a state machine, workflow graph, or event-driven model, the new code transitions state correctly. No skipped states, no invalid transitions.

6. **Audit events emitted** — Side-effecting operations (writes, deletes, auth events, financial events) emit audit log entries where the project's audit policy requires it.

7. **Meaningful test assertions** — Tests assert specific values, shapes, or behaviors — not just `is not None` or `status == 200`. An assertion that passes even when the feature is broken is not a test.

8. **No regression in existing tests** — `make test-unit` passes with zero failures. Tests are not modified to pass around a broken implementation (fix the implementation, not the test).

9. **Edge cases handled** — The implementation handles empty inputs, zero values, maximum sizes, concurrent access (where applicable), and the error cases called out in the acceptance criteria.

10. **Documentation matches behavior** — Any docstrings, comments, or README snippets that describe the changed code accurately reflect the new behavior. Stale documentation is corrected.

---

## Common fixes

| Failure | Fix |
|---|---|
| Acceptance criterion not met | Re-read the issue; implement the missing behavior |
| Spec mismatch | Update ARCHITECTURE.md if the spec evolved; or fix the implementation |
| Silenced error | Add error handling; log with context or surface to caller |
| Broken existing test | Fix the implementation — don't change the test to pass |
| Weak assertions | Assert specific return values, not just existence |
| API contract broken | Add a `/v2/` path or restore the original signature |
