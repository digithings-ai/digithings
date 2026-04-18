# Security Rubric (10-point)

**Target: ≥ 8/10 to merge. < 7 blocks merge.**

Score one point per criterion you fully satisfy. Partial credit is not allowed — either you pass or you don't.

---

## Criteria

| # | Criterion | Points | How to Check | How to Fix |
|---|-----------|--------|-------------|-----------|
| 1 | **No secrets in code** — No API keys, tokens, passwords, or PEM strings in source files or committed config | 1 | `grep -r "sk-\|dgk_live_\|-----BEGIN"` in your diff | Move to env vars; reference `.env.example` pattern |
| 2 | **No PII in spans or logs** — DigiSmith spans and audit log payloads do not contain raw prompts, full document bodies, file paths outside workspace roots, or bearer tokens | 1 | Review any `audit_log()` or `traceable`-wrapped call; check span inputs/outputs | Summarize or hash the sensitive content; strip before logging |
| 3 | **Input validation at system boundaries** — All data entering from HTTP, MCP, or CLI is validated via Pydantic models before use; no raw `dict` access on untrusted input | 1 | Look for `request.body`, `json.loads`, or `**kwargs` on any HTTP handler without a Pydantic parse | Add a Pydantic model; raise `422` on validation failure |
| 4 | **No injection vectors** — No `subprocess.run(user_input)`, no f-string SQL, no `eval()` or `exec()` on user-supplied strings | 1 | Search diff for `subprocess`, `eval`, `exec`, string-formatted SQL | Parameterize queries; use `shlex.split`; gate `DIGI_ALLOW_CODE_EXEC` |
| 5 | **Scope-checked auth** — Protected routes check the required JWT scope via `digikey.integrations.service_middleware`; no route bypasses auth when `DIGIKEY_JWKS_URL` is configured | 1 | Verify new FastAPI routes use the middleware; check for `@router.get` without scope dependency | Add scope dependency using the shared middleware pattern |
| 6 | **Fail-closed on missing auth config** — If auth is not configured, protected routes return `503 auth_not_configured`, not `200` | 1 | Add a test that hits the route with no `DIGIKEY_JWKS_URL` set | Follow the existing `service_middleware` fail-closed pattern |
| 7 | **No new loopback exceptions** — No new `0.0.0.0` bind, no new ports opened without matching `SECURITY.md` approval | 1 | Search diff for `0.0.0.0`, `host="0.0.0.0"`, new `ports:` in docker-compose | Bind `127.0.0.1`; document any exception in `SECURITY.md` |
| 8 | **No live-trading path touched without human gate** — Changes to broker adapters, order submission, or execution logic include a human-in-the-loop interrupt | 1 | Search diff for `IBAdapter`, `AlpacaAdapter`, order submission code | Add `DIGI_INTERRUPT_AFTER_RESEARCH` check or explicit human approval note in PR |
| 9 | **Least-privilege secret access** — New env vars that hold secrets are documented in `.env.example`; existing secrets are not broadened in scope | 1 | Check `.env.example` for new secret vars; verify no secret is now used in a new context without justification | Add to `.env.example` with a comment; review scope |
| 10 | **No debug or development back-doors in production paths** — No `DIGI_ENABLE_DEBUG_ENDPOINTS=1`-gated code in default paths; no hardcoded `dev_global` keys; no `DIGICHAT_DEV_AUTH` checks reachable in prod | 1 | Check that new debug routes are behind the env flag; check for hardcoded dev tokens | Gate behind existing `DIGI_ENABLE_DEBUG_ENDPOINTS` or `DIGIKEY_ALLOW_DEV_GLOBAL` patterns |

---

## Examples

### Passing (Score: 10)

```python
# Pydantic-validated input at HTTP boundary
class WorkflowRequest(BaseModel):
    prompt: str
    session_id: str

@router.post("/workflow")
async def run_workflow(req: WorkflowRequest, _: None = Depends(require_scope("digigraph:workflow"))):
    ...
```

### Failing (Score: 7 — criterion 3 fails)

```python
# Raw dict access on untrusted input
@router.post("/workflow")
async def run_workflow(body: dict):
    prompt = body["prompt"]  # No validation — could be missing or malformed
    ...
```

---

## Notes

- Criterion 8 is automatically a human-gate trigger in the PR template — even a score of 10 requires human review for live-trading changes.
- Criterion 2 is the most commonly missed. Always review `traceable` wrapper inputs before submitting.
