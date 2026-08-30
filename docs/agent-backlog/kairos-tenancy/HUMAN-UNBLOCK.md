# Kairos — human unblock checklist (minimal, ordered)

**Status: PARTIAL UNLOCK (2026-08-30 E2E push) — NOT COMPLETE.** Workspace bootstrap + settings JWT **200** + live vault seal (settings **v21**, ops Custom + fake api_key) unlocked. Still need Stripe/Mailgun/Google/Alpaca for staging E2E (checkout = `PRICE_NOT_CONFIGURED`). Do not merge [#3183](https://github.com/digithings-ai/digithings/pull/3183) until you intentionally cut over Pages.

Env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/ea5347f2-e16e-4f90-a63d-706ffd01128f  
Deploy detail: [`DEPLOYMENT.md`](DEPLOYMENT.md)  
Audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md) · artifact `/opt/cursor/artifacts/kairos-completion-audit-e2e-push.md`  
Waiting artifact: `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` (`PARTIAL_UNLOCK`)  
Docs branch: `cursor/kairos-audit-e2e-push-3d52`  
Fix compare: https://github.com/digithings-ai/digithings/compare/develop...cursor/settings-uuid-bind-fix-3d52

---

## 0) Paste into Cursor Cloud env secrets (names + format only)

Replace / fill these in the Cursor environment secret store. **Values never go in git.**

| Name | Format hint |
|------|-------------|
| `SUPABASE_ACCESS_TOKEN` | Personal access token `sbp_…` — file `.local/secrets/cursor-cloud-agent-supabase-pat` (label **cursor cloud agent**) works; re-paste into Cursor env if process env drops it |
| `STRIPE_SECRET_KEY` | Stripe **test** secret `sk_test_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` from Stripe Dashboard → EF webhook |
| `STRIPE_PRICE_BASELINE_MONTHLY` | `price_…` |
| `STRIPE_PRICE_CUSTOM_MONTHLY` | `price_…` |
| `STRIPE_PRICE_BASELINE_ANNUAL` | `price_…` (optional) |
| `STRIPE_PRICE_CUSTOM_ANNUAL` | `price_…` (optional) |
| `MAILGUN_API_KEY` | Mailgun private API key (MCP currently auth-fails; env EMPTY) |
| `MAILGUN_DOMAIN` | Verified sending domain |
| `NOTIFY_FROM` | Verified From address on that domain |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client (still needed) |
| `ALPACA_OAUTH_CLIENT_ID` / `ALPACA_OAUTH_CLIENT_SECRET` | Alpaca **paper** OAuth app |

**Done on `core` EF secrets:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.  
**Done Auth:** GitHub provider **Enabled** on `core`. Google still Disabled. Email Enabled — Agentmail path works.  
**Done product:** mig 107 bootstrap; settings GET/PATCH notifications with JWT; vault seal after uuid-bind (v21).

---

## 0b) Workspace bootstrap — RESOLVED

mig **107** + settings `ensureCallerWorkspace` — Agentmail JWT settings **200**. Personal workspace exists (`plan_tier=free` by default). Ops may elevate to `custom` for vault probes until Stripe prices land (document clearly — **not** Stripe-sourced).

---

## 1) Set remaining Supabase Edge Function secrets (`core`)

`sbp_…` PAT available. Remaining vendor keys still empty — set when obtained:

```bash
supabase secrets set \
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

## 2) Redeploy billing Edge Functions (after Stripe secrets)

Preferred order: `stripe-webhook` (no verify JWT) → `create-checkout-session` / `customer-portal`. Settings already **v21**.

Smoke: unauth → gateway `401`; Stripe webhook without key must not stay `STRIPE_NOT_CONFIGURED` once secret is set; checkout must clear `PRICE_NOT_CONFIGURED`.

---

## 3) Supabase Auth providers on `core`

- **GitHub:** Enabled.
- **Email:** Enabled — Agentmail signup/confirm works.
- **Google:** Still Disabled.

---

## 4) Stripe webhook (test mode)

1. Products/prices for Baseline + Custom (monthly required).
2. Endpoint → `…/functions/v1/stripe-webhook`.
3. Put `whsec_…` into EF secrets.
4. One test Checkout → claim / `plan_tier` sync (replaces ops SQL elevation).

---

## 5) Paper Alpaca connect

1. Finish Alpaca OAuth app (paper); put client id/secret in EF secrets.
2. Staging: sign in → Settings → Brokers → connect paper (OAuth — not fake api_key).
3. Place paper order-intent → mirror fill path (no live trading).

---

## 6) Flag cutover (human release gate — last)

Only when staging E2E (signup → Stripe test → Alpaca paper → overlay → digest) is green:

1. Keep Cloudflare Access on initially.
2. Merge deliberate Pages promote when ready (**not** auto-merge #3183).
3. Flip `NEXT_PUBLIC_OLYMPUS_AUTH` on Pages.
4. Apply cutover SQL `migrations/cutover/900_…` only after Access + flag plan.
5. RLS proof harness post-apply; then Access off.

**Still out of epic:** IBKR vendor onboarding, live trading, legal adviser read.
