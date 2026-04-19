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

## Data protection

- **Client and pilot work** lives under `projects/` (gitignored; never pushed to public remotes). Treat this as confidential.
- **Index and corpus licensing** — DigiSearch indexes must respect upstream copyright and license. Do not automate retrieval of paywalled content without entitlement. The optional `edgar_dev` corpus is for dev/testing on loopback only; cite the upstream dataset when publishing results.
- **Per-tenant isolation** on multi-tenant deployments is a roadmap item (see `digibase/ARCHITECTURE.md` — DigiBase data-plane). Today, tenant isolation is enforced at the DigiKey key-scope level, not at the storage layer.

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

## Revocation

JWT revocation before natural expiry is a roadmap item (tracked under the [DigiKey revocation epic](https://github.com/digithings-ai/digithings/issues/6)). Today, revocation requires rotating the signing key or waiting for token expiry. Design any deployment with token TTLs short enough that this is acceptable.

## Reporting vulnerabilities

If you believe you have found a security vulnerability in DigiThings:

1. **Do not** open a public GitHub issue.
2. Email **dany.stefan@matador.ai** with `[DigiThings Security]` in the subject.
3. Include steps to reproduce, affected component(s), and any known impact.
4. Expect an acknowledgement within 72 hours and a coordinated-disclosure timeline within 7 days.

We'll work with you on an embargo period if appropriate and credit you in the release notes if you'd like.

## PR security rubric

Every pull request is expected to pass the `docs/scoring/SECURITY.md` rubric at ≥ 8/10 before merge. Doc-only PRs touching `SECURITY.md` itself are excluded from auto-merge (see [docs/agent-backlog/AUTOMERGE.md](docs/agent-backlog/AUTOMERGE.md)).
