# digiquant Supabase Edge Functions

Deno Edge Functions for the digiquant **`core`** Supabase project. Layout mirrors
the existing `prices-live/` lane (`deno.json` import map → `npm:@supabase/supabase-js@2`).

| Function | `verify_jwt` | Purpose |
|----------|--------------|---------|
| `prices-live` | `true` (rate-guarded; see function header) | Finnhub quote upsert |
| `stripe-webhook` | **`false`** | Stripe → `workspaces` + Auth claim sync (T2) |
| `create-checkout-session` | `true` | Logged-in Checkout session |
| `customer-portal` | `true` | Stripe Customer Portal session |

Shared modules live under [`_shared/`](_shared/): `stripe.ts`, `tiers.ts`,
`supabase-admin.ts`, `webhook-handler.ts`.

## Deploy

```bash
# From digiquant/supabase (or repo root with --project-ref)
supabase functions deploy stripe-webhook --no-verify-jwt
supabase functions deploy create-checkout-session
supabase functions deploy customer-portal
```

`config.toml` already pins `verify_jwt` per function; `--no-verify-jwt` on the
webhook deploy is belt-and-suspenders for older CLI versions.

## Secrets (never commit values)

```bash
supabase secrets set \
  STRIPE_SECRET_KEY=sk_live_… \
  STRIPE_WEBHOOK_SECRET=whsec_… \
  STRIPE_PRICE_BASELINE_MONTHLY=price_… \
  STRIPE_PRICE_BASELINE_ANNUAL=price_… \
  STRIPE_PRICE_CUSTOM_MONTHLY=price_… \
  STRIPE_PRICE_CUSTOM_ANNUAL=price_… \
  NEXT_PUBLIC_APP_URL=https://olympus.example.com
```

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
deno test --allow-env \
  _shared/tiers.test.ts \
  stripe-webhook/stripe-webhook.test.ts
```

Or via the workspace task:

```bash
deno task --cwd digiquant/supabase/functions test
```

Tests mock Stripe signature HMAC + an in-memory admin client — no live network,
no real secrets.

## HTTP error contract (roadmap P4)

Stable JSON `{ "code": "...", "message": "..." }` — never stack traces, never
Stripe/Supabase keys in responses or logs.

| Status | Code (examples) | When |
|--------|-----------------|------|
| 401 | `UNAUTHENTICATED` | Missing/invalid user JWT (checkout/portal) |
| 403 | `WORKSPACE_FORBIDDEN` | No membership / wrong workspace / not owner |
| 400 | `INVALID_SIGNATURE` | Webhook signature fail |
| 409 | `NO_STRIPE_CUSTOMER` | Portal without `stripe_customer_id` |

Webhook always returns **200** to Stripe on duplicate events, out-of-order
ignores, and claim-sync failures (`claim_sync_pending=true` on the workspace row
for retry on the next event).
