# digiquant Supabase Edge Functions

Deno Edge Functions for the digiquant **`core`** Supabase project. Layout mirrors
the existing `prices-live/` lane (`deno.json` import map → `npm:@supabase/supabase-js@2`).

| Function | `verify_jwt` | Purpose |
|----------|--------------|---------|
| `prices-live` | `true` (rate-guarded; see function header) | Finnhub quote upsert |
| `stripe-webhook` | **`false`** | Stripe → `workspaces` + Auth claim sync (T2) |
| `create-checkout-session` | `true` | Logged-in Checkout session (T2) |
| `customer-portal` | `true` | Stripe Customer Portal session (T2) |
| `settings` | `true` | Profile / brokers / notifications (T3) |

Shared modules live under [`_shared/`](_shared/): `stripe.ts`, `tiers.ts`,
`supabase-admin.ts`, `webhook-handler.ts`, `billing-auth.ts`, `cors.ts`
(browser preflight for digiquant.io → Functions), `vault.ts`
(K3 public contract mirror), `profile-schemas.ts`, `settings-handlers.ts`.

Browser callers on `digiquant.io` send `Authorization` (and often `Content-Type`),
which triggers an OPTIONS preflight. `settings`, `create-checkout-session`, and
`customer-portal` answer OPTIONS with `204` + `Access-Control-Allow-*` before
auth; `jsonError` / `jsonOk` also emit those headers so error responses stay
readable from the static origin.

## Settings (T3) — architecture note

`settings` validates `InvestmentProfile` / `AssetPreferences` against the v1 JSON
schemas, appends versioned `olympus_profile_config` overlays (never mutates;
never the reserved `house` key), and seals broker credentials with the vault
`parseCredential` + `sealCredential` contract (AAD =
`{workspace_id}:{broker}:{env}`). Responses never include ciphertext or
plaintext. `GET /notifications` hydrates prefs (empty → 200 defaults, `updated_at: null`;
no write). `PATCH /notifications` upserts `notification_prefs` (migration 103 / K5).
Member-scoped service-role reads: `GET /jobs` (`job_runs`), `GET /fills`
(`broker_executions` fingerprints, no `external_fill_id`), `GET /notifications/log`
(event keys only), `GET /app-urls` (pinned Alpaca redirect_uri + billing return
URL under `/dashboard`, plus the public Alpaca OAuth client id — never the secret). `GET /profile` includes workspace `plan_tier` +
`subscription_status` and `has_stripe_subscription` (boolean only) and never Stripe ids.

**Deploy requires** K3 vault + `broker_connections` and K5 `notification_prefs`
on the target DB. See [`settings/README.md`](settings/README.md).

## Deploy

```bash
# From digiquant/supabase (or repo root with --project-ref)
supabase functions deploy stripe-webhook --no-verify-jwt
supabase functions deploy create-checkout-session
supabase functions deploy customer-portal
# Only after K3 vault + broker_connections are live:
supabase functions deploy settings
```

`config.toml` already pins `verify_jwt` per function; `--no-verify-jwt` on the
webhook deploy is belt-and-suspenders for older CLI versions.

## Secrets (never commit values)

```bash
supabase secrets set \
  STRIPE_SECRET_KEY=sk_live_… \
  STRIPE_WEBHOOK_SECRET=whsec_… \
  STRIPE_PRICE_BRIEF_MONTHLY=price_… \
  STRIPE_PRICE_BRIEF_ANNUAL=price_… \
  STRIPE_PRICE_DESK_MONTHLY=price_… \
  STRIPE_PRICE_DESK_ANNUAL=price_… \
  STRIPE_PRICE_STUDIO_MONTHLY=price_… \
  STRIPE_PRICE_STUDIO_ANNUAL=price_… \
  NEXT_PUBLIC_APP_URL=https://digiquant.io \
  DIGIQUANT_VAULT_MASTER_KEY="$(openssl rand -base64 32)" \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…
```

**Checkout / portal return URLs** append `/dashboard/settings/?tab=billing`.
`APP_URL` on `core` must be `https://digiquant.io` (origin only — never loopback,
never a path that already includes `/dashboard` or `/olympus`).

`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` are injected by
the Edge Runtime — do not put the service role key in app env files that ship to
browsers. Local names also accepted as fallbacks: `CORE_SUPABASE_URL`,
`CORE_SUPABASE_SERVICE_KEY`, `CORE_SUPABASE_ANON_KEY`.

Stripe Dashboard webhook endpoint:

```
https://<project-ref>.supabase.co/functions/v1/stripe-webhook
```

Events to enable: `checkout.session.completed`, `customer.subscription.created`,
`customer.subscription.updated`, `customer.subscription.deleted`,
`invoice.payment_failed`.

## Local Deno tests

There is **no** CI Deno lane yet (follow-up: wire an `olympus-functions` job). Run
locally:

```bash
cd digiquant/supabase/functions

# Install Deno if needed: https://deno.land (# or: curl -fsSL https://deno.land/install.sh | sh)
deno test --allow-env --allow-read \
  _shared/app-url.test.ts \
  _shared/access.test.ts \
  _shared/cors.test.ts \
  _shared/profile-schemas.test.ts \
  _shared/billing-auth.test.ts \
  _shared/tiers.test.ts \
  _shared/vault.test.ts \
  stripe-webhook/stripe-webhook.test.ts \
  settings/settings.test.ts
```

Or via the workspace tasks:

```bash
deno task --cwd digiquant/supabase/functions test
deno task --cwd digiquant/supabase/functions test:settings
```

Tests mock Stripe signature HMAC + an in-memory admin client / vault seams — no
live network, no real secrets.

## HTTP error contract

Stable JSON `{ "code": "...", "message": "..." }` — never stack traces, never
Stripe/Supabase keys in responses or logs.

| Status | Code (examples) | When |
|--------|-----------------|------|
| 401 | `UNAUTHENTICATED` | Missing/invalid user JWT (checkout/portal/settings) |
| 403 | `WORKSPACE_FORBIDDEN` | No membership / wrong workspace / not owner |
| 400 | `INVALID_SIGNATURE` | Webhook signature fail |
| 400 | `SCHEMA_INVALID` / `HOUSE_KEY_FORBIDDEN` / `INVALID_CREDENTIAL` | Profile or credential reject |
| 409 | `NO_STRIPE_CUSTOMER` | Portal without `stripe_customer_id` |
| 409 | `VERSION_CONFLICT` | Profile optimistic-concurrency miss |
| 404 | `CONNECTION_NOT_FOUND` | Revoke unknown row |
| 503 | `NOT_READY` | Missing `notification_prefs` / `broker_connections` tables |

Webhook always returns **200** to Stripe on duplicate events, out-of-order
ignores, and claim-sync failures (`claim_sync_pending=true` on the workspace row
for retry on the next event).
