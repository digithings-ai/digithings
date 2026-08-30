# settings Edge Function (T3)

Authenticated Settings backend for Olympus: investment profile overlays, broker
connect/revoke, and notification prefs.

| Setting | Value |
|---------|-------|
| `verify_jwt` | **true** |
| Deploy | **BLOCKED ON K3 MERGE** + module migrations **096–098** |

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
| `GET` | `/profile` | Load tip `olympus_profile_config` for workspace member (`?workspace_id=` / `?profile_key=` optional, default key `workspace`). **Empty contract:** no tip → **200** with `version_id`/`recorded_at` null, empty `label`, null investment/assets — read-only, never inserts. `house` key → **400**. Missing table → **503 `NOT_READY`**. No Custom-tier write gate (read for hydrate). **Observer bootstrap:** if the JWT user has no `workspace_members` row, the handler calls `ensure_personal_workspace` (migration 107) before resolve — creates a free personal workspace + owner membership (never system/house). |
| `PATCH` | `/profile` | Tier gate; schema re-validate; append workspace-scoped version; reject `house` key; 409 on version/supersedes conflict |
| `GET` | `/brokers` | Fingerprint projection only |
| `POST` | `/brokers/connect` | Tier gate; `api_key` or Alpaca `oauth` (server-pinned `redirect_uri`); seal via vault; reconnect = revoke-then-insert |
| `POST` | `/brokers/revoke` | Fail closed on unknown row |
| `GET` | `/notifications` | Load `notification_prefs` for workspace member (`?workspace_id=` optional). **Empty contract:** no row → **200** with defaults (`daily_digest`/`holding_change_alerts`/`execution_alerts` false, `digest_hour_utc` 12, `email` from JWT when present, `updated_at: null`) — read-only, never inserts. Missing table → **503 `NOT_READY`**. |
| `PATCH` | `/notifications` | Upsert `notification_prefs` (member authz; validates email + `digest_hour_utc` 0–23) |

## Tier gate

`plan_tier ∈ {custom, enterprise}` is required for profile writes and broker
connect, gated on **`workspaces.plan_tier` only** (authoritative after Stripe
CAS). JWT `app_metadata.plan_tier` is presentation / claim-sync side — never
prefer it here (stale elevated claim after cancel would fail-open). Otherwise
**403 `TIER_FORBIDDEN`**. UI `can()` is presentation only.

## Secrets

```bash
supabase secrets set \
  DIGIQUANT_VAULT_MASTER_KEY="$(openssl rand -base64 32)" \
  APP_URL=https://app.example \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…   # never NEXT_PUBLIC_
```

Pinned OAuth callback: `{APP_URL}/olympus/settings/brokers/callback/`.

## Tests

```bash
cd digiquant/supabase/functions
deno test --allow-env --allow-read \
  _shared/vault.test.ts \
  settings/settings.test.ts
```
