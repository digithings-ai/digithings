# digichat customer license as managed-deployment entitlement (design)

- **Date:** 2026-09-27
- **Status:** Draft — awaiting owner review
- **Pilot customer:** DataTap (Azure container + own Azure Foundry agent, iframe embed)
- **Precedent:** [digichat embed: pluggable external backends](2026-07-02-digichat-embed-external-backend-design.md)
- **Revision note:** this design supersedes commit `e90c05e4e`, which framed the license as a free-vs-licensed **feature tier** enforced at container startup. That commit stays in history; the model below replaces it. The owner's revised model: digichat software is never gated, and the license is a **managed-deployment entitlement** — it gates the licensed service relationship (support/updates, digithings-hosted services), not chat features.
- **Human gate:** implementation touches `digikey/` JWT issuance (auth/crypto path) and adds a new inbound heartbeat route (external network surface). Per root `AGENTS.md` both require owner approval at implementation time. This spec itself is docs-only.

## Problem

The DataTap pilot runs digichat as a self-hosted container in their Azure subscription, fronting their own Azure Foundry agent via their existing relay (the `foundry` backend from the precedent spec). Our marginal cost for their deployment is ~zero: Foundry inference spend is theirs, hosting is theirs. What the license records is the **managed-deployment relationship** — we installed and configured digichat specifically for them — not metered usage and not the right to run the software at all.

Today a managed deployment is indistinguishable from an anonymous one: a container running for a customer carries no signed statement of who it serves, which term it is covered by, or which of our hosted services it may call. We need a license mechanism that:

1. never gates the software: an unlicensed container serves every feature, and startup never refuses on a missing/invalid license,
2. expresses the commercial term (~90 days, renewed per release) as a signed, offline-verifiable status,
3. authenticates the deployment to our hosted services at our edge, where online validation is acceptable.

## Non-goals

- **No startup gating.** No network call is required for the container to start or serve, and no license state ever blocks serving. Availability coupling explicitly rejected.
- **No usage metering or billing.** No turn counting, no seat counting, no paywall logic. This spec licenses the service relationship, not use.
- **No feature tiers.** There is no free-vs-licensed config surface. Every deployment config option is available to every operator.
- **No changes to our Cloudflare workers' tenants config.** The `digichat-cloudflare` / `digithings-stack-cloudflare` routing and tenant registries are untouched, except for one optional new inbound heartbeat route (see §7, human-gated).
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

Note on repo convention: a license `exp` is a **validity bound**, not a rate limit, timeout, or tool-call budget. The repo's no-limits rule concerns operational throttling; a commercial term end is out of scope for that rule. This is stated explicitly to avoid confusion.

## Deployment entitlement (replaces the tier matrix)

There is no FREE vs LICENSED config surface. Every operator — licensed or not — can configure every backend, model list, tool catalog entry, MCP server, and UI knob. The license entitles the **service relationship**:

| Entitlement | Unlicensed container | Licensed container |
|---|---|---|
| Serve chat (all backends, models, tools, UI) | yes | yes |
| Support / updates entitlement (commercial record: who, which term, which version line) | no | yes (`sub`, `license_id`, `iat`/`exp`, `max_version`) |
| Call digithings-hosted services (digisearch corpus, hosted web search — §6) | no (our edge refuses) | yes, within `services` scope |

Enforcement lives at **our edge**, never in the container. The container's only job is to present the license when calling our services and to report its own status honestly (§5, §7).

## Issuance flow

- **Who signs:** digikey, reusing the existing RSA keypair (`DIGIKEY_PRIVATE_KEY_PEM`). A small issuance path (CLI or admin endpoint) mints license JWTs with the claims above and a long TTL (~90 days). This is new code on the `digikey/` auth/crypto path, so the implementing change needs owner review per the minimal gate.
- **Key custody:** the private key never leaves our infrastructure. No secret values appear in this spec or in any customer-facing artifact.
- **Per-release renewal:** each digichat release ships with a fresh license file for each active customer (term = ~90 days from release). The customer drops the new license into their container config (env var or mounted file) as part of their normal image-update procedure. Renewal is therefore a side effect of staying current, not a separate ceremony.
- **Out-of-band delivery:** licenses travel by the existing commercial channel (email / shared vault), never baked into a public image layer. The `Dockerfile.digichat-cloudflare` header already forbids baking tenant tokens as build args (layer history); the same prohibition applies to license JWTs — runtime env only.

## Container verification (status, not gate)

- **Key provisioning:** the container ships with (or is configured with) the digikey **public** key via a `DIGICHAT_LICENSE_PUBLIC_KEY_PEM`-style env var. Verification is purely local crypto against this provisioned key. JWKS fetch is **not** used: network verification is out because offline-safe startup is mandatory.
- **Hook point:** `src/instrumentation.ts` `register()` already calls `initDigichatConfigAtStartup()`. License verification slots into the same startup path — parse → verify signature → check `exp`/`aud`/`iss` → compare `hosts` against configured hosts → compare `max_version` against the baked `DIGICHAT_VERSION` — but its result is a **status**, surfaced in `GET /api/health` output, the startup log line, and the heartbeat (§7). It never exits non-zero and never degrades serving.
- **Failure mode (required): always serve.** Missing/invalid/expired license → log clearly (`license_status: unlicensed`, with reason: missing/invalid/expired/host-mismatch/version-pinned) and keep serving every feature. There is no warn-only transition window because there is no fail-closed state to transition into.
- **Clock-skew tolerance:** allow ~5 minutes of leeway on `iat`/`exp` checks. Container host clocks in customer Azure environments drift; a hard edge would turn skew into false unlicensed status.
- **Key rotation:** the public-key env supports a list (current + previous) so a digikey key rotation does not flip licensed containers to unlicensed before they pick up the new key. Rotation procedure ships with the implementation.

## Hosted-service auth (the hard gate, at our edge)

Only some self-hosted call paths reach our infrastructure. Verified against `apps/digichat/src`:

- **Reaches our services — digigraph path only.** `src/app/api/chat/route.ts:493` resolves upstream auth and `route.ts:510-511` builds the digigraph client for the operator-configured digigraph URL. The corpus/vault headers (`X-Digi-Corpus-Index`, `X-Digi-Vault-Prefix` at `route.ts:523-531`) are only written when `adapter.capabilities.corpus` is true — and only the digigraph adapter declares `corpus: true` (`src/lib/backend-adapters.ts:132-143`); foundry declares `corpus: false` (`:148-165`). The `X-Digi-Enable-Web-Search` header (`route.ts:592-594`) is likewise written only on the digigraph path: the AI-SDK branch returns earlier (`route.ts:460-475`).
- **Stays on the operator's backends — everything else.** AI-SDK backends (`openai-completions`, `openai-responses`, `anthropic`, `google-vertex`) call the operator-configured `baseUrl` with the operator's key, and their web-search path uses the **provider's own** built-in search tool at the provider's pricing (`src/lib/adapters/ai-sdk/providers.ts:89-103`). The foundry path uses the customer's Azure identity; its agent wires its own search (DataTap: their own azure_ai_search). None of these touch our infrastructure.

Design:

- **Token transport:** when the container calls digigraph, it forwards its license JWT in an `X-Digi-License` header alongside the existing `X-Digichat-Tenant` / `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` / `X-Digi-Enable-Web-Search` headers. Containers with no license configured omit the header. The header value is the license only — never key material, which the container does not hold.
- **Validation point:** our digigraph edge (or the hosted search/corpus service fronting it). It validates the license signature against the digikey public key, checks `exp`, `sub`/`tenant_slug`, and the `services` scope against the requested hosted capability (corpus lookup, hosted web search). Online verification against digikey (JWKS or verify endpoint) is fine here — this is our infrastructure, so there is no customer-availability coupling.
- **Which hosted calls require a license vs stay open:** any call that spends our resources or reads our hosted data requires a valid license with the matching `services` scope — corpus retrieval against our digisearch index, hosted web search executed on our side. Plain inference through a customer-pointed digigraph URL with no hosted-service headers stays open (it spends the operator's compute, not ours). The exact header-to-scope map ships with the implementation.
- **Failure mode at our edge:** refuse the hosted-service portion only (error naming the missing scope), never the whole chat request where separable. A foundry-path container calling nothing of ours is unaffected by definition.

## Heartbeat (optional, fail-open, visibility only)

- **Shape:** `{license_id, customer, license_status, version, hosts_configured, started_at, seq}` posted on a slow cadence (e.g. hourly — cadence chosen for visibility, not enforcement). No usage counts, no message contents, no end-user identifiers. `license_status` carries the local verification outcome, so an expired-but-serving deployment is visible rather than silent.
- **Transport options:** (a) a new inbound route on the `digithings-stack-cloudflare` worker, or (b) a route on the `digichat-cloudflare` worker (which already proxies `/api/*` paths per `apps/digichat-cloudflare/src/paths.ts`). Either way this is a **new inbound network surface** and therefore requires owner approval at implementation time.
- **Grace semantics:** heartbeat is advisory. Send failures (network, DNS, our worker down) are logged and retried with backoff, and **never** affect serving. A container that never successfully heartbeats keeps running indefinitely. There is no grace-period state machine because there is nothing to grace: the heartbeat gates nothing.

## Threat model

What this stops:

- **Anonymous consumption of our hosted services:** calling our digisearch corpus or hosted web search without a license fails at our edge, which validates signatures with our own keys — not patchable from the customer environment.
- **Term overrun on the service relationship:** an expired license fails edge validation; continued hosted-service use requires a renewal (which requires the commercial relationship).
- **Cross-customer reuse of hosted services:** `sub`/`hosts` binding means customer A's license does not authorize customer B's deployment at our edge.

What this does **not** stop (accepted):

- **Unlicensed operation of the software:** fully possible by design. Anyone with the image runs every feature indefinitely against their own backends and keys. This is the open-core model, not a leak.
- **Determined edge-spoofing from a tampered container:** a customer controls the container environment, so they can strip the `X-Digi-License` header or present another deployment's token — but our edge still validates the signature and scope, so stripping only downgrades them to unlicensed (no hosted services), and reuse is attributable via `license_id` in heartbeat and edge logs.
- **Clock rollback:** a customer can skew their host clock to stretch local `exp` status display. Edge validation uses our clocks, which bounds the practical exposure to cosmetic status only.

Why container launch-gating was rejected twice over: a start-time or periodic network check couples customer availability to our infrastructure, in an environment (their Azure subscription, their Foundry spend) where we contribute zero runtime value — and under the revised model there is nothing in the software to protect, only the service relationship, which is enforceable at our edge without touching their availability.

## Rollout for the DataTap pilot

1. Implement issuance (digikey side) + status verification (digichat startup path, serve-always) + heartbeat-behind-a-flag, on a task branch per repo routing.
2. Implement license validation at our digigraph edge for corpus and hosted web-search calls (header-to-scope map ships with the implementation).
3. Issue the first DataTap license (`sub: datatap`, hosts per their embed parents, 90-day term, unpinned version for the pilot, `services` covering whatever hosted services they consume — initially likely none, since their foundry agent wires its own search).
4. DataTap adds two env values to their container config: the license JWT and the public key PEM. No image rebuild needed on their side beyond picking up the release that contains the check. **Their container keeps working regardless — before, during, and after licensing. An expired or missing license changes their status display and their access to our hosted services, never their chat.**
5. Heartbeat receiver (if approved) lands independently; containers with no configured heartbeat endpoint simply skip it.

## Open decisions for the owner

1. **Separate issuer/keypair for licenses vs reuse of the access-token key?** Reuse is simpler and grounded in existing code; a dedicated keypair isolates blast radius if either token class is compromised.
2. **`max_version` pinning: on for the pilot or leave unpinned?** Pinning ties renewal to upgrades (stronger commercial lever, more operational friction); unpinned is frictionless and `exp` still ends the term.
3. **Heartbeat receiver: `digithings-stack-cloudflare` worker vs `digichat-cloudflare` worker?** Former centralizes customer telemetry; latter is closer to the container path. Either is a new inbound route needing owner approval.
4. **Header-to-scope map for the edge gate:** exactly which digigraph-upstream headers require which `services` scope (corpus index, vault prefix, hosted web search), and whether plain inference through an operator-pointed digigraph URL with no hosted headers stays fully open.
5. **Token transport shape:** raw license JWT in `X-Digi-License` vs a derived short-lived token minted at startup from the license (smaller headers, but adds a minting step).
6. **License delivery channel** (email vs shared vault) and who owns issuance operationally (owner-run CLI vs self-serve admin endpoint).

Mooted by the revision (closed, no decision needed): refuse-to-start vs degraded-serve (now always-serve); warn-only transition window (no fail-closed state to transition into); `features` claim scopes (no feature tiers exist).

## Verification

- No code changed by this spec (docs-only).
- Release-config claim verified: `infra/digichat-release/config/digichat.yaml.example` (models commented out `:78-83`, operator-supplied digigraph credential `:85`, empty catalogs, `webSearch: false`), `ModelsSchema` defaults (`apps/digichat/src/lib/deploy-config/schema.ts:216-226`), runtime-only credential reads (`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:32-38`), Dockerfile no-bake rule (`Dockerfile.digichat-cloudflare:4-5`).
- Hosted-service path split verified: digigraph-path headers (`apps/digichat/src/app/api/chat/route.ts:493-531,592-594`), capability declarations (`apps/digichat/src/lib/backend-adapters.ts:132-165`), provider-priced search (`apps/digichat/src/lib/adapters/ai-sdk/providers.ts:89-103`).
- Internal links: precedent spec linked by filename in the same directory.
- `make doc-check` run to confirm internal links resolve (see task report).
