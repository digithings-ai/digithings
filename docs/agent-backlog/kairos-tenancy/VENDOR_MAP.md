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
| Products / prices | Product catalog → **Brief / Desk / Studio** (see [`PRICING.md`](PRICING.md)). Do **not** name products Baseline or Custom. |
| Env → price IDs (today’s EFs) | still `STRIPE_PRICE_BASELINE_*` / `STRIPE_PRICE_CUSTOM_*` until the three-rung hop. Target names: `STRIPE_PRICE_BRIEF_*` / `STRIPE_PRICE_DESK_*` / `STRIPE_PRICE_STUDIO_*` |
| Webhook endpoint | Developers → Webhooks → Add endpoint |
| Webhook URL | `https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1/stripe-webhook` |
| Webhook secret | Endpoint → Signing secret (`whsec_…`) → `STRIPE_WEBHOOK_SECRET` |
| Local file (when ready) | `.local/secrets/digithings-stripe.env` |
| Human gate | hCaptcha on signup — screenshot `/opt/cursor/artifacts/stripe-hcaptcha-human-needed.png` |
| Signup attempt email | `digithings@agentmail.to` (re-filled 2026-08-30; hCaptcha image challenge after Create account) |

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
| Signup attempt email | **digithings@agentmail.to** (re-filled 2026-08-30 recheck; still reCAPTCHA-blocked) |
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
| Signup attempt | **digithings@agentmail.to** (re-filled 2026-08-30; Turnstile still blocks Sign up) |
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
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py --apply
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_staging_e2e.py
```

Check-only (exit 2 until files + required key names exist; never prints values):

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py
```

## Browser tabs left open for human (paused)

1. Stripe register + hCaptcha image challenge (`digithings@agentmail.to`) — `/opt/cursor/artifacts/vendor-stripe-hcaptcha-2026-08-30.png`
2. Mailgun signup + reCAPTCHA error (`digithings@agentmail.to`) — `/opt/cursor/artifacts/vendor-mailgun-recaptcha-2026-08-30.png`
3. Alpaca signup + Turnstile (`digithings@agentmail.to`) — `/opt/cursor/artifacts/vendor-alpaca-turnstile-2026-08-30.png`

Human ask: `/opt/cursor/artifacts/HUMAN-CAPTCHA-ALL-VENDORS.md`
