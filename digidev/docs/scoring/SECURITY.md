# Security rubric

Default minimum: **8/10**

Score one point per criterion satisfied. Criteria that don't apply to your change count as satisfied.

---

## Criteria

1. **No secrets in code** — No API keys, tokens, passwords, private keys, or PEM strings hardcoded in source files. Secrets belong in environment variables, documented in `.env.example`.

2. **No PII in logs or traces** — No raw user input, bearer tokens, email addresses, or personally identifiable data written to logs, spans, or audit records.

3. **Input validation at boundaries** — All HTTP endpoints, CLI entry points, and message queue consumers validate input with typed models (Pydantic, dataclasses, TypeScript types, Zod, etc.). No raw dict/object access on untrusted input.

4. **No injection vectors** — No `eval()`, `exec()`, f-string SQL queries, shell command construction from user input, or unguarded `subprocess` calls with user-controlled arguments. Use parameterised queries for SQL; use `subprocess` with a list, not a string.

5. **Auth on new routes** — Every new HTTP route has appropriate authentication and authorisation. If the route is intentionally public, that is documented.

6. **Fail-closed on missing config** — If auth configuration (keys, secrets, JWKS endpoints) is missing at startup, the service refuses to start or returns 503, not 200. No silent fallback to unauthenticated mode.

7. **No new unreviewed network exposure** — No new `0.0.0.0` bind, no new publicly published port, no new network-facing service without a SECURITY.md entry or explicit review.

8. **No sensitive paths touched without human gate** — If this change touches auth code, crypto, or live-trading paths, the Human Gate section of the PR template is filled in and at least one human has approved.

9. **Least-privilege secrets** — Any new secret added to `.env.example` has a comment explaining its purpose and minimum required scope. No over-privileged tokens.

10. **No debug backdoors** — No hardcoded admin passwords, no `if DEBUG: skip_auth`, no temporary bypass code left in production paths.

---

## Common fixes

| Failure | Fix |
|---|---|
| Secret in code | Move to env var, rotate the exposed secret, add to `.env.example` |
| Missing input validation | Add a typed model (Pydantic, Zod, etc.) at the endpoint boundary |
| SQL injection risk | Use parameterised queries or an ORM |
| Missing auth on route | Add middleware or decorator; document if intentionally public |
| PII in logs | Add a redaction step before logging; use a log sanitiser |
