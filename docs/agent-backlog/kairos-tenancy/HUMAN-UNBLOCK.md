# Kairos — human unblock checklist (minimal, ordered)

**Status: PARTIAL UNLOCK (2026-08-30) — NOT COMPLETE.** `sbp_` works from `.local/secrets/cursor-cloud-agent-supabase-pat` (label **cursor cloud agent**); process env may still need pasted `SUPABASE_ACCESS_TOKEN`. Vault + `APP_URL` on EF; settings **v19** ACTIVE; **GitHub Auth Enabled** on `core`. Agentmail Auth user confirmed; **workspace bootstrap applied** (mig 107 + EF v19) — JWT settings **200** for profile/notifications/brokers. Still need Stripe/Mailgun/Google/Alpaca for staging E2E (checkout = `PRICE_NOT_CONFIGURED`). Do not merge [#3183](https://github.com/digithings-ai/digithings/pull/3183) until you intentionally cut over Pages.

Env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/ea5347f2-e16e-4f90-a63d-706ffd01128f  
Deploy detail: [`DEPLOYMENT.md`](DEPLOYMENT.md)  
Audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md) · artifact `/opt/cursor/artifacts/kairos-completion-audit-fresh.md`  
Waiting artifact: `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` (`PARTIAL_UNLOCK`)  
Docs branch: `cursor/kairos-audit-agentmail-auth-3d52`

---

## 0) Paste into Cursor Cloud env secrets (names + format only)

Replace / fill these in the Cursor environment secret store. **Values never go in git.**

| Name | Format hint |
|------|-------------|
| `SUPABASE_ACCESS_TOKEN` | Personal access token `sbp_…` — **re-paste** from gitignored `.local/secrets/cursor-cloud-agent-supabase-pat` labeled **cursor cloud agent**. Process env was ABSENT this turn (file load only). |
| `STRIPE_SECRET_KEY` | Stripe **test** secret `sk_test_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` from Stripe Dashboard → EF webhook |
| `STRIPE_PRICE_BASELINE_MONTHLY` | `price_…` |
| `STRIPE_PRICE_CUSTOM_MONTHLY` | `price_…` |
| `STRIPE_PRICE_BASELINE_ANNUAL` | `price_…` (optional) |
| `STRIPE_PRICE_CUSTOM_ANNUAL` | `price_…` (optional) |
| `MAILGUN_API_KEY` | Mailgun private API key (MCP currently auth-fails) |
| `MAILGUN_DOMAIN` | Verified sending domain |
| `NOTIFY_FROM` | Verified From address on that domain |
| `AUTH_GOOGLE_CLIENT_ID` / `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth client (still needed) |
| `ALPACA_OAUTH_CLIENT_ID` / `ALPACA_OAUTH_CLIENT_SECRET` | Alpaca **paper** OAuth app |

**Done on `core` EF secrets:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`.  
**Done Auth:** GitHub provider **Enabled** on `core` (OAuth App `digiquant olympus`). Google still Disabled. Email Enabled — Agentmail signup/confirm works for agent-owned users.

---

## 0b) Workspace bootstrap (new blocker after Auth unlock)

Real JWT settings E2E now fails closed with `WORKSPACE_FORBIDDEN` because **`workspace_members` is empty** (2 orphan enterprise system/house workspaces, 0 members). Observer (free) users need an automatic personal workspace + owner membership on first session (or an explicit EF route). Until that ships or ops provision membership, Settings profile/notifications/brokers cannot return 200 for new Auth users. Checkout fails earlier on `PRICE_NOT_CONFIGURED` until Stripe prices land.

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

- **GitHub:** Enabled (callback `https://rwagjbkvxkdwqmouagad.supabase.co/auth/v1/callback`). Site URL + Olympus redirect allow-list set.
- **Email:** Enabled — agent used Agentmail (`@agentmail.to`) for signup/confirm without inventing SQL users.
- **Google:** Still Disabled — create OAuth client when captcha-free console access is available; then enable in dashboard.

---

## 4) Stripe webhook (test mode)

1. Products/prices for Baseline + Custom (monthly required).
2. Endpoint → `…/functions/v1/stripe-webhook` with events for checkout + subscription lifecycle.
3. Put `whsec_…` into EF secrets (step 1).
4. One test Checkout → claim / `plan_tier` sync (requires workspace membership first — see §0b).

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
