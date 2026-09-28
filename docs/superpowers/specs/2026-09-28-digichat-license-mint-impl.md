# digichat license-mint CLI + issuance flow (implementation spec, slice 1)

- **Date:** 2026-09-28
- **Status:** Implementation spec — authorizes one implementing task PR; runtime changes land through that PR with the digikey human gate
- **Binds to:** [digichat customer license design](2026-09-27-digichat-customer-license-design.md) (rev 4, eight owner decisions; this spec implements decision 5, issuance half)
- **Scope:** owner-run `license-mint` CLI, license JWT construction, `license_id` allowlist registry, CLI revoke, rotation procedure, manual email delivery. Nothing else.
- **Human gate:** slice 1 touches `digikey/` JWT issuance (auth/crypto path). Per root `AGENTS.md` the implementing PR needs owner review and must not merge on green CI alone. This spec itself is docs-only.

## 0. How to execute this spec (read this first, executor)

1. **Read first:** `digikey/AGENTS.md` (pre-flight checklist), `digikey/ARCHITECTURE.md` §3 (API surface) and §5 (security analysis), then the bound design spec above. Never skip the component `AGENTS.md`.
2. **Branching:** the implementing change touches `digikey/` code, so it is `component:digikey` and goes through the module tier per `scripts/project_routing.json` — cut with `make task ISSUE=N`, never from a stale base.
3. **Spec file ≠ code file:** this document prescribes interfaces, behavior, and acceptance. Exact function names below are recommendations; what is binding is the CLI contract (§2), the claims table (§3), the registry shape (§4), and the acceptance checklist (§9).
4. **Conventions:** Pydantic v2, strict typing, ruff line length 100, lowercase digi names in prose. Raw key/license material is never logged — only `license_id` and customer slug are safe to log (same rule as `key_id`/prefix in `digikey/AGENTS.md`).
5. **Tests:** `pytest tests/ -m unit -k "digikey" -v` passes before and after; `ruff check digikey/ && ruff format --check digikey/`. No stack required (sqlite).

## 1. Locked decisions (inherited — not re-decided here)

| # | Decision (from the design spec log) | Slice-1 consequence |
|---|---|---|
| D1 | Keypair reuse — licenses mint with the existing digikey RS256 access-token keypair | CLI loads the same signing key the server uses (`load_or_create_signing_key` in `digikey/src/digikey/crypto_keys.py`); no new keypair, no new env var |
| D5 | Issuance is owner-run CLI; self-serve minting endpoint deferred | No new HTTP endpoint in slice 1. No `POST /v1/admin/licenses`. Delivery is manual email (§7) |
| D4 | Raw license JWT, `aud=digichat-license`, ~90d TTL | Claims table §3 is fixed; no derived-token work |
| D8 | Heartbeat presents the same JWT as a Bearer token; server checks signature + allowlist + expiry keyed off `license_id` | Slice 1 writes the allowlist rows the heartbeat slice will read (§4, §5). The heartbeat endpoint itself is a later slice (non-goal) |

## 2. CLI surface

New `license-mint` subcommand on the existing `digikey` CLI (`digikey/src/digikey/cli.py:10-32`, argparse subparsers pattern). Mirrors `issue-key`, mints a license JWT instead of an opaque API key.

### 2.1 Arguments

| Argument | Required | Default | Meaning |
|---|---|---|---|
| `--customer` | yes | — | Customer slug, e.g. `datatap`. Becomes `sub` and `tenant_slug`. Blank/whitespace rejected (same guard as `--tenant` at `cli.py:32-34` and `_nonblank_tenant_slug` at `server.py:125-135`) |
| `--hosts` | yes | — | Comma-separated embed-parent hostnames, e.g. `datatapstream.com,www.datatapstream.com`. Becomes `hosts`. At least one non-blank entry required |
| `--term-days` | no | `90` | Commercial term length in days. Positive int, upper bound 180 (longer terms need an owner decision, not a flag) |
| `--services` | no | absent | Comma-separated hosted-service scopes, e.g. `digisearch-corpus,hosted-web-search`. Omitted entirely when not passed (absent means entitled to the hosted services of the commercial term — design § License claims). Unknown scope strings rejected against a fixed allowlist `{"digisearch-corpus", "hosted-web-search"}` kept next to the CLI |
| `--label` | no | `""` | Human-readable label stored on the registry row, never in the JWT |

Open question recorded (not blocking): whether `--hosts` should stay required if a future customer has no stable embed parents. For the pilot it is required; relaxing it later is a spec amendment, not implementer discretion.

### 2.2 Environment and guards

- `DIGIKEY_DATABASE_URL` required — same fail-loud behavior as `issue-key` (`cli.py:36-39`).
- `DIGIKEY_PRIVATE_KEY_PEM` required to be set. The CLI must refuse to mint when the signing key would be ephemeral (`DIGIKEY_ALLOW_EPHEMERAL_KEY=1` path in `crypto_keys.py`): a license signed by a throwaway key can never verify, so minting under it is always a bug. Exit non-zero with a message naming the missing env var.
- No `dev_global`-style bypass kind. Licenses are always customer-scoped; there is no global license.

### 2.3 Outputs (stdout contract)

On success the CLI prints exactly four lines (mirroring `cli.py:73-75`):

```text
license_id=9f3c…
customer=datatap
exp=1785004800
license_jwt=<compact RS256 JWT, shown once>
```

- The JWT is shown once, like the raw `dgk_live_` key: it is not stored anywhere retrievable, so the owner copies it into the delivery email immediately (§7).
- Nothing secret-adjacent beyond the JWT itself appears: no private key material, no admin token. `license_id`, customer, and `exp` are safe to log and to keep in the commercial record.
- Exit codes: `0` on success; `1` on missing env; `2` (argparse) on bad args; non-zero with `license not found`-style message reserved for the revoke path (§5). Re-minting for the same customer creates a new row and a new `license_id` — mint is append-only, never upsert.

### 2.4 `--dry-run` (recommended, not binding)

A `--dry-run` flag that validates args, loads the key, builds the claims, and prints them as JSON without signing or inserting a row. Cheap to add on the same path; gives the owner a pre-send check. Binding requirement is only that dry-run, if shipped, writes nothing.

## 3. JWT claims table

Construction reuses `issue_access_token()` (`digikey/src/digikey/jwt_issue.py:23-85`): RS256, `kid` header, `DIGIKEY_JWT_TTL_SEC` overridden by an explicit `ttl_sec = term_days * 86400`. License-specific claims ride the same pairwise-omit pattern as `profile_id`/`profile_version` (`jwt_issue.py:76-79`) — omitted when absent, never half-emitted. Recommended shape is a thin `issue_license_token()` wrapper in the same module (same review, same key handling); adding optional `hosts`/`services`/`kind` parameters to the shared function is equivalent. What is binding is the emitted claims table:

| Claim | Value | Source |
|---|---|---|
| `iss` | existing digikey issuer (`_issuer()`, `jwt_issue.py:19-20`) | reuse — `aud` discriminates license from access token |
| `aud` | `digichat-license` | constant; a license never validates as an access token and vice versa |
| `sub` | customer slug | `--customer` |
| `tenant_slug` | mirrors `sub` | keeps the digikey claim vocabulary |
| `jti` | fresh uuid4 hex | same generation as `jwt_issue.py:55`; this value is the `license_id` |
| `license_id` | mirrors `jti` | explicit duplicate for heartbeat/edge correlation without jti literacy |
| `hosts` | list of hostnames | `--hosts`, non-empty |
| `services` | list of scopes | `--services`; omitted entirely when not passed |
| `kind` | `digichat-license` | constant discriminator on top of `aud` |
| `iat` / `exp` | now / now + term | `exp - iat == term_days * 86400`; default 90d = 7776000s |
| `scope` | `" ".join(services)` when services present, else omitted | follows the existing `scope` mirror convention (`jwt_issue.py:80`) without inventing access semantics |

Deliberately absent: `scopes` (access-token vocabulary — licenses carry `services`), `key_pub`, `principal_kind`, `project_id`, `tenant_id`, `max_version` (unpinned by owner decision), `features` (dropped in design rev 1 — no licensed capabilities exist).

Verifier-side notes (for the later slices, stated here so the minter does not break them): `exp`/`iat` checks allow ~5 minutes of clock-skew leeway (design § Container verification); `services`-absent means entitled, not unentitled.

## 4. Registry schema (the `license_id` allowlist)

### 4.1 New table, not a reuse

A new `digikey_licenses` table (`digikey/src/digikey/db_schema.py`, next to `ApiKeyRow`). Rationale, stated so a future reader does not "simplify" it away:

- `ApiKeyRow` stores bcrypt hashes of opaque secrets (`key_crypto.py:20-28`). A license is a signed JWT, not a presented secret — there is nothing to hash, and stuffing a `license_id` into the API-key registry would entangle heartbeat allowlist reads with bcrypt verification paths.
- The design (rev 4, decision 8) requires the heartbeat/edge to answer three distinct states keyed off `license_id`: valid, revoked, unknown. That is a nullable-`revoked_at` row lookup, mirroring the `ApiKeyRow.revoked_at` convention (`db_schema.py:40`).

Recommended columns:

| Column | Type | Notes |
|---|---|---|
| `license_id` | `String(36)`, PK | the JWT `jti`; stable id per issuance |
| `customer_slug` | `String(256)`, indexed, NOT NULL | mirrors `sub`/`tenant_slug` |
| `hosts` | JSON list, NOT NULL | as minted |
| `services` | JSON list, nullable | NULL = absent = entitled |
| `issued_at` | tz datetime, `server_default=func.now()` | follows `ApiKeyRow.created_at` |
| `expires_at` | `Integer`, NOT NULL | unix `exp`, so allowlist reads can report expired without parsing the JWT |
| `revoked_at` | tz datetime, nullable | NULL = live; set = revoked |
| `label` | `String(256)`, nullable | owner note, never in the JWT |

### 4.2 Migration story: none needed

`init_db()` uses `create_all`, which creates missing tables but never alters existing ones (`digikey/src/digikey/db_migrate.py` header). A brand-new table is picked up automatically on next startup — no `db_migrate.py` addition, no backfill. State this in the implementing PR so reviewers do not ask for a migration module.

### 4.3 What is NOT recorded

License jtis are NOT written to `JtiIssuedRow` and NOT pushed to the Redis blocklist. The blocklist is a short-TTL mechanism for short-lived access JWTs (default 900s, `ARCHITECTURE.md` §5); a 90-day blocklist entry per license would be pure weight with no reader — revocation for licenses is enforced at the heartbeat and at our edge via the allowlist (§5), never via jti blocklist. If a future slice wants belt-and-braces blocklisting, that is a new spec, not an drive-by.

### 4.4 Allowlist read contract (for the heartbeat slice — normative here)

Later heartbeat/edge code resolves a presented `license_id` to exactly one state:

| State | Row condition | Meaning |
|---|---|---|
| valid | row exists, `revoked_at IS NULL`, `expires_at > now` | serve / authorize |
| expired | row exists, `revoked_at IS NULL`, `expires_at <= now` | identified-but-lapsed: report expired, refuse hosted-service and product-traffic authorization on expiry grounds (design § Heartbeat receiver) |
| revoked | row exists, `revoked_at IS NOT NULL` | explicit deny → revoke latch (design § Response handling) |
| unknown | no row | explicit deny, distinct answer from revoked (mirrors the unknown-401 vs revoked-401 distinction at `server.py:315-318`) |

Slice 1 implements the write side (mint inserts, revoke sets `revoked_at`); the read side ships with the heartbeat slice against this contract.

## 5. Revoke / allowlist wiring (slice-1 portion)

- **CLI:** `digikey license-revoke --license-id <jti>` sets `revoked_at = utcnow()` on the matching row. Idempotent (re-revoking prints `revoked=true, already_revoked=true`-style output, exit 0). Unknown `license_id` is an error (exit non-zero, `license not found`) — distinct from revoked, preserving the unknown-vs-revoked distinction end to end.
- **No HTTP endpoint in slice 1.** Revocation is owner-run at a terminal against the same database the server reads — revoking needs no redeploy on either side by design. An admin HTTP revoke (mirroring `POST /v1/admin/keys/{key_id}/revoke`, `server.py:366-403`) arrives with the heartbeat slice, which needs server-side allowlist access anyway; speccing it now would freeze an API its only consumer does not exist yet.
- **Drill acceptance (design § Rollout step 5, runnable with slice 1 alone):** mint → confirm row live → `license-revoke` → confirm `revoked_at` set → re-mint for the same customer yields a distinct `license_id` that reads live. The stop-serving half of the drill waits for the heartbeat slice.

## 6. Rotation story (digikey keypair)

Constraint: `public_jwks()` serves a single key (`jwt_issue.py:88-99`), and customer containers carry the public key via `DIGIKEY_PUBLIC_KEY_PEM`, which supports a list (current + previous) per the design § Container verification. Rotation is therefore procedural — no server change in slice 1:

1. Generate the new RSA keypair offline; note its `kid`.
2. Ask each active customer to append the new public PEM to their public-key list (tolerate both keys). No urgency: old licenses keep verifying against the old entry.
3. Switch digikey to the new private key (`DIGIKEY_PRIVATE_KEY_PEM`). All new mints sign with the new `kid`.
4. After every license minted under the old key has expired or been re-minted (bounded by the 90-day term), customers drop the old PEM from their list.

Invariants the procedure relies on (do not break in slice 1): the `kid` header stays set on every mint (it is the only signal distinguishing pre- from post-rotation licenses in edge logs); `issue_access_token` defaults (`aud=digi-ecosystem`, 900s TTL) stay untouched — license values are always passed explicitly.

## 7. Email delivery mechanism (manual, pilot)

No code. The owner copies the one-time `license_jwt` stdout line into the existing commercial channel (email) together with:

1. the `DIGIKEY_PUBLIC_KEY_PEM` value active at mint time (public — safe to email),
2. the customer config block: which env var/file carries the JWT, the `hosts` it was minted for, the `exp` date in plain language (term end),
3. the renewal note: each digichat release ships a fresh license; rotation is a side effect of staying current (design § Issuance flow).

Operating rules (binding on the human, not the code): never commit a JWT to the repo, never paste one into an issue or PR, never bake one into an image layer (same prohibition as tenant tokens, `Dockerfile.digichat-cloudflare:4-5`). If a JWT is ever exposed in the wrong place, revoke and re-mint — the drill in §5 is the recovery procedure.

## 8. Test plan

Unit only, no stack (sqlite via `DIGIKEY_DATABASE_URL`, same as the existing digikey suite):

| Area | Cases |
|---|---|
| Claims table | golden JWT decode: every row of §3 present with exact values; `aud` is `digichat-license` and validates as neither `digi-ecosystem` access token nor vice versa; default term is exactly 7776000s; `services` key absent (not empty) when `--services` omitted; `scope` mirror present iff services present |
| CLI validation | blank `--customer` rejected; empty `--hosts` rejected; `--term-days 0` / negative / `>180` rejected; unknown `--services` entry rejected; missing `DIGIKEY_DATABASE_URL` exits non-zero; missing `DIGIKEY_PRIVATE_KEY_PEM` (ephemeral path) refuses to mint |
| Registry | mint inserts a live row retrievable by `license_id`; re-mint same customer yields distinct `license_id`; revoke sets `revoked_at`, is idempotent, unknown id errors distinctly; `create_all` picks up the new table on a fresh database |
| Rotation-adjacent | mint under key A verifies against public key A; `kid` header present and stable per key |

Selectors: `pytest tests/ -m unit -k "digikey" -v`; `ruff check digikey/ && ruff format --check digikey/`. The implementing PR states the exact new test file paths; binding requirement is the case coverage above, not file names.

## 9. Acceptance criteria

- [ ] `digikey license-mint --customer <slug> --hosts <h1,h2>` prints `license_id`, `customer`, `exp`, `license_jwt` and inserts a live `digikey_licenses` row; the JWT decodes (offline, public key) to exactly the §3 claims table
- [ ] Defaults hold without flags: 90-day term, no `services` key, `aud=digichat-license`, `kind=digichat-license`, `iss` equal to the access-token issuer
- [ ] `digikey license-revoke --license-id <jti>` flips the row to revoked idempotently; unknown ids error distinctly from revoked ones
- [ ] Mint refuses without `DIGIKEY_PRIVATE_KEY_PEM` (no ephemeral-key licenses, ever) and without `DIGIKEY_DATABASE_URL`
- [ ] No new HTTP route, no change to `issue_access_token` defaults, no `JtiIssuedRow`/blocklist writes, no migration module — reviewer can verify each absence by grep
- [ ] `digikey/ARCHITECTURE.md` updated: license claims, `digikey_licenses` table, and the §4.4 read contract documented where the heartbeat slice will find them
- [ ] Revocation drill (§5) run by the owner against a scratch database before the implementing PR leaves draft
- [ ] Unit suite + ruff clean per §8; this spec's `make doc-check` green

## 10. Non-goals (explicit)

- **Heartbeat endpoint** (`POST` against digikey carrying the Bearer license JWT) — next slice, reads the §4.4 contract.
- **Container verification and heartbeat scheduler** (digichat startup path, `startLicenseHeartbeat`) — digichat slice, not digikey.
- **Edge enforcement** (digigraph header-to-scope checks) — services slice.
- **Self-serve/admin minting endpoint** — deferred by owner decision (D5); a `POST /v1/admin/licenses` proposal in the implementing PR is out of scope and must be split out.
- **Usage metering, billing, seat counting** — there is no meter in this program (design § Non-goals).
- **JWKS multi-key serving** — rotation is procedural (§6); changing `public_jwks()` to serve a key set is not slice 1.
- **Changing access-token behavior** — TTL default, `aud` default, bcrypt paths, and the existing revoke endpoint are untouched.

## Verification (this spec — docs-only)

- No code changed by this spec.
- Every file:line claim grounded against `origin/develop`: `jwt_issue.py:23-85` (issue function, aud/TTL overrides, profile pairwise-omit `:76-79`, `scope` mirror `:80`, single-key JWKS `:88-99`), `cli.py:10-32` (subparser/args), `:32-39` (tenant guard, DB-url guard), `:51-75` (keygen/hash/insert/print), `server.py:54` (module-level signing-key load), `:116-135` (admin bearer, tenant guard), `:160-194` (admin issue endpoint), `:309-318` (prefix lookup, bcrypt verify, unknown-401 vs revoked-401), `:366-403` (revoke endpoint, 404, blocklist write, 503-on-failure), `key_crypto.py:12-28` (generate/hash/verify), `db_schema.py:23-40` (`ApiKeyRow`, `revoked_at`), `db_migrate.py` header (`create_all` + in-place upgrade pattern), `crypto_keys.py` (`load_or_create_signing_key`, ephemeral-key gate), `ARCHITECTURE.md:153` (exp convention) and §5 (blocklist semantics).
- No license code exists yet in `digikey/src` (grep for `license` returns nothing) — slice 1 is greenfield on the reuse seams above.
- Internal links: design spec linked by filename in the same directory.
- `make doc-check` run to confirm internal links resolve (see task report).
