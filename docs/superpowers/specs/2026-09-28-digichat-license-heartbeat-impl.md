# digichat container license verification + 24h heartbeat (implementation spec, slice 2)

- **Date:** 2026-09-28
- **Status:** Implementation spec — authorizes one implementing task PR; runtime changes land through that PR
- **Revision note (2026-09-28):** five owner decisions recorded (§1.2) — expiry → refuse (`503 license_expired`), add `GET /healthz`, refusal scope chat + plan-proof only, env names confirmed, canonical hosts source = embed tenant host keys. §12 now leaves only question 4 open, reframed as a pre-rotation verification check rather than a blocker.
- **Binds to:** [digichat customer license design](2026-09-27-digichat-customer-license-design.md) (rev 5, eight owner decisions plus the rev-5 expiry-refusal resolution — this spec implements the container half: § Container verification, § Heartbeat, § Stop-serving mechanics) and [digichat license-mint CLI (slice 1)](2026-09-28-digichat-license-mint-impl.md) (the `digikey_licenses` allowlist + its §4.4 four-state read contract, which the heartbeat receiver reads in slice 3)
- **Scope:** local startup verification, the revoke latch state machine, the heartbeat **sender**, the `503 license_revoked` refusal on product traffic, and health surfacing. Nothing else.
- **Slice boundary:** the digikey HTTP receiver and the edge scope checks are **slice 3**. Slice 2 ships against the request/response contract in §8 and must behave correctly (fail open, keep serving) when that endpoint does not exist yet.
- **Human gate:** slice 2 changes **no `digikey/` code**, so the auth/crypto gate is not triggered by this spec. It does add a recurring outbound call from the container to digikey carrying the license credential — digichat already egresses to digikey (`DIGIKEY_URL`, `apps/digichat/src/lib/digigraph-upstream.ts:93`), so this is a new *cadence*, not a new destination. Per root `AGENTS.md` the implementing PR should still get owner review, because this slice defines the stop-serving behavior. This spec itself is docs-only.

## 0. How to execute this spec (read this first, executor)

1. **Read first:** `apps/digichat/AGENTS.md` (pre-flight checklist — note the auth-on-every-route rule and the `DIGICHAT_AUTO_MIGRATE` guard), then `apps/digichat/ARCHITECTURE.md` §3 (API surface — Health/Chat), §5 (BFF pattern, instrumentation), §10 (deployment config), §11 (env vars, startup). Then the bound design spec above. Never skip the component `AGENTS.md`.
2. **Branching:** the implementing change touches `apps/digichat/**`, so it is `component:digichat` and routes to `module/digichat` per `scripts/project_routing.json` → cut with `make task ISSUE=N`, never from a stale base. `origin/module/digichat` was measured **37 commits behind `origin/develop`** when this spec was written; `make task` refuses a stale module base and prints the sync recipe — follow it rather than working around it.
3. **Spec file ≠ code file:** this document prescribes interfaces, behavior, and acceptance. Exact file/function names below are recommendations; what is binding is the verification sequence (§3), the state machine (§4), the heartbeat contract (§5, §8), the refusal shape (§6), and the acceptance checklist (§10).
4. **Conventions:** TypeScript strict, ESLint clean, Vitest, line length per repo config, lowercase digi names in prose (code identifiers keep their casing). **The raw license JWT and any key material are never logged, never returned in a response, and never written to a file** — `license_id`, customer slug, and `exp` are safe to log (slice 1 §2.3).
5. **Tests / commands:** `npm run test`, `npm run lint`, `npm run build` from `apps/digichat/`. No stack required for the slice-2 suite (§9).
6. **Docs duties in the implementing PR:** `apps/digichat/ARCHITECTURE.md` (§3 Health — including the new `GET /healthz` route, §7.2 — §5 instrumentation/startup, §11 env-var table) and `.env.example` — this spec names the env vars (§2) but ships no code and no env entries.

## 1. Decisions

### 1.1 Locked (inherited — not re-decided here)

| # | Decision (source) | Slice-2 consequence |
|---|---|---|
| D1 | Keypair reuse: licenses are RS256 signed with the existing digikey keypair, verified offline via `DIGIKEY_PUBLIC_KEY_PEM` (design decisions 1) | No JWKS fetch, no network in the verify path, no new key env |
| D2 | `aud=digichat-license`, `kind=digichat-license`, existing `iss` (design decisions 1, § License claims; slice 1 §3) | Local claim checks use exactly these values |
| D3 | Heartbeat credential = the raw license JWT as a Bearer token in `Authorization` (design decision 8) | One credential; no derived token, no separate heartbeat key |
| D4 | Cadence 24h owner-fixed; explicit revoked/unknown → stop product traffic within ~24h; errors → serve + backoff bounded by `exp` (design decision 6, § Heartbeat) | Interval is a constant, not an env var; backoff never exceeds 24h |
| D5 | Scheduler home: `startLicenseHeartbeat()` from `register()` in `instrumentation.ts`, `setInterval(24h).unref()`, guarded by `NEXT_RUNTIME === "nodejs"` (design decision 7) | Not a route-handler cron, not `trusted-proxy-server.mjs` |
| D6 | Startup never blocks on network; no launch-gating (design decision 6, § Container verification) | Verify is pure local crypto; the first heartbeat is fire-and-forget |
| D7 | Four-state contract: `valid` / `expired` / `revoked` / `unknown` (slice 1 §4.4, normative) | The container mirrors the same vocabulary locally; the receiver maps it in slice 3 |
| D8 | `max_version` unpinned; heartbeat reports version truthfully (design decision 2) | Version comes from the existing resolver chain (§5.4), no semver compare |

### 1.2 Owner decisions (recorded 2026-09-28)

Five decisions the owner closed after this draft. Each replaces an open question in §12 and is applied inline where its topic is covered; nothing else in the spec changes.

| # | Decision | Closes | Applied in |
|---|---|---|---|
| OD1 | **Expiry → refuse.** Once the license JWT's `exp` passes (plus the §3.2 skew leeway), the container refuses product traffic with `503 license_expired` — matching slice 1 §4.4's four-state contract. The bound design contradicted itself on this point; design rev 5 (owner-confirmed 2026-09-28) resolves the contradiction in favor of refuse-at-expiry | §12.1 | §4.1, §10; design rev 5 |
| OD2 | **Add `GET /healthz`** — an auth-exempt liveness route always answering `{"ok": true}` (root `AGENTS.md` § Liveness vs status), separate from `/api/health`, which reports license state | §12.2 | §0, §7.2, §9, §10 |
| OD3 | **Refusal scope: chat + plan-proof only.** `POST /api/chat` (and the `/api/v1/chat` re-export) plus `POST /api/plan-proof` refuse with `503 license_revoked` / `503 license_expired`; auth, config, embed-tenant, health, and all other routes keep answering so the state stays diagnosable | §12.3 | §6.2, §6.3, §9, §10 |
| OD4 | **Env names confirmed:** `DIGICHAT_LICENSE_JWT` (inline) and `DIGICHAT_LICENSE_FILE` (mounted file), the file winning when both are set | §12.6 | §2 |
| OD5 | **Canonical hosts source: embed tenant host keys.** Startup verify derives the deployment's hosts from the same tenant-config keys that route embed traffic, not from a separate `DIGICHAT_EMBED_HOSTS` list | §12.5 | §2, §3.5 |

## 2. Env / credential provisioning

The customer container carries exactly one credential (the license JWT) plus the public verification key. Slice 1 §7 defers the *name* of the license env var to this slice; it is fixed here and owner-confirmed (OD4, 2026-09-28).

| Env var | Required | Meaning |
|---|---|---|
| `DIGICHAT_LICENSE_JWT` | one of the two | The raw compact RS256 license JWT, inline. Never logged, never echoed |
| `DIGICHAT_LICENSE_FILE` | one of the two | Absolute path to a file containing only the JWT (mounted secret / config file). If set and readable it **wins** over the inline env, so a renewal is a file swap without an env edit |
| `DIGIKEY_PUBLIC_KEY_PEM` | yes for licensed verify | One **or more** concatenated `-----BEGIN PUBLIC KEY-----` SPKI PEMs (rotation list, current + previous — design § Container verification) |
| `DIGIKEY_ISSUER` | recommended | Expected `iss`. Defaults to `http://127.0.0.1:8005` exactly as `_issuer()` does (`digikey/src/digikey/jwt_issue.py:19-20`); must equal the issuer in force at mint time or every license fails the `iss` check |
| `DIGIKEY_URL` | yes for heartbeat | Heartbeat base URL. Existing digichat env (`digigraph-upstream.ts:93`, documented in `apps/digichat/ARCHITECTURE.md` §11) — no new destination var |
| deploy-config `hosts` / `DIGICHAT_EMBED_TENANTS` | optional | Read-only inputs for the advisory `hosts` comparison (§3.5) — canonical source is the embed tenant host keys (OD5); `DIGICHAT_EMBED_HOSTS` is **not** an input. Never written by this slice |

Rules:

- **Absent both license vars → `unlicensed`.** Log `license_status=unlicensed reason=missing_credential` once at startup; no heartbeat timer is ever started; serving is unaffected. An unlicensed container is the open-core default, not an error (design § Deployment entitlement).
- **No kill switch.** There is deliberately no `DIGICHAT_LICENSE_DISABLE`. Suppressing the heartbeat is already possible for a hostile operator (firewall it) and is already accepted and bounded by `exp` (design § Threat model). Shipping a flag would make the same act convenient and would read as an endorsement.
- **Public-key list format is defined here, not by the Python side.** Split `DIGIKEY_PUBLIC_KEY_PEM` on `-----BEGIN PUBLIC KEY-----` boundaries, trim, drop empties; verify the signature against each candidate and accept if any verifies. Rotation is procedural (slice 1 §6): append the new PEM first, drop the old one after the old term lapses. Do not rely on `kid` for selection — the env carries no `kid` → key mapping (logging the incoming `kid` header is fine; it is not secret).
- **Never bake either value into an image layer.** Same prohibition as `DIGICHAT_EMBED_TENANTS` (`Dockerfile.digichat-cloudflare:4-5`); runtime env / mounted file only (design § Issuance flow).
- Delivery itself stays with slice 1 §7 (owner email): the JWT, the public PEM(s), the hosts it was minted for, and the plain-language `exp`.

## 3. Startup verification sequence (local only, fail-open)

Hook point: `register()` in `apps/digichat/src/instrumentation.ts` (currently 11 lines: `NEXT_RUNTIME` guard `:2`, `initDigichatConfigAtStartup()` `:4-7`, migrate early-return `:8-10`). The license step **must be inserted before the migrate early-return at line 8**, otherwise `DIGICHAT_AUTO_MIGRATE != "1"` (the common case) would skip it. Recommended shape:

```ts
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { initDigichatConfigAtStartup } = await import("@/lib/deploy-config/loader");
  initDigichatConfigAtStartup();          // must run first: §3.5 reads configured hosts
  const { initLicenseStateAtStartup } = await import("@/lib/license");
  initLicenseStateAtStartup();            // pure local crypto — never awaits the network
  const { startLicenseHeartbeat } = await import("@/lib/license/heartbeat");
  startLicenseHeartbeat();                // schedules; first attempt is fire-and-forget
  if (process.env.DIGICHAT_AUTO_MIGRATE !== "1") return;
  const { runMigrate } = await import("@/lib/migrate");
  await runMigrate();
}
```

`initLicenseStateAtStartup()` is awaited (it is synchronous CPU work: parse + RSA verify of a ≤2KB token, microseconds-to-milliseconds) but it **never performs I/O other than reading the env/file**. `startLicenseHeartbeat()` returns immediately; its first network attempt runs unawaited.

### 3.1 Step order (normative)

Run in this order and stop at the first failure; each failure records a reason code and leaves the state `unlicensed`:

1. **Parse** — read `DIGICHAT_LICENSE_FILE` (if set and readable) else `DIGICHAT_LICENSE_JWT`. Split the compact JWT on `.`, require three segments, base64url-decode the header and payload, `JSON.parse`. Failures: `missing_credential`, `malformed_jwt`, `bad_json`.
2. **Signature** — header `alg` must be `RS256` (reject `none` and every symmetric alg outright: this is the classic key-confusion hole, and the only accepted algorithm is asymmetric). Verify `signingInput = header.payload` against every candidate PEM from §2 using `node:crypto` (`createPublicKey(pem)` + `verify("RSA-SHA256", …)`). **No new dependency**: digichat has no JWT library today (`apps/digichat/package.json` dependencies contain neither `jose` nor `jsonwebtoken`), and the checks below are a dozen lines of `node:crypto` — adding a runtime dep for them is not justified. Failures: `bad_signature`, `no_public_key`.
3. **Claims** — in this order: `exp`/`iat` (see §3.2), `aud === "digichat-license"`, `iss` equals `DIGIKEY_ISSUER` (§2), `kind === "digichat-license"`, `hosts` is a non-empty string array, `sub`/`tenant_slug` present, `license_id` (or its `jti` mirror) present and a string. Failures: `exp_missing`, `expired`, `aud_mismatch`, `iss_mismatch`, `kind_mismatch`, `hosts_invalid`, `claims_missing`.
4. **Hosts (advisory)** — §3.5. Never fails verification.

### 3.2 Time handling

- Allow **300s (5 min) of clock-skew leeway** on both `iat` and `exp` (design § Container verification): accept when `now <= exp + 300` **and** `iat <= now + 300`. Container clocks in customer Azure environments drift; a hard edge turns skew into a false unlicensed status.
- The `exp` captured here is the local **expiry backstop**: it bounds every fail-open path (design § Expiry backstop). Evaluate it against the local clock on every read (§4), not once at boot — a container that runs past `exp` must transition without needing a heartbeat.

### 3.3 Fail-open semantics (startup)

- **Any throw during verification is caught inside `initLicenseStateAtStartup()`.** `register()` must not propagate a license error: a broken or absent license never prevents boot, never prevents config init, and never prevents `runMigrate()`. Log one structured line (§7) and continue with `unlicensed`.
- **A startup error is not a latch.** `unlicensed` is a serving state: every feature, backend, model, tool, and UI knob keeps working (design § Non-goals, § Deployment entitlement). Only two states refuse product traffic: `revoked` (learned) and `expired` (§4).
- The config loader next door is deliberately the opposite (`getDigichatConfig()` "fail closed: first load error sticks", `apps/digichat/src/lib/deploy-config/loader.ts:408-418`). Do **not** copy that pattern for licenses; the design's fail-open requirement is explicit and is the opposite trade.

### 3.4 Restart semantics

Verification runs from scratch on every boot. A latched `revoked` state does **not** survive a restart on its own (design § Startup behavior): the process starts `valid`/`expired`/`unlicensed` purely from local crypto, and the immediately-scheduled first heartbeat (§5.2) re-learns `revoked` within seconds rather than a full interval. Restart-to-evade therefore buys seconds, not ~24h, and still stops at `exp`.

- **No persistence of the latch** (in-memory only). Persisting to disk is explicitly optional in the design and is a non-goal here (§11): it adds a write path on a customer-controlled filesystem that a hostile operator trivially clears anyway.

### 3.5 Hosts comparison (advisory only)

The `hosts` claim is descriptive binding for status display, not an authorization gate (design § License claims). Compare it against the deployment's **canonical host keys — the same tenant-config keys that route embed traffic** (OD5): the merged embed-tenant host registry, resolved exactly as embed routing resolves it:

- the deploy-config `hosts` record keys (`apps/digichat/src/lib/deploy-config/schema.ts:542`) **after** the `DIGICHAT_EMBED_TENANTS` overlay merge (`mergeEmbedTenantsOverlay`, `apps/digichat/src/lib/deploy-config/loader.ts:276`, which folds tenant keys + `aliases` in), looked up with `matchHostDeployment` (`loader.ts:490-498`);
- the `DIGICHAT_EMBED_TENANTS` registry keys + `aliases` (`apps/digichat/src/lib/embed-tenants.ts:774`) via `resolveEmbedTenantByHost` (`embed-tenants.ts:818`).

Those two are one chain, not two lists: `resolveVerifiedEmbedTenantFromHostToken` tries the merged hosts first and the raw registry second (`apps/digichat/src/lib/embed-chat-tenant.ts:153`), so together they name the **registered** hosts this container routes embed traffic for (an unregistered parent may still be served anonymously on a single-install container — that is embed auth, not host inventory, and not this comparison's concern). `DIGICHAT_EMBED_HOSTS` (`apps/digichat/src/proxy.ts:7`, the runtime CSP feed) is **not** an input — it feeds CSP, not routing, so it is not evidence of which hosts this deployment serves (this replaces the earlier three-source union, OD5).

Normalize both sides with the existing host normalization rules (`normalizeEmbedHost`, `embed-tenants.ts:266-280`) — lowercase, strip trailing dot, drop port — before comparing.

- **Overlap is enough.** Report `hosts_mismatch` when *no* license host appears among the configured hosts; partial overlap (license lists 2, container configures 1) is not a mismatch, because a container may legitimately serve a subset.
- **No configured hosts to compare → skip silently** (`hosts_check: skipped` in the log line), never a warning: a single-install client container with no embed registry has nothing to compare against.
- Mismatch never changes the serving state and never blocks a heartbeat; it is a log line plus the health `license_detail` value (§7).

## 4. Revoke latch state machine

### 4.1 States

| State | Source of truth | Product traffic | Heartbeat |
|---|---|---|---|
| `unlicensed` | local: no credential or §3 failure | **serve** | never |
| `valid` | local: §3 passed and `now <= exp + 300` | **serve** | every 24h / backoff |
| `expired` | local: §3 passed and `now > exp + 300` | **refuse** (`503 license_expired`) | continues (reporting) |
| `revoked` | learned: explicit deny from our side (§5.3) | **refuse** (`503 license_revoked`) | continues (reporting) |

`unknown` from the server (no allowlist row) maps to `revoked` locally: both are explicit denies by design (design § Heartbeat, decision 8; slice 1 §4.4). The distinction is preserved in `license_detail` for the log/health surface, not in the serving behavior.

**Owner-confirmed 2026-09-28 (OD1): `expired` refuses.** The bound design contradicted itself — its container-verification failure mode read "expired … keep serving every feature" while its expiry backstop read "the container serves at most until `exp`" — and design rev 5 resolves the contradiction in favor of refuse-at-expiry. This table stands as written: both `expired` and `revoked` refuse, `unlicensed` never does (§3.3).

### 4.2 Transitions

```text
                 §3 pass
  (boot) ─────────────────────► valid ──(now > exp+300)──► expired
    │                            │  ▲                          │
    │ §3 fail / absent           │  │ explicit valid answer     │ explicit expired answer
    ▼                            │  │ (never un-latches exp)    │ (stays expired)
 unlicensed                      │  │                           │
                                 │  └───────────┬───────────────┘
                                 │              │ 401 + license_revoked | unknown_license
                                 └──────────────┴──────► revoked   (terminal until restart)
```

- **`revoked` and `expired` are terminal within a process.** Nothing the server returns un-latches them (no "re-validated" answer exists in the contract, §8); recovery is a re-licensed deployment or a restart *after* the credential is fixed. A restart from `revoked` re-enters at `valid` only if the `license_id` is live again — which the first heartbeat then confirms.
- **Error outcomes never move the state.** Network failure, timeout, 5xx,404, unrecognized 401 → state unchanged, backoff scheduled (§5.4). This is the fail-open half of design decision 6.
- **Expiry is evaluated lazily on every read** of the state (route guard, health) as well as by the heartbeat, so `valid → expired` does not depend on a timer firing.

### 4.3 Where the state lives

A process-wide singleton exposed through a synchronous accessor, because route handlers must read it **synchronously** (a guard cannot `await` startup):

```ts
// apps/digichat/src/lib/license/state.ts
export type LicenseState = "unlicensed" | "valid" | "expired" | "revoked";
export function getLicenseState(): { state: LicenseState; detail?: string; licenseId?: string; sub?: string; exp?: number };
export function setLicenseState(next): void;
export function resetLicenseStateForTests(): void;
```

- Back it with `globalThis` (e.g. `const g = globalThis as …` holding one object) rather than a bare module-level `let`. `instrumentation.ts` and the route handlers are separate compiled bundles in the standalone build, and Next does not promise they share module instances — a bare `let` can silently give each bundle its own copy, which would make the latch invisible to the exact routes it must guard. The in-repo config singleton (`loader.ts:405`) cannot be used as proof either way because it lazily loads on cache miss (`:409-418`). Cost of `globalThis` is one property; cost of guessing wrong is a latch that never fires.
- Import the license modules dynamically from `register()` (same pattern as the existing `await import("@/lib/deploy-config/loader")`) and statically from route handlers.
- `resetLicenseStateForTests()` is required: `globalThis` outlives a test file's module registry.

## 5. Heartbeat sender

Home: `apps/digichat/src/lib/license/heartbeat.ts` exporting `startLicenseHeartbeat()` (design decision 7), called from `register()` (§3). Everything below is inside that module.

### 5.1 Cadence

- **Interval constant `LICENSE_HEARTBEAT_INTERVAL_MS = 24 * 60 * 60 * 1000`.** Not configurable by env — it is an owner-fixed validity-check cadence, and the design's worst-case revocation latency (~24h) is a promise about that constant (design § Heartbeat). A knob would let a deployment quietly make revocation slower than promised.
- `setInterval(...).unref()` so the timer never holds the process open (design decision 7). Every retry timeout is unref'd too.
- Guarded by `NEXT_RUNTIME === "nodejs"` at the `register()` call site; the module also asserts the runtime when started directly in tests.
- Exported `stopLicenseHeartbeat()` (clears timers, resets attempt counters) for tests and for a future graceful-shutdown hook. Not wired to any shutdown path in this slice.

### 5.2 First attempt

Start the timer **and** fire one attempt immediately, unawaited. This is the design's "best-effort remote key check that never blocks startup (its result only seeds the heartbeat state)" (§ Container verification): it is simply the heartbeat, sent early. It must not delay `register()` returning, must not block the first request, and a failure of this attempt is an ordinary error (§5.4) — it cannot delay or prevent serving.

Consequence (desirable): a container restarted to clear the latch re-learns `revoked` in well under a second instead of waiting up to 24h.

### 5.3 Request

```http
POST {DIGIKEY_URL}/v1/licenses/heartbeat
Authorization: Bearer <raw license JWT, unchanged>
Content-Type: application/json

{"license_id":"…","customer":"datatap","license_status":"valid","version":"2.3.2",
 "hosts_configured":["datatapstream.com"],"started_at":"2026-09-28T09:14:02.000Z","seq":1}
```

- The header carries the credential; the body carries telemetry (design decision 8). No usage counts, no message contents, no end-user identifiers (design § Heartbeat shape).
- `license_id` from the `license_id`/`jti` claim; `customer` from `sub`; `license_status` is the **local** state at send time (`valid` or `expired` — `unlicensed` never sends, `revoked` sends `revoked`); `version` per §5.4; `hosts_configured` = the normalized configured-host set from §3.5 (may be `[]`); `started_at` = ISO-8601 UTC of process start; `seq` = monotonic counter starting at `1`, process-local, incremented per attempt.
- Timeout: **10s** via `AbortController` (the health probe already uses this pattern with a 4s budget, `apps/digichat/src/app/api/health/route.ts:13-21`; the extra headroom covers a slow TLS handshake to a distant digikey). Aborting is an error outcome.
- Only one attempt in flight at a time; a tick that fires while an attempt is running is dropped, not queued.

### 5.4 Version truth

Report `version` by reusing the existing resolution chain, **not** by importing `trusted-proxy-server.mjs`:

- the proxy resolves the version at boot (`resolveDigichatVersion`, `apps/digichat/scripts/trusted-proxy-server.mjs:48-67`: env → `/etc/digichat-version` → `package.json`) and exports it into `process.env.DIGICHAT_VERSION` before spawning `server.js` (`:102-113`);
- inside the Next process the same value is read by `healthVersion()` (`apps/digichat/src/app/api/health/route.ts:8-10`: `DIGICHAT_VERSION` env → `package.json`).

Extract `healthVersion()` into a shared helper (e.g. `src/lib/license/version.ts`) and have **both** `GET /api/health` and the heartbeat import it, so the two surfaces cannot drift. The image bake that makes the env non-empty is `Dockerfile.digichat-cloudflare:41-44` + `:57`.

### 5.5 Response handling

| Outcome | Recognition rule | Effect |
|---|---|---|
| **valid** | HTTP 200 and body `{"license_status":"valid"}` | state → `valid` (if it was `revoked`/`expired`, see §4.2: expired stays expired); next attempt in 24h |
| **expired** | HTTP 200 and body `{"license_status":"expired"}` | identified-but-lapsed (slice 1 §4.4): state → `expired`; next attempt in 24h |
| **explicit deny** | HTTP **401** **and** body `error` ∈ {`license_revoked`, `unknown_license`} | latch `revoked` (`detail` records which); product traffic refused from this moment; next attempt still 24h |
| **everything else** | any 2xx/3xx/4xx/5xx not matched above; unrecognized 401 (e.g. digikey's ordinary auth middleware rejecting the token with `{"error":"unauthorized"}`); 404/405 (slice 3 not deployed); DNS/TLS/connect errors; timeout; JSON parse failure | **error** → state unchanged, serve, retry with backoff (§5.6) |

Two rules make this safe, and both are normative:

- **Deny requires *both* the 401 status and a recognized `error` code.** A bare 401 from any other layer must not latch — otherwise a digikey middleware misconfiguration would brick a healthy customer deployment. This is the fail-open half applied to status codes.
- **Slice 2 must be fully operational before slice 3 exists.** A digikey that does not serve `/v1/licenses/heartbeat` answers 404 (or a proxy answers HTML/502); that is an error outcome, so the deployment serves normally at its 24h cadence until the receiver ships. Shipping order is an acceptance criterion (§10), not a hope.

### 5.6 Backoff (errors only)

No error-grace timer exists by design — the grace is bounded by the license's own `exp` (design § Heartbeat response handling). Parameters:

- base delay **5 min**, doubling per consecutive error (**5m → 10m → 20m → …**), capped at **6h**, ±10% jitter to avoid a fleet synchronizing on us;
- never schedule an attempt further out than 24h, so backoff can slow retries but can never weaken the owner-fixed cadence;
- reset to the plain 24h interval on any 200 (valid/expired) or on an explicit deny;
- every scheduled delay is `unref`'d; a crash in the attempt body is caught and logged, never rethrown into the timer callback.

The backoff is bounded by `exp` in the only way that matters: the container serves fail-open while our side is unreachable, and serving stops at `expired` regardless of whether a heartbeat ever succeeded (§4).

## 6. Stop-serving: `503` refusal and where it hooks in

### 6.1 Response shape

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error":"license_revoked","message":"This deployment's license has been revoked. Chat is disabled until the deployment is re-licensed."}
```

- Status **503**, `error` **`license_revoked`**, matching the design's stop-serving mechanics and the repo's existing `503 auth_not_configured` idiom. `license_expired` uses the same shape with `{"error":"license_expired","message":"This deployment's license has expired. Chat is disabled until a renewed license is provisioned."}`.
- **No `Retry-After` header**: the condition is not client-retryable, and a retry hint would make clients hammer a state only an operator can clear.
- The message is operator-facing and carries no detail about `license_id`, hosts, or our infrastructure.
- Build it in one place (recommended: `licenseRefusal(): Response | null` in `src/lib/license/state.ts`, returning `null` for `unlicensed`/`valid`). Where the existing `jsonError()` helper is in scope (`apps/digichat/src/app/api/chat/route.ts:77-87`), reuse it so the body shape stays identical across routes.

### 6.2 Required hook points (normative)

Refusal scope is **chat + plan-proof only** (OD3, 2026-09-28): these two handlers, covering three routes — nothing else is guarded.

| Route | Site | Why |
|---|---|---|
| `POST /api/chat` | first statement of `POST`, **before** `requireDigiChatAuth(req)` (`route.ts:89-90`) | the product-traffic choke point; also covers `POST /api/v1/chat`, which re-exports this handler (`apps/digichat/src/app/api/v1/chat/route.ts:1`). Auth order matters: a revoked deployment must refuse even an authenticated caller, and refusing first is also the cheaper check |
| `POST /api/plan-proof` | `route.ts:40`, before any embed-tenant/token work | mints chat-eligible tier proofs — product traffic by another name (design § Stop-serving mechanics) |

Coverage note: the design's stop-serving mechanics names `POST /api/chat` and "the embed routes (`/api/embed/*`, `/api/plan-proof`, all proxied per `apps/digichat-cloudflare/src/paths.ts:6-19`)". The owner narrowed slice 2 (OD3) to chat + plan-proof, so `/api/embed/*` — including `GET /api/embed/tenant-config` — keeps answering (§6.3): diagnosability wins over a perfectly coherent stop, because auth, config, embed-tenant, and health are how an operator learns *why* they are being refused. `paths.ts` routes traffic to the container but is edge-side config in a different package — it is **not** a guard and is untouched by this slice.

### 6.3 Deliberately not hooked (this slice)

- `GET /api/health` — must keep answering truthfully (§7), including while refused.
- `/api/auth/*` — session sign-in/out must keep working so an operator or customer can still see what state they are in; blocking auth turns a status problem into a lockout.
- `/api/deploy/chrome` (public chrome), `/api/baseline-chat` (dev-only), `/api/mcp/oauth/*`.
- **HTML page routes and `/embed`** — the page shell still renders; slice 2 refuses product *traffic* (turn-taking, embed config, tier proofs), not document loads. Extending the refusal into `src/proxy.ts` is explicitly out of scope: its `matcher` (`proxy.ts:40-42`) does not cover `/api/*` anyway, and reading a Node-process latch from the proxy bundle is exactly the cross-bundle hazard §4.3 exists to avoid.
- `GET /api/embed/tenant-config` — **OD3 (2026-09-28):** refusal is chat + plan-proof only; the embed-tenant config route keeps answering so a refused deployment can still be diagnosed. (It was a hook point in the first draft of §6.2, matching the design's embed-route list; the owner narrowed the scope.)
- `/api/conversations*`, `/api/ecosystem/config`, `/api/byok/*` — outside the chat + plan-proof scope (OD3), so question 3 resolves as "refuse exactly these two handlers".

## 7. Health, logging, and metrics surfacing

### 7.1 `GET /api/health`

Additive fields only, in `apps/digichat/src/app/api/health/route.ts`:

```jsonc
{ "ok": true,                      // computation UNCHANGED (route.ts:63-68)
  "checks": { "service": "ok", … },
  "version": "2.3.2",
  "license_status": "revoked",     // unlicensed | valid | expired | revoked
  "license_detail": "heartbeat_deny_revoked" }  // short enum, optional, never a secret
```

- `license_status` is **always present** (a deployment with no license reports `unlicensed`) — an absent field would be indistinguishable from "not implemented".
- **The `ok` computation and the 200/503 mapping (`route.ts:63-77`) do not change.** That is the design's instruction (§ Stop-serving mechanics: "add a `license_status` field … without changing the `ok` computation"), and it keeps an orchestrator's existing restart policy from treating a revoked license as a downstream outage and crash-looping the container.
- `license_detail` is a closed enum drawn from §3.1/§3.5/§4 (`missing_credential`, `malformed_jwt`, `bad_signature`, `expired`, `aud_mismatch`, `iss_mismatch`, `hosts_mismatch`, `heartbeat_deny_revoked`, `heartbeat_deny_unknown`, `heartbeat_unreachable`, …). It never carries the JWT, a PEM, or a hostname list.
- Document the new fields in `apps/digichat/ARCHITECTURE.md` §3 Health and the env table in §11.

### 7.2 Liveness

There is a real tension the implementation must not paper over: `ok` stays `true` while revoked, yet the design also says "no probe may report healthy product traffic while revoked" and "keep a license-independent liveness signal available" (§ Stop-serving mechanics). Resolved as follows for this slice:

- `/api/health` is a **status** endpoint: it reports `license_status` honestly and keeps its downstream `ok` semantics. A probe that must decide "restart the container?" keeps keying on `ok` (unchanged behavior, no crash loops).
- A probe that must decide "is this deployment allowed to serve turns?" reads `license_status`.
- **Add `GET /healthz` (OD2, owner-confirmed 2026-09-28).** An auth-exempt liveness route that always answers `{"ok": true}` — the stack convention in root `AGENTS.md` § Liveness vs status — separate from `/api/health`, which reports license state (§7.1). It answers `{"ok":true}` in **all four** states, `revoked` and `expired` included: the orchestrator's restart decision never depends on license state, and no product-traffic probe is fooled, because a probe that must decide "may this deployment serve turns?" reads `license_status` off `/api/health` (§7.1). digichat has no such route today; it must also reach the container through the edge proxy, since `shouldProxyToDigiChat` (`apps/digichat-cloudflare/src/paths.ts:6-19`) routes `/api/health` but not `/healthz` — that is edge *routing*, not a guard, so it does not conflict with the §6.2 note about `paths.ts`. This closes open question 2.

### 7.3 Logs

One structured line per state change and one per heartbeat outcome, via `console.warn` (errors/denies) or `console.log` (informational), matching the existing `[digichat-config] …` startup line style (`loader.ts:426-428`):

```text
[license] status=valid detail=ok license_id=9f3c… customer=datatap exp=1785004800 hosts=2
[license] status=revoked detail=heartbeat_deny_revoked license_id=9f3c… seq=7
[license] heartbeat error detail=timeout seq=8 next_attempt_in_ms=300000
```

- Log the startup verification result **once**; heartbeat successes are not logged per tick at `log` level (24h cadence makes them cheap, but a per-attempt `debug`-style line keeps noise bounded if the interval ever changes) — the binding rule is: denies and errors are always logged, and **the raw JWT, the PEM, and any Authorization header are never logged**.
- **No new metrics backend.** digichat has none of its own; health + logs are the surfacing surface for this slice. Exporting counters to digismith later is a separate, small change.

## 8. Slice-3 contract dependency (normative for both sides)

Slice 2 calls; slice 3 implements. The interface is fixed here so neither slice re-litigates it.

**Request (slice 2 owns):**

- `POST {DIGIKEY_URL}/v1/licenses/heartbeat`
- `Authorization: Bearer <raw license JWT>` — the same bytes as the `X-Digi-License` header that a later slice will forward on hosted-service calls (design decision 8; forwarding is **not** slice 2 — see §11)
- Body exactly as in §5.3.

**Response (slice 3 owns):**

| HTTP | Body | Meaning |
|---|---|---|
| 200 | `{"license_status":"valid"}` | signature valid, `license_id` present on the allowlist, not expired (slice 1 §4.4 `valid`) |
| 200 | `{"license_status":"expired"}` | signature valid, row live, `expires_at <= now` — identified but lapsed; still 200 so it is **not** a deny (slice 1 §4.4 `expired`) |
| 401 | `{"error":"license_revoked","message":…}` | row exists with `revoked_at` set (slice 1 §4.4 `revoked`) → container latches |
| 401 | `{"error":"unknown_license","message":…}` | no row (slice 1 §4.4 `unknown`) → container latches, `detail` records unknown |
| any other | any | undefined for slice 3; slice 2 treats it as an error (fail open) |

Requirements on slice 3, derived from slice 2's recognition rules (§5.5):

1. **Expiry is 200, never 401.** An expired-but-authentic license identifies the deployment (design decision 8); returning 401 would latch `revoked` on an expired license and destroy the expired/revoked distinction slice 1's contract exists for.
2. **The route must not be rejected by digikey's ordinary API-key/admin auth layer with a generic 401.** It authenticates *as* a license, so it needs its own path handling; a generic `{"error":"unauthorized"}` is indistinguishable from a misconfiguration to slice 2, which will (correctly) ignore it — but then revocation would never take effect. Slice 3 must prove the four rows above produce exactly the four mapped responses.
3. Server-side evaluation order: parse → verify signature → read `license_id` from the allowlist (slice 1 §4.4) → expiry. Revoked beats expired (a revoked row that has also expired still answers `license_revoked`).
4. The allowlist is the slice-1 `digikey_licenses` table; adding the admin/CLI allowlist operations needed to run the revocation drill is slice 3's (slice 1 §5 already landed the CLI revoke).

**What slice 2 does not need from slice 3 to ship:** anything. That is the point of §5.5's fail-open recognition rules.

## 9. Test plan

Vitest, node environment, no stack — `npm run test` in `apps/digichat/` (config: `apps/digichat/vitest.config.ts`, `src/**/*.test.ts`). Recommended new files `src/lib/license/verify.test.ts`, `state.test.ts`, `heartbeat.test.ts`, `route-guard.test.ts`, plus an update to `src/app/api/health/route.test.ts`. Binding is the case coverage, not the file names.

| Area | Cases |
|---|---|
| Parse | valid 3-segment JWT; 2-segment / empty / non-base64url rejected (`malformed_jwt`); payload not JSON (`bad_json`); absent env and absent file (`missing_credential`); `DIGICHAT_LICENSE_FILE` wins over inline env; unreadable file falls back to inline env (or `missing_credential` when neither works) |
| Signature | correct PEM verifies; tampered payload/signature rejected (`bad_signature`); `alg: none` rejected; `alg: HS256` rejected without ever touching a HMAC path (key-confusion); second PEM in a two-PEM list verifies (rotation list); zero-PEM env rejected (`no_public_key`) |
| Claims | wrong `aud` (`aud_mismatch`); wrong `iss` (`iss_mismatch`); missing `kind`/`license_id`/`sub` (`claims_missing`); `hosts` non-array/empty (`hosts_invalid`) |
| Clock skew | `exp` 4 min in the past still `valid`; `exp` 6 min in the past → `expired`; `iat` 4 min in the future accepted; `iat` far future rejected. Use injected clock, not `vi.setSystemTime` alone, if the module reads time through a seam |
| Hosts | exact match; subset (license ⊇ configured) not a mismatch; disjoint sets → `hosts_mismatch` **and state stays `valid`**; no configured hosts → skipped; trailing-dot/case/port normalization matches |
| State machine | boot with valid token → `valid`; lazy expiry flips to `expired` without a heartbeat; `401 license_revoked` from `valid` → `revoked`; `401 unknown_license` → `revoked` with `detail=heartbeat_deny_unknown`; **bare 401 `{error:"unauthorized"}` → state unchanged**; 404/500/timeout → state unchanged; `revoked` is terminal (a later 200 `valid` does not clear it); `resetLicenseStateForTests` clears `globalThis` |
| Guard | `revoked` → 503 body `{"error":"license_revoked",…}`, content-type JSON, no `Retry-After`; `expired` → 503 `license_expired`; `valid`/`unlicensed` → `null` (request proceeds); guard runs before auth in `POST /api/chat` (spy on `requireDigiChatAuth` not being called when refused); `/api/v1/chat` refuses too (re-export); `GET /api/embed/tenant-config` still answers while `revoked` (OD3) |
| Heartbeat scheduling | interval constant is 24h; `.unref()` called on the interval and on every retry timer; first attempt fires without awaiting; only one in-flight attempt (tick during flight is dropped); `stopLicenseHeartbeat()` clears everything |
| Backoff | 5m → 10m → 20m … capped 6h; never > 24h; reset on 200; jitter within ±10%; error body never throws out of the timer callback |
| Response handling | 200 `valid` / 200 `expired` / 401 deny / 404 / 500 / aborted timeout → mapped per §5.5; malformed 200 body → error |
| Heartbeat body | exact key set `{license_id, customer, license_status, version, hosts_configured, started_at, seq}`; `seq` starts at 1 and increments; `Authorization: Bearer` carries the raw JWT and **never** appears in logs (assert on `console.log`/`warn` spy args) |
| Health | `license_status` present in all four states; `ok` and HTTP status identical to pre-change behavior for the same `checks` fixture (regression guard on `route.ts:63-77`); `version` equals the shared helper's value; `GET /healthz` answers `{"ok":true}` with 200 in all four states and never consults license state (OD2) |
| Startup | `register()` completes with a broken license (no throw, migrate still reachable); license step runs before the `DIGICHAT_AUTO_MIGRATE` early-return (assert via a unit test of the extracted ordering or a comment-plus-review note — a full `register()` integration test is not required) |

Commands: `npm run test`, `npm run lint`, `npm run build` (type check) — all from `apps/digichat/`.

## 10. Acceptance criteria

- [ ] A container with `DIGICHAT_LICENSE_JWT` + `DIGIKEY_PUBLIC_KEY_PEM` verifies locally at startup through the §3 order and reports `license_status=valid` in `GET /api/health`; no network call occurs during verification (prove it: run the verify unit with `fetch`/`net` stubbed to throw and assert success)
- [ ] Absent/broken/expired-license-at-boot never blocks boot or the first request; `register()` does not throw; `runMigrate()` still runs (fail-open, §3.3)
- [ ] The advisory `hosts` comparison derives configured hosts from the embed tenant host keys only — `DIGICHAT_EMBED_HOSTS` contributes nothing, and a disjoint set still leaves the state `valid` (§3.5, OD5)
- [ ] `startLicenseHeartbeat()` is called from `register()`, guarded by `NEXT_RUNTIME === "nodejs"`, uses a 24h constant interval, and every timer is `unref`'d (design decision 7 verifiable by grep)
- [ ] The first heartbeat attempt fires immediately and unawaited; a failing first attempt does not delay serving (§5.2)
- [ ] On `401` + `license_revoked`/`unknown_license`, product traffic is refused **at that heartbeat** with `503 {"error":"license_revoked"}` from `POST /api/chat` and `POST /api/plan-proof` (plus `/api/v1/chat`, which re-exports the chat handler), while `GET /api/embed/tenant-config`, `/api/auth/*`, config routes, and `GET /healthz` keep answering — and `/api/health` reports `license_status=revoked` with `ok` unchanged (§6, §7.1; scope per OD3)
- [ ] `GET /healthz` exists, is auth-exempt, and answers `{"ok": true}` in all four license states, distinct from `/api/health`, which reports license state (§7.2, OD2)
- [ ] Every other non-200 outcome — including a digikey with **no heartbeat route at all** — leaves serving untouched and schedules a bounded backoff (§5.5, §5.6): slice 2 ships safely before slice 3
- [ ] Local `exp` + 5 min leeway flips `valid → expired` without any heartbeat and refuses with `503 license_expired`, so the fail-open window is bounded by the 90-day term (design § Expiry backstop; owner-confirmed OD1, design rev 5)
- [ ] A restart clears the in-memory latch, and the immediate first heartbeat re-learns `revoked` (§3.4) — revocation drill: mint → heartbeat ok → `digikey license-revoke` (slice 1 §5) → next heartbeat → container refuses → re-mint → restart → container serves again
- [ ] No raw JWT, PEM, or `Authorization` header value appears in any log line, health response, or error body (test assertion in §9)
- [ ] No new npm dependency for JWT verification (§3.1)
- [ ] `apps/digichat/ARCHITECTURE.md` (§3 Health, §5 startup, §11 env vars) and `.env.example` updated in the implementing PR
- [ ] `npm run test`, `npm run lint`, `npm run build` green in `apps/digichat/`
- [ ] This spec's `python3 scripts/check_doc_links.py` green

## 11. Non-goals (explicit)

- **No heartbeat receiver.** The digikey endpoint, its scope handling, and the allowlist read side are slice 3 (§8). No `digikey/` code changes in slice 2.
- **No edge scope checks.** The digigraph header-to-scope map (`X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` / `X-Digi-Enable-Web-Search` → `services`) and **`X-Digi-License` forwarding on digigraph calls** are the edge slice. Slice 2 adds no headers to upstream calls.
- **No launch-gating.** Startup never refuses to boot and never waits on the network (design decision 6); "the container won't start" is not an outcome this slice can produce, by design.
- **No feature gating.** No config option, model, tool, MCP server, or UI knob is hidden or disabled in any state (design § Non-goals).
- **No latch persistence**, no disk writes, no new database tables or columns.
- **No JWKS fetch**, no `kid`-based key selection, no key-rotation automation (procedural per slice 1 §6).
- **No kill switch** env var (§2).
- **No HTML/page refusal** and no `src/proxy.ts` changes (§6.3).
- **No new metrics backend**, no Prometheus/digismith export.
- **No changes** to `requireDigiChatAuth`, deploy-config fail-closed loading, rate limits, or the health `ok` computation.
- **No admin/HTTP revoke surface** (slice 1 CLI revoke stands; the HTTP admin endpoint is slice 3's).

## 12. Open questions

Owner decisions recorded 2026-09-28 (§1.2) close five of these six; only question 4 remains open, and it is framed as a pre-rotation-run verification check, not a spec blocker.

1. **Resolved (2026-09-28, OD1) — the expired license refuses product traffic.** The design contradicted itself: § Container verification failure mode said "expired … keep serving every feature", § Expiry backstop said "the container serves at most until `exp`". Design **rev 5** (owner-confirmed 2026-09-28) resolves the contradiction in favor of the backstop, matching slice 1 §4.4 (`expired` → refuse product traffic on expiry grounds) and the brief's "errors → serve + backoff bounded by 90d exp". §4's `expired → 503 license_expired` stands and is now confirmed rather than provisional; the design's failure-mode bullet points at the rev-5 resolution. Rejected: expired-but-serving, which would move `expired` to the serve column, leave only `revoked` refusing, and make `exp` unenforceable against an operator who firewalls us.
2. **Resolved (2026-09-28, OD2) — add `GET /healthz`.** An auth-exempt liveness route always answering `{"ok": true}`, separate from `/api/health` (which reports license state), per the stack convention in root `AGENTS.md` § Liveness vs status. Applied in §7.2, including the edge-reachability consequence (`shouldProxyToDigiChat` does not route it today).
3. **Resolved (2026-09-28, OD3) — refusal scope is chat + plan-proof only.** `POST /api/chat` (and the `/api/v1/chat` re-export) plus `POST /api/plan-proof` refuse with `503 license_revoked` / `503 license_expired`; auth, config, embed-tenant, health — and `/api/conversations*`, `/api/ecosystem/config`, `/api/byok/*` — keep answering so a refused deployment stays diagnosable. The alternatives from the original question are both out: extending to `/api/conversations*` buys coherence but not enforcement, and extending to config/auth risks locking an operator out of the surface that reports the problem. Applied in §6.2, §6.3.
4. **Open — multi-PEM `DIGIKEY_PUBLIC_KEY_PEM` outside the container (verification check before a rotation run, not a slice-2 blocker).** The list format is defined here for TypeScript (§2), but the same env var is consumed by Python (`digikey/src/digikey/jwt_verify.py:61` → `jwt.decode(token, pem, …)` at `:78`) in other services — `compose.profile-a.yml:92,158` passes it to digivault and digigraph, and a two-PEM value in a shared `.env` may fail Python's single-key load. Slice 2 is unaffected: it ships no rotation and reads the list only in digichat. What stays open is the **check to run before slice 1 §6's rotation procedure is executed with a list** — verify Python's behavior with concatenated PEMs, or scope the list to the digichat container's env — so the footgun is defused on rotation day rather than decided now.
5. **Resolved (2026-09-28, OD5) — the canonical hosts source is the embed tenant host keys.** §3.5 now compares against the same tenant-config keys that route embed traffic (deploy-config `hosts` after the `DIGICHAT_EMBED_TENANTS` overlay, plus the registry fallback) instead of a three-way union; `DIGICHAT_EMBED_HOSTS` (the CSP feed) is no longer an input. Applied in §2, §3.5.
6. **Resolved (2026-09-28, OD4) — env names confirmed:** `DIGICHAT_LICENSE_JWT` (inline) and `DIGICHAT_LICENSE_FILE` (mounted file), the file winning when both are set (§2). Renaming after customers provision is not free, which is why this was closed now.

## Verification (this spec — docs-only)

- No code changed by this spec; branch `docs/spec-license-heartbeat` off `origin/develop` at `0a9199c28`. Owner decisions recorded 2026-09-28 in §1.2; §12 keeps only question 4 open.
- Every file:line claim above re-read against `origin/develop`: `apps/digichat/src/instrumentation.ts:1-11` (11-line `register()`, `NEXT_RUNTIME` guard `:2`, config init `:4-7`, migrate early-return `:8-10`), `apps/digichat/src/app/api/health/route.ts:8-10` (`healthVersion`), `:13-21` (4s `AbortController` probe), `:63-68` (`ok` computation), `:70-77` (`{ok, checks, version}` + 200/503), `apps/digichat/src/app/api/chat/route.ts:77-87` (`jsonError`), `:89-90` (`POST` + `requireDigiChatAuth`), `apps/digichat/src/app/api/v1/chat/route.ts:1` (re-export of the chat `POST`), `apps/digichat/src/app/api/plan-proof/route.ts:40`, `apps/digichat/src/app/api/embed/tenant-config/route.ts:13` (public `GET`), `apps/digichat-cloudflare/src/paths.ts:6-19` (proxied paths), `Dockerfile.digichat-cloudflare:4-5` (no-bake rule), `:41-44` + `:57` (version bake → `/etc/digichat-version`), `:69` (CMD `trusted-proxy-server.mjs`), `apps/digichat/scripts/trusted-proxy-server.mjs:48-67` (`resolveDigichatVersion`) + `:102-113` (`start()` spawns `server.js` with the resolved env), `apps/digichat/src/lib/deploy-config/loader.ts:405-430` (config singleton + fail-closed `initDigichatConfigAtStartup`), `apps/digichat/src/lib/deploy-config/schema.ts:542` (`hosts` record), `apps/digichat/src/lib/deploy-config/loader.ts:276` (`mergeEmbedTenantsOverlay` folds `DIGICHAT_EMBED_TENANTS` into `hosts`) + `:490-498` (`matchHostDeployment`), `apps/digichat/src/lib/embed-tenants.ts:266-280` (`normalizeEmbedHost`) + `:774` (key + aliases) + `:818` (`resolveEmbedTenantByHost`), `apps/digichat/src/lib/embed-chat-tenant.ts:153` (merged-hosts → registry fallback chain), `apps/digichat/src/lib/digigraph-upstream.ts:93` (`DIGIKEY_URL`), `apps/digichat/src/proxy.ts:7` (`DIGICHAT_EMBED_HOSTS`) + `:40-42` (matcher), `apps/digichat/vitest.config.ts` (node env, `src/**/*.test.ts`), `digikey/src/digikey/jwt_issue.py:19-20` (`_issuer()`), `:23` (`issue_access_token`), `:80` (`scope` mirror), `:88` (`public_jwks`), `digikey/src/digikey/jwt_verify.py:61` + `:78` (Python single-PEM path), `scripts/project_routing.json` (`component:digichat` → `module/digichat`).
- Staleness measured, not assumed: `git rev-list --count origin/module/digichat..origin/develop` = 37 at spec time.
- Greenfield confirmed: `grep -rni license apps/digichat/src apps/digichat/scripts` → 0 hits; no `jose`/`jsonwebtoken` in `apps/digichat/package.json`.
- Consistency with slice 1: the §4 state vocabulary and the §8 response mapping are exactly slice 1 §4.4's four states; slice 1 §10 lists "container verification and heartbeat scheduler" as this slice's scope, and this spec's §11 lists slice 1's CLI revoke / allowlist as already landed.
- Internal links: both bound specs linked by filename in the same directory.
- `python3 scripts/check_doc_links.py` run from the worktree (see task report).
