# settings Edge Function (T3)

Authenticated Settings backend for the digiquant dashboard: investment profile overlays, broker
connect/revoke, and notification prefs.

| Setting | Value |
|---------|-------|
| `verify_jwt` | **true** |
| CORS | OPTIONS → 204 + Allow-* (digiquant.io browser callers) |
| Deploy | After K3 + migrations **096–108** (108 = creator/product grants) + **112** (invite codes) |

## Tier gate (effective plan)

Writes to Profile / Pipeline / Keys require **effective** plan_tier ∈
(`studio`, `enterprise`). Brokers require **desk+** (`desk`, `studio`,
`enterprise`). Effective = `max(workspaces.plan_tier,
entitlement_grants.plan_floor)` (migration **108**, ranks remapped in **115**).
Creator seed (`chris.stefan@proton.me` → `studio`) unlocks Kairos Settings
without Stripe. JWT claim alone is not authoritative.

## Deploy gate — blocked on K3 + tenancy migrations

This function seals broker credentials with the K3 vault public contract
(`parseCredential` / `sealCredential` / AAD binding) and writes
`broker_connections`. It also stamps `olympus_profile_config.workspace_id`
(added in migration **097**).

**Do not deploy until all of the following are on the deploy target:**

1. Module migrations **096–098** (workspaces foundation, tenant columns including
   `olympus_profile_config.workspace_id`, RLS hardening).
2. K3 (`digiquant.vault.envelope` + migration `099_broker_connections.sql`).
3. K5 migration **103** (`notification_prefs` + `notification_log`) for
   `GET` / `PATCH /notifications`.

Until then:

1. **Do not** `supabase functions deploy settings`.
2. Frontend may still call the URL — the function returns clear errors
   (`NOT_READY` / `ADMIN_NOT_CONFIGURED`) when tables or vault key are absent.
3. After preconditions land: set `DIGIQUANT_VAULT_MASTER_KEY` (and optional
   `DIGIQUANT_VAULT_KEY_ID`), `APP_URL` (pinned OAuth `redirect_uri`), then:

```bash
supabase functions deploy settings
```

The TypeScript vault under `_shared/vault.ts` mirrors the Python public API and
must pass `_shared/vault-vectors.json` (copied from K3's `tests/dq/vault/vectors.json`),
including `negative_cases`.

Profile schema re-validation imports the real
`digiquant/docs/schemas/{investment_profile,asset_preferences}.v1.json` files
(no hand-copied TS transcription).

## Routes

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/profile` | Load tip `olympus_profile_config` for workspace member (`?workspace_id=` / `?profile_key=` optional, default key `workspace`). **Empty contract:** no tip → **200** with `version_id`/`recorded_at` null, empty `label`, null investment/assets — read-only, never inserts. `house` key → **400**. Missing table → **503 `NOT_READY`**. No Studio-tier write gate (read for hydrate). Includes workspace `plan_tier` + `subscription_status` + `has_stripe_subscription` (boolean only; never `stripe_customer_id` / `stripe_subscription_id`). **Observer bootstrap:** if the JWT user has no `workspace_members` row, the handler calls `ensure_personal_workspace` (migration 107) before resolve — creates a free personal workspace + owner membership (never system/house). |
| `PATCH` | `/profile` | Tier gate; schema re-validate; append workspace-scoped version; reject `house` key; 409 on version/supersedes conflict |
| `GET` | `/brokers` | Fingerprint projection only |
| `POST` | `/brokers/connect` | Tier gate; `api_key` or Alpaca `oauth` (server-pinned `redirect_uri`); seal via vault; reconnect = revoke-then-insert |
| `POST` | `/brokers/revoke` | Fail closed on unknown row |
| `GET` | `/keys` | BYOK fingerprint projection only (`workspace_provider_credentials`) |
| `POST` | `/keys/connect` | Tier gate; seal LLM `api_key` with AAD `workspace:provider:llm`; reconnect = revoke-then-insert |
| `POST` | `/keys/revoke` | Fail closed on unknown row |
| `GET` | `/notifications` | Load `notification_prefs` for workspace member (`?workspace_id=` optional). **Empty contract:** no row → **200** with defaults (`daily_digest`/`holding_change_alerts`/`execution_alerts` false, `digest_hour_utc` 12, `email` from JWT when present, `updated_at: null`) — read-only, never inserts. Missing table → **503 `NOT_READY`**. |
| `GET` | `/notifications/log` | Member-scoped `notification_log` event keys (`event_key`, `sent_date`, `sent_at`; no bodies). Empty → **200** `{events: []}`. Missing table → **503 `NOT_READY`**. |
| `PATCH` | `/notifications` | Upsert `notification_prefs` (member authz; validates email + `digest_hour_utc` 0–23) |
| `GET` | `/jobs` | Member-scoped `job_runs` (id, job_type, status, error, idempotency_key, started_at, finished_at; limit 50). Service-role read — PostgREST `authenticated` is revoked. Empty → **200** `{jobs: []}`. |
| `GET` | `/fills` | Member-scoped `broker_executions` fingerprints (id, symbol, quantity, executed_at, recorded_at — never `external_fill_id`). Empty → **200** `{fills: []}`. |
| `GET` | `/app-urls` | Member read of pinned Alpaca `redirect_uri`, billing return URL, and **public** Alpaca OAuth client id (never `ALPACA_OAUTH_CLIENT_SECRET`). Empty client id → `""` until EF secrets land. |
| `POST` | `/access/redeem-invite` | JWT required. Body `{ code, product_key? }`. Compares SHA-256 of `code` to secret `FX_HUB_INVITE_HASH` and/or `product_invite_codes`. On match, INSERT `client_product_grants` for the caller email (`fx_hub`). Rate-limited (8/hour). Does not accept a missing email (OAuth without email → `EMAIL_REQUIRED`). Never returns whether the env hash exists. Dashboard auto-redeems after auth when the visitor opened `?invite=` (stashed in sessionStorage); the paste form is fallback. |

## Writes vs remaining-hop Stripe

Writes (PATCH profile, broker/key connect) use **effective** plan (see **Tier gate (effective plan)** above). JWT `app_metadata.plan_tier` is never the write gate — a stale elevated claim after cancel would fail-open.

`GET /profile` still returns **`workspaces.plan_tier`** plus `has_stripe_subscription` (boolean only). Remaining-hop Stripe proof requires that workspace column in `{studio, enterprise}`, `subscription_status=active`, **and** the Stripe boolean. A creator `plan_floor=studio` on a `free` workspace must not prove checkout. Grant-only `studio` without Stripe ids must not prove checkout. Brief or Desk Stripe must not prove overlay checkout. UI `can()` is presentation only.

Profile GET returns `watchlist`, `themes`, and `research_budget_usd` from the tip
payload (SETTINGS-IA Pipeline tab). PATCH accepts the same fields (budget ≥ 0 or null).

See `docs/agent-backlog/kairos-tenancy/SETTINGS-IA.md`.

## Secrets

```bash
supabase secrets set \
  DIGIQUANT_VAULT_MASTER_KEY="$(openssl rand -base64 32)" \
  APP_URL=https://digiquant.io \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…   # never NEXT_PUBLIC_
  FX_HUB_INVITE_HASH=…           # sha256 hex of the FX Hub invite; never NEXT_PUBLIC_
```

`APP_URL` must be the **site origin** (`https://digiquant.io`) — never
`http://127.0.0.1` and never a path that already includes `/dashboard`
(helpers in `_shared/app-url.ts` strip a trailing `/dashboard`, and a leftover
`/olympus` suffix, to avoid doubling `basePath`). Pinned OAuth callback:
`{origin}/dashboard/settings/brokers/callback/`. Billing return:
`{origin}/dashboard/settings/?tab=billing`.

## Tests

```bash
cd digiquant/supabase/functions
deno test --allow-env --allow-read \
  _shared/vault.test.ts \
  _shared/access.test.ts \
  _shared/app-url.test.ts \
  _shared/cors.test.ts \
  _shared/invite.test.ts \
  _shared/profile-schemas.test.ts \
  _shared/billing-auth.test.ts \
  settings/settings.test.ts
```
