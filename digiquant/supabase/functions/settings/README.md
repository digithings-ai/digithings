# settings Edge Function (T3)

Authenticated Settings backend for Olympus: investment profile overlays, broker
connect/revoke, and notification prefs.

| Setting | Value |
|---------|-------|
| `verify_jwt` | **true** |
| Deploy | **BLOCKED ON K3 MERGE** |

## Deploy gate — blocked on K3

This function seals broker credentials with the K3 vault public contract
(`parseCredential` / `sealCredential` / AAD binding) and writes
`broker_connections`. Until K3 (`digiquant.vault.envelope` + migration
`099_broker_connections.sql`) is merged onto the deploy target
(`module/digiquant` → develop):

1. **Do not** `supabase functions deploy settings`.
2. Frontend may still call the URL — the function returns clear errors
   (`NOT_READY` / `ADMIN_NOT_CONFIGURED`) when tables or vault key are absent.
3. After K3 merges: set `DIGIQUANT_VAULT_MASTER_KEY` (and optional
   `DIGIQUANT_VAULT_KEY_ID`), then deploy:

```bash
supabase functions deploy settings
```

The TypeScript vault under `_shared/vault.ts` mirrors the Python public API and
must pass `_shared/vault-vectors.json` (copied from K3's `tests/dq/vault/vectors.json`).

## Routes

| Method | Path | Behavior |
|--------|------|----------|
| `PATCH` | `/profile` | Schema re-validate; append `olympus_profile_config` version; reject `house` key; 409 on version conflict |
| `GET` | `/brokers` | Fingerprint projection only |
| `POST` | `/brokers/connect` | `api_key` or Alpaca `oauth` (server-side code exchange); seal via vault |
| `POST` | `/brokers/revoke` | Fail closed on unknown row |
| `PATCH` | `/notifications` | **503 `NOT_READY`** until K5 lands `notification_prefs` |

## Secrets

```bash
supabase secrets set \
  DIGIQUANT_VAULT_MASTER_KEY="$(openssl rand -base64 32)" \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…   # never NEXT_PUBLIC_
```

## Tests

```bash
cd digiquant/supabase/functions
deno test --allow-env --allow-read \
  _shared/vault.test.ts \
  settings/settings.test.ts
```
