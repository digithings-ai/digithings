# Accuracy Rubric (10-point)

**Target: ≥ 9/10 to merge. < 8 blocks merge.**

Accuracy has the highest bar because correctness issues in this domain (quant finance, orchestration, auth) have real consequences. Score one point per criterion.

---

## Criteria

| # | Criterion | Points | How to Check | How to Fix |
|---|-----------|--------|-------------|-----------|
| 1 | **Matches ARCHITECTURE.md spec** — The implementation matches what `{component}/ARCHITECTURE.md` describes: correct endpoints, correct data models, correct flow order | 1 | Side-by-side diff of your code against the Public API and Data Flow sections | Align code to spec; if spec is wrong, update it in the same PR |
| 2 | **Workflow state transitions are correct** — LangGraph nodes update `WorkflowState` fields consistently; no node reads a field it hasn't ensured is set; conditional edges match the graph definition | 1 | Trace the state field through each node in the graph; check `graph/nodes.py` and edge conditions | Add guards or defaults; update edge conditions to match the new state shape |
| 3 | **Audit events emitted for state changes** — Any new action that changes persistent state (workflow start/end, tool call, backtest result, key issuance) emits an `audit_log()` event with `event_type`, `request_id`, `workflow_id` | 1 | Search diff for new side-effecting operations; check that they have a corresponding `audit_log(...)` call | Add `audit_log("event_type", agent_id, {...})` using the pattern in `digiclaw/audit.py` |
| 4 | **DigiSmith spans carry required attributes** — Any new `@traceable` span includes `workflow_id`, `request_id`, `session_id`; optional `job_id` when a DigiQuant job is in scope | 1 | Check `traceable` wrapper kwargs; verify span inputs include the three required ids | Pass ids as `run_extra={"metadata": {"workflow_id": ..., "request_id": ..., "session_id": ...}}` |
| 5 | **Error paths are handled, not silenced** — Every `try/except` either re-raises, logs with context, or converts to a structured error; no bare `except: pass` | 1 | Search diff for `except:`, `except Exception: pass`, swallowed errors | Add logging or structured error return; use `digibase` error envelope |
| 6 | **API contracts unchanged or versioned** — Public HTTP endpoint signatures (method, path, request schema, response schema) are not changed in a breaking way; if a break is needed, a `/v2/` path is introduced | 1 | Compare new route signatures against ARCHITECTURE.md Public API section | Keep v1 route; add v2 route with new contract; deprecate v1 in ARCHITECTURE.md |
| 7 | **Strategy invariants preserved** — DigiQuant changes do not alter the Nautilus `Actor` event lifecycle (on_start → on_bar → on_order_event → on_stop); signal generation is deterministic for a given seed/params | 1 | Run `digiquant backtest` before and after and compare results for the same params | Check that no statefulness was accidentally introduced; review Nautilus event order |
| 8 | **JWT scope contract unchanged** — New protected routes use the existing scope naming convention (`service:action`); no route accepts `*` scope without the dev-global gate | 1 | Check new route's `require_scope()` call against the scope table in ARCHITECTURE.md | Use an existing scope or add a new one to the DigiKey scope table and ARCHITECTURE.md |
| 9 | **Test assertions are meaningful** — Tests assert specific values or behaviors, not just that a function returns without exception; no `assert result is not None` as the only assertion | 1 | Read each new test; confirm assertions check specific fields, values, or error codes | Add assertions on specific fields: `assert result.sharpe_ratio > 0`, `assert resp.status_code == 422` |
| 10 | **No regression in existing tests** — `make test-unit` passes with zero failures after the change; no existing test is deleted or weakened to make the PR green | 1 | Run `make test-unit` and confirm zero failures | Fix the regression at the source; do not skip or delete tests |

---

## Examples

### Passing (Score: 10)

```python
async def run_backtest(req: BacktestRequest, ...) -> BacktestResult:
    audit_log("backtest_start", "digiquant", {"strategy": req.strategy, "request_id": req.request_id})
    try:
        result = await _run_nautilus(req)
        audit_log("backtest_complete", "digiquant", {"job_id": result.run_id})
        return result
    except NautilusError as exc:
        audit_log("backtest_failed", "digiquant", {"error": str(exc)})
        raise HTTPException(status_code=500, detail={"code": "backtest_error", "message": str(exc)})
```

### Failing (Score: 7 — criteria 3, 5, 9 fail)

```python
async def run_backtest(req: BacktestRequest, ...) -> dict:
    try:
        result = await _run_nautilus(req)
        return result  # No audit event
    except Exception:
        pass  # Silenced error
```

Test:
```python
def test_backtest():
    result = run_backtest(req)
    assert result is not None  # Meaningless assertion
```

---

## Notes

- Criterion 10 is a hard gate. Never merge with failing tests.
- Criterion 2 only applies to DigiGraph changes. Score it 1 automatically for other components.
- Criterion 7 only applies to DigiQuant strategy changes. Score it 1 automatically for other components.
