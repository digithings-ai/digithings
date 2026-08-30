# Kairos — human unblock checklist (minimal, ordered)

**Status: WAITING_HUMAN_CAPTCHA (2026-08-30T21:40Z) — NOT COMPLETE.** Identity: **digithings** ([#3236](https://github.com/digithings-ai/digithings/pull/3236) merged). Forms still filled as `digithings@agentmail.to`; captchas still block Stripe (hCaptcha), Mailgun (reCAPTCHA), Alpaca (Turnstile). No vendor EF secrets set. Staging E2E exit **2** (9 named secrets). Olympus Auth Pages live (#3231) — **GitHub login proven on prod** (`auth.users` github + mig 107 Personal `plan_tier=free`). Live Settings EF proven from digiquant.io after CORS deploy (`cursor/settings-ef-cors-053b`): profile/notifications/brokers GET **200**; free connect → **`TIER_FORBIDDEN`**. Prod Settings **UI tabs** still need draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) promote (`main` is pre-T3 shell). Do not merge #3183 yet; never apply cutover 900.

**Secret files (when obtained):** `.local/secrets/digithings-stripe.env`, `digithings-mailgun.env`, `digithings-alpaca.env` — **not** `cursor-cloud-agent-*.env`.  
**Canonical inbox:** `digithings@agentmail.to` (interim `cursor-cloud-agent6060@agentmail.to` = accidental only).  
**Identity:** [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md) · `/opt/cursor/artifacts/kairos-digithings-vendor-naming-ready.md`  
**Human captcha ask:** `/opt/cursor/artifacts/HUMAN-CAPTCHA-ALL-VENDORS.md`  
**Vendor map:** [`VENDOR_MAP.md`](VENDOR_MAP.md) · `/opt/cursor/artifacts/kairos-VENDOR-MAP.md`  
**Waiting:** `/opt/cursor/artifacts/kairos-WAITING-ON-SECRETS.json` (`identity=digithings`)  
**Post-GitHub audit:** `/opt/cursor/artifacts/kairos-completion-audit-post-github.md`  
**Vendor docs:** [#3233](https://github.com/digithings-ai/digithings/pull/3233) + captcha-ask [#3239](https://github.com/digithings-ai/digithings/pull/3239) · GitHub proof [#3240](https://github.com/digithings-ai/digithings/pull/3240)  
Env dashboard: https://cursor.com/dashboard/cloud-agents/environments/e/ea5347f2-e16e-4f90-a63d-706ffd01128f  
Deploy detail: [`DEPLOYMENT.md`](DEPLOYMENT.md)  
Audit: [`COMPLETION_AUDIT.md`](COMPLETION_AUDIT.md)

Loud-fail gates (after paste):
```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_cron_check.py
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.notify.dispatch --require-mailgun
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.olympus.overlay --check
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.olympus.kairos.sync_cron --check
```

### 0a) Auth Pages on `main` — DONE (#3231) + GitHub login proven

[#3231](https://github.com/digithings-ai/digithings/pull/3231) squash-merged to `main`. Smoke: `https://digiquant.io/olympus/login` → **308** → `/olympus/login/` **200** + Login UI (Google + GitHub). Keep Access on `/olympus/*` until intentional cutover. Do **not** apply `900_*`. Do **not** merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183).

**GitHub Auth (2026-08-30T21:15Z):** human signed in on prod. `core` DB: `auth.users` = 2 (1 github / 1 email); GitHub user → Personal workspace owner `plan_tier=free` via mig 107 trigger. No bootstrap fix needed. Evidence: `/opt/cursor/artifacts/kairos-github-auth-prod-proof.md`.

**Settings EF CORS (2026-08-30T21:38Z):** `settings` / `create-checkout-session` / `customer-portal` answer OPTIONS with 204 + Allow-*; browser fetch from digiquant.io works. Branch `cursor/settings-ef-cors-053b` (deployed to core). Free-tier connect remains `TIER_FORBIDDEN`.

---

## 0) Paste into Cursor Cloud env secrets (names + format only)

Replace / fill these in the Cursor environment secret store. **Values never go in git.**

| Name | Format hint |
|------|-------------|
| `SUPABASE_ACCESS_TOKEN` | Personal access token `sbp_…` — file `.local/secrets/digithings-supabase-pat` (label **digithings**) works; re-paste into Cursor env if process env drops it. See [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md) |
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
**Done product:** mig 107 bootstrap; settings GET/PATCH; vault seal; Settings/billing CORS preflight; free connect → `TIER_FORBIDDEN` (GitHub WS still `free`).

---

## 0b) Workspace bootstrap — RESOLVED

mig **107** + settings `ensureCallerWorkspace` — Agentmail JWT settings **200**. Personal workspace exists. Ops may elevate to `custom` for vault/overlay probes until Stripe prices land (document clearly — **not** Stripe-sourced). GitHub user’s personal WS remains **`free`** (2026-08-30 Settings E2E; ops elevate not applied). Notification prefs point at Agentmail inbox for digest when Mailgun lands.

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
  AUTH_GOOGLE_CLIENT_ID=… \
  AUTH_GOOGLE_CLIENT_SECRET=… \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…
```

Prefer writing values first to `.local/secrets/digithings-*.env` (gitignored), then `secrets set` from those files. Never commit values.

---

## 2) Human captcha (paused)

Do **not** resume Stripe / Mailgun / Alpaca signup until human replies captcha done (or says continue). Screenshots and map: [`VENDOR_MAP.md`](VENDOR_MAP.md).

---

## 3) After secrets land

1. Redeploy settings + create-checkout-session + stripe-webhook EFs if needed.
2. `python scripts/kairos_staging_e2e.py` — expect past named-secret loud-fail.
3. Update [`WAITING-ON-SECRETS.json`](WAITING-ON-SECRETS.json) status.
