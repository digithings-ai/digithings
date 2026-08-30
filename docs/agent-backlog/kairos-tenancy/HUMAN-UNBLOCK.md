# Kairos — human unblock checklist (minimal, ordered)

**Status: PARTIAL UNLOCK (2026-08-30) — NOT COMPLETE.** `sbp_` obtained in agent VM; vault + `APP_URL` EF secrets pushed; settings EF **v17** full deploy + 401 smoke. Still need Stripe/Mailgun/Auth/Alpaca for staging E2E. Do not merge [#3183](https://github.com/digithings-ai/digithings/pull/3183) until you intentionally cut over Pages.

Env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/ea5347f2-e16e-4f90-a63d-706ffd01128f  
Deploy detail: [`DEPLOYMENT.md`](DEPLOYMENT.md)  
Audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md)  
Waiting artifact: `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` (`PARTIAL_UNLOCK`)

---

## 0) Paste into Cursor Cloud env secrets (names + format only)

Replace / fill these in the Cursor environment secret store. **Values never go in git.**

| Name | Format hint |
|------|-------------|
| `SUPABASE_ACCESS_TOKEN` | Personal access token `sbp_…` — **agent already created** token `cursor-kairos-cloud-agent` (gitignored `.local/secrets/supabase_access_token`); **paste into Cursor env** to replace JWT |
| `STRIPE_SECRET_KEY` | Stripe **test** secret `sk_test_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` from Stripe Dashboard → EF webhook |
| `STRIPE_PRICE_BASELINE_MONTHLY` | `price_…` |
| `STRIPE_PRICE_CUSTOM_MONTHLY` | `price_…` |
| `STRIPE_PRICE_BASELINE_ANNUAL` | `price_…` (optional) |
| `STRIPE_PRICE_CUSTOM_ANNUAL` | `price_…` (optional) |
| `MAILGUN_API_KEY` | Mailgun private API key |
| `MAILGUN_DOMAIN` | Verified sending domain |
| `NOTIFY_FROM` | Verified From address on that domain |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client |
| `AUTH_GITHUB_CLIENT_ID` / `AUTH_GITHUB_CLIENT_SECRET` | GitHub OAuth App |
| `ALPACA_OAUTH_CLIENT_ID` / `ALPACA_OAUTH_CLIENT_SECRET` | Alpaca **paper** OAuth app |

**Done on `core` EF secrets:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.

---

## 1) Set remaining Supabase Edge Function secrets (`core`)

`sbp_…` PAT available in agent VM. Remaining vendor keys still empty — set when obtained:

```bash
supabase secrets set \
  DIGIQUANT_VAULT_MASTER_KEY=… \
  DIGIQUANT_VAULT_KEY_ID=v1 \
  APP_URL=… \
  NEXT_PUBLIC_APP_URL=… \
  STRIPE_SECRET_KEY=… \
  STRIPE_WEBHOOK_SECRET=… \
  STRIPE_PRICE_BASELINE_MONTHLY=… \
  STRIPE_PRICE_CUSTOM_MONTHLY=… \
  MAILGUN_API_KEY=… \
  MAILGUN_DOMAIN=… \
  NOTIFY_FROM=… \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…
```

Webhook URL: `https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1/stripe-webhook`

---

## 2) Redeploy Edge Functions (after secrets)

Preferred order: `stripe-webhook` (no verify JWT) → `create-checkout-session` / `customer-portal` → `settings` (full monorepo bundle or keep thin pin on latest develop SHA).

Smoke: unauth → gateway `401`; Stripe webhook without key must not stay `STRIPE_NOT_CONFIGURED` once secret is set.

---

## 3) Supabase Auth providers on `core`

In dashboard: enable **Google** + **GitHub** with the client IDs/secrets from step 0. Confirm redirect URLs match Olympus / Auth config.

---

## 4) Stripe webhook (test mode)

1. Products/prices for Baseline + Custom (monthly required).
2. Endpoint → `…/functions/v1/stripe-webhook` with events for checkout + subscription lifecycle.
3. Put `whsec_…` into EF secrets (step 1).
4. One test Checkout → claim / `plan_tier` sync.

---

## 5) Paper Alpaca connect

1. Finish Alpaca OAuth app (paper); put client id/secret in EF secrets.
2. Staging: sign in → Settings → Brokers → connect paper.
3. Place paper order-intent → mirror fill path (no live trading).

---

## 6) Flag cutover (human release gate — last)

Only when staging E2E (signup → Stripe test → Alpaca paper → overlay → digest) is green:

1. Keep Cloudflare Access on initially.
2. Merge deliberate Pages promote when ready (**not** auto-merge #3183).
3. Flip `NEXT_PUBLIC_OLYMPUS_AUTH` on Pages.
4. Apply cutover SQL `migrations/cutover/900_…` only after Access + flag plan (see [`DEPLOYMENT.md`](DEPLOYMENT.md) §6).
5. RLS proof harness post-apply; then Access off.

**Still out of epic:** IBKR vendor onboarding, live trading, legal adviser read.
