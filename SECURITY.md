# Security

This document describes the security posture of DigiThings and how to report vulnerabilities. See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and [docs/scoring/SECURITY.md](docs/scoring/SECURITY.md) for the PR-review rubric.

## Threat model

DigiThings is designed to run on a single host or private network. The primary threats we design against:

- **Unauthorized access** to orchestration, search, or trading surfaces (arbitrary code execution, data exfiltration, unauthorized trades).
- **Credential leakage** via logs, spans, audit events, or error responses.
- **Prompt or tool-call abuse** — malicious input reaching agent workflows that drive real actions.
- **Accidental live-trading** — anything that could execute a broker order without explicit human approval.

We are **not** designing for public internet exposure by default. Running DigiThings on a public endpoint without a dedicated gateway and hardened auth is out of scope.

## Non-negotiable defaults

These are enforced in code and reviewed on every PR:

1. **Loopback binding.** Every service binds `127.0.0.1` in `docker-compose.yml`. No `0.0.0.0` without matching SECURITY.md approval (enforced by the `docs/scoring/SECURITY.md` rubric).
2. **DigiKey JWT required on protected routes.** DigiGraph, DigiQuant, and DigiSearch require `DIGIKEY_JWKS_URL` (or `DIGIKEY_PUBLIC_KEY_PEM`) and an `Authorization: Bearer <JWT>` on non-exempt routes. There is no legacy static `DIGI_API_KEY` fallback. DigiSearch additionally requires a real index backend (Azure or Chroma) unless `DIGISEARCH_ALLOW_STUB=1` (tests only).
3. **Human gates before any live trade.** Broker adapters (IB, Alpaca, QuantConnect) currently raise `NotImplementedError`. Any change to those paths requires explicit human approval per `docs/scoring/SECURITY.md` criterion 5.
4. **Debug and thread endpoints are off by default.** `DIGI_ENABLE_DEBUG_ENDPOINTS` and `DIGI_ENABLE_THREAD_API` default to `0`; `/v1/debug/*`, `/test_llm`, and `/threads/*` are not exposed unless explicitly enabled.
5. **LiteLLM proxy is not unauthenticated in non-dev deployments.** With no `LITELLM_MASTER_KEY`, the proxy may accept requests without a Bearer — acceptable only on loopback/trusted networks. Beyond local dev, set `LITELLM_MASTER_KEY` (and `LITELLM_PROXY_API_KEY` on DigiGraph to match, or issue virtual keys via DigiKey).
6. **Audit events must be redacted before persistence.** Every `audit.jsonl` writer must go through `digibase.audit.redact_mapping` (or equivalent). API keys, JWTs, prompts, and document bodies must not appear in audit events. The `/v1/status` endpoint on DigiSmith is public — keep it secret-free.
7. **Observability spans do not carry secrets.** DigiSmith spans must include `workflow_id`, `request_id`, `session_id` but never raw prompts, API keys, or full document bodies.
8. **Bounded outbound HTTP timeouts.** Every service-to-service `httpx` call site constructs its client through `digibase.http_client.async_client` / `sync_client`, which apply a default `httpx.Timeout(connect=5, read=30, write=10, pool=5)` envelope. Bare `httpx.AsyncClient()` / `httpx.Client()` — which default to *no* read timeout and will hang indefinitely against a slow upstream LLM or broker — are forbidden in production code. Call sites that legitimately need longer budgets (e.g. 600 s backtest submission) pass an explicit `timeout=` override; the helpers preserve it verbatim. This bounds worst-case request latency under upstream degradation and prevents resource exhaustion on stalled connections.

## Data protection

- **Client and pilot work** lives under `projects/` (gitignored; never pushed to public remotes). Treat this as confidential.
- **Index and corpus licensing** — DigiSearch indexes must respect upstream copyright and license. Do not automate retrieval of paywalled content without entitlement. The optional `edgar_dev` corpus is for dev/testing on loopback only; cite the upstream dataset when publishing results.
- **Per-tenant isolation** on multi-tenant deployments is a roadmap item (see `digibase/ARCHITECTURE.md` — DigiBase data-plane). Today, tenant isolation is enforced at the DigiKey key-scope level, not at the storage layer.

## Secrets scanning

Every pull request and every push to `develop`/`main` runs
[`gitleaks`](https://github.com/gitleaks/gitleaks) via
`.github/workflows/gitleaks.yml`. The workflow is pinned to a commit SHA
(supply-chain hardening) and fails the job on any finding.

- **What's scanned.** PRs scan the diff; `develop`/`main` pushes scan the
  commit range. Configuration lives at [`.gitleaks.toml`](.gitleaks.toml) and
  extends the default ruleset (AWS, GCP, Azure, GitHub, generic API keys,
  PEM private keys, JWTs).
- **Local reproduction.** `make secrets-scan` runs the same config against
  the working tree. Install gitleaks via `brew install gitleaks` or
  `go install github.com/gitleaks/gitleaks/v8@latest`.
- **Allowlist policy.** `tests/`, `.env.example`, top-level and `docs/**/*.md`
  markdown, and `scripts/claude-hooks/fixtures/` are allowlisted because they
  only contain placeholder values, fake/ephemeral fixtures, or
  vendor-published example tokens (e.g. `AKIAIOSFODNN7EXAMPLE`). Adding a new
  allowlist entry requires a comment in `.gitleaks.toml` justifying why the
  match is safe, and reviewers are expected to push back on entries that
  broaden the allowlist without a clear fixture/example rationale.
- **If a real secret leaks.** **Rotate first**, then add an allowlist entry.
  Order matters — adding the allowlist before rotation hides the leak from
  future scans without removing the live credential. Once rotated, the
  allowlist entry (ideally a path + regex scoped to the specific value or a
  commit SHA pin) documents that the historical reference is safe.

## Remote access

If you need to reach the stack from outside the host, use **Tailscale** or **Cloudflare Tunnel** rather than exposing ports publicly. `DIGICHAT_PUBLISH_HOST=0.0.0.0` is documented as an escape hatch for LAN exposure but should still sit behind a VPN or tunnel — never on the public internet.

An edge gateway (currently DigiClaw's scope) is the intended single Internet-facing surface: OIDC or mTLS, session binding, global rate limits, with DigiGraph and the verticals kept on loopback or private networks behind it.

## Rate limiting (auth paths)

DigiKey applies a per-IP token-bucket rate limiter to its auth-sensitive
routes — `POST /v1/admin/keys` (key issuance) and `POST /v1/oauth/token`
(JWT mint). Defaults: 10 requests/minute sustained, burst 20. Override via
`DIGIKEY_RL_PER_MIN` and `DIGIKEY_RL_BURST`. On breach the service returns
HTTP 429 with body `{"detail": "rate_limited", "retry_after": N}` and a
`Retry-After` header.

Exempt routes (no limiter overhead): `GET /health`,
`GET /.well-known/jwks.json`, and any future `/healthz`, `/metrics`,
`/v1/status`. This keeps liveness probes unaffected under load.

The limiter is pure in-process. Cross-process / multi-instance sharing is a
follow-up — a Redis or DigiBase-backed store would be the upgrade path. For
today's loopback-bound, single-instance DigiKey deployment, per-process
buckets are sufficient to blunt brute-force attempts against the bcrypt
verify path.

## CORS policy

Every FastAPI service (DigiGraph, DigiQuant, DigiSearch, DigiSmith, DigiKey)
installs CORS middleware via the shared helper
[`digibase.cors.install_cors`](digibase/src/digibase/cors.py). The helper reads
an **explicit allowlist** from the environment — there is no wildcard
(`*`) default, and there is no default that accepts arbitrary browser origins.

**Precedence** (first non-empty wins):

1. `<SERVICE>_CORS_ORIGINS` — per-service override
   (`DIGIGRAPH_CORS_ORIGINS`, `DIGIQUANT_CORS_ORIGINS`,
   `DIGISEARCH_CORS_ORIGINS`, `DIGISMITH_CORS_ORIGINS`,
   `DIGIKEY_CORS_ORIGINS`).
2. `DIGI_CORS_ORIGINS` — global allowlist shared by every service.
3. `DIGI_ALLOWED_ORIGINS` — legacy global allowlist (back-compat; deprecated,
   will be removed after downstream configs migrate).
4. *(unset)* — the allowlist is **empty**. Browsers are denied the
   `Access-Control-Allow-Origin` header; no cross-origin script can call the
   service. Loopback server-to-server traffic is unaffected because CORS is a
   browser-enforced policy.

All four env vars accept a comma-separated list of origins. Each origin may
contain `${VAR}` / `$VAR` references that are expanded from the process
environment at startup, e.g. `https://${UI_HOST}`.

**Fixed middleware profile** (not configurable — keeps the attack surface
predictable):

- `allow_credentials=True` — required for cookie/session-based bearer flow
  from DigiChat.
- `allow_methods=["GET","POST","PUT","DELETE","OPTIONS"]` — no `TRACE`,
  `CONNECT`, or wildcard.
- `allow_headers=["Authorization","Content-Type","X-Request-ID"]` — the
  minimum set used across the stack.
- `max_age=600` — browser caches the preflight response for 10 minutes.

Deployments that serve a browser UI **must** set at least one of the env vars
above. `scripts/run_stack_local.sh` defaults to localhost origins for dev
ergonomics; production deployments set the exact DigiChat origin.

## Revocation

JWT revocation before natural expiry is a roadmap item (tracked under the [DigiKey revocation epic](https://github.com/digithings-ai/digithings/issues/6)). Today, revocation requires rotating the signing key or waiting for token expiry. Design any deployment with token TTLs short enough that this is acceptable.

## Reporting vulnerabilities

If you believe you have found a security vulnerability in DigiThings:

1. **Do not** open a public GitHub issue.
2. Email **dany.stefan@matador.ai** with `[DigiThings Security]` in the subject.
3. Include steps to reproduce, affected component(s), and any known impact.
4. Expect an acknowledgement within 72 hours and a coordinated-disclosure timeline within 7 days.

We'll work with you on an embargo period if appropriate and credit you in the release notes if you'd like.

## Dependency-audit policy

Every Python component is scanned on every PR, every push to `main`/`develop`, and weekly (Monday 06:00 UTC) by the [`pip-audit` workflow](.github/workflows/pip-audit.yml) against the [OSV](https://osv.dev) vulnerability database.

- **Blocks merge:** any finding with OSV severity **HIGH** or **CRITICAL** (CVSS ≥ 7.0).
- **Warn-only:** findings at **MEDIUM** or **LOW** severity, and findings with unknown severity — surfaced via `::warning::` annotations on the PR, not gated.
- **Scope:** `digibase`, `digigraph`, `digiquant`, `digisearch`, `digismith`, `digikey`, `digiclaw`. Each component is installed with its `[dev]` extras and audited against the resolved transitive closure. `digiquant[nautilus]` is excluded (tracked in #42). `digichat/` (Node) is audited by a sibling `npm audit --omit=dev` job (follow-up).

### Accepting a CVE

To accept a finding — e.g. because the vulnerable code path is not reachable in our usage, or an upstream patch is imminent — add the vuln ID to [`pip-audit-ignore.txt`](pip-audit-ignore.txt) at the repo root:

```
# GHSA-xxxx-xxxx-xxxx — justification (why not exploitable for us + review date)
GHSA-xxxx-xxxx-xxxx
```

Every entry requires a neighbouring comment documenting the rationale and a re-evaluation trigger (upstream fix version or calendar date). Unjustified entries are review-rejected.

Preferred remediation, in order:

1. Pin a patched version in the component's `pyproject.toml` (and update the lockfile/editable-install contract).
2. Swap the dependency if no fix is available.
3. Only then: add to `pip-audit-ignore.txt` with justification.

## PR security rubric

Every pull request is expected to pass the `docs/scoring/SECURITY.md` rubric at ≥ 8/10 before merge. Doc-only PRs touching `SECURITY.md` itself are excluded from auto-merge (see [docs/agent-backlog/AUTOMERGE.md](docs/agent-backlog/AUTOMERGE.md)).
