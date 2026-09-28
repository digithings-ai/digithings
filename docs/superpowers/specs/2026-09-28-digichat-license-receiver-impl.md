# digikey heartbeat receiver + edge scope checks (implementation spec, slice 3)

- **Date:** 2026-09-28
- **Status:** Implementation spec — authorizes the implementing task PR(s); runtime changes land through those PRs with the digikey human gate
- **Binds to:** [digichat customer license design](2026-09-27-digichat-customer-license-design.md) (rev 5, eight owner decisions; this spec implements the server half: § Heartbeat receiver, § Hosted-service auth validation point), [license-mint CLI (slice 1)](2026-09-28-digichat-license-mint-impl.md) (the `digikey_licenses` allowlist + its normative §4.4 four-state read contract, which this slice reads), and [container verification + heartbeat sender (slice 2)](2026-09-28-digichat-license-heartbeat-impl.md) (the sender; §8 fixes the request/response contract this slice serves)
- **Scope:** the digikey heartbeat POST endpoint (four-state allowlist read) + the admin license-revoke endpoint + the digigraph edge license scope checks (`X-Digi-License` against `services`). Nothing else.
- **Slice boundary:** the license-mint CLI and `digikey_licenses` writes are slice 1; the container verification, revoke latch, and heartbeat sender are slice 2. Slice 3 reads the allowlist slice 1 writes and answers the sender slice 2 ships. Slice 2 is fully operational before this slice exists (its §5.5 fail-open rules make that safe — see §10).
- **Human gate:** slice 3 adds a new `digikey/` HTTP surface (auth-adjacent: it authenticates license bearers) and touches digigraph request handling on an auth-adjacent path. Per root `AGENTS.md` the implementing PR(s) need owner review and must not merge on green CI alone. This spec itself is docs-only.

## 0. How to execute this spec (read this first, executor)

1. **Read first:** `digikey/AGENTS.md` (pre-flight checklist — bcrypt untouched, raw key material never logged, new endpoints admin-gated or explicitly public) and `digikey/ARCHITECTURE.md` §3 (API surface) and §6 (security analysis); then `digigraph/AGENTS.md` (pre-flight — no new digisearch/digiquant imports, `DigiAuthMiddleware` path scopes) and `digigraph/ARCHITECTURE.md` (§6 request context / auth, corpus routing). Then the three bound specs above. Never skip the component `AGENTS.md` files.
2. **Branching:** the implementing change touches `digikey/` and `digigraph/` code, so it spans `component:digikey` and `component:digigraph` — cut with `make task ISSUE=N` per `scripts/project_routing.json`, never from a stale base. One PR per component is acceptable (receiver first, edge second); what is binding is the contract in §3, shared unchanged by both.
3. **Spec file ≠ code file:** this document prescribes interfaces, behavior, and acceptance. Exact function names below are recommendations; what is binding is the endpoint contract (§2), the four-state table (§3), the evaluation order (§4), the error-code spellings (§3–§5), the edge scope map (§7), and the acceptance checklist (§9).
4. **Conventions:** Pydantic v2, strict typing, ruff line length 100, lowercase digi names in prose (code identifiers keep their casing). The raw license JWT and any key material are never logged, never returned in a response, and never written to a file — `license_id`, customer slug, and `exp` are safe to log (slice 1 §2.3).
5. **Tests / commands:** `pytest tests/ -m unit -k "digikey or digigraph" -v` passes before and after; `ruff check digikey/ digigraph/ && ruff format --check digikey/ digigraph/`. No stack required (sqlite via `DIGIKEY_DATABASE_URL`, same as the existing digikey suite).
6. **Docs duties in the implementing PR(s):** `digikey/ARCHITECTURE.md` (new endpoint, license verify path, error-code table) and `digigraph/ARCHITECTURE.md` (license scope checks, `X-Digi-License` header, plain-inference-open guarantee) — this spec names the behavior but ships no code and no doc edits.

## 1. Locked decisions (inherited — not re-decided here)

| # | Decision (source) | Slice-3 consequence |
|---|---|---|
| D1 | Keypair reuse — licenses are RS256 with the existing digikey keypair, `aud=digichat-license` (design 1; slice 1 §3) | Receiver verifies against the server's own signing key (`load_or_create_signing_key` in `digikey/src/digikey/crypto_keys.py:56`); no new keypair, no new env var |
| D2 | Heartbeat credential = raw license JWT as Bearer token; server checks signature + allowlist + expiry keyed off `license_id` (design 8) | Single-step check in §4; the allowlist is slice 1's `digikey_licenses`, not the bcrypt API-key registry and not the jti blocklist |
| D3 | Four-state contract `valid` / `expired` / `revoked` / `unknown` (slice 1 §4.4, normative; slice 2 §8) | §3 reproduces the mapping byte-for-byte; expired is HTTP 200, never 401 |
| D4 | Deny requires HTTP 401 **and** a recognized `error` code; everything else is fail-open (slice 2 §5.5) | The receiver must never emit a bare or generic 401 for a license state — §3 fixes the only two 401 bodies that latch |
| D5 | Header-to-scope map: corpus headers → `digisearch-corpus`, web-search header → `hosted-web-search`; plain inference stays open (design 3) | §7 enforces exactly these two scopes at exactly the two enforcement points; no third scope, no inference gate |
| D6 | `X-Digi-License` forwarding on digigraph calls is the edge slice, not slice 2 (slice 2 §11) | The forwarding one-liner lands with the edge half of this slice (§7.1) |

## 2. Heartbeat endpoint contract

`POST /v1/licenses/heartbeat` on digikey (the path slice 2 §5.3 and §8 send to — fixed on both sides so neither slice re-litigates it).

**Request (slice 2 owns; repeated here so the receiver can be tested standalone):**

```http
POST /v1/licenses/heartbeat
Authorization: Bearer <raw license JWT, unchanged>
Content-Type: application/json

{"license_id":"…","customer":"datatap","license_status":"valid","version":"2.3.2",
 "hosts_configured":["datatapstream.com"],"started_at":"2026-09-28T09:14:02.000Z","seq":1}
```

- The header carries the credential; the body carries telemetry (design decision 8). No usage counts, no message contents, no end-user identifiers.
- **This route authenticates *as* a license.** It must not pass through the ordinary API-key exchange path (`server.py:303-358`, prefix lookup + bcrypt) or the admin bearer gate (`_require_admin`, `server.py:116-123`): a license JWT is not an opaque `dgk_live_` secret and carries no admin token. Its only credential check is §4.

**Response (this slice owns):** exactly §3. `any other` input is an error outcome the sender rides out (slice 2 §5.5).

## 3. Four-state read logic (normative — identical to slice 1 §4.4 and slice 2 §8)

| State | Row condition | HTTP | Body | Sender effect |
|---|---|---|---|---|
| valid | row exists, `revoked_at IS NULL`, `expires_at > now` | 200 | `{"license_status":"valid"}` | stays `valid`; next attempt in 24h |
| expired | row exists, `revoked_at IS NULL`, `expires_at <= now` | 200 | `{"license_status":"expired"}` | identified-but-lapsed → `expired`; **not** a deny |
| revoked | row exists, `revoked_at IS NOT NULL` | 401 | `{"error":"license_revoked","message":…}` | latches `revoked` at that heartbeat |
| unknown | no row for the presented `license_id` | 401 | `{"error":"unknown_license","message":…}` | latches `revoked` with `detail=heartbeat_deny_unknown` |

Binding rules:

1. **Expiry is 200, never 401.** An expired-but-authentic license identifies the deployment (design decision 8); a 401 would latch `revoked` on an expired license and collapse the expired/revoked distinction the contract exists for (slice 2 §8). This is the single most load-bearing line of this slice.
2. **Only these two 401 bodies latch.** `license_revoked` and `unknown_license` under the `error` key — exactly the spellings slice 2 §5.5 recognizes. No other 401 shape may carry license-state meaning.
3. **Signature-invalid, malformed, or wrong-audience tokens answer generic 401** (`{"error":"unauthorized","message":…}`, matching the middleware idiom at `digikey/src/digikey/integrations/service_middleware.py:143-148`). The sender treats an unrecognized 401 as an error outcome (serve + backoff), which is correct: a token that fails crypto tells us nothing about allowlist state, so it must not latch.
4. **Malformed telemetry bodies are 400, never deny.** A well-signed JWT with a bad/mismatched telemetry body (missing keys, body `license_id` ≠ JWT `license_id`) answers `400 {"error":"invalid_heartbeat_body",…}` — an error outcome the sender rides out. Telemetry hygiene must never stop product traffic.
5. **The `error`-key shape is deliberate and differs from digikey's neighbors.** The shared middleware answers `{"code": …, "message": …}` (`service_middleware.py:65-67,85-88,99-102`) and `HTTPException` paths use `detail` (`server.py:315-318`). The heartbeat answers `{"error": …, "message": …}` because that is what slice 2 §5.5 matches on. Do not "normalize" it to either neighbor convention — doing so silently breaks the latch.
6. **Clock-skew leeway is 300s symmetric**, same as both prior slices (slice 1 §verifier notes, slice 2 §3.2): expiry compares `expires_at <= now` with ~5 minutes of tolerance so customer-clock drift never flips a live license to expired at the boundary.

## 4. Single-step check (normative evaluation order)

Per heartbeat request, in this order (slice 2 §8):

1. **Parse** — extract the Bearer token; reject missing/empty with generic 401. Split compact JWT, require three segments.
2. **Verify signature** — RS256 only (reject `none` and every symmetric `alg` outright — the classic key-confusion hole; `digikey/AGENTS.md` RS256-not-HS256 rule). Verify against the server's own signing key (`_private_key` loaded at `server.py:54`; derive the public half — no new key, no JWKS fetch for our own signatures). Checks: `aud == "digichat-license"`, `iss` equals the server issuer (`_issuer()`, `jwt_issue.py:19-20`), `kind == "digichat-license"`, `license_id` (or its `jti` mirror) present. Failure at this step → generic 401 (§3 rule 3).
   - Do **not** reuse `jwt_verify.decode_token()` as-is: it enforces the access-token audience (`_audience_list()`, `jwt_verify.py:29-31`, default `digi-ecosystem`) and normalizes into `TokenClaims`, which has no license fields (`models.py:12-36`). A license-specific verify (same RS256 path, license audience + `kind` check) is required; sharing helpers below the audience check is fine.
3. **Allowlist read** — `license_id` lookup against `digikey_licenses` (slice 1 §4.1). No row → `unknown` (401 `unknown_license`). Row with `revoked_at` set → `revoked` (401 `license_revoked`). This is a nullable-`revoked_at` row lookup mirroring the `ApiKeyRow.revoked_at` convention (`db_schema.py:40`) — **not** the bcrypt verification path (`key_crypto.py:20-28`) and **not** the Redis jti blocklist (slice 1 §4.3: a 90-day blocklist entry per license would be pure weight with no reader).
4. **Expiry** — live row with `expires_at <= now` (300s leeway) → `expired` (200). **Revoked beats expired:** a revoked row that has also expired still answers `license_revoked` — revocation is the operator's explicit act and must stay visible as such in logs.

**Expired still identifies.** An expired-but-authentic license reports the deployment as expired rather than anonymous (design decision 8): the 200 `expired` body may carry the `license_id` and customer slug (both safe to log per slice 1 §2.3) so edge logs and heartbeat logs stay attributable. It refuses hosted-service and product-traffic authorization on expiry grounds — never as a deny.

## 5. Revoke wiring (allowlist removal, no redeploy)

- **Primary path is slice 1's CLI:** `digikey license-revoke --license-id <jti>` sets `revoked_at` (slice 1 §5). The heartbeat read side picks it up on the next lookup — no redeploy on either side by design. This slice adds no new revocation *mechanism*.
- **This slice adds the admin HTTP revoke** (deferred by slice 1 §5 to the slice that needs server-side allowlist access): `POST /v1/admin/licenses/{license_id}/revoke`, mirroring `POST /v1/admin/keys/{key_id}/revoke` (`server.py:366-403`):
  - gated by `_require_admin` (`server.py:116-123`) — `DIGIKEY_ADMIN_TOKEN` bearer, 503 when unconfigured, 401 on mismatch;
  - idempotent: re-revoking a revoked row answers `{"revoked": true}` with exit/success semantics unchanged (same convention as the CLI's `already_revoked`, slice 1 §5);
  - unknown `license_id` → 404 `license not found`-style answer, distinct from revoked — preserving the unknown-vs-revoked distinction end to end (the same distinction the existing `:379-381` 404 and `:315-318` unknown-401 vs revoked-401 draw);
  - **no blocklist writes** (slice 1 §4.3 — licenses are allowlist-enforced, never jti-blocklisted); the 503-on-blocklist-failure branch of the key-revoke endpoint (`server.py:393-401`) therefore has no counterpart here.
- **Revocation drill** (design § Rollout step 5, runnable once slices 1–3 all land): mint → heartbeat 200 `valid` → `license-revoke` (CLI or admin endpoint) → next heartbeat 401 `license_revoked` → container refuses with 503 → re-mint → restart → container serves again (slice 2 §10).

## 6. Rate, abuse, and observability

- **The 24h heartbeat cadence and the ~90d term are validity cadences, not rate limits or budgets** (design § License claims note). Nothing in this slice frames them as throttling, and no new throttle knob is introduced.
- **Abuse posture for a 1/day caller:** carry the existing `rate_limit_dependency` on the heartbeat route exactly as the admin/oauth routes do (`server.py:163,226,369,423` — defaults `DIGIKEY_RL_PER_MIN=10`, burst 20, `ratelimit.py:22-25`). A 1/day caller consumes a negligible fraction of its bucket; the per-bearer bucket key (`rate_limit_key` hashes the token, `ratelimit.py:116-125`) isolates license bearers from each other. A 429 answer is an error outcome the sender rides out (serve + backoff), so even a misconfigured fleet that synchronized its heartbeats degrades to retries, never to a latch. No dedicated abuse table, no IP allowlist, no per-license quota — a daily POST needs none of them.
- **Logs (structured, secret-free):** one line per heartbeat outcome at the existing digikey log style — `license_id`, customer slug, resolved state, `seq`, sender-reported `license_status`/`version`. Never the raw JWT, never the `Authorization` header value, never a PEM (same rule as `key_id`/prefix in `digikey/AGENTS.md`). Revoked/unknown answers log at warning level (operator action is expected); valid/expired at info.
- **Metrics:** reuse the installed `install_metrics(app, service="digikey")` (`server.py:49`) — a `license_heartbeat_total{result}` counter over the four states plus a generic-error bucket. No new metrics backend (slice 2 §7.3 sets the same rule for its side: health + logs, no new exporter).
- **`/healthz` stays untouched** — auth-exempt, always `{"ok": true}` (`server.py:99-107`); the heartbeat route must not alter liveness semantics.

## 7. Edge scope checks

### 7.1 License transport on hosted-service calls

When the container calls digigraph it forwards its license JWT in an `X-Digi-License` header alongside the existing `X-Digichat-Tenant` / `X-Digi-Tenant` / `X-Digi-Caller` headers (`apps/digichat/src/app/api/chat/route.ts:515-531` upstream headers block; corpus headers `:523-531`, web-search header `:592-594`). Containers with no license omit the header. The value is the same raw JWT as the heartbeat Bearer token (design decision 4 — single credential). The one-line forwarding addition lands with the edge half of this slice (slice 2 §11 excludes it from the sender). `X-Digi-License` is greenfield today (no sender, no reader — grep confirms zero hits).

### 7.2 Scope map (normative — design decision 3, adopted exactly)

| Requested hosted capability | Headers present | Required `services` scope | Enforcement point |
|---|---|---|---|
| digisearch corpus / digivault prefix routing | `X-Digi-Corpus-Index` (`route.ts:526`) / `X-Digi-Vault-Prefix` (`route.ts:529`) | `digisearch-corpus` | digigraph corpus resolution: `resolve_corpus_override` (`digigraph/src/digigraph/corpus_routing.py:137`) via `_digi_fields_from_request` (`digigraph/src/digigraph/http_api/context.py:51`), which unconditionally overwrites `digisearch_index` / `vault_path_prefix` |
| hosted web search | `X-Digi-Enable-Web-Search` (`route.ts:593`) → body-or-header `enable_web_search` on the chat path (`_resolve_enable_web_search_chat`, `digigraph/src/digigraph/http_api/chat_resolve.py:104`), body `enable_web_search` on `/workflow` (`models.py:226`) | `hosted-web-search` | web-search opt-in resolution feeding `enable_web_search` graph state (`workflow.py:378`), gated by `apply_web_search_opt_in` (`tool_policy.py:81`) and the `web_search` tool `when` predicates (`orchestration/web_search_tools.py:69`) |
| plain inference | none of the three hosted headers | — (open) | no enforcement point is touched |

- **Validation per call:** signature against the digikey public key (online JWKS or `DIGIKEY_PUBLIC_KEY_PEM` — this is our infrastructure, so online verification is acceptable per the design § Validation point), `exp`, `sub`/`tenant_slug`, and the `services` scope against the requested capability. `services`-absent means entitled, not unentitled (slice 1 §verifier notes) — an incorporates-everything commercial term needs no scope list.
- **No per-call online allowlist check at edge in this slice.** Revocation freshness at our edge comes from the heartbeat latch (an honest revoked container stops calling within ~24h) plus the `exp` backstop. A per-call allowlist read would couple every hosted turn to digikey availability; a hostile container that ignores its latch is bounded by the term it already paid for (design § Threat model — accepted). If a later slice wants online edge checks, that is a new spec, not a drive-by.
- **Licenses never authorize inference.** The `DigiAuthMiddleware` scopes (`digigraph:chat`, `digigraph:workflow`, `digisearch:query` — `digikey/src/digikey/integrations/service_middleware.py:161-211`) are unchanged: operator JWT auth still gates the routes themselves. The license check is an *additional* capability gate that fires only when a hosted header is present.

### 7.3 Refusal surface (hosted portion only)

- A hosted capability requested without an authorizing license (header absent, invalid, expired, wrong scope) is refused with **403 `{"error":"insufficient_license_scope","message":…}` naming the missing scope** — the design's "refuse the hosted-service portion only (error naming the missing scope), never the whole chat request where separable" (design § Hosted-service auth). Scope for this slice: refuse the request when it asks for a hosted capability it is not entitled to (corpus grounding is not separable from the turn — a silent downgrade to ungrounded answers would hide entitlement state and risks answering from the wrong corpus, the same class `corpus_routing.py:1-20` guards against).
- **Plain-inference-open guarantee:** a request carrying none of the three hosted headers never touches a license check and behaves exactly as today — with or without `X-Digi-License`, valid or absent. A foundry-path container calling nothing of ours is unaffected by definition. The test plan (§8) pins this with a regression case.
- **Multi-tenant isolation is unchanged:** when `DIGI_TENANT_CORPUS_MAP` is set it stays authoritative and client headers stay ignored (`corpus_routing.py:165-198`); the license gate sits *after* map resolution and can only narrow, never widen, corpus selection. A set-but-broken map still raises `TenantCorpusMapError` → 503 (`context.py:87-90`).

## 8. Test plan

Unit only, no stack (sqlite via `DIGIKEY_DATABASE_URL`, same as the existing digikey suite; digigraph edge cases via `TestClient` with auth stubbed at the middleware boundary where the suite already does so):

| Area | Cases |
|---|---|
| Four-state matrix | live row → 200 `valid`; live-but-expired row → **200 `expired` (never 401)**; revoked row → 401 `license_revoked`; missing row → 401 `unknown_license`; revoked-and-expired row → 401 `license_revoked` (revoked beats expired) |
| Crypto boundary | tampered payload/signature → generic 401 `unauthorized` (not a latch code); `alg: none` / `HS256` rejected without a HMAC path; wrong `aud` / wrong `iss` / missing `kind` / missing `license_id` → generic 401; 300s skew honored both directions (expired 4 min ago reads live; 6 min ago reads expired) |
| Contract fidelity | every 401 the route emits carries `error` ∈ {`license_revoked`, `unknown_license`, `unauthorized`} — assert no other 401 body shape exists on this route; telemetry mismatch (body `license_id` ≠ JWT) → 400, never deny; malformed JSON → 400 |
| Auth isolation | license JWT presented to `/v1/oauth/token` fails (wrong audience — not an access token); access JWT presented to `/v1/licenses/heartbeat` fails (wrong audience — symmetric); admin bearer presented as heartbeat Bearer fails crypto (not a license) |
| Admin revoke | revoke flips live → revoked idempotently; unknown id → 404 distinctly; no blocklist write occurs (assert); `_require_admin` enforced (401 without token, 503 without env) |
| Rate/abuse | 1/day cadence consumes no meaningful bucket (assert by config arithmetic, not by sleeping); 429 (forced via low test limits) maps to sender error-outcome shape, never a latch code |
| Edge corpus | `X-Digi-Corpus-Index` + valid in-scope license → override flows as today; same headers + absent/invalid/out-of-scope license → 403 naming `digisearch-corpus`; map-set deployments keep map-authoritative behavior with the license gate narrowing only |
| Edge web-search | `X-Digi-Enable-Web-Search` + in-scope license → `enable_web_search` true on both chat and workflow paths; without scope → refused naming `hosted-web-search` |
| Plain-open regression | identical plain-inference requests (no hosted headers) with absent / valid / expired / revoked license → byte-identical behavior to pre-change (no license code path executes) |
| Secret hygiene | assert on log capture: no raw JWT, no `Authorization` value, no PEM in any heartbeat or edge log line, response, or error body |

Selectors: `pytest tests/ -m unit -k "digikey or digigraph" -v`; `ruff check digikey/ digigraph/ && ruff format --check digikey/ digigraph/`. The implementing PR(s) state the exact new test file paths; binding requirement is the case coverage above, not file names.

## 9. Acceptance criteria

- [ ] `POST /v1/licenses/heartbeat` with a minted license answers the four rows of §3 exactly — including expired → 200 and revoked-beats-expired — against a scratch database seeded by slice 1's CLI
- [ ] No 401 emitted by the route carries an `error` code outside {`license_revoked`, `unknown_license`, `unauthorized`}; slice 2's sender test-suite (§9, response-handling row) passes unmodified against this receiver
- [ ] The route is unreachable through the API-key exchange and admin-bearer paths (auth-isolation cases in §8 green)
- [ ] `POST /v1/admin/licenses/{license_id}/revoke` flips live → revoked idempotently, 404s unknown ids distinctly, writes no blocklist entries
- [ ] End-to-end revocation drill (mint → heartbeat 200 → revoke → heartbeat 401 → container 503 → re-mint → restart → serve) passes with the slice-2 container
- [ ] Edge: corpus and web-search headers enforce their scopes with 403 scope-naming refusals; plain inference is byte-identical with and without a license
- [ ] No raw JWT, PEM, or `Authorization` value in any log, metric label, response, or error body (§8 secret-hygiene assertion green)
- [ ] No change to access-token behavior — TTL/aud defaults, bcrypt paths, existing revoke endpoint, JWKS shape, and `DigiAuthMiddleware` scopes all untouched (reviewer verifies by grep)
- [ ] `digikey/ARCHITECTURE.md` (endpoint, license verify, error codes) and `digigraph/ARCHITECTURE.md` (scope checks, `X-Digi-License`, plain-open guarantee) updated in the implementing PR(s)
- [ ] Unit suite + ruff clean per §8; this spec's `python3 scripts/check_doc_links.py` green

## 10. Rollout order (normative)

1. Slice 1 (mint + allowlist writes) → slice 2 (container verify + sender) → **this slice (receiver + edge)**. Slice 2 ships safely before the receiver exists: a digikey without `/v1/licenses/heartbeat` answers 404, which is an error outcome (serve + backoff) under the §3/§5.5 recognition rules — shipping order is an acceptance property, not a hope.
2. Within this slice, receiver before edge: heartbeats must be able to learn deny before hosted-service calls are gated, so the first enforcement signal a deployment ever sees comes from its own heartbeat, not from a surprising 403 on a corpus call.
3. The revocation drill (§5) runs owner-operated against the pilot deployment before any customer depends on the behavior.

## 11. Non-goals (explicit)

- **No CLI** — mint/revoke CLI is slice 1 (§5's HTTP revoke is the only allowlist write here, and it writes `revoked_at` only).
- **No container sender, verification, latch, or refusal pages** — slice 2. No `apps/digichat/**` changes except the `X-Digi-License` forwarding one-liner (§7.1), which rides the edge PR.
- **No launch-gating.** Nothing here stops a container from starting; enforcement is heartbeat-latch (container side, slice 2) and hosted-capability refusal (edge side, this slice).
- **No feature gating.** No config option, model, tool, MCP server, or UI knob is hidden or disabled in any state (design § Non-goals).
- **No usage metering, billing, or seat counting** — there is no meter in this program.
- **No JWKS multi-key serving** — rotation stays procedural (slice 1 §6); the receiver verifies against the server's own key.
- **No per-call online allowlist check at edge** (§7.2) — heartbeat latch + `exp` backstop is the revocation model; online edge checks are a future spec if ever wanted.
- **No changes** to access-token issuance/verification defaults, bcrypt paths, the API-key revoke endpoint, `DigiAuthMiddleware` scopes, multi-tenant corpus-map authority, or the health/liveness endpoints.
- **No new metrics backend**, no Prometheus/digismith export beyond the existing digikey metrics install.

## 12. Open questions

1. **Online edge revocation checks (deferred, not a blocker).** §7.2 deliberately skips per-call allowlist reads at edge. If a hostile-but-licensed deployment ignores its latch and keeps calling hosted services, we serve it until `exp`. The design accepts this (bounded by the paid term); closing it later means an edge→digikey read with its own availability coupling, which needs its own spec.
2. **Should `expired` edge calls identify?** §4 says the heartbeat 200 `expired` body may carry `license_id`/customer for log attribution. Whether the 403 `insufficient_license_scope` body echoes the same (attributable) or stays minimal is implementer choice within the secret-hygiene rule — `license_id` and customer slug are safe either way.

## Verification (this spec — docs-only)

- No code changed by this spec; branch `docs/spec-license-receiver` off `origin/develop` at `e1c701d2e`.
- Every file:line claim grounded against `origin/develop`: `digikey/src/digikey/server.py:54` (module-level signing-key load), `:99-107` (`/healthz` liveness), `:116-135` (admin bearer, tenant guard), `:163`/`:226`/`:369`/`:423` (`rate_limit_dependency` on admin/oauth routes), `:303-358` (API-key exchange: prefix lookup `:309`, bcrypt verify `:312`, unknown-401 `:316`, revoked-401 `:318`), `:366-403` (admin key revoke: 404 `:381`, blocklist write `:394`, 503-on-failure `:401`), `jwt_issue.py:19-20` (`_issuer()`), `:23-85` (`issue_access_token`, `kid` header `:82`), `:88-99` (single-key JWKS), `jwt_verify.py:29-31` (access-token audience list — why the receiver needs its own license verify), `:60-91` (JWKS-or-PEM verify paths), `crypto_keys.py:56` (`load_or_create_signing_key`, ephemeral-key gate), `key_crypto.py:12-28` (generate/hash/verify — untouched), `db_schema.py:23-40` (`ApiKeyRow`, `revoked_at`), `db.py:62-70` (`init_db`/`create_all`), `ratelimit.py:22-25` (defaults), `:116-125` (per-bearer bucket key), `:192-198` (429 shape), `models.py:12-36` (`TokenClaims` — no license fields), `integrations/service_middleware.py:37-42` (bearer extraction), `:65-67`/`:85-88`/`:99-102` (`code`-key error idiom — deliberately not reused), `:143-148` (generic `unauthorized` 401 idiom — reused), `:161-211` (path-scope tables — unchanged), `digigraph/src/digigraph/corpus_routing.py:37-39` (header constants), `:137-210` (`resolve_corpus_override`, map-authoritative `:165-198`), `http_api/context.py:51-156` (`_digi_fields_from_request`, unconditional overwrites), `:159-164` (`_with_digi_request_context`), `http_api/chat_resolve.py:104-109` (body-or-header web-search resolution), `models.py:88-96`/`:226-232` (`enable_web_search` fields), `workflow.py:378` (graph-state injection), `tool_policy.py:81-103` (opt-in gating), `orchestration/web_search_tools.py:69` (`when` predicate), `digigraph/src/digigraph/server.py:648` (chat-path resolution), `apps/digichat/src/app/api/chat/route.ts:515-531` (upstream headers), `:592-594` (web-search header), `apps/digichat-cloudflare/src/paths.ts:6-19` (proxied paths — untouched).
- Greenfield confirmed: `X-Digi-License` has zero hits across the tree; no `digikey_licenses` table exists yet (slice 1 unimplemented) — this slice reads the contract slice 1 §4.1/§4.4 specifies.
- Consistency: the §3 table is exactly slice 1 §4.4's four states and slice 2 §8's response mapping, with the exact `error` spellings slice 2 §5.5 recognizes; evaluation order is slice 2 §8's parse → signature → allowlist → expiry with revoked-beats-expired.
- Internal links: all three bound specs linked by filename in the same directory.
- `python3 scripts/check_doc_links.py` run from the worktree (see task report).
