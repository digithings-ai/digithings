# Kairos — human unblock checklist (minimal, ordered)

**Status: PARTIAL UNLOCK (2026-08-30 Auth Pages) — NOT COMPLETE.** Workspace bootstrap + settings JWT **200** + vault seal + free-tier `TIER_FORBIDDEN` + notify prefs→Agentmail unlocked. Notify CLI loud-fails `MAILGUN_NOT_CONFIGURED`. Staging E2E still needs Stripe/Mailgun/Google/Alpaca. Prod `/olympus/login` **404** until narrow Auth Pages PR merges to `main`.

Env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/ea5347f2-e16e-4f90-a63d-706ffd01128f  
Deploy detail: [`DEPLOYMENT.md`](DEPLOYMENT.md)  
Audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md) · artifact `/opt/cursor/artifacts/kairos-completion-audit-auth-pages.md`  
Waiting artifact: `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` (`PARTIAL_UNLOCK`)  
**Auth Pages (merge to `main`):** `cursor/olympus-auth-pages-e036` — https://github.com/digithings-ai/digithings/compare/main...cursor/olympus-auth-pages-e036  
**Docs/audit (`develop`):** `cursor/kairos-auth-pages-audit-e036`  
**Do not merge** draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) for the login 404. **Never apply cutover 900** with this Pages fix.

Loud-fail gates (after paste):
```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.notify.dispatch --require-mailgun
```

### 0a) Merge Auth Pages to `main` (agent-unblocked; human merge)

1. Open/merge compare URL above (`cursor/olympus-auth-pages-e036` → `main`).
2. Wait for Cloudflare Pages rebuild (`scripts/build-digiquant.sh`; AUTH defaults on under `CF_PAGES` when unset).
3. Smoke: `https://digiquant.io/olympus/login` → **200** + Login UI (GitHub works; Google still Disabled on `core`).
4. Keep Access on `/olympus/*` until intentional cutover. Do **not** apply `900_*`.

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
**Done product:** mig 107 bootstrap; settings GET/PATCH; vault seal; **settings v22** (`OAUTH_NOT_CONFIGURED`); **create-checkout-session v5** (names missing price env).

---

## 0b) Workspace bootstrap — RESOLVED

mig **107** + settings `ensureCallerWorkspace` — Agentmail JWT settings **200**. Personal workspace exists. Ops may elevate to `custom` for vault/overlay probes until Stripe prices land (document clearly — **not** Stripe-sourced). Live-retry left workspace at `custom` after proving free→`TIER_FORBIDDEN`. Notification prefs point at Agentmail inbox for digest when Mailgun lands.

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

Preferred order: `stripe-webhook` (no verify JWT) → `create-checkout-session` / `customer-portal`. Settings already **v22**.

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
