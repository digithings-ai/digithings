# Security

This document describes the security posture of digithings and how to report vulnerabilities. See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and [docs/agents/CODE_REVIEW_POLICY.md](docs/agents/CODE_REVIEW_POLICY.md) for the review policy.

## Release signing keys

Release tags are signed by an OpenSSH Ed25519 software key held by the release
agent on the build host. A valid signature attests that the tag was cut by that
agent through the release script; it does **not** attest a human review. The tag
ruleset, the signer policy in [`scripts/deploy/allowed_signers`](scripts/deploy/allowed_signers),
the release ledger and the nightly audit carry that accountability.

Every tag is signed by one principal, `release@digithings`. Two keys are
enrolled; `valid-before` is compared against the **tagger time of the tag being
verified**, so an older key keeps verifying the tags it cut. It cannot sign a
tag dated after its bound, but the tag date is chosen by the signer.

| Key | SHA256 fingerprint | Signing window ends (`valid-before`) |
|-----|--------------------|--------------------------------------|
| K1 | `SHA256:Chsn3YHmj/fgmLR6MpDLe3S+zGpNXsiT5FBh3PvAQZo` | 2026-12-01 (`20261201Z`) |
| K2 | `SHA256:WwoXS26H5hX2jDb9WRjuq7F0ZHn1luXV+pMQhrat6GM` | 2027-06-01 (`20270601Z`) |

K1 covers tags cut before 2026-12-01, including `r0-v0.1.1` and
`strategies-v0.1.0`. K2 is the current rotating key and signs every new tag.

One earlier tag sits outside this policy on purpose. `r0-v0.1.0` was cut during
the initial repository promotion with a bootstrap key that was never enrolled in
`scripts/deploy/allowed_signers`. Its signature therefore does not verify against
the published signers and its fingerprint is deliberately not listed here. It is
superseded by `r0-v0.1.2` and is **not** a current trust anchor: verify and pin
`r0-v0.1.2`, or a later tag signed by K2, instead.

**Trust the fingerprints published here, not the copy of
`scripts/deploy/allowed_signers` inside the tagged tree.** Anyone able to write
the tag can also write the tree it points at, so a file that vouches for itself
is not evidence. Read this document from the release page, or from a checkout
you already trust, and compare the fingerprint shown by `ssh-keygen -lf` for
that key before you verify.

Anonymous verification needs no GitHub account and no key of your own:

```bash
git clone --no-tags https://github.com/digithings-ai/digithings.git
cd digithings
git fetch --depth=1 origin refs/tags/r0-v0.1.1:refs/tags/r0-v0.1.1
git -c gpg.ssh.allowedSignersFile=scripts/deploy/allowed_signers verify-tag r0-v0.1.1
```

A pass prints a line naming the principal and the key fingerprint, for example:

```text
Good "git" signature for release@digithings with ED25519 key SHA256:Chsn3YHmj/fgmLR6MpDLe3S+zGpNXsiT5FBh3PvAQZo
```

Compare that fingerprint with the table above. A fingerprint that is not listed
is a refusal, not a warning, even if `verify-tag` reports a good signature
against the in-tree file.

## Client data under `projects/`

Every agent runs as the same unix user, so filesystem permissions cannot separate
engagements. The control is at the **tool-call boundary**: the opencode plugin
[`.opencode/plugins/projects-path-guard.js`](.opencode/plugins/projects-path-guard.js)
refuses any read under `projects/` except

1. `projects/README.md` — not client data; and
2. `projects/<engagement-dir>/**` — the single engagement bound to the run.

It is **default-deny and fails closed**: no bound engagement, a missing or
unreadable mapping, or a path that cannot be evaluated are all denials. Paths are
normalised (`..`, absolute paths, symlinks) before matching, so the guard cannot
be walked around by writing the path differently. Every refusal is logged as a
`projects_path_denied` audit event. One engagement per run: a run holds the paths
of the engagement named in `DIGI_ENGAGEMENT`, resolved through an explicit
operator-supplied engagement map that is kept private and does not ship with the
public tree.

Kill switch: `DIGI_PROJECTS_PATH_GUARD=off`, which is logged. Every other value,
including an unrecognised one, enforces.

`.gitignore` is **not** part of this control. It prevents a commit; it never
prevented a read.

## Threat model

digithings is designed to run on a single host or private network. The primary threats we design against:

- **Unauthorized access** to orchestration, search, or trading surfaces (arbitrary code execution, data exfiltration, unauthorized trades).
- **Credential leakage** via logs, spans, audit events, or error responses.
- **Prompt or tool-call abuse** — malicious input reaching agent workflows that drive real actions.
- **Accidental live-trading** — anything that could execute a broker order without explicit human approval.

We are **not** designing for public internet exposure by default. Running digithings on a public endpoint without a dedicated gateway and hardened auth is out of scope.

### STRIDE table

Controls cited in the Mitigation column are already landed on `develop`; see the
[Non-negotiable defaults](#non-negotiable-defaults), [Rate limiting](#rate-limiting-auth-paths),
[CORS policy](#cors-policy), [Secrets scanning](#secrets-scanning),
[Personal data in tracked payloads](#personal-data-in-tracked-payloads), and
[Dependency-audit policy](#dependency-audit-policy) sections for implementation detail.
STRIDE categories: **S**poofing, **T**ampering, **R**epudiation, **I**nformation disclosure,
**D**enial of service, **E**levation of privilege.

| Actor | Asset | Threat (STRIDE) | Mitigation (current) | Residual risk |
|-------|-------|-----------------|----------------------|---------------|
| External unauthenticated attacker | digichat BFF / leaked service endpoint | S — forge identity, replay tokens | RS256 JWTs with JWKS rotation; digichat session binding; CORS allowlist (no `*`) via `digibase.cors`. | JWKS cached 300 s — revocation propagation delayed; no WAF / bot-management layer. |
| External unauthenticated attacker | Auth paths (`/v1/oauth/token`, `/v1/admin/keys`) | D — brute-force / credential stuffing against bcrypt verify | Per-IP token-bucket limiter in `digikey.ratelimit` (10 rpm, burst 20); `/healthz` / JWKS exempt so probes stay live under load. | Pure in-process bucket — no cross-instance sharing; no global DDoS protection beyond per-IP. |
| External unauthenticated attacker | All FastAPI services | T/I — malformed payloads, parser abuse, unbounded bodies | Pydantic v2 models with `extra="forbid"` at every HTTP handler; bounded `httpx` timeouts via `digibase.http_client`; loopback binding keeps the attack surface off the public Internet by default. | No explicit request body-size cap at the ASGI layer; relies on upstream gateway for byte limits. |
| External unauthenticated attacker | `/healthz`, `/.well-known/jwks.json` | I — fingerprint service versions | Endpoints are deliberately minimal and secret-free; `/v1/status` on digitrace is audited for secret leakage. | Version / stack fingerprinting is possible from response shape; acceptable given public-by-design contract. |
| Compromised digikey API key holder | Tenant data in digisearch / digiquant | E — widen blast radius beyond issued scopes | Scoped API keys with per-route scope enforcement (`service_middleware`); tenant scope bound at the key layer. | Storage-layer tenant isolation is a roadmap item — today, isolation is key-scope-only (see `digibase/ARCHITECTURE.md`). |
| Compromised digikey API key holder | Live-trading paths (IB/Alpaca/QuantConnect adapters) | E — submit real orders | Broker adapters raise `NotImplementedError`; any code change touching them requires a `Human-Approved-By:` commit trailer enforced by `scripts/hooks/pre-push.sh`; the live-trading human gate lives in `docs/agents/CODE_REVIEW_POLICY.md`. | No runtime circuit-breaker yet — the gate is source-tree + commit-trailer, not a runtime interlock. |
| Compromised digikey API key holder | Audit trail | R — deny actions taken | Immutable JSONL audit via `digibase.audit.redact_mapping`; spans carry `workflow_id`, `request_id`, `session_id`. | Audit log is local per-host; no append-only remote sink or signed chain. |
| Compromised digikey API key holder | Rate-limited endpoints | D — exhaust quota for co-tenants | Per-IP limiter today; key issuance gated by admin scope. | No per-key / per-tenant quotas on orchestration or search paths yet. |
| Malicious LLM output (prompt injection) | Tool-calls from digigraph agents | E — coerce agent into unintended tool use | Pydantic v2 structured outputs across tool boundaries; MCP tool allowlist in `digigraph/orchestration/registry.py`; debug/thread endpoints off by default; live-trading adapters stubbed. | Prompt-injection from retrieved digisearch documents is not systematically defended — no content-level sanitizer or trust-tier tagging on retrieved context. |
| Malicious LLM output (prompt injection) | Outbound HTTP from tools | I — data exfiltration via crafted tool args | `digibase.http_client` enforces bounded timeouts; agent-harness PreToolUse hooks (`scripts/claude-hooks/`) block network calls to non-allowlisted hosts during agent development. | No runtime egress allowlist for service-to-service traffic in production paths. |
| Malicious LLM output (prompt injection) | Audit / span payloads | I — smuggle user secrets into observability | `digibase.audit.redact_mapping` strips prompts, JWTs, keys, doc bodies before persistence; `/v1/status` kept secret-free by contract. | Redaction is pattern-based — novel secret formats may pass through until a rule is added. |
| Insider / developer with repo write access | `SECURITY.md`, `.github/workflows/`, live-trading code | T/E — silently weaken controls | agent-harness PreToolUse hooks (`scripts/claude-hooks/`) block edits to protected paths off a `task-N-*` branch; pre-push hook blocks live-trading pushes without `Human-Approved-By:` trailer; CI PR-linkage workflow rejects orphan commits. | Hooks run in the developer's local environment — a determined insider bypassing the harness still needs to clear PR review and branch protection. |
| Insider / developer with repo write access | Client / pilot material | I — accidental commit of confidential data | `projects/` is gitignored and never pushed to public remotes; `gitleaks` CI on every PR and push with pinned SHA; [seed-payload PII gate](#personal-data-in-tracked-payloads) on every PR diff. | `gitleaks` allowlist entries require discipline — an incorrectly scoped entry could mask a real leak. The PII gate only reads addresses, and only in payloads; names have no reliable shape and stay out of scope. |
| Insider / developer with repo write access | `main` branch | T — unreviewed merge | `main` pushes require `ALLOW_MAIN_PUSH=1`; branch protection + PR scoring gate (Security ≥ 8, Accuracy ≥ 9). | Relies on GitHub branch protection being correctly configured — audited out-of-band. |
| Compromised dependency (supply-chain) | Any Python component | T/E — malicious transitive package | `pip-audit` workflow on every PR, every `develop`/`main` push, and weekly; fails merge on HIGH/CRITICAL (CVSS ≥ 7); acceptances require a justified `pip-audit-ignore.txt` entry. | MEDIUM/LOW findings are warn-only; `digiquant[nautilus]` is excluded (tracked in #42); `digichat/` Node audit is a sibling follow-up job. |
| Compromised dependency (supply-chain) | GitHub Actions runners | T — malicious action version | The gitleaks scanner is a checksum-pinned release; third-party actions in `.github/workflows/` are pinned by version. | Not every action in the repo is SHA-pinned — audited on change to any workflow file. |
| Co-tenant on shared host (research Phase 5) | Another tenant's index / audit / backtest output | I/E — cross-tenant read or privilege escalation | digikey scoped keys enforce tenant scope at the auth layer; audit events are redacted per tenant. | No storage-layer tenant isolation yet; no per-tenant resource quotas; multi-tenant deployment is explicitly a Phase 5 roadmap item. |
| Co-tenant on shared host (research Phase 5) | Shared LiteLLM proxy | D — exhaust shared LLM budget | LiteLLM caching enabled; `LITELLM_MASTER_KEY` + virtual keys required beyond loopback dev. | No per-tenant token/cost budget enforcement at the proxy layer. |

### Review cadence

This table is re-reviewed at the start of each phase (Phase 3, Phase 4, Phase 5)
and after any new public-facing endpoint ships. Update the Mitigation column
when a control lands on `develop`; move items out of the Residual-risk column
only once a concrete mitigation is merged and exercised by tests.

## Non-negotiable defaults

These are enforced in code and reviewed on every PR:

1. **Loopback binding.** Every service binds `127.0.0.1` in `docker-compose.yml`. No `0.0.0.0` without matching SECURITY.md approval (enforced by review per `docs/agents/CODE_REVIEW_POLICY.md`).
2. **digikey JWT required on protected routes.** digigraph, digiquant, and digisearch require `DIGIKEY_JWKS_URL` (or `DIGIKEY_PUBLIC_KEY_PEM`) and an `Authorization: Bearer <JWT>` on non-exempt routes. There is no legacy static `DIGI_API_KEY` fallback. digisearch additionally requires a real index backend (Azure or Chroma) unless `DIGISEARCH_ALLOW_STUB=1` (tests only).
3. **Human gates before any live trade.** Broker adapters (IB, Alpaca, QuantConnect) currently raise `NotImplementedError`. Any change to those paths requires explicit human approval per `docs/agents/CODE_REVIEW_POLICY.md`.
4. **Debug and thread endpoints are off by default.** `DIGI_ENABLE_DEBUG_ENDPOINTS` and `DIGI_ENABLE_THREAD_API` default to `0`; `/v1/debug/*`, `/test_llm`, and `/threads/*` are not exposed unless explicitly enabled.
5. **LiteLLM proxy is not unauthenticated in non-dev deployments.** With no `LITELLM_MASTER_KEY`, the proxy may accept requests without a Bearer — acceptable only on loopback/trusted networks. Beyond local dev, set `LITELLM_MASTER_KEY` (and `LITELLM_PROXY_API_KEY` on digigraph to match, or issue virtual keys via digikey).
6. **Audit events must be redacted before persistence.** Every `audit.jsonl` writer must go through `digibase.audit.redact_mapping` (or equivalent). API keys, JWTs, prompts, and document bodies must not appear in audit events. The `/v1/status` endpoint on digitrace is public — keep it secret-free.
7. **Observability spans do not carry secrets.** digitrace spans must include `workflow_id`, `request_id`, `session_id` but never raw prompts, API keys, or full document bodies.
8. **Bounded outbound HTTP timeouts.** Every service-to-service `httpx` call site constructs its client through `digibase.http_client.async_client` / `sync_client`, which apply a default `httpx.Timeout(connect=5, read=30, write=10, pool=5)` envelope. Bare `httpx.AsyncClient()` / `httpx.Client()` — which default to *no* read timeout and will hang indefinitely against a slow upstream LLM or broker — are forbidden in production code. Call sites that legitimately need longer budgets (e.g. 600 s backtest submission) pass an explicit `timeout=` override; the helpers preserve it verbatim. This bounds worst-case request latency under upstream degradation and prevents resource exhaustion on stalled connections.

## Data protection

- **Client and pilot work** lives under `projects/` (gitignored; never pushed to public remotes). Treat this as confidential.
- **Provider-side account records.** An account-level usage or billing export
  from a model provider can mix several deployments' data. Treat it as
  confidential: keep it out of agent context, issues and this repository, and
  record only the redacted per-deployment figure you need.
- **Index and corpus licensing** — digisearch indexes must respect upstream copyright and license. Do not automate retrieval of paywalled content without entitlement. The optional `edgar_dev` corpus is for dev/testing on loopback only; cite the upstream dataset when publishing results.
- **Per-tenant isolation** on multi-tenant deployments is a roadmap item (see `digibase/ARCHITECTURE.md` — digibase data-plane). Today, tenant isolation is enforced at the digikey key-scope level, not at the storage layer.

## Secrets scanning

Every pull request and every push to `develop`/`main` runs
[`gitleaks`](https://github.com/gitleaks/gitleaks) in the `secrets` job of
`.github/workflows/public-ci.yml`. The scanner is a pinned release verified by
checksum (supply-chain hardening), and the job fails on any finding.

- **What's scanned.** PRs scan the diff; `develop`/`main` pushes scan the
  commit range. Configuration lives at [`.gitleaks.toml`](.gitleaks.toml) and
  extends the default ruleset (AWS, GCP, Azure, GitHub, generic API keys,
  PEM private keys, JWTs).
- **Local reproduction.** `make secrets-scan` runs the same config against
  the working tree. Install gitleaks via `brew install gitleaks` or
  `go install github.com/gitleaks/gitleaks/v8@latest`.
- **Local pre-push guard.** `make hooks-install` installs
  `scripts/hooks/pre-push.sh`, which runs the same config over the commits a
  push would add. When `gitleaks` or `.gitleaks.toml` is unavailable the hook
  **refuses the push** instead of skipping the scan: the GitHub workflow covers
  pull requests and pushes to `main` only, so a topic-branch push would
  otherwise leave unscanned. The installer asks the same question before it replaces the hook:
  with no `gitleaks` on `PATH` it refuses and leaves the installed hook alone,
  because `make agents-init` reinstalls this shared hook on every start and a
  generator must not be what turns a machine that cannot scan into one that
  cannot push. `PRE_PUSH_SKIP_GITLEAKS=1` skips the scan for one push and prints
  the refs it did not scan — for synthetic fixtures and machines that cannot
  install the binary, not for a push you believe is clean.
- **Secret-list drift.** `make secrets-audit` matches every `secrets.*` read under
  `.github/` against each level a name can live at — repo secret, repo variable, org
  secret, environment secret — and reports `dead` (a repo secret nothing reads),
  `not repo-level` (defined at another level), `unresolved` (defined nowhere, so Actions
  substitutes an empty string), `repo-over-org` (defined at both, where the repo copy
  silently wins) and `env-over-repo` (defined at both, where a job that declares that
  environment reads the environment copy). `--strict` exits non-zero on `dead`;
  `--strict-unresolved` does the same for `unresolved`. Both refuse to pass when a level
  could not be read. Passing `--secrets-file` keeps the whole run offline. It is a local
  check, not a CI gate.
- **Allowlist policy.** `tests/`, top-level and `docs/**/*.md` markdown, and
  `scripts/claude-hooks/fixtures/` are allowlisted because they only contain
  placeholder values, fake/ephemeral fixtures, or vendor-published example
  tokens (e.g. `AKIAIOSFODNN7EXAMPLE`). Example templates are deliberately
  **not** path-allowlisted: the root `.env.example` stays scanned, and the
  placeholder values it carries (`replace-with-…`, `your-…-here`, `<…>`) are
  filtered by the value patterns in `.gitleaks.toml`. Adding a new
  allowlist entry requires a comment in `.gitleaks.toml` justifying why the
  match is safe, and reviewers are expected to push back on entries that
  broaden the allowlist without a clear fixture/example rationale.
- **If a real secret leaks.** **Rotate first**, then add an allowlist entry.
  Order matters — adding the allowlist before rotation hides the leak from
  future scans without removing the live credential. Once rotated, the
  allowlist entry (ideally a path + regex scoped to the specific value or a
  commit SHA pin) documents that the historical reference is safe.

## Personal data in tracked payloads

`gitleaks` looks for credentials. It does not look for **personal data**, and
the two are not the same problem: a seed payload (`apps/*/container/seed/*.jsonl`)
is copied wholesale into a running vector store, so one committed address
reaches every person the tenant talks to. This gate exists because a seed
payload quoting customer addresses and staff-only notes once reached `main`
with every check green.

- **The gate.** `scripts/check_pii_seed_payloads.py` fails a commit that adds
  or modifies a tracked `.jsonl`/`.json` payload containing an email address
  outside the RFC 2606 / 6761 reserved domains (`.test`, `.example`,
  `.invalid`, `.localhost`, and the `example.com|net|org` names). It runs in
  the `secrets` job of `.github/workflows/public-ci.yml` on every PR diff.
- **Local reproduction.** `make pii-scan` scans the working tree (the form to
  run before committing a new seed payload); `make pii-scan-all` scans every
  tracked payload.
- **Reserved domains, not an allowlist.** Fixtures stay writable using
  `jane.doe@example.test`; a real-looking domain such as `gmail.com` or
  `acme.example.com` is a finding. There is deliberately no exemption list to
  widen.
- **Diff-scoped by default.** Introducing the gate cannot retroactively fail
  on the payload that is already committed. `--all` scans the whole
  tree, and is the mode to run once containment has landed. It is not a
  required status check until then: a required check that is red on arrival
  teaches people to bypass it.
- **It prints counts, never addresses.** A guard whose output can be pasted
  into a CI log is a second disclosure channel, and this repo is public. The
  finding is `path:line: count`.
- **What it does not catch.** Display names and internal tags have no
  reliable shape; a name in free text is only removable by a product decision
  (German and Spanish prose need real name detection), not by a lint rule. The
  masking default that keeps them out of a helpdesk corpus lives in the
  private helpdesk MCP server, not in this repository.
- **If a payload leaks.** Mask before committing, not after. Whether a
  committed payload counts as a notifiable breach is a legal call, not a code
  reviewer's.

## Remote access

If you need to reach the stack from outside the host, use **Tailscale** or **Cloudflare Tunnel** rather than exposing ports publicly. `DIGICHAT_PUBLISH_HOST=0.0.0.0` is documented as an escape hatch for LAN exposure but should still sit behind a VPN or tunnel — never on the public internet.

An edge gateway (currently digibot's scope) is the intended single Internet-facing surface: OIDC or mTLS, session binding, global rate limits, with digigraph and the verticals kept on loopback or private networks behind it.

## Rate limiting (auth paths)

digikey applies a per-IP token-bucket rate limiter to its auth-sensitive
routes — `POST /v1/admin/keys` (key issuance) and `POST /v1/oauth/token`
(JWT mint). Defaults: 10 requests/minute sustained, burst 20. Override via
`DIGIKEY_RL_PER_MIN` and `DIGIKEY_RL_BURST`. On breach the service returns
HTTP 429 with body `{"detail": "rate_limited", "retry_after": N}` and a
`Retry-After` header.

Exempt routes (no limiter overhead): `GET /health`,
`GET /.well-known/jwks.json`, and any future `/healthz`, `/metrics`,
`/v1/status`. This keeps liveness probes unaffected under load.

The limiter is pure in-process. Cross-process / multi-instance sharing is a
follow-up — a Redis or digibase-backed store would be the upgrade path. For
today's loopback-bound, single-instance digikey deployment, per-process
buckets are sufficient to blunt brute-force attempts against the bcrypt
verify path.

## CORS policy

Every FastAPI service (digigraph, digiquant, digisearch, digitrace, digikey)
installs CORS middleware via the shared helper
[`digibase.cors.install_cors`](digibase/src/digibase/cors.py). The helper reads
an **explicit allowlist** from the environment — there is no wildcard
(`*`) default, and there is no default that accepts arbitrary browser origins.

**Precedence** (first non-empty wins):

1. `<SERVICE>_CORS_ORIGINS` — per-service override
   (`DIGIGRAPH_CORS_ORIGINS`, `DIGIQUANT_CORS_ORIGINS`,
   `DIGISEARCH_CORS_ORIGINS`, `DIGITRACE_CORS_ORIGINS`,
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
  from digichat.
- `allow_methods=["GET","POST","PUT","DELETE","OPTIONS"]` — no `TRACE`,
  `CONNECT`, or wildcard.
- `allow_headers=["Authorization","Content-Type","X-Request-ID"]` — the
  minimum set used across the stack.
- `max_age=600` — browser caches the preflight response for 10 minutes.

Deployments that serve a browser UI **must** set at least one of the env vars
above. `scripts/run_stack_local.sh` defaults to localhost origins for dev
ergonomics; production deployments set the exact digichat origin.

## Revocation

JWT revocation before natural expiry is a roadmap item (tracked under the [digikey revocation epic](https://github.com/digithings-ai/digithings/issues/6)). Today, revocation requires rotating the signing key or waiting for token expiry. Design any deployment with token TTLs short enough that this is acceptable.

## Reporting vulnerabilities

If you believe you have found a security vulnerability in digithings:

1. **Do not** open a public GitHub issue.
2. Email **contact@digithings.ai** with `[digithings Security]` in the subject.
3. Include steps to reproduce, affected component(s), and any known impact.
4. Expect an acknowledgement within 72 hours and a coordinated-disclosure timeline within 7 days.

We'll work with you on an embargo period if appropriate and credit you in the release notes if you'd like.

## Dependency-audit policy

Every Python component is scanned on every PR, every push to `main`/`develop`, and weekly (Monday 06:00 UTC) by the `pip-audit` workflow against the [OSV](https://osv.dev) vulnerability database.

- **Blocks merge:** any finding with OSV severity **HIGH** or **CRITICAL** (CVSS ≥ 7.0).
- **Warn-only:** findings at **MEDIUM** or **LOW** severity, and findings with unknown severity — surfaced via `::warning::` annotations on the PR, not gated.
- **Scope:** `digibase`, `digigraph`, `digiquant`, `digisearch`, `digitrace`, `digikey`, `digibot`. Each component is installed with its `[dev]` extras and audited against the resolved transitive closure. `digiquant[nautilus]` is excluded (tracked in #42).

The JS workspaces are covered by the sibling `npm audit` workflow on the same cadence, auditing the whole `apps/*` + `packages/*` closure from the single root `package-lock.json`.

- **Blocks merge:** any advisory npm reports as **HIGH** or **CRITICAL**.
- **Warn-only:** **MODERATE**, **LOW** and unknown severities.
- **Per-advisory acceptance:** the classifier matches the ignore list against each advisory individually, not against the package — a *new* advisory on a package that already has accepted ones still blocks.
- **Fails closed:** an npm audit that could not reach the registry (error body, or no `vulnerabilities` key) fails the lane rather than reporting clean.
- **Scope note:** accepted npm advisories live in [`npm-audit-ignore.txt`](npm-audit-ignore.txt) and follow the same justification requirement as the Python list below.

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

This policy covers vulnerabilities only. Third-party **license** obligations — including recorded acceptances of weak-copyleft dependencies — are handled separately in [docs/LICENSING.md](docs/LICENSING.md).

## PR security review

Every pull request touching a security surface gets a security-lens review per `docs/agents/CODE_REVIEW_POLICY.md` before merge (the self-score rubric was removed in #4868). Changes to `SECURITY.md` itself always get a human review.
