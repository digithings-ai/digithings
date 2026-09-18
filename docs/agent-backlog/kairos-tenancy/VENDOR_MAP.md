# Vendor map — digithings (Kairos staging secrets)

> Transparent map of where each secret lives and how to re-fetch.
> **No secret values in this file.** Identity / label: **digithings** (repo-global).
> Local files: `/workspace/.local/secrets/digithings-*.env` (gitignored).
> Supabase project: `core` / `rwagjbkvxkdwqmouagad`.
>
> **Naming correction (2026-08-30):** prior drafts used `cursor-cloud-agent-*.env` —
> those paths are **wrong**. Resume under **digithings** paths only.

## Vendor identity (Proton `admin@digithings.ai`)

Canonical rules: [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md).

| Item | Value |
|------|-------|
| **Vendor email** | `admin@digithings.ai` (Proton; domain connected) |
| **Login** | Email + password / vendor 2FA. Owner completes CAPTCHA and Proton confirm codes on the desktop. **No company Google account** (Workspace not purchased). |
| **Not used** | `digithings@agentmail.to`, `cursor-cloud-agent6060@agentmail.to`; Sign in with Google as the company path |
| Never store | Proton / Google passwords or 2FA in git or GitHub Secrets |
| Later | Add `admin@digithings.ai` as owner on Google Cloud / GitHub / Supabase and transfer off the personal Google |

## Stripe (TEST mode) — BLOCKED on hCaptcha

| Item | Path |
|------|------|
| Signup / login | https://dashboard.stripe.com/register · https://dashboard.stripe.com/login |
| Test mode toggle | Dashboard top-right **Test mode** |
| Secret key | Developers → API keys → Secret key (`sk_test_…`) |
| Publishable key | Same page (`pk_test_…`) — not required by current EFs |
| Products / prices | Product catalog → **Brief / Desk / Studio** (see [`PRICING.md`](PRICING.md)). Do **not** name products Baseline or Custom. |
| Env → price IDs | `STRIPE_PRICE_BRIEF_{MONTHLY,ANNUAL}` / `STRIPE_PRICE_DESK_*` / `STRIPE_PRICE_STUDIO_*` |
| Webhook endpoint | Developers → Webhooks → Add endpoint |
| Webhook URL | `https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1/stripe-webhook` |
| Webhook secret | Endpoint → Signing secret (`whsec_…`) → `STRIPE_WEBHOOK_SECRET` |
| Local file (when ready) | `.local/secrets/digithings-stripe.env` |
| Human gate | hCaptcha on signup — owner on the desktop |
| Account email | `admin@digithings.ai`. Do not use Agentmail or company Google SSO. |

## Cloudflare Email Sending — verify domain + token

| Item | Path |
|------|------|
| Console | https://dash.cloudflare.com/ → account → Email → Email Sending |
| API token | My Profile → API Tokens → Create Token → permission **Email Sending: Edit** → `CLOUDFLARE_EMAIL_API_TOKEN` |
| Account id | Account Home → account id (already `CLOUDFLARE_ACCOUNT_ID` in the repo) |
| From | Verified sending address → `NOTIFY_FROM` (bare address or `Name <addr@domain>`) |
| Test send | `python -m digiquant.notify.dispatch --require-notify` |
| Local file (when ready) | `.local/secrets/digithings-notify.env` |
| Human gate | Token creation + domain verification — owner on the desktop |
| Note | Dedicated **Email Sending: Edit** token, not the broad deploy token: rotating one must not break the other. |
| Suppression | Enforced service-side at send time; no pre-send suppression query. |

## Alpaca (paper) — BLOCKED on Cloudflare Turnstile

| Item | Path |
|------|------|
| Signup | https://app.alpaca.markets/signup |
| Login | https://app.alpaca.markets/account/login |
| Paper dashboard | https://app.alpaca.markets/paper/dashboard |
| OAuth apps | Broker / OAuth developer console (if available) → Client ID/Secret |
| Env names | `ALPACA_OAUTH_CLIENT_ID`, `ALPACA_OAUTH_CLIENT_SECRET` |
| Fallback | Paper API Key ID + Secret (if OAuth console blocked) — map per settings EF / DEPLOYMENT.md |
| Local file (when ready) | `.local/secrets/digithings-alpaca.env` |
| Human gate | Cloudflare Turnstile — owner on the desktop |
| Account email | `admin@digithings.ai`. Do not use Agentmail. |

## Google OAuth (optional Supabase Auth) — not started

| Item | Path |
|------|------|
| Console | https://console.cloud.google.com/apis/credentials |
| Create | OAuth client ID → Web application |
| Redirect URI | `https://rwagjbkvxkdwqmouagad.supabase.co/auth/v1/callback` |
| Env names | `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET` |
| Enable in Supabase | Authentication → Providers → Google |
| Local file (when ready) | `.local/secrets/digithings-google.env` |
| Note | GitHub Auth already Enabled on `core`. Product Google login (Supabase) rides the existing personal Google Cloud OAuth client until org transfer. |

## Already set on `core` EF (names only)

`DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, platform `SUPABASE_*`, `FINNHUB_API_KEY`

## After secrets land (agent resume — digithings paths only)

```bash
export SUPABASE_ACCESS_TOKEN="$(tr -d '\n' < .local/secrets/digithings-supabase-pat)"
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py --apply
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_staging_e2e.py
```

Check-only (exit 2 until files + required key names exist; never prints values):

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py
```

## Human gate

Owner uses **`admin@digithings.ai`** (Proton) on vendor forms and completes
CAPTCHA / confirm codes on the desktop. No company Google account. Abandoned
Agentmail form fills are not a signup path.
