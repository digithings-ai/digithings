# Kairos — human unblock checklist (minimal, ordered)

**Status: WAITING_HUMAN (2026-09-01T01:10Z) — NOT COMPLETE.** Core **112** (`product_invite_*`) applied + `olympus_schema_migrations` stamped `112_product_invite_codes.sql` (invite rows still 0). Do **not** apply cutover 113/900; do **not** MCP-apply 114 ([#3340](https://github.com/digithings-ai/digithings/pull/3340) is the human `db-migrate` path). CLI `113_economic_calendar_authenticated_select` is the calendar SELECT under the wrong number, not the unique-drop. Identity: **digithings** ([#3236](https://github.com/digithings-ai/digithings/pull/3236) merged). [#3325](https://github.com/digithings-ai/digithings/pull/3325) is on `develop` (`a8bd41741`): public path `/dashboard/`, workspace `frontend/dashboard`. Live Pages still serve `/olympus/` (200) and `/dashboard/` (404). Pages twin for `main` is [#3356](https://github.com/digithings-ai/digithings/pull/3356) (`332265428`) — **human-merge only**, **parallel** to house Python PRs. H9 PostgREST timeout [#3359](https://github.com/digithings-ai/digithings/pull/3359) (`5bf6e90de`) is CI-green (39 checks) and **human-merge only** — daemon-thread 70s deadline so a hung `price_history` / ledger `execute()` cannot pin the house GHA until the 240-minute cancel. Develop backport [#3360](https://github.com/digithings-ai/digithings/pull/3360) squash-merged (`f0fa15dc4`). After [#3356](https://github.com/digithings-ai/digithings/pull/3356) is live (`/dashboard` 200): add Auth redirect `https://digiquant.io/dashboard/auth/callback/` (keep olympus callback), Access on `/dashboard/*`, **then** redeploy settings EF. Do **not** redeploy EF while `/dashboard` 404s. Site `/build-info.json` is `3601f72df` (`2026-08-31T20:42:57Z`) after Python-only main hotfix [#3334](https://github.com/digithings-ai/digithings/pull/3334); `/olympus/build-info.json` 404. That rebuild does not ship `/dashboard/`. Do **not** weaken `public_app_urls_ok`; do **not** redeploy settings EF with `/dashboard` URLs until Pages ships that path. Forms still filled as `digithings@agentmail.to`; captchas still block Stripe (hCaptcha), Mailgun (reCAPTCHA), Alpaca (Turnstile). No vendor EF secrets set (`digithings-{stripe,mailgun,alpaca}.env` still absent). Staging E2E exit **3** (Observer `GET /settings/app-urls` path contract); after Pages+EF cutover the next miss is exit **2** (9 named secrets). Auth Pages live (#3231) — **GitHub login proven on prod** at `/olympus/login/`. Account Settings IA is on `develop` ([#3264](https://github.com/digithings-ai/digithings/pull/3264)) and remaining hops on Settings About ([#3269](https://github.com/digithings-ai/digithings/pull/3269)). House documents upsert hotfix [#3278](https://github.com/digithings-ai/digithings/pull/3278) on `main` (`2df473110`). Ledger stamp hotfix [#3331](https://github.com/digithings-ai/digithings/pull/3331) squash-merged to `main` as `9f898ec1d` (stamps house `workspace_id`, keeps `on_conflict=date`). UUID stringify hotfix [#3334](https://github.com/digithings-ai/digithings/pull/3334) squash-merged to `main` as `3601f72df` (`_json_safe` coerces UUID; develop port [#3335](https://github.com/digithings-ai/digithings/pull/3335)). Scheduled house GHA `33426508863` **failed** (`23502` then UUID `TypeError`; checkout `ref: main` from pre-#3331/#3334). Digest `horizon_hourse` + H6 `conviction_delta` clamp landed on `develop` as [#3353](https://github.com/digithings-ai/digithings/pull/3353) (`6f45d073f`); main cherry-pick [#3354](https://github.com/digithings-ai/digithings/pull/3354) is **human-merge only**. House fail-softs on `main` are **human-merge only** — order [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) then [#3340](https://github.com/digithings-ai/digithings/pull/3340) (`db-migrate` in `production` after 114). **Parallel** (do not stack): [#3356](https://github.com/digithings-ai/digithings/pull/3356) (Pages twin) and [#3359](https://github.com/digithings-ai/digithings/pull/3359) (H9 timeout). Authoring agent must not merge PRs into `main`. Monday 2026-08-31 house ledger was recovered operator-side (`8ab9840f-0946-4026-860b-cce20f75eb93`); H9 recovery CLI is [#3337](https://github.com/digithings-ai/digithings/pull/3337) on `develop` (`eb791dd99`) — do **not** merge [#3332](https://github.com/digithings-ai/digithings/pull/3332). Calendar authenticated SELECT is ledger **114** ([#3338](https://github.com/digithings-ai/digithings/pull/3338), `db3745b7e`) — do **not** merge [#3321](https://github.com/digithings-ai/digithings/pull/3321). Scheduled pipeline proof is still the next `cron: "0 12 * * *"` — do **not** `workflow_dispatch`. Overlay private books are fail-closed on `develop` ([#3277](https://github.com/digithings-ai/digithings/pull/3277), `legacy_book_unique`) until staged 113. Do **not** apply 113 while main writers are date-only. Do **not** merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) / [#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.

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
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_pages_dashboard_gate.py
# when live /dashboard/ login/ callback/ settings/ are all 200:
# PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_pages_dashboard_gate.py --apply
# --apply also requires this checkout to pin /dashboard app URLs and
# POST /access/redeem-invite (exit 5 if run from main / olympus-pinned EF source)
# and each live settings/checkout/portal ESZIP to contain those markers
# (exit 6 while any bundle is still v32 /olympus).
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_apply_vendor_secrets.py
# when all three .local/secrets/digithings-{stripe,mailgun,alpaca}.env exist:
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_apply_vendor_secrets.py --apply
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_seal_byok.py
# when .local/secrets/digithings-byok.env exists (BYOK_PROVIDER + BYOK_API_KEY):
# PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_seal_byok.py --apply --workspace-id <entitled-uuid>
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_cron_check.py
PATH="$PWD/.venv/bin:$PATH" make kairos-cron-check
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.notify.dispatch --require-mailgun
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.olympus.overlay --check
# After Stripe + BYOK only — never `--execute --all` on Observer:
# PATH="$PWD/.venv/bin:$PATH" python -m digiquant.olympus.overlay --execute --workspace-id <uuid>
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.olympus.kairos.sync_cron --check
```

Overlay / sync `--check` need `CORE_SUPABASE_URL` + `CORE_SUPABASE_SERVICE_KEY` in the
process env (not in the Cloud Agent env today). This VM can load a gitignored
PAT-fetched file under `.local/secrets/` for those two names only. Do **not**
`--execute` overlay while BYOK is missing (`byok_present=0`). Sync cron **holds**
Alpaca `auth_kind=api_key` (`ALPACA_API_KEY_SYNC_HELD` / `alpaca_api_key_held`);
`--all` will not poll the ops-custom paper row. The oauth hop is still unproven.

Scheduled probe (not installed from `cursor/*` — `.github/workflows/` is protected):
copy `docs/agent-backlog/kairos-tenancy/kairos-cron-check.workflow.yml` to
`.github/workflows/kairos-cron-check.yml` on a `chore/` or `feat/` branch. Probe is
`--check` / `--dry-run` only; house daily stays on `pipeline-olympus.yml`.

House digest send (after Mailgun GitHub secrets exist): splice
`docs/agent-backlog/kairos-tenancy/pipeline-olympus-mailgun.env.yml` into the
"Run Olympus research pipeline" `env:` on the same `chore/`/`feat/` branch.
Without those names, `hermes.chain` close-out logs `MAILGUN_NOT_CONFIGURED` and
skips (fail-soft; the book still commits).

### 0a) Auth Pages on `main` — DONE (#3231) + GitHub login proven

[#3231](https://github.com/digithings-ai/digithings/pull/3231) squash-merged to `main`. Smoke: `https://digiquant.io/olympus/login` → **308** → `/olympus/login/` **200** + Login UI (Google + GitHub). Account Settings IA + `?tab=billing` / radius 0: [#3266](https://github.com/digithings-ai/digithings/pull/3266) merge-committed to `main` 2026-08-31T09:48Z (Cloudflare Pages rebuild may lag). Keep Access on `/dashboard/*` until intentional cutover. Do **not** apply `900_*`. Do **not** merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) / [#3256](https://github.com/digithings-ai/digithings/pull/3256) — those are full `develop`→`main` promotes, not the account UI path.

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

**Done on `core` EF secrets:** `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID`, `APP_URL=https://digiquant.io`, `NEXT_PUBLIC_APP_URL=https://digiquant.io` (verified Observer `GET /settings/app-urls` 200, no loopback). Checkout returns to `/olympus/settings/?tab=billing`.
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
