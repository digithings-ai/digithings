# digichat customer license enforcement for self-hosted containers (design)

- **Date:** 2026-09-27
- **Status:** Draft — awaiting owner review
- **Pilot customer:** DataTap (Azure container + own Azure Foundry agent, iframe embed)
- **Precedent:** [digichat embed: pluggable external backends](2026-07-02-digichat-embed-external-backend-design.md)
- **Human gate:** implementation touches `digikey/` JWT issuance (auth/crypto path) and adds a new inbound heartbeat route (external network surface). Per root `AGENTS.md` both require owner approval at implementation time. This spec itself is docs-only.

## Problem

The DataTap pilot runs digichat as a self-hosted container in their Azure subscription, fronting their own Azure Foundry agent via their existing relay (the `external-relay` backend from the precedent spec). Our marginal cost for their deployment is ~zero: Foundry inference spend is theirs, hosting is theirs. What needs licensing is the **software** — the right to run the digichat container — not metered usage.

Today an unlicensed container is indistinguishable from a licensed one: anyone with the image runs it indefinitely, with no binding to a customer, version, or term. We need a license mechanism that:

1. works fully offline (customer Azure environments may be network-restricted; availability coupling to our infrastructure was explicitly rejected),
2. expires on a commercial term (~90 days) so renewal ships alongside releases,
3. gives us optional deployment visibility without ever gating availability.

## Non-goals

- **No launch phone-home.** No network call is required for the container to start or serve. Availability coupling explicitly rejected.
- **No usage metering or billing.** No turn counting, no seat counting, no paywall logic. This spec licenses the software, not its use.
- **No changes to our Cloudflare workers' tenants config.** The `digichat-cloudflare` / `digithings-stack-cloudflare` routing and tenant registries are untouched, except for one optional new inbound heartbeat route (see §7, human-gated).
- **No new auth model for end users.** The embed path stays anonymous; licenses bind containers, not chat users.

## License claims

A license is a signed JWT (compact serialization, RS256 — same algorithm as digikey access tokens). Proposed claims:

| Claim | Meaning |
|---|---|
| `iss` | issuer, e.g. `https://digikey.digithings.ai` (distinct from access-token issuer recommended; see open decisions) |
| `aud` | `digichat-license` (distinct audience so a license can never be mistaken for an access token and vice versa) |
| `sub` | customer slug, e.g. `datatap` |
| `tenant_slug` | mirrors `sub` (keeps the digikey claim vocabulary) |
| `license_id` | stable id per issuance (`jti`-style), for correlating heartbeats and renewals |
| `hosts` | allowed embed-parent hostnames, e.g. `["datatapstream.com", "www.datatapstream.com"]` — advisory binding, matched against the container's configured hosts |
| `max_version` (optional) | highest digichat version this license covers (e.g. `"1.4.x"`); absent means unpinned |
| `iat` / `exp` | issuance and term end (~90 days) |
| `kind` | `"digichat-license"` — belt-and-braces discriminator on top of `aud` |
| `features` (optional) | licensed capability scopes, e.g. `["custom-backends", "custom-catalog", "hosted-extras"]`; absent means all licensed capabilities enabled. Lets a license be scoped down without minting new claim types per feature |

Note on repo convention: a license `exp` is a **validity bound**, not a rate limit, timeout, or tool-call budget. The repo's no-limits rule concerns operational throttling; a commercial term end is out of scope for that rule. This is stated explicitly to avoid confusion.

## License tiers

Unlicensed containers serve a **baseline subset**; a valid license unlocks the full config surface. The split is enforced at existing seams (startup config check + chat-route gates), verified against `apps/digichat/src` — file:line pins below.

| Capability | FREE (no license) | LICENSED | Enforcement seam |
|---|---|---|---|
| Serve container | yes, baseline config only | yes, full config | startup license check in `src/instrumentation.ts` `register()` + `src/lib/deploy-config/loader.ts` (fail-closed Zod precedent); unlicensed + non-baseline config → refuse to start |
| Backend `digigraph` | yes | yes | `src/lib/deploy-config/schema.ts:238` (`DigigraphBackendSchema`); free pins `backend.type` to `digigraph` |
| Custom backends (`foundry`, `openai-completions`, `openai-responses`, `anthropic`, `google-vertex`, `langgraph`, `ag-ui`, `a2a`) | no | yes (`custom-backends`) | same startup check; union at `schema.ts:391` |
| Models (`models.default` / `available`, `allowPicker`) | digithings defaults only | custom (`custom-backends` scope) | config check; projection folds legacy `modelPicker` into `allowPicker` (`schema.ts:204`, `route-client-config.ts:126`) |
| Tool catalog (`tools.catalog` custom entries) | empty/default only | any (`custom-catalog`) | already fail-closed on empty catalog: `deploy-config/force-tool.ts:23` (`catalogAllowsForceTool`), `:39` (`allowedForceTools`); license check only needs to gate the config, the runtime allowlist already denies the rest |
| digisearch corpus (`digisearchIndex` → `X-Digi-Corpus-Index`) | no | yes (`hosted-extras`) | `src/app/api/chat/route.ts:525`; header only set when configured, so blocking the config blocks the spend |
| Web search (`gate.webSearch`) | no | yes (`hosted-extras`) | `route.ts:441` — client must ask AND tenant must allow; free pins `gate.webSearch` to false |
| digivault prefix (`vaultPathPrefix` → `X-Digi-Vault-Prefix`) | no (to confirm — sketch silent, same corpus seam) | yes (`hosted-extras`) | `route.ts:528` |
| Operator MCP servers (`mcp.servers`) | none | configured | chat-route forwarding; note the foundry adapter already declares `mcp: false` (`backend-adapters.ts:163`), so this only bites on the digigraph path |
| BYO MCP (`mcp.allowUserServers` / `allowAddForm`) | allowed via explicit opt-in | allowed | already gated per-tenant, defaults deny (`schema.ts:465`, `embed-client-config.ts:120`); free tier sets `allowUserServers: true` in config — no new check. Session URLs merged only when allowed (`route.ts:565`) |
| UI surface (attachments, dictation, speech, reasoning/sources/branchPicker, skins) | defaults | full | config-level only, no new check (`FeaturesSchema` defaults at `schema.ts:195`; skin at `ChromeSchema`) |
| `showByok` / `llmAccess` modes | unchanged (operator choice) | unchanged | out of scope — existing SaaS/BYOK knobs, not license-gated |
| Gate modes (`turn_limited` / `ungated` / `trial_form`), `requiredPlanTier` / plan-proof | unchanged | unchanged | out of scope — Desk+ SaaS gating stays as-is (`route.ts:212`, `embed-tenants.ts:260`) |

Where the table says "config check", that is the one new verification step: after signature/expiry/hosts/version checks pass (or when no license is present), the startup path compares the loaded deployment against the licensed surface and fails closed on mismatch.

### Sketch-vs-code contradictions

1. **`external-relay` is retired — do not write it into the license.** The sketch names `foundry/external-relay` as the licensed backends, but both the YAML schema and the legacy embed-tenant parser reject `external-relay` (and `digivault`-as-backend): `embed-tenants.test.ts:305`. The live non-digigraph set is `foundry` plus seven newer types (`openai-completions`, `openai-responses`, `anthropic`, `google-vertex`, `langgraph`, `ag-ui`, `a2a` — `schema.ts:391`). The `custom-backends` scope must cover the whole union, not the two named in the sketch.
2. **Hosted extras only bite on the digigraph path.** The foundry adapter already declares `webSearch: false`, `mcp: false`, `corpus: false` (`backend-adapters.ts:146`); the DataTap agent wires its own azure_ai_search. Gating `digisearchIndex` / `gate.webSearch` therefore constrains digigraph-path tenants only — which is exactly the baseline being protected, so the split still works, but the spec should not promise spend-protection on non-digigraph paths where digichat never spent anything.
3. **BYO MCP defaults deny, so "allowed on baseline" needs an explicit opt-in.** `allowUserServers` / `allowAddForm` default false and the bridge passes them through only on strict `=== true` (`embed-client-config.ts:169`). The free tier does not get BYO servers by doing nothing; the baseline config must set `allowUserServers: true`. No code change, but the baseline config template must say so.
4. **digisearch cannot be separated from "the digigraph backend" as cleanly as the sketch implies** — it is not a separate backend but a catalog entry + corpus headers forwarded to digigraph (`force-tool.ts:9`, `route.ts:525`). The enforceable split is therefore "free digigraph configs carry no `digisearchIndex` and no `digisearch` catalog entry", enforced at the startup config check; the runtime allowlist already denies unlisted tools.

## Issuance flow

- **Who signs:** digikey, reusing the existing RSA keypair (`DIGIKEY_PRIVATE_KEY_PEM`). A small issuance path (CLI or admin endpoint) mints license JWTs with the claims above and a long TTL (~90 days). This is new code on the `digikey/` auth/crypto path, so the implementing change needs owner review per the minimal gate.
- **Key custody:** the private key never leaves our infrastructure. No secret values appear in this spec or in any customer-facing artifact.
- **Per-release renewal:** each digichat release ships with a fresh license file for each active customer (term = ~90 days from release). The customer drops the new license into their container config (env var or mounted file) as part of their normal image-update procedure. Renewal is therefore a side effect of staying current, not a separate ceremony.
- **Out-of-band delivery:** licenses travel by the existing commercial channel (email / shared vault), never baked into a public image layer. The `Dockerfile.digichat-cloudflare` header already forbids baking tenant tokens as build args (layer history); the same prohibition applies to license JWTs — runtime env only.

## Container verification

- **Key provisioning:** the container ships with (or is configured with) the digikey **public** key via a `DIGICHAT_LICENSE_PUBLIC_KEY_PEM`-style env var. Verification is purely local crypto against this provisioned key. JWKS fetch is **not** used: network verification is out because offline-safe startup is mandatory.
- **Hook point:** `src/instrumentation.ts` `register()` already calls `initDigichatConfigAtStartup()`, which fails closed on invalid config (`src/lib/deploy-config/loader.ts` is the Zod fail-closed precedent). License verification slots into the same startup path: parse → verify signature → check `exp`/`aud`/`iss` → check `hosts` overlap with configured hosts → check `max_version` against the baked `DIGICHAT_VERSION`.
- **Failure mode (recommended): refuse to serve, with a clear log line.** Missing/invalid/expired license → the process exits non-zero at startup (same fail-closed posture as bad `digichat.yaml`), so orchestrators surface it as a crash loop with an actionable message, not a silently degraded chat. A degraded-but-serving mode (banner, read-only) is the main alternative — see open decisions.
- **Clock-skew tolerance:** allow ~5 minutes of leeway on `iat`/`exp` checks. Container host clocks in customer Azure environments drift; a hard edge would turn skew into false outages.
- **Key rotation:** the public-key env supports a list (current + previous) so a digikey key rotation does not brick licensed containers before they pick up the new key. Rotation procedure ships with the implementation.

## Heartbeat (optional, fail-open, visibility only)

- **Shape:** `{license_id, customer, version, hosts_configured, started_at, seq}` posted on a slow cadence (e.g. hourly — cadence chosen for visibility, not enforcement). No usage counts, no message contents, no end-user identifiers.
- **Transport options:** (a) a new inbound route on the `digithings-stack-cloudflare` worker, or (b) a route on the `digichat-cloudflare` worker (which already proxies `/api/*` paths per `apps/digichat-cloudflare/src/paths.ts`). Either way this is a **new inbound network surface** and therefore requires owner approval at implementation time.
- **Grace semantics:** heartbeat is advisory. Send failures (network, DNS, our worker down) are logged and retried with backoff, and **never** affect serving. A container that never successfully heartbeats keeps running until its license `exp`. There is no grace-period state machine because there is nothing to grace: the heartbeat gates nothing.

## Threat model

What this stops:

- **Casual unlicensed use:** running the image without ever being a customer requires forging an RS256 signature, which requires the private key.
- **Term overrun:** an expired license fails verification; continued use requires a renewal (which requires the commercial relationship).
- **Cross-customer reuse:** `sub`/`hosts` binding means customer A's license does not cleanly authorize customer B's hostnames (enforced as a startup check, advisory strength — see below).
- **Replay across terms:** `license_id` + `exp` bound each token to its term; an old license cannot extend itself.

What this does **not** stop (accepted):

- **Determined image tampering:** a customer controls the container environment, so they can patch out the check. This is a speed bump plus a legal anchor, not DRM. Full prevention is impossible without a launch phone-home, which was rejected on availability grounds.
- **License sharing between cooperating parties:** `hosts` binding is advisory; two parties sharing hostnames or ignoring the mismatch log can share a license. Detection (via heartbeat `license_id` appearing from divergent sources) is visibility-only.
- **Clock rollback:** a customer can skew their host clock to stretch `exp`. The skew tolerance (§5) is small; large rollback breaks TLS elsewhere in their stack, which bounds the practical exposure.

Why launch-gating was rejected: a start-time or periodic network check couples customer availability to our infrastructure. Our outage would become their outage, in an environment (their Azure subscription, their Foundry spend) where we contribute zero runtime value. The commercial term is enforced by expiry, not by phone-home.

## Rollout for the DataTap pilot

1. Implement issuance (digikey side) + verification (digichat startup path) behind the heartbeat-behind-a-flag, on a task branch per repo routing.
2. Issue the first DataTap license (`sub: datatap`, hosts per their embed parents, 90-day term, unpinned version for the pilot).
3. DataTap adds two env values to their container config: the license JWT and the public key PEM. No image rebuild needed on their side beyond picking up the release that contains the check.
4. Migration from unlicensed containers: the first release containing the check ships with a **warn-only transition window** (invalid/missing license logs loudly but still serves), announced with an end date; the following release flips to fail-closed. This avoids bricking the pilot on upgrade day.
5. Heartbeat receiver (if approved) lands independently; containers with no configured heartbeat endpoint simply skip it.

## Open decisions for the owner

1. **Failure mode: refuse-to-start vs degraded-serve?** Spec recommends fail-closed (refuse to serve); degraded (serve with banner / read-only) is softer on the pilot but weaker as a license.
2. **Separate issuer/keypair for licenses vs reuse of the access-token key?** Reuse is simpler and grounded in existing code; a dedicated keypair isolates blast radius if either token class is compromised.
3. **`max_version` pinning: on for the pilot or leave unpinned?** Pinning ties renewal to upgrades (stronger commercial lever, more operational friction); unpinned is frictionless but lets a customer run one image past term end only until `exp` anyway.
4. **Heartbeat receiver: `digithings-stack-cloudflare` worker vs `digichat-cloudflare` worker?** Former centralizes customer telemetry; latter is closer to the container path. Either is a new inbound route needing owner approval.
5. **Warn-only transition window length** for the pilot migration (one release? fixed calendar date?).
6. **License delivery channel** (email vs shared vault) and who owns issuance operationally (owner-run CLI vs self-serve admin endpoint).

## Verification

- No code changed by this spec (docs-only).
- Internal links: precedent spec linked by filename in the same directory.
- `make doc-check` run to confirm internal links resolve (see task report).
