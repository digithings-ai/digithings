# Vendor map — digithings (Kairos staging secrets)

> Transparent map of where each secret lives and how to re-fetch.
> **No secret values in this file.** Identity / label: **digithings** (repo-global).
> Local files: `/workspace/.local/secrets/digithings-*.env` (gitignored).
> Supabase project: `core` / `rwagjbkvxkdwqmouagad`.
>
> **Naming correction (2026-08-30):** prior drafts used `cursor-cloud-agent-*.env` —
> those paths are **wrong**. Resume under **digithings** paths only.

## Vendor identity (company Google)

Canonical rules: [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md).

| Item | Value |
|------|-------|
| **Vendor email** | `admin@digithings.ai` |
| **Login** | Google account for that address. Owner signs into Google on the desktop; agents use **Sign in with Google** in that session. |
| **Not used** | `digithings@agentmail.to`, `cursor-cloud-agent6060@agentmail.to` — no completed vendor accounts; do not create any |
| Never store | Google password / 2FA in git or GitHub Secrets |

## Stripe (TEST mode) — BLOCKED on hCaptcha

| Item | Path |
|------|------|
| Signup / login | https://dashboard.stripe.com/register · https://dashboard.stripe.com/login |
| Test mode toggle | Dashboard top-right **Test mode** |
| Secret key | Developers → API keys → Secret key (`sk_test_…`) |
| Publishable key | Same page (`pk_test_…`) — not required by current EFs |
| Products / prices | Product catalog → create **Baseline** + **Custom** (monthly required; annual optional) |
| Env → price IDs | `STRIPE_PRICE_BASELINE_MONTHLY`, `STRIPE_PRICE_CUSTOM_MONTHLY`, optional `*_ANNUAL` |
| Webhook endpoint | Developers → Webhooks → Add endpoint |
| Webhook URL | `https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1/stripe-webhook` |
| Webhook secret | Endpoint → Signing secret (`whsec_…`) → `STRIPE_WEBHOOK_SECRET` |
| Local file (when ready) | `.local/secrets/digithings-stripe.env` |
| Human gate | hCaptcha on signup — owner on the desktop |
| Account email | `admin@digithings.ai` (Google SSO if Stripe offers it). Do not use Agentmail. |

## Mailgun — BLOCKED on reCAPTCHA

| Item | Path |
|------|------|
| Signup | https://signup.mailgun.com/new/signup (free, no card → 100 msg/day) |
| Login | https://login.mailgun.com/login/ |
| API key | Settings → API Security → Private API key → `MAILGUN_API_KEY` |
| Domain | Sending → Domains (sandbox `sandbox….mailgun.org` OK for staging) → `MAILGUN_DOMAIN` |
| From | Verified sender on that domain → `NOTIFY_FROM` |
| Sandbox recipients | Authorize **`admin@digithings.ai`** |
| Test send | Sending → Send email, or `python -m digiquant.notify.dispatch --require-mailgun` |
| Local file (when ready) | `.local/secrets/digithings-mailgun.env` |
| Human gate | reCAPTCHA / SMS — owner on the desktop |
| Account email | `admin@digithings.ai`. Do not use Agentmail. |
| MCP status | Mailgun MCP auth fails until API key set |

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
| Account email | `admin@digithings.ai` (Alpaca often has no Google SSO). Do not use Agentmail. |

## Google OAuth (optional Supabase Auth) — not started

| Item | Path |
|------|------|
| Console | https://console.cloud.google.com/apis/credentials |
| Create | OAuth client ID → Web application |
| Redirect URI | `https://rwagjbkvxkdwqmouagad.supabase.co/auth/v1/callback` |
| Env names | `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET` |
| Enable in Supabase | Authentication → Providers → Google |
| Local file (when ready) | `.local/secrets/digithings-google.env` |
| Note | GitHub Auth already Enabled on `core`. Product Google login (Supabase) is separate from the **admin@digithings.ai** Google account used on vendor consoles. |

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

Owner signs into **`admin@digithings.ai` Google** on the desktop, then agents resume
with Sign in with Google. Abandoned Agentmail form fills are not a signup path.
