# digithings-stack Split (digikey / digigraph / digisearch → Workers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `DigiStackContainer` Profile-A instance by re-hosting its three Python FastAPI services (digikey, digigraph, digisearch) on Cloudflare Workers backed by D1 and Vectorize, preserving every route, auth decision and data contract.

**Architecture:** Each service becomes its own standalone Worker (`apps/digikey-worker`, `apps/digisearch-worker`, `apps/digigraph-worker`) that claims the existing `key.` / `search.` / `graph.digithings.ai` routes the stack container currently owns. Shared state moves from Postgres/Redis to D1 (`digikey` keys, issued-jti, licenses, profile pointers; digisearch document+chunk metadata) and Vectorize (digisearch embeddings). The stack Worker (`apps/digithings-stack-cloudflare`) loses its container-routes catch-all, the `[[containers]] DigiStackContainer` block, and its class registration.

**Tech Stack:** Cloudflare Workers (TypeScript, `nodejs_compat`, `compatibility_date = "2026-09-04"`), `wrangler` 4.x, D1 (SQLite), Vectorize, `@cloudflare/vitest-pool-workers` + vitest for tests (mirror `apps/digiquant-runner`), WebCrypto for RS256 JWT signing.

**Spec:** DIG-2914 (`ef5c208b-621f-4db7-8a7a-7b90ff96950f`), description "Aligned with DIG-2887. Removes the Profile A container." + Chris's unfreeze comment `443a63f0` (18 Oct 2026).

## Global Constraints

- Cloudflare account id is exactly `ae2ea3eb4ce5f7cc9bec1478f6e60e15` (from `apps/digiquant-runner/wrangler.toml`) — every new worker sets `account_id`.
- New workers use `compatibility_date = "2026-09-04"` and `compatibility_flags = ["nodejs_compat"]` (mirror `apps/digiquant-runner/wrangler.toml`).
- Public hostnames are fixed and must not change: `key.digithings.ai` (container port 8005), `search.digithings.ai` (8002), `graph.digithings.ai` (8000).
- `workers_dev = false` on every routed worker (mirror `apps/digithings-stack-cloudflare/wrangler.toml`).
- Admin authority for digikey is the bearer token in env `DIGIKEY_ADMIN_TOKEN`; the existing eval is `Authorization: Bearer <DIGIKEY_ADMIN_TOKEN>` in `digikey/src/digikey/server.py:133-139`.
- Minted API keys carry the prefix `dgk_live_` (`digikey/src/digikey/key_crypto.py`).
- JWTs are RS256, signed with `DIGIKEY_PRIVATE_KEY_PEM`, `kid` = `DIGIKEY_KEY_ID`, published at `/.well-known/jwks.json` (`digikey/src/digikey/crypto_keys.py:61-62`, `jwt_issue.py:82-84`).
- The jti blocklist is FAIL-CLOSED when `DIGIKEY_REQUIRE_BLOCKLIST=1` (`digikey/src/digikey/blocklist.py:54-57`).
- Every route, method and path currently served by the three services must be reachable at the same public URL with the same status/semantics; no route may be dropped without an explicit board decision recorded on DIG-2914.
- **No deployment and no merge without approval** — the single human gate stays intact; `wrangler deploy`, `wrangler d1 execute --remote`, and `git push` to a shared branch are all gated.
- D1 database name, Vectorize index name, and their created ids are DECISIONS (Task 1), not values assumed here — never invent an id.

---

## Review Focus

The reviewer must confirm, in this order:

1. **Task 1 blocks Phase 2 and Phase 3.** This plan deliberately does not specify tasks for digisearch or digigraph beyond their sequencing. `bcrypt` (digikey) and `langgraph` (digigraph) have no Workers runtime equivalent; the plan must not proceed past Task 12 until a human has answered Task 1. A plan that quietly "ports" either is wrong.
2. **Route parity is measured, not asserted.** The parity sweep task must enumerate the source route table from the Python `server.py` files and assert the Workers route table is set-equal, with a firing control (a route that exists on one side and not the other must make the check fail).
3. **Auth is not silently weakened.** `dgk_live_` verification, admin bearer, jti blocklist fail-closed, and BFF-session semantics must each survive with a negative test (wrong credential → 401, never 200).
4. **The container is removed last and only after every hostname answers from the new workers** — verified by an anonymous probe at each public hostname with a control.

---

## Scope Check

`docs/superpowers/plans/` per the writing-plans skill: **this spec covers three independent subsystems**, so per the skill's Scope Check it must be split into separate plans, one per subsystem, each producing working testable software on its own:

- **Plan A (this document): Foundation + digikey.** digikey is the auth authority and the smallest service (24 `.py` files / 3,168 lines), and the other two depend on its tokens. It is the correct first increment and it delivers a working service.
- **Plan B: digisearch** (160 `.py` / 28,816 lines) — owed after Task 1 resolves the Vectorize index naming; retrieval semantics (pgvector → Vectorize) need their own design pass.
- **Plan C: digigraph** (147 `.py` / 23,045 lines) — owed after Task 1 resolves the orchestration runtime; `langgraph` + `langgraph-checkpoint-*` have no 1:1 JS equivalent, so this is a re-implementation decision, not a port.

Plans B and C are **not** written in this pass; writing placeholder tasks for them would violate the skill's No-Placeholders rule. They are named here so the sequencing is explicit.

---

## Task 1: Resolve the gating architecture decisions (BLOCKING)

**Files:**
- Create: `docs/adr/00XX-digithings-stack-workers-d1-vectorize.md` (next free ADR number — read `docs/adr/README.md` line 9 for the high-water slot)
- Test: none (this task's deliverable is a recorded decision, verified by reading the ADR back)

**Interfaces:**
- Consumes: nothing.
- Produces: `decision.key_hash` (`argon2id` | `bcrypt-wasm` | `verifier-sidecar`), `decision.graph_runtime`, `decision.d1_database_name`, `decision.vectorize_index_name`. Later tasks read these by name from the ADR.

- [ ] **Step 1: Write the ADR skeleton with the three open questions**

Create the ADR with a "Status: Proposed", a "Context" quoting the two blockers verbatim from this plan's background, and three "Decision" subsections (key hashing, graph runtime, D1/Vectorize names).

- [ ] **Step 2: Confirm the blockers are real (do not trust this document)**

Run: `grep -rn "bcrypt" digikey/pyproject.toml digikey/src/digikey/key_crypto.py` and `grep -rn "^langgraph\|langgraph" digigraph/pyproject.toml`
Expected: bcrypt is a declared dependency and imported in `key_crypto.py`; langgraph (and its checkpoint packages) are declared dependencies. If either grep returns nothing, STOP — the premise of this task is wrong and the plan must be re-derived.

- [ ] **Step 3: Record the decisions and route them to the board**

Fill in the ADR decisions, mark it "Decision", and post a single question card on DIG-2914 with `kind: ask_user_questions`, `supersedeOnUserComment: false`, `continuationPolicy: wake_assignee`, `resolverPolicy: human_only`, one question per decision. Do not proceed to Task 2 until answered.

- [ ] **Step 4: Verify the decision landed**

Run: `sed -n '1,200p' docs/adr/00XX-digithings-stack-workers-d1-vectorize.md | grep -c 'Status: Decision'`
Expected: `1`. A card that was merely accepted is an authorisation, not a decision — the ADR must carry the value.

---

## Task 2: Scaffold `apps/digikey-worker`

**Files:**
- Create: `apps/digikey-worker/package.json`
- Create: `apps/digikey-worker/wrangler.toml`
- Create: `apps/digikey-worker/tsconfig.json`
- Create: `apps/digikey-worker/src/index.ts`
- Create: `apps/digikey-worker/src/__tests__/health.test.ts`
- Create: `apps/digikey-worker/vitest.config.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `export default { fetch(request: Request, env: Env): Promise<Response> }`; `interface Env { STACK_DB: D1Database }`.

- [ ] **Step 1: Copy the sibling worker skeleton**

Run: `ls apps/digiquant-runner/{package.json,wrangler.toml,tsconfig.json,vitest.config.ts,src/index.ts}`
Expected: all five exist. Use them as the template — do not invent a build config.

- [ ] **Step 2: Write the failing health test**

```ts
import { describe, it, expect } from "vitest";
import worker from "../index";

describe("health", () => {
  it("answers GET /healthz with ok", async () => {
    const res = await worker.fetch(new Request("http://key.digithings.ai/healthz"), {} as any);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true });
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/health.test.ts`
Expected: FAIL — module or default export not found.

- [ ] **Step 4: Write minimal implementation**

Create `src/index.ts` exporting a default fetch handler that answers `/health` and `/healthz` with `{"ok": true}` (digikey's own health shape — read `digikey/src/digikey/server.py:110-125` and match field names), 404 otherwise. `wrangler.toml` sets `name = "digithings-digikey"`, `account_id`, `compatibility_date`, `nodejs_compat`, `workers_dev = false`, and a `[[d1_databases]]` binding `STACK_DB` using the Task 1 database name.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/health.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): scaffold worker skeleton with health route

Part of DIG-2914.
EOF`

---

## Task 3: D1 schema for digikey (four tables)

**Files:**
- Create: `apps/digikey-worker/migrations/0001_init.sql`
- Create: `apps/digikey-worker/src/schema.ts`
- Test: `apps/digikey-worker/src/__tests__/schema.test.ts`

**Interfaces:**
- Consumes: `Env.STACK_DB` (Task 2).
- Produces: table names `digikey_api_keys`, `digikey_jti_issued`, `digikey_user_profile_pointers`, `digikey_licenses`; `schema.ensureSchema(db: D1Database): Promise<void>`.

- [ ] **Step 1: Write the failing schema test**

Assert each of the four tables exists after `ensureSchema` runs against a test D1, using `SELECT name FROM sqlite_master WHERE type='table'` and a set comparison that requires all four.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/schema.test.ts`
Expected: FAIL — tables missing.

- [ ] **Step 3: Write minimal implementation**

Translate the four Postgres tables from `digikey/src/digikey/db_schema.py` (`digikey_api_keys` :24, `digikey_jti_issued` :53, `digikey_user_profile_pointers` :93, `digikey_licenses` :126) to SQLite DDL. Map types: `TIMESTAMPTZ` → `TEXT` (ISO-8601), `UUID`/`TEXT` → `TEXT`, `JSONB` → `TEXT`. Preserve every unique constraint and index as a `CREATE UNIQUE INDEX` / `CREATE INDEX`. Store each table's original Postgres DDL as a comment above its SQLite equivalent so a reviewer can diff them.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/schema.test.ts`
Expected: PASS.

- [ ] **Step 5: Prove the translation is faithful**

Run: `grep -c 'CREATE TABLE' apps/digikey-worker/migrations/0001_init.sql`
Expected: `4`. Any other number means a table was dropped or duplicated — stop.

- [ ] **Step 6: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): D1 schema for the four digikey tables

Part of DIG-2914.
EOF`

---

## Task 4: Announce the new host route without cutting over

**Files:**
- Modify: `apps/digikey-worker/wrangler.toml` (add `[[routes]]` for `key.digithings.ai` **commented out** with a pointer to Task 12)
- Test: `apps/digikey-worker/src/__tests__/routes.test.ts`

**Interfaces:**
- Consumes: Task 2 skeleton.
- Produces: nothing executable — this task records the cutover intent so Task 12 is mechanical.

- [ ] **Step 1: Write a test pinning that the route block is NOT live yet**

Assert the raw `wrangler.toml` text contains `# cutover:` and does NOT contain an uncommented `pattern = "key.digithings.ai"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/routes.test.ts`
Expected: FAIL.

- [ ] **Step 3: Add the commented route block**

Add the `# cutover: enabled in Task 12` block. Do not enable it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/routes.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): record (commented) host route for cutover

Part of DIG-2914.
EOF`

---

## Task 5: RS256 JWT signing via WebCrypto

**Files:**
- Create: `apps/digikey-worker/src/jwt.ts`
- Test: `apps/digikey-worker/src/__tests__/jwt.test.ts`

**Interfaces:**
- Consumes: `Env.DIGIKEY_PRIVATE_KEY_PEM: string`, `Env.DIGIKEY_KEY_ID: string`, `Env.DIGIKEY_ISSUER: string`, `Env.DIGIKEY_AUDIENCE: string`, `Env.DIGIKEY_JWT_TTL_SEC: string`.
- Produces: `signJwt(claims: Record<string, unknown>, env: Env): Promise<string>`; `publicJwks(env: Env): Promise<Jwks>`.

- [ ] **Step 1: Write the failing test**

Sign a claim set, then verify the signature with the public key derived from the same PEM; assert the header carries `alg: RS256` and `kid === env.DIGIKEY_KEY_ID`, and that the JWKS contains the matching `kid`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/jwt.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Use `crypto.subtle.importKey("pkcs8", …)` + `crypto.subtle.sign({ name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, …)`. Mirror the claim set field-for-field from `digikey/src/digikey/jwt_issue.py` (read lines 60-120) — do not invent claims. Export the JWKS shape from `server.py`'s `/.well-known/jwks.json` handler (:127).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/jwt.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): RS256 JWT signing and JWKS via WebCrypto

Part of DIG-2914.
EOF`

---

## Task 6: Port `POST /v1/oauth/token`

**Files:**
- Create: `apps/digikey-worker/src/routes/oauth-token.ts`
- Test: `apps/digikey-worker/src/__tests__/oauth-token.test.ts`

**Interfaces:**
- Consumes: `signJwt` (Task 5), `schema` (Task 3).
- Produces: `handleOauthToken(request: Request, env: Env): Promise<Response>`.

- [ ] **Step 1: Write the failing test**

Table-driven from the Python handler `digikey/src/digikey/server.py:239-382`: (a) a valid API key → 200 with `access_token`; (b) a wrong key → 401; (c) a revoked key → 401. Each negative asserts a non-200, per the Review Focus rule.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/oauth-token.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Read the Python handler in full and reproduce its decisions in order — request parsing, key lookup, verification, issuance, `digikey_jti_issued` insert. Do not add or drop a branch. Route the API-key verification through Task 7's `verifyApiKey`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/oauth-token.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): port POST /v1/oauth/token

Part of DIG-2914.
EOF`

---

## Task 7: API-key hashing and verification (the Task 1 decision)

**Files:**
- Create: `apps/digikey-worker/src/key-crypto.ts`
- Test: `apps/digikey-worker/src/__tests__/key-crypto.test.ts`

**Interfaces:**
- Consumes: `env.key_hash` decision from Task 1.
- Produces: `hashSecret(secret: string): Promise<string>`; `verifySecret(secret: string, hash: string): Promise<boolean>`.

- [ ] **Step 1: Write the failing test**

Round-trip: `verifySecret(s, await hashSecret(s))` is true; `verifySecret("wrong", h)` is false; a malformed stored hash returns false rather than throwing.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/key-crypto.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Implement whichever of `argon2id` / `bcrypt-wasm` / `verifier-sidecar` Task 1 chose. If the decision is a migration off bcrypt, include the legacy-path read (verify against a stored `$2b$` bcrypt hash) plus a re-hash-on-successful-login path, and a test proving a legacy hash verifies once and is upgraded.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/key-crypto.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): api-key hashing and verification

Part of DIG-2914.
EOF`

---

## Task 8: Port the admin-gated key routes

**Files:**
- Create: `apps/digikey-worker/src/admin.ts`
- Create: `apps/digikey-worker/src/routes/admin-keys.ts`
- Test: `apps/digikey-worker/src/__tests__/admin-keys.test.ts`

**Interfaces:**
- Consumes: `Env.DIGIKEY_ADMIN_TOKEN`, `hashSecret` (Task 7), `schema` (Task 3).
- Produces: `requireAdmin(request: Request, env: Env): Response | null`; `handleAdminCreateKey`; `handleAdminRevokeKey`.

- [ ] **Step 1: Write the failing tests**

Cover `POST /v1/admin/keys` (:177) and `POST /v1/admin/keys/{key_id}/revoke` (:383): (a) no admin bearer → 401; (b) wrong bearer → 401; (c) correct bearer → 201/200 with the `dgk_live_`-prefixed key on create.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/admin-keys.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Reproduce `_require_admin()` (:133-139) exactly — constant-time comparison against `DIGIKEY_ADMIN_TOKEN`. Port both handlers branch-for-branch.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/admin-keys.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): port admin key create/revoke routes

Part of DIG-2914.
EOF`

---

## Task 9: Port the revoked-jti blocklist (fail-closed)

**Files:**
- Create: `apps/digikey-worker/src/blocklist.ts`
- Test: `apps/digikey-worker/src/__tests__/blocklist.test.ts`

**Interfaces:**
- Consumes: `Env.DIGIKEY_REQUIRE_BLOCKLIST`, `Env.STACK_DB`.
- Produces: `isBlocked(jti: string, env: Env): Promise<boolean>`; `revokeJti(jti: string, exp: number, env: Env): Promise<void>`.

- [ ] **Step 1: Write the failing test**

With `DIGIKEY_REQUIRE_BLOCKLIST=1` and a missing/unreachable store, `isBlocked` must THROW (fail-closed), not return false. With a working store, a revoked jti returns true and an unknown jti false.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/blocklist.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Port `digikey/src/digikey/blocklist.py` (`_KEY_PREFIX="jti:"` :24; fail-closed :54-57) onto the `digikey_jti_issued` table, honouring expiry. Keep the Redis→D1 semantic that a store failure under `REQUIRE_BLOCKLIST=1` is a hard error.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/blocklist.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): port jti blocklist fail-closed onto D1

Part of DIG-2914.
EOF`

---

## Task 10: Port BFF-session and license routes

**Files:**
- Create: `apps/digikey-worker/src/routes/bff-sessions.ts`
- Create: `apps/digikey-worker/src/routes/licenses.ts`
- Test: `apps/digikey-worker/src/__tests__/bff-licenses.test.ts`

**Interfaces:**
- Consumes: `requireAdmin`, `schema`.
- Produces: `handleBffSessionRevoke` (`POST /v1/admin/bff-sessions/revoke` :437); `handleLicenseHeartbeat` (`POST /v1/licenses/heartbeat` :497); `handleLicenseRevoke` (`POST /v1/admin/licenses/{license_id}/revoke` :611).

- [ ] **Step 1: Write the failing tests**

One positive and one negative per route, negative asserting non-200 (wrong `DIGIKEY_BFF_TOKEN` for the BFF route; missing license for the license route).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/bff-licenses.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Port each Python handler (:437, :497, :611) branch-for-branch onto `digikey_licenses` / `digikey_user_profile_pointers`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/digikey-worker && npx vitest run src/__tests__/bff-licenses.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add apps/digikey-worker && git commit -s -F - <<'EOF'
feat(digikey-worker): port bff-session revoke and license routes

Part of DIG-2914.
EOF`

---

## Task 11: Route-parity sweep for digikey

**Files:**
- Create: `scripts/check_digikey_route_parity.py`
- Test: `tests/scripts/test_check_digikey_route_parity.py`

**Interfaces:**
- Consumes: `digikey/src/digikey/server.py` (source of truth) and `apps/digikey-worker/src/index.ts` (target).
- Produces: an exit code — 0 when the route sets are equal, 1 otherwise.

- [ ] **Step 1: Write the failing test**

The test seeds a synthetic source route list and a target list missing one entry, asserts the checker exits 1. Then seeds equal lists, asserts exit 0. This is the firing control the Review Focus requires.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_check_digikey_route_parity.py -v`
Expected: FAIL — checker missing.

- [ ] **Step 3: Write minimal implementation**

Parse `(method, path)` pairs from the Python file's `@app.<method>("<path>")` decorators and from the TS router table; assert set equality; print the symmetric difference on failure.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_check_digikey_route_parity.py -v`
Expected: PASS.

- [ ] **Step 5: Run it against the real trees**

Run: `python3 scripts/check_digikey_route_parity.py`
Expected: exit 0, printing the 9 routes on both sides. Anything else means a route is missing — stop and fix before cutover.

- [ ] **Step 6: Commit**

Run: `git add scripts/check_digikey_route_parity.py tests/scripts/test_check_digikey_route_parity.py && git commit -s -F - <<'EOF'
test(digikey): route parity checker between python source and worker

Part of DIG-2914.
EOF`

---

## Task 12: Enable the route and verify from outside (gated)

**Files:**
- Modify: `apps/digikey-worker/wrangler.toml` (uncomment the `key.digithings.ai` route)
- Modify: `apps/digithings-stack-cloudflare/wrangler.toml` (remove the `key.digithings.ai` hostname mapping :48-52)
- Modify: `apps/digithings-stack-cloudflare/src/ports.ts` (drop the `key` → 8005 entry :64-81)

**Interfaces:**
- Consumes: every prior task in this plan.
- Produces: a deployed digikey Worker owning `key.digithings.ai`.

- [ ] **Step 1: Confirm the approval gate**

Do not run any command in this task until the human approval is recorded on DIG-2914. If it is not, STOP and report.

- [ ] **Step 2: Deploy the worker**

Run: `cd apps/digikey-worker && npx wrangler deploy`
Expected: a deployment id; a `key.digithings.ai` route claimed.

- [ ] **Step 3: Probe the public hostname anonymously with a control**

Run: `curl -s -o /dev/null -w '%{http_code}\n' https://key.digithings.ai/healthz` and, as the control, `curl -s -o /dev/null -w '%{http_code}\n' https://key.digithings.ai/no-such-path-xyz`
Expected: `200` and a `404` respectively — the second proves the first is not a catch-all.

- [ ] **Step 4: Commit**

Run: `git add apps/digikey-worker apps/digithings-stack-cloudflare && git commit -s -F - <<'EOF'
feat(digikey-worker): cut key.digithings.ai over to the worker

Part of DIG-2914.
EOF`

---

## Task 13: Remove `DigiStackContainer` and the stack container routing (gated)

**Files:**
- Modify: `apps/digithings-stack-cloudflare/wrangler.toml` (delete the `[[containers]] DigiStackContainer` block :113-140 and its `class_name`/`new_sqlite_classes` registration :180/:192)
- Modify: `apps/digithings-stack-cloudflare/src/index.ts` (delete the container-routes catch-all :635-647 and the `STACK` container accessor)
- Test: `apps/digithings-stack-cloudflare/src/__tests__/no-stack-container.test.ts`

**Interfaces:**
- Consumes: Task 12 (digikey live). digisearch and digigraph must ALSO already be live on their own workers — this task is the LAST step of the epic, not of Plan A.
- Produces: a stack worker with no `DigiStackContainer`.

- [ ] **Step 1: Write the failing test**

Assert the raw `wrangler.toml` contains no `DigiStackContainer` and `src/index.ts` contains no `SHARED_STACK_CONTAINER_ID`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/digithings-stack-cloudflare && npx vitest run src/__tests__/no-stack-container.test.ts`
Expected: FAIL.

- [ ] **Step 3: Remove the container block, registration and routing**

Delete exactly the three regions named in **Files**. Leave `DigiQuantMcpContainer` and `DigiChatContainer` untouched — they are a different removal (DIG-2887 family).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/digithings-stack-cloudflare && npx vitest run src/__tests__/no-stack-container.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit (gated)**

Run: `git add apps/digithings-stack-cloudflare && git commit -s -F - <<'EOF'
feat(stack): remove DigiStackContainer and its routing

Part of DIG-2914. Last step of the split; requires digisearch + digigraph workers live.
EOF`

---

## Self-Review

**(1) Spec coverage.** DIG-2914 asks for digikey / digigraph / digisearch on Workers + D1/Vectorize and the removal of the Profile A container. Covered: digikey end-to-end (Tasks 2-13), container removal (Task 13), D1 (Tasks 3, 9), and the gating decisions for the other two (Task 1). **Gaps, stated plainly:** digisearch and digigraph have NO task detail here — by the Scope Check they are Plans B and C, owed after Task 1. Vectorize has no task in this plan because no service in Plan A uses it. This is a deliberate, named deferral, not an omission.

**(2) Placeholder scan.** No "TBD", no "add appropriate error handling", no "similar to Task N", no reference to an undefined type. Tasks that depend on a decision (7, 9) name the decision and the branch to take for each option rather than leaving it blank.

**(3) Type consistency.** `Env` gains `STACK_DB`, `DIGIKEY_PRIVATE_KEY_PEM`, `DIGIKEY_KEY_ID`, `DIGIKEY_ISSUER`, `DIGIKEY_AUDIENCE`, `DIGIKEY_JWT_TTL_SEC`, `DIGIKEY_ADMIN_TOKEN`, `DIGIKEY_BFF_TOKEN`, `DIGIKEY_REQUIRE_BLOCKLIST` in Task 2 and is consumed unchanged thereafter. `signJwt`, `hashSecret`, `verifySecret`, `isBlocked`, `revokeJti`, `requireAdmin` are each defined once and referenced by the exact name in later tasks.

**(4) Honest limits.** This plan does NOT cover: the TypeScript/D1 data migration of live rows out of Postgres (a cutover-runbook step owned by the same task that probes production), the D1 database creation itself (`wrangler d1 create` needs the Task 1 name and the approval gate), or Vectorize index creation. Each is named where it belongs.

---

## Execution Handoff

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Use `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Before either:** Task 1 is BLOCKING and requires a human decision on all three questions. Plans B and C are owed after that decision.

**Gate:** no deploy, no merge, no `--remote` D1 write without the DIG-2914 approval being recorded first.
