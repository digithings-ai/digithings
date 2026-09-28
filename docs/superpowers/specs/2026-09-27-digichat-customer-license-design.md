# digichat customer license as managed-deployment entitlement (design)

- **Date:** 2026-09-27 (rev 2: 2026-09-28, owner-approved revocation model)
- **Status:** Draft — revocation model owner-approved; awaiting implementation review
- **Pilot customer:** DataTap (Azure container + own Azure Foundry agent, iframe embed)
- **Precedent:** [digichat embed: pluggable external backends](2026-07-02-digichat-embed-external-backend-design.md)
- **Revision note (rev 1):** this design supersedes commit `e90c05e4e`, which framed the license as a free-vs-licensed **feature tier** enforced at container startup. That commit stays in history; the model below replaces it. The owner's revised model: digichat software is never feature-gated, and the license is a **managed-deployment entitlement** — it gates the licensed service relationship (support/updates, digithings-hosted services), not chat features.
- **Revision note (rev 2, owner-confirmed 2026-09-28):** the owner approved heartbeat revocation. The container holds a customer key in its env; the key sits on an allowlist on our side (the digikey key registry). The owner revokes by removing the key, and the customer container must stop serving chat. The container presents the key to our side every 24 hours (owner-fixed). An explicit revoked/unknown answer stops product traffic at that heartbeat (within ~24h of revocation); network errors and our outages fail open with retry, bounded by the license's own expiry. Sections below marked [rev 2] implement this; the always-serve language of rev 1 is superseded wherever it conflicts.
- **Human gate:** implementation touches `digikey/` JWT issuance (auth/crypto path) and adds a heartbeat check against digikey (auth-adjacent surface). Per root `AGENTS.md` both require owner approval at implementation time. This spec itself is docs-only. (rev 1 note about a new inbound worker heartbeat route is withdrawn — rev 2 reuses digikey, see §7.)

## Problem

The DataTap pilot runs digichat as a self-hosted container in their Azure subscription, fronting their own Azure Foundry agent via their existing relay (the `foundry` backend from the precedent spec). Our marginal cost for their deployment is ~zero: Foundry inference spend is theirs, hosting is theirs. What the license records is the **managed-deployment relationship** — we installed and configured digichat specifically for them — not metered usage and not the right to run the software at all.

Today a managed deployment is indistinguishable from an anonymous one: a container running for a customer carries no signed statement of who it serves, which term it is covered by, or which of our hosted services it may call. We need a license mechanism that:

1. never feature-gates the software: every deployment can configure every backend, model list, tool, and UI knob; no licensed capabilities exist in the code,
2. expresses the commercial term (~90 days, renewed per release) as a signed, offline-verifiable status,
3. authenticates the deployment to our hosted services at our edge, where online validation is acceptable,
4. [rev 2] revokes promptly when online: the container presents its customer key to our side every 24 hours; an explicit revoked/unknown answer stops product traffic at that heartbeat (within ~24h of revocation), while network errors and our outages fail open with retry, bounded by the license's own expiry.

## Non-goals

- **No feature tiers.** There is no free-vs-licensed config surface. Every deployment config option is available to every operator.
- **No usage metering or billing.** No turn counting, no seat counting, no paywall logic. This spec licenses the service relationship, not use.
- **[rev 2] No startup network dependency.** No network call is required for the container to start or serve a first request: startup validation is local crypto plus a best-effort remote check that never blocks. (Supersedes the rev-1 "no license state ever blocks serving" rule: an explicit-revoke answer learned via heartbeat does stop product traffic — see §7.)
- **No changes to our Cloudflare workers' tenants config.** The `digichat-cloudflare` / `digithings-stack-cloudflare` routing and tenant registries are untouched; rev 2 needs no new inbound worker route (see §7, heartbeat reuses digikey).
- **No new auth model for end users.** The embed path stays anonymous; licenses bind containers, not chat users.

## Ungated software (verified against the release)

The release ships WITHOUT default models plugged in and WITHOUT our API keys. The operator supplies their own models, keys, backends, and tools. Verified:

- `infra/digichat-release/config/digichat.yaml.example:78-83` — the `models:` block is entirely commented out; no default model ships. `ModelsSchema` (`apps/digichat/src/lib/deploy-config/schema.ts:216`) makes `default` optional and `available` default to `[]`.
- `digichat.yaml.example:85-92` — the default backend is `type: digigraph` with no URL or credential in the file; the comment states it needs the operator's `DIGIKEY_BFF_TOKEN` plus a digigraph URL. The foundry alternative carries `YOUR_PROJECT` / `YOUR_AGENT` placeholders, not values.
- AI-SDK backends never take key material in config: the config only names an env var (`apiKeyEnv`), read at runtime by `readBackendApiKey` (`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:32`), with the `DIGICHAT_BACKEND_` prefix enforced by the schema so a config cannot point at `AUTH_SECRET`.
- `tools.catalog` and `mcp.servers` default to empty (`digichat.yaml.example:95-113`); `gate.webSearch` defaults to false (`:124`).
- `Dockerfile.digichat-cloudflare:4-5` already forbids baking tenant tokens as build args (layer history); only the version string and asset prefix are baked (`:38-44`).
- **No gap found:** nothing in the image or the release config bakes in a default model or a usable key. If a future release adds either, that is a bug against this section, not a license event.

## License claims

A license is a signed JWT (compact serialization, RS256 — same algorithm as digikey access tokens). Proposed claims:

| Claim | Meaning |
|---|---|
| `iss` | issuer, e.g. `https://digikey.digithings.ai` (distinct from access-token issuer recommended; see open decisions) |
| `aud` | `digichat-license` (distinct audience so a license can never be mistaken for an access token and vice versa) |
| `sub` | customer slug, e.g. `datatap` |
| `tenant_slug` | mirrors `sub` (keeps the digikey claim vocabulary) |
| `license_id` | stable id per issuance (`jti`-style), for correlating heartbeats and hosted-service calls |
| `hosts` | embed-parent hostnames this deployment was configured for, e.g. `["datatapstream.com", "www.datatapstream.com"]` — descriptive binding, matched against the container's configured hosts for status display |
| `services` (optional) | hosted-service scopes this deployment may call, e.g. `["digisearch-corpus", "hosted-web-search"]`; absent means the deployment is entitled to the hosted services covered by its commercial term. Scopes name our services, never chat features |
| `max_version` (optional) | highest digichat version this license covers (e.g. `"1.4.x"`); absent means unpinned |
| `iat` / `exp` | issuance and term end (~90 days) |
| `kind` | `"digichat-license"` — belt-and-braces discriminator on top of `aud` |

The earlier `features` claim (licensed capability scopes such as `custom-backends`) is dropped: there are no licensed capabilities in the software, so there is nothing for it to scope. `services` replaces it and names only digithings-hosted services.

Note on repo convention: a license `exp` and the 24-hour heartbeat cadence are **validity / validity-check cadences**, not rate limits, timeouts, or tool-call budgets. The repo's no-limits rule concerns operational throttling; a commercial term end and a revocation-check interval are out of scope for that rule. This is stated explicitly to avoid confusion.

## Deployment entitlement (replaces the tier matrix)

There is no FREE vs LICENSED config surface. Every operator — licensed or not — can configure every backend, model list, tool catalog entry, MCP server, and UI knob. The license entitles the **service relationship**:

| Entitlement | Unlicensed container | Licensed container |
|---|---|---|
| Serve chat (all backends, models, tools, UI) | yes | yes |
| Support / updates entitlement (commercial record: who, which term, which version line) | no | yes (`sub`, `license_id`, `iat`/`exp`, `max_version`) |
| Call digithings-hosted services (digisearch corpus, hosted web search — §6) | no (our edge refuses) | yes, within `services` scope |

Enforcement lives at **our edge** (hosted services) and at the **container's heartbeat** (product traffic after explicit revoke), never in feature config. The container's jobs are to present its key every 24 hours (§7), to report its own status honestly (§5, §7), and to stop serving product traffic once our side has explicitly revoked it.

[rev 2] Entitlement row added to the table:

| Entitlement | Licensed, key valid | Licensed, key revoked (learned at heartbeat) | Unlicensed container |
|---|---|---|---|
| Serve chat (all backends, models, tools, UI) | yes | **no** — product traffic refused until re-licensed | yes |
| Support / updates entitlement (commercial record: who, which term, which version line) | yes (`sub`, `license_id`, `iat`/`exp`, `max_version`) | lapsed | no |
| Call digithings-hosted services (digisearch corpus, hosted web search — §6) | yes, within `services` scope | no (our edge refuses) | no (our edge refuses) |

An unlicensed container (no key ever issued) still serves every feature indefinitely — the open-core model is unchanged. Revocation only ever takes away what was explicitly granted.

## Issuance flow

- **Who signs:** digikey, reusing the existing RSA keypair (`DIGIKEY_PRIVATE_KEY_PEM`). A small issuance path (CLI or admin endpoint) mints license JWTs with the claims above and a long TTL (~90 days). This is new code on the `digikey/` auth/crypto path, so the implementing change needs owner review per the minimal gate.
- **Key custody:** the private key never leaves our infrastructure. No secret values appear in this spec or in any customer-facing artifact.
- **Per-release renewal:** each digichat release ships with a fresh license file for each active customer (term = ~90 days from release). The customer drops the new license into their container config (env var or mounted file) as part of their normal image-update procedure. Renewal is therefore a side effect of staying current, not a separate ceremony.
- **Out-of-band delivery:** licenses travel by the existing commercial channel (email / shared vault), never baked into a public image layer. The `Dockerfile.digichat-cloudflare` header already forbids baking tenant tokens as build args (layer history); the same prohibition applies to license JWTs — runtime env only.

## Container verification (status + revoke latch, not a startup gate)

- **Key provisioning:** the customer container carries two env values: the license JWT and a customer API key (the heartbeat credential, allowlisted in the digikey registry). The container also carries the digikey **public** key via a `DIGICHAT_LICENSE_PUBLIC_KEY_PEM`-style env var. Local verification is purely local crypto against this provisioned key. JWKS fetch is **not** used for startup: network verification is out because offline-safe startup is mandatory.
- **Hook point:** `src/instrumentation.ts` `register()` currently calls only `initDigichatConfigAtStartup()` (`apps/digichat/src/instrumentation.ts:1-11`), then migrates. License verification slots into the same startup path — parse → verify signature → check `exp`/`aud`/`iss` → compare `hosts` against configured hosts → compare `max_version` against the baked `DIGICHAT_VERSION` — plus one best-effort remote key check that **never blocks startup** (its result only seeds the heartbeat state below).
- **Startup behavior [rev 2, settled]:**
  - First boot and restart behave the same: attempt validation at startup; serve on valid signature + unexpired `exp` even if our side is unreachable (fail-open startup — an explicit-revoke state is only learnable via heartbeat, and a fresh container has learned nothing).
  - A latched revoked state does not survive a restart by itself: on boot the container re-validates locally and resumes serving until the next heartbeat teaches it otherwise. Restart-to-evade therefore buys at most one heartbeat interval (~24h), and the license `exp` still bounds everything. Persisting the latch to disk is an implementation option, not a requirement.
- **Failure mode [rev 2, settled]: fail-open on errors, fail-closed on explicit deny.** Missing/invalid/expired license locally → log clearly (`license_status: unlicensed`, with reason) and keep serving every feature. Heartbeat network errors, timeouts, or our outage → keep serving, retry with backoff. Explicit revoked/unknown answer from our side → latch revoked state and stop serving product traffic (see §7). There is no warn-only transition window: the only fail-closed state is a learned explicit revoke.
- **Clock-skew tolerance:** allow ~5 minutes of leeway on `iat`/`exp` checks. Container host clocks in customer Azure environments drift; a hard edge would turn skew into false unlicensed status.
- **Key rotation:** the public-key env supports a list (current + previous) so a digikey key rotation does not flip licensed containers to unlicensed before they pick up the new key. Rotation procedure ships with the implementation.

## Hosted-service auth (the hard gate, at our edge)

Only some self-hosted call paths reach our infrastructure. Verified against `apps/digichat/src`:

- **Reaches our services — digigraph path only.** `src/app/api/chat/route.ts:493` resolves upstream auth and `route.ts:510-511` builds the digigraph client for the operator-configured digigraph URL. The corpus/vault headers (`X-Digi-Corpus-Index`, `X-Digi-Vault-Prefix` at `route.ts:523-531`) are only written when `adapter.capabilities.corpus` is true — and only the digigraph adapter declares `corpus: true` (`src/lib/backend-adapters.ts:132-143`); foundry declares `corpus: false` (`:148-165`). The `X-Digi-Enable-Web-Search` header (`route.ts:592-594`) is likewise written only on the digigraph path: the AI-SDK branch returns earlier (`route.ts:460-475`).
- **Stays on the operator's backends — everything else.** AI-SDK backends (`openai-completions`, `openai-responses`, `anthropic`, `google-vertex`) call the operator-configured `baseUrl` with the operator's key, and their web-search path uses the **provider's own** built-in search tool at the provider's pricing (`src/lib/adapters/ai-sdk/providers.ts:89-103`). The foundry path uses the customer's Azure identity; its agent wires its own search (DataTap: their own azure_ai_search). None of these touch our infrastructure.

Design:

- **Token transport:** when the container calls digigraph, it forwards its license JWT in an `X-Digi-License` header alongside the existing `X-Digichat-Tenant` / `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` / `X-Digi-Enable-Web-Search` headers. Containers with no license configured omit the header. The header value is the license JWT only — never the heartbeat key, which is presented solely to digikey at heartbeat time.
- **Validation point:** our digigraph edge (or the hosted search/corpus service fronting it). It validates the license signature against the digikey public key, checks `exp`, `sub`/`tenant_slug`, and the `services` scope against the requested hosted capability (corpus lookup, hosted web search). Online verification against digikey (JWKS or verify endpoint) is fine here — this is our infrastructure, so there is no customer-availability coupling.
- **Which hosted calls require a license vs stay open:** any call that spends our resources or reads our hosted data requires a valid license with the matching `services` scope — corpus retrieval against our digisearch index, hosted web search executed on our side. Plain inference through a customer-pointed digigraph URL with no hosted-service headers stays open (it spends the operator's compute, not ours). The exact header-to-scope map ships with the implementation.
- **Failure mode at our edge:** refuse the hosted-service portion only (error naming the missing scope), never the whole chat request where separable. A foundry-path container calling nothing of ours is unaffected by definition.

## Heartbeat (revocation check, 24h cadence — [rev 2] replaces the advisory-only design)

- **What it is:** every 24 hours (owner-fixed interval) the container presents its customer key to our side. The 24h cadence is a validity-check cadence, not a throttle: it sets the worst-case revocation latency (~24h from owner revoke to container stop-serving), nothing else.
- **Receiver (grounded recommendation): reuse digikey, no new worker route.** The heartbeat can be an authenticated check against digikey itself — e.g. a token-exchange attempt or a lightweight key-verify endpoint. digikey already stores only bcrypt hashes (`ApiKeyRow.key_hash`, `digikey/src/digikey/db_schema.py:27`; `hash_secret` in `digikey/src/digikey/key_crypto.py:21`), verifies presented keys with `verify_secret` (`digikey/src/digikey/server.py:309-314`), and already distinguishes the two answers the container needs: unknown key → `401 "invalid api_key"` (`server.py:315-316`), revoked key → `401 "key revoked"` (`server.py:317-318`). Revocation itself is the existing admin endpoint `POST /v1/admin/keys/{key_id}/revoke` (`server.py:366-403`), which sets `revoked_at` and blocklists live jtis — so revoking needs no redeploy and no new service. The rev-1 open question of `digithings-stack-cloudflare` vs `digichat-cloudflare` receiver placement is closed by removing the need for a new inbound worker route. (Adding a verify endpoint, or reusing exchange, is still new `digikey/` surface and stays human-gated at implementation time.)
- **Shape:** `{license_id, customer, license_status, version, hosts_configured, started_at, seq}` alongside the key presentation. No usage counts, no message contents, no end-user identifiers. `license_status` carries the local verification outcome, so an expired-but-serving deployment is visible rather than silent.
- **Response handling [rev 2, settled]:**
  - Explicit revoked/unknown (e.g. HTTP 401 with `key revoked` / `invalid api_key`) → latch revoked state and **stop serving product traffic promptly at that heartbeat** (see stop-serving mechanics below). Worst case ~24h after the owner revokes.
  - Network errors, timeouts, our outage (5xx, DNS, connection refused) → **keep serving**, retry with backoff, stay serving. There is deliberately no error-grace timer to tune: the error-grace is bounded by the license's own `exp` (see expiry backstop).
- **Expiry backstop:** the license JWT keeps its ~90-day `exp`. Even if the operator firewalls our endpoints so heartbeats can never succeed, the container serves at most until `exp` — revocation is fast when online, eventual when hostile. No grounded reason was found to change the ~90d term: it matches the per-release renewal rhythm (a fresh license ships per release) and bounds hostile error-grace to one commercial term.
- **Stop-serving mechanics (recommended):** refuse product traffic at the entry points with HTTP 503 + a `license_revoked` error code — `POST /api/chat` (which already gates on `requireDigiChatAuth`, `apps/digichat/src/app/api/chat/route.ts:89-90`) and the embed routes (`/api/embed/*`, `/api/plan-proof`, all proxied per `apps/digichat-cloudflare/src/paths.ts:10-16`). Surface the state truthfully: add a `license_status` field to `GET /api/health` output alongside the existing `checks` map, without changing the `ok` computation — `GET /api/health` already returns 503 when downstreams fail (`apps/digichat/src/app/api/health/route.ts:24-77`), so a 503 product-traffic refusal is consistent with what orchestrators already expect. Liveness semantics stay intact: no probe may report healthy product traffic while revoked, and a license refusal must not corrupt whatever pure liveness signal the orchestrator uses for restart decisions (the stack convention is an auth-exempt always-ok `GET /healthz` with no downstream checks — root `AGENTS.md` § Liveness vs status; digichat currently exposes only `GET /api/health`, so if the implementation folds license state into that route, keep a license-independent liveness signal available and document which endpoint the orchestrator should probe).

## Threat model

What this stops:

- **Anonymous consumption of our hosted services:** calling our digisearch corpus or hosted web search without a license fails at our edge, which validates signatures with our own keys — not patchable from the customer environment.
- **Term overrun on the service relationship:** an expired license fails edge validation; continued hosted-service use requires a renewal (which requires the commercial relationship).
- **Cross-customer reuse of hosted services:** `sub`/`hosts` binding means customer A's license does not authorize customer B's deployment at our edge.

What this does **not** stop (accepted):

- **Unlicensed operation of the software:** fully possible by design — a container that was never issued a key serves every feature indefinitely against its own backends and keys. This is the open-core model, not a leak. Revocation only bites deployments that were provisioned and then revoked.
- **Determined edge-spoofing from a tampered container:** a customer controls the container environment, so they can strip headers or present another deployment's token — but our edge still validates the signature and scope, so stripping only downgrades them to unlicensed (no hosted services), and reuse is attributable via `license_id` in heartbeat and edge logs.
- **Clock rollback:** a customer can skew their host clock to stretch local `exp` status display. Edge validation uses our clocks, which bounds the practical exposure to cosmetic status only.
- **Hostile firewalling of our endpoints:** an operator who blocks all heartbeat traffic keeps serving until the license `exp` (~90 days). Accepted: revocation is fast when online, eventual when hostile, and the backstop is the term they already paid for.

Why container launch-gating was rejected (rev 1) and what replaced it (rev 2): a start-time network check couples customer availability to our infrastructure, in an environment (their Azure subscription, their Foundry spend) where we contribute zero runtime value. rev 2 keeps that insight — startup never blocks on network — and moves enforcement to the heartbeat: explicit deny fails closed, errors fail open. There is still nothing in the software to protect (no feature tiers); what the heartbeat protects is the service relationship, with at most ~24h of overrun when online.

## Rollout for the DataTap pilot

1. Implement issuance (digikey side: license JWT minting + customer API key in the existing registry) + startup verification (digichat startup path, fail-open) + 24h heartbeat with revoke latch and product-traffic refusal, on a task branch per repo routing.
2. Implement license validation at our digigraph edge for corpus and hosted web-search calls (header-to-scope map ships with the implementation).
3. Issue the first DataTap license (`sub: datatap`, hosts per their embed parents, 90-day term, unpinned version for the pilot, `services` covering whatever hosted services they consume — initially likely none, since their foundry agent wires its own search) plus their heartbeat key (created via the existing `POST /v1/admin/keys` issuance, stored bcrypt-hashed like every other key).
4. DataTap adds three env values to their container config: the license JWT, the heartbeat key, and the public key PEM. No image rebuild needed on their side beyond picking up the release that contains the check.
5. Revocation drill (owner-run, before or during the pilot): revoke the pilot key via `POST /v1/admin/keys/{key_id}/revoke`, confirm the container stops serving product traffic at the next heartbeat and reports the state truthfully in health output, then re-issue. **Allowlist ops:** add/remove key flows run by the owner against the digikey registry (existing admin endpoints) — revocation needs no redeploy on either side by design. Prefer the registry over worker env precisely so that removing a key is a single admin call, not a release.

## Open decisions for the owner

1. **Separate issuer/keypair for licenses vs reuse of the access-token key?** Reuse is simpler and grounded in existing code; a dedicated keypair isolates blast radius if either token class is compromised.
2. **`max_version` pinning: on for the pilot or leave unpinned?** Pinning ties renewal to upgrades (stronger commercial lever, more operational friction); unpinned is frictionless and `exp` still ends the term.
3. **Header-to-scope map for the edge gate:** exactly which digigraph-upstream headers require which `services` scope (corpus index, vault prefix, hosted web search), and whether plain inference through an operator-pointed digigraph URL with no hosted headers stays fully open.
4. **Heartbeat credential transport shape:** present the customer API key via token-exchange attempt vs a dedicated lightweight verify endpoint on digikey. Exchange reuses code paths verbatim but mints a short-lived JWT every 24h per deployment (harmless); a verify endpoint is smaller but new surface.
5. **License delivery channel** (email vs shared vault) and who owns issuance operationally (owner-run CLI vs self-serve admin endpoint).

Settled by rev 2 (closed, no decision needed): failure mode (fail-open on errors, fail-closed on explicit deny); heartbeat interval (24h, owner-fixed); heartbeat receiver placement (reuse digikey — no new worker route); startup behavior (validate attempt, serve on valid signature+expiry even if unreachable; revoke state learnable only via heartbeat).

Mooted by rev 1 (closed, no decision needed): refuse-to-start vs degraded-serve as a startup question (startup never blocks; enforcement moved to heartbeat); warn-only transition window (the only fail-closed state is a learned explicit revoke); `features` claim scopes (no feature tiers exist).

## Verification

- No code changed by this spec (docs-only).
- Release-config claim verified: `infra/digichat-release/config/digichat.yaml.example` (models commented out `:78-83`, operator-supplied digigraph credential `:85`, empty catalogs, `webSearch: false`), `ModelsSchema` defaults (`apps/digichat/src/lib/deploy-config/schema.ts:216-226`), runtime-only credential reads (`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:32-38`), Dockerfile no-bake rule (`Dockerfile.digichat-cloudflare:4-5`).
- Hosted-service path split verified: digigraph-path headers (`apps/digichat/src/app/api/chat/route.ts:493-531,592-594`), capability declarations (`apps/digichat/src/lib/backend-adapters.ts:132-165`), provider-priced search (`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:89-103`).
- rev-2 grounding verified: digikey registry fit — bcrypt-only storage (`digikey/src/digikey/db_schema.py:27`, `digikey/src/digikey/key_crypto.py:21-26`), presented-key verification with distinct unknown vs revoked answers (`digikey/src/digikey/server.py:309-318`), existing revoke endpoint setting `revoked_at` + blocklisting live jtis (`server.py:366-403`); startup hook — `register()` calls only `initDigichatConfigAtStartup()` (`apps/digichat/src/instrumentation.ts:1-11`), license check slots into the same path; health surface — public `GET /api/health` returns `{ok, checks, version}` with 200/503 (`apps/digichat/src/app/api/health/route.ts:24-77`), additive `license_status` field recommended; stop-serving seam — `POST /api/chat` gates on `requireDigiChatAuth` (`route.ts:89-90`), embed routes proxied (`apps/digichat-cloudflare/src/paths.ts:10-16`); no `/healthz` route exists in digichat — liveness-vs-status constraint documented as a requirement on the implementation, not an existing endpoint.
- Internal links: precedent spec linked by filename in the same directory.
- `make doc-check` run to confirm internal links resolve (see task report).
