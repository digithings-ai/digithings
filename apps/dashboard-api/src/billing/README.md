# Billing — Supabase edge functions, ported to Workers

The Stripe billing surface that used to run as three Supabase Edge Functions,
ported to a Cloudflare Workers runtime module inside `apps/dashboard-api`.

| Edge function (still live) | Worker module (this port) |
| --- | --- |
| `digiquant/supabase/functions/stripe-webhook` | `routes.ts` → `handleStripeWebhook` |
| `digiquant/supabase/functions/customer-portal` | `routes.ts` → `handleCustomerPortal` |
| `digiquant/supabase/functions/create-checkout-session` | `routes.ts` → `handleCreateCheckoutSession` |
| `digiquant/supabase/functions/_shared/*` | `stripe.ts`, `tiers.ts`, `admin.ts`, `billing-auth.ts`, `webhook-handler.ts`, `app-url.ts`, `cors.ts`, `http.ts`, `env.ts` |

## What "ported" means here, and what it deliberately does not mean

The wire contract is unchanged. Same paths, same methods, same status codes,
same `{ "code", "message" }` error bodies, same order of checks — the dashboard
parses those bodies today and must not need a client change at cutover. Every
status/code/message triple in `routes.test.ts` is copied from the Edge Function
it replaces.

Two runtime differences were unavoidable and are the whole substance of the port:

- **`Deno.env.get` → an injected `env` record** (`env.ts`). Every lookup the
  Edge Functions did is preserved, including the `SUPABASE_*` /
  `CORE_SUPABASE_*` fallback pairs. The port reads `env`; it does not declare
  anything.
- **`Deno.serve` → an exported `fetch` handler** (`router.ts`). `Deno.serve` has
  no Workers equivalent, so each function became a `(request, env) => Response`
  function and `createBillingFetch` is the adapter a Worker entrypoint would
  mount.

One dependency change: `@supabase/supabase-js` is not a dependency of this
package, so `admin.ts` does not vendor a query-builder client. It defines a
narrow `AdminDb` interface and one PostgREST-over-`fetch` implementation, which
also matches the existing house pattern in `src/supabase.ts`. A later leaf that
moves the tables to D1 replaces that one file; the handlers do not change.

## Not wired, on purpose

`createBillingFetch` is not mounted in `src/index.ts`. Mounting it means binding
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and the six `STRIPE_PRICE_*`
values as Worker secrets, which is a production change and is Chris's call
under epic DIG-2887. A test pins this: `no-deno.test.ts` asserts the
dashboard-api entrypoint does not reference `billing`.

No `wrangler.toml` was edited, no `[vars]` key or secret was added, and the
Supabase Edge Functions are untouched. They stay live as the two-week rollback
while the Worker path is exercised.

## Wiring, when the cutover is approved

```ts
// apps/dashboard-api/src/index.ts
const billing = createBillingFetch(env);
```

then dispatch `billing.fetch(request)` for the three paths in `BILLING_PATHS`,
and point the Stripe webhook URL at the Worker. Chris updates the webhook URL
himself.

## Tests

`vitest run src/billing` — 67 tests.

- `routes.test.ts` — the wire contract: every status/code/message triple per
  handler, driven with real HMAC signatures so each arm is reached rather than
  short-circuited by an earlier check.
- `stripe.test.ts` — signature verification against a real HMAC (valid,
  tampered body, wrong secret, out-of-tolerance, and the exact tolerance
  boundary), event parsing, and tier/price mapping.
- `admin.test.ts` — the PostgREST layer, which the route tests never reach
  because they inject a stub: duplicate-event classification, the out-of-order
  CAS guard, and fail-closed reads.
- `no-deno.test.ts` — a `Deno` global would throw at request time on Workers
  and nowhere else, so the tree is scanned for one (comments stripped, with a
  control that proves the stripper runs).

Nine mutants were run against this suite to confirm it can fail; all nine are
killed, including the owner-role check and the webhook signature verification.