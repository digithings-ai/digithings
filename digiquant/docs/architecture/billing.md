## Billing (T2)

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

dashboard **consumer** subscription tiers are driven by Stripe Checkout + Customer Portal +
webhook Edge Functions under `digiquant/supabase/functions/` (not Next.js route handlers).
This is distinct from ADR-0004's digikey metered API seat flow — here entitlements ride
Supabase Auth JWT `app_metadata.plan_tier` (`free | brief | desk | studio | enterprise`)
and denormalized `workspaces` billing columns for RLS.

| Function | Auth | Role |
|----------|------|------|
| `stripe-webhook` | Stripe-Signature (`STRIPE_WEBHOOK_SECRET`); `verify_jwt=false` | Idempotent `stripe_events` insert → roadmap P4 column mapping → Auth claim sync |
| `create-checkout-session` | Supabase user JWT (`verify_jwt=true`) | Owner's workspace via `workspace_members`; reuses `stripe_customer_id`; price ids from env; success/cancel → `{APP_URL}/dashboard/settings/?tab=billing&checkout=…` (`_shared/app-url.ts`) |
| `customer-portal` | Supabase user JWT (`verify_jwt=true`) | Portal session for existing `stripe_customer_id`; return `{APP_URL}/dashboard/settings/?tab=billing` |

`APP_URL` / `NEXT_PUBLIC_APP_URL` is the **site origin** (`https://digiquant.io`).
Helpers strip a trailing `/dashboard` (and a leftover `/dashboard`) so a mistaken path does not double the basePath.
Loopback origins (`127.0.0.1`) break Alpaca `redirect_uri` and Stripe return URLs;
`GET /settings/app-urls` is the Observer probe. It also returns the public
Alpaca OAuth client id (never the secret) so Brokers connect can start as soon
as EF secrets land, without a Pages rebuild. Settings UI opens the Billing tab from
`?tab=billing` / `?checkout=success|cancel`.

**Pages `/dashboard` cutover.** `scripts/digiquant_pages_dashboard_gate.py` probes
live Pages. `--apply` deploys `settings` / `create-checkout-session` /
`customer-portal` only when `/dashboard` login / auth callback / settings /
Alpaca brokers callback are 200, this
checkout mounts `POST /access/redeem-invite` and pins `/dashboard` in
`_shared/app-url.ts`, **and** the live ESZIP for each of those three functions
(`GET https://api.supabase.com/v1/projects/{ref}/functions/{slug}/body`)
contains those executable markers (line and block comments do not count).
Settings also requires `method === "POST" && path === "/access/redeem-invite"`.
Live v32 is `/dashboard` on settings, checkout, and portal — `--apply` must not
report success while any of those bundles is still stale. Exit 3 while Pages
404s; exit 5 if checkout source is stale; exit 6 if a live bundle is still
stale. Never weakens `public_app_urls_ok`. Requires `SUPABASE_ACCESS_TOKEN`
for the post-deploy ESZIP proof (never logged).

Shared helpers: `_shared/{stripe.ts,tiers.ts,supabase-admin.ts,webhook-handler.ts,billing-auth.ts}`.
Price → tier map keys off `STRIPE_PRICE_BRIEF_{MONTHLY,ANNUAL}` /
`STRIPE_PRICE_DESK_{MONTHLY,ANNUAL}` / `STRIPE_PRICE_STUDIO_{MONTHLY,ANNUAL}` (set via `supabase secrets set` — see
`digiquant/supabase/functions/README.md`). Paid claims only while status maps to
`active`/`past_due` (trialing→active); deleted/incomplete force `plan_tier=free`.
Ordering is atomic via `workspaces.last_stripe_event_created` CAS (migration 101).
Idempotency uses `stripe_events.applied_at` — insert-first with NULL marker; duplicate
pending re-applies; applied rows are true no-ops (poison-pill fix). Claim-sync runs on
every applied event; failures set `workspaces.claim_sync_pending` (migration 100) and
still return 200 after marking applied. HTTP errors use stable JSON codes (401/403/…);
never stack traces or keys.

**Settings entitlement (T3).** `settings` Edge Function tier gates
(`PATCH /profile`, `POST /brokers/connect`) read **`workspaces.plan_tier` only** —
never the JWT claim. Preferring a stale elevated `app_metadata.plan_tier` after
cancel (when claim sync failed) would fail-open and still seal broker credentials
or append overlay profiles on a `free` workspace.

**FX Hub invite (12x).** `POST /functions/v1/settings/access/redeem-invite`
requires a session JWT. The Edge Function hashes the submitted code and
compares it to `FX_HUB_INVITE_HASH` (Supabase secret, never `NEXT_PUBLIC_*`)
and/or `product_invite_codes` (migration 112). A match INSERTs
`client_product_grants (email, product_key='fx_hub')` and appends
`product_invite_redemptions` for the operator. This is not a login-optional
passphrase — the static export still bakes the anon key.

Structural SQL coverage: `tests/dq/dashboard/test_migration_billing.py`. Deno unit tests
(colocated under `functions/`) cover signature reject, duplicate no-op, out-of-order,
checkout→active→cancel, and claim-sync failure. CI Deno wiring is a documented follow-up.

