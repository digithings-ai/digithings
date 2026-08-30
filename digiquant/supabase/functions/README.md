# digiquant Supabase Edge Functions

Deno Edge Functions for the digiquant **`core`** Supabase project. Layout mirrors
the existing `prices-live/` lane (`deno.json` import map → `npm:@supabase/supabase-js@2`).

| Function | `verify_jwt` | Purpose |
|----------|--------------|---------|
| `prices-live` | `true` (rate-guarded; see function header) | Finnhub quote upsert |
| `stripe-webhook` | **`false`** | Stripe → `workspaces` + Auth claim sync (T2 — on `module/digiquant`) |
| `create-checkout-session` | `true` | Logged-in Checkout session (T2) |
| `customer-portal` | `true` | Stripe Customer Portal session (T2) |
| `settings` | `true` | Profile / brokers / notifications (T3) — **deploy blocked on K3** |

Shared modules live under [`_shared/`](_shared/): `supabase-admin.ts`,
`billing-auth.ts`, `vault.ts` (K3 public contract mirror), `profile-schemas.ts`,
`settings-handlers.ts`. T2 also contributes `stripe.ts` / `tiers.ts` /
`webhook-handler.ts` on `module/digiquant`.

## Settings (T3) — architecture note

`settings` validates `InvestmentProfile` / `AssetPreferences` against the v1 JSON
schemas, appends versioned `olympus_profile_config` overlays (never mutates;
never the reserved `house` key), and seals broker credentials with the vault
`parseCredential` + `sealCredential` contract (AAD =
`{workspace_id}:{broker}:{env}`). Responses never include ciphertext or
plaintext. `PATCH /notifications` returns `503 NOT_READY` until K5 lands
`notification_prefs`.

**Deploy is blocked until K3 merges** (vault + `broker_connections`). See
[`settings/README.md`](settings/README.md).

## Deploy

```bash
# From digiquant/supabase (or repo root with --project-ref)
supabase functions deploy stripe-webhook --no-verify-jwt   # after T2 on target
supabase functions deploy create-checkout-session
supabase functions deploy customer-portal
# Only after K3 vault + broker_connections are live:
supabase functions deploy settings
```

`config.toml` pins `verify_jwt` per function.

## Secrets (never commit values)

```bash
supabase secrets set \
  STRIPE_SECRET_KEY=sk_live_… \
  STRIPE_WEBHOOK_SECRET=whsec_… \
  STRIPE_PRICE_BASELINE_MONTHLY=price_… \
  STRIPE_PRICE_BASELINE_ANNUAL=price_… \
  STRIPE_PRICE_CUSTOM_MONTHLY=price_… \
  STRIPE_PRICE_CUSTOM_ANNUAL=price_… \
  NEXT_PUBLIC_APP_URL=https://olympus.example.com \
  DIGIQUANT_VAULT_MASTER_KEY="$(openssl rand -base64 32)" \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…
```

`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` are injected by
the Edge Runtime — do not put the service role key in app env files that ship to
browsers.

## Local Deno tests

```bash
cd digiquant/supabase/functions
deno task test:settings
# or full suite when T2 function sources are present:
# deno task test
```

Tests mock admin clients + vault / Stripe seams — no live network, no real secrets.

## HTTP error contract

Stable JSON `{ "code": "...", "message": "..." }` — never stack traces, never
secrets in responses or logs.

| Status | Code (examples) | When |
|--------|-----------------|------|
| 401 | `UNAUTHENTICATED` | Missing/invalid user JWT |
| 403 | `WORKSPACE_FORBIDDEN` | No membership / wrong workspace |
| 400 | `SCHEMA_INVALID` / `HOUSE_KEY_FORBIDDEN` / `INVALID_CREDENTIAL` | Profile or credential reject |
| 409 | `VERSION_CONFLICT` | Profile optimistic-concurrency miss |
| 404 | `CONNECTION_NOT_FOUND` | Revoke unknown row |
| 503 | `NOT_READY` | Notifications before K5; brokers table before K3 |
