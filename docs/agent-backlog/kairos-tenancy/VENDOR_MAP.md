# Vendor map — digithings (Kairos staging secrets)

> Transparent map of where each secret lives and how to re-fetch.
> **No secret values in this file.** Identity / label: **digithings** (repo-global).
> Local files: `/workspace/.local/secrets/digithings-*.env` (gitignored).
> Supabase project: `core` / `rwagjbkvxkdwqmouagad`.
>
> **Naming correction (2026-08-30):** prior drafts used `cursor-cloud-agent-*.env` —
> those paths are **wrong**. Resume under **digithings** paths only.

## Agentmail (verification inbox)

| Item | Value |
|------|-------|
| **Canonical inbox** | `digithings@agentmail.to` |
| Interim inbox (accidental; do not prefer) | `cursor-cloud-agent6060@agentmail.to` — created mid-onboard; migrate any pending vendor signups back to digithings@ when re-trying |
| How to re-fetch mail | Agentmail MCP `list_messages` / `list_threads` on inboxId |
| Purpose | Email verification for Stripe / Mailgun / Alpaca / Supabase Auth |

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
| Human gate | hCaptcha on signup — screenshot `/opt/cursor/artifacts/stripe-hcaptcha-human-needed.png` |
| Signup attempt email | `digithings@agentmail.to` (form filled, Create account blocked by captcha) |

## Mailgun — BLOCKED on reCAPTCHA

| Item | Path |
|------|------|
| Signup | https://signup.mailgun.com/new/signup (free, no card → 100 msg/day) |
| Login | https://login.mailgun.com/login/ |
| API key | Settings → API Security → Private API key → `MAILGUN_API_KEY` |
| Domain | Sending → Domains (sandbox `sandbox….mailgun.org` OK for staging) → `MAILGUN_DOMAIN` |
| From | Verified sender on that domain → `NOTIFY_FROM` |
| Sandbox recipients | Authorize **`digithings@agentmail.to`** (canonical). Interim `cursor-cloud-agent6060@agentmail.to` only if that signup already completed |
| Test send | Sending → Send email, or `python -m digiquant.notify.dispatch --require-mailgun` |
| Local file (when ready) | `.local/secrets/digithings-mailgun.env` |
| Human gate | reCAPTCHA failed (“Could not validate”) — may also require SMS |
| Screenshot | `/opt/cursor/artifacts/mailgun-recaptcha-human-needed.png` |
| Signup attempt email | Interim form used `cursor-cloud-agent6060@agentmail.to` — **re-prefer digithings@** on next attempt |
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
| Human gate | Cloudflare Turnstile — Sign up stays disabled until solved |
| Screenshot | `/opt/cursor/artifacts/alpaca-turnstile-human-needed.png` |
| Signup attempt | Interim email `cursor-cloud-agent6060@agentmail.to`; **canonical = digithings@agentmail.to** |
| Prior login | `digithings@agentmail.to` → Cognito `NotAuthorizedException` (account never completed) |

## Google OAuth (optional Supabase Auth) — not started

| Item | Path |
|------|------|
| Console | https://console.cloud.google.com/apis/credentials |
| Create | OAuth client ID → Web application |
| Redirect URI | `https://rwagjbkvxkdwqmouagad.supabase.co/auth/v1/callback` |
| Env names | `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET` |
| Enable in Supabase | Authentication → Providers → Google |
| Local file (when ready) | `.local/secrets/digithings-google.env` |
| Note | GitHub Auth already Enabled on `core`; Google optional |

## Already set on `core` EF (names only)

`DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL`, `NEXT_PUBLIC_APP_URL`, platform `SUPABASE_*`, `FINNHUB_API_KEY`

## After secrets land (agent resume — digithings paths only)

```bash
export SUPABASE_ACCESS_TOKEN="$(tr -d '\n' < .local/secrets/digithings-supabase-pat)"
set -a
source .local/secrets/digithings-stripe.env
source .local/secrets/digithings-mailgun.env
source .local/secrets/digithings-alpaca.env
set +a
npx supabase secrets set --project-ref rwagjbkvxkdwqmouagad \
  STRIPE_SECRET_KEY=… STRIPE_WEBHOOK_SECRET=… \
  STRIPE_PRICE_BASELINE_MONTHLY=… STRIPE_PRICE_CUSTOM_MONTHLY=… \
  MAILGUN_API_KEY=… MAILGUN_DOMAIN=… NOTIFY_FROM=… \
  ALPACA_OAUTH_CLIENT_ID=… ALPACA_OAUTH_CLIENT_SECRET=…
npx supabase functions deploy stripe-webhook --project-ref rwagjbkvxkdwqmouagad --no-verify-jwt
npx supabase functions deploy create-checkout-session --project-ref rwagjbkvxkdwqmouagad
npx supabase functions deploy customer-portal --project-ref rwagjbkvxkdwqmouagad
npx supabase functions deploy settings --project-ref rwagjbkvxkdwqmouagad
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
```

## Browser tabs left open for human (paused)

1. Stripe register + hCaptcha (`digithings@agentmail.to`)
2. Mailgun signup + reCAPTCHA error (interim inbox on form — migrate to digithings@)
3. Alpaca signup + Turnstile (interim inbox on form — migrate to digithings@)
