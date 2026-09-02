# digiquant — human unblock checklist (minimal, ordered)

**Status: EPIC DELIVERED (2026-09-01) — live proof is [#3391](https://github.com/digithings-ai/digithings/issues/3391).** Owner closed without a live E2E / house schedule. **2026-09-01T10:04Z:** fail-softs + unique-conflict + Pages twin + H9 timeout + calendar 114 are on `main` (`c532fc096`). Remaining: next `0 12 * * *` schedule (house proof exit **3**), live `/dashboard/` 404 until Pages rebuild, vendor secrets, staged 113 after a green cron. Do not `workflow_dispatch`. Do not `--apply` while `/dashboard` 404s. Do not apply 113/900. Draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) / [#3256](https://github.com/digithings-ai/digithings/pull/3256) stay open.

**Operator snapshot (2026-09-01T09:26Z, still true for #3391).** [#3388](https://github.com/digithings-ai/digithings/issues/3388) auto-closed on the docs squash; use #3391. House proof failsofts line [#3384](https://github.com/digithings-ai/digithings/pull/3384) squash-merged to `develop` (`5574b9394`). Live `python scripts/digiquant_house_pipeline_proof.py` exit **5** plus `failsofts=#3343 OPEN MERGEABLE CLEAN #3348 OPEN MERGEABLE CLEAN #3351 OPEN MERGEABLE CLEAN #3354 OPEN MERGEABLE CLEAN stack ready (do not merge from authoring agent)`. `origin/main` is still UUID-hotfix `3601f72df` — merge [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) before the 12:00 UTC cron; do not `workflow_dispatch`. Pages twin [#3356](https://github.com/digithings-ai/digithings/pull/3356) HEAD `ebbb311b5` is CI-green with Alpaca OAuth callback export (human-merge only; parallel). [#3383](https://github.com/digithings-ai/digithings/pull/3383) squash-merged to `develop` (`6785c44d4`). [#3354](https://github.com/digithings-ai/digithings/pull/3354) HEAD `54fd0e7b4` is stack-clean. [#3381](https://github.com/digithings-ai/digithings/pull/3381) squash-merged to `develop` (`a463d0b10`): canonical operator secrets/CLIs are `DIGIQUANT_*` / `scripts/digiquant_*.py` (retired names remain readable aliases). Live re-probe 2026-09-01T08:40Z: `python scripts/digiquant_cron_check.py` exit **2** (`MAILGUN_NOT_CONFIGURED`); `python scripts/digiquant_route_cron.py --check` exit **0** (`routing_enabled=false`); overlay `--check` exit **0**; `python scripts/digiquant_pages_dashboard_gate.py` exit **3**. Do not set `DIGIQUANT_EXECUTION_ROUTING=1` without an explicit human decision. Overlay remaining-hop naming [#3372](https://github.com/digithings-ai/digithings/pull/3372) (`8bc46d220`) plus persist-on refuse-succeeded [#3373](https://github.com/digithings-ai/digithings/pull/3373) (`35826445e`) are on `develop`. Operator record of that leftover UNIQUE hop [#3374](https://github.com/digithings-ai/digithings/pull/3374) (`11665a789`) and staging E2E remaining-hop logs on Observer-hop failure [#3375](https://github.com/digithings-ai/digithings/pull/3375) (`ca4e15a3b`) are on `develop`. Combined cron probe [#3370](https://github.com/digithings-ai/digithings/pull/3370) is on `develop` (`3b4e71c18`). Overlay route cron [#3369](https://github.com/digithings-ai/digithings/pull/3369) is on `develop` (`986082b76`). House proof CLI [#3367](https://github.com/digithings-ai/digithings/pull/3367) is on `develop` (`207dd0a68`). **Merge fail-softs on `main` before the 12:00 UTC cron** ([#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354)) or the schedule still runs `3601f72df` without those writers. Core **112** (`product_invite_*`) applied + `olympus_schema_migrations` stamped `112_product_invite_codes.sql` (invite rows still 0). Do **not** apply cutover 113/900; do **not** MCP-apply 114 ([#3340](https://github.com/digithings-ai/digithings/pull/3340) is the human `db-migrate` path). CLI `113_economic_calendar_authenticated_select` is the calendar SELECT under the wrong number, not the unique-drop. Identity: **digithings** ([#3236](https://github.com/digithings-ai/digithings/pull/3236) merged). [#3325](https://github.com/digithings-ai/digithings/pull/3325) is on `develop` (`a8bd41741`): public path `/dashboard/`, workspace `frontend/dashboard`. Live Pages still serve `/olympus/` (200) and `/dashboard/` (404). Pages twin for `main` is [#3356](https://github.com/digithings-ai/digithings/pull/3356) (`ebbb311b5`) — **human-merge only**, **parallel** to house Python PRs. CI green: twin fail-closes unless `dist/dashboard/settings/brokers/callback/` exports (`alpaca-oauth-callback`); Pages job listed that route on both trees. Live `/olympus/settings/brokers/callback/` **200**, `/dashboard/.../callback/` **404**. Local `CF_PAGES=1 NEXT_PUBLIC_OLYMPUS_AUTH=1 bash scripts/build-digiquant.sh` on the prior SHA exported `dist/olympus/` and `dist/dashboard/` (login / auth/callback / settings present; HTML `_next` prefixes do not cross-leak). `origin/main` already has Settings remaining-hop UI under `frontend/olympus` (without `overlay_legacy_book_unique`); the twin will show the five hops from GET `/jobs` `/fills` `/notifications/log` once Pages is 200. Do not stack develop remaining-hop naming onto #3356. H9 PostgREST timeout [#3359](https://github.com/digithings-ai/digithings/pull/3359) (`5bf6e90de`) is CI-green (39 checks) and **human-merge only** — daemon-thread 70s deadline so a hung `price_history` / ledger `execute()` cannot pin the house GHA until the 240-minute cancel. Develop backport [#3360](https://github.com/digithings-ai/digithings/pull/3360) squash-merged (`f0fa15dc4`). After [#3356](https://github.com/digithings-ai/digithings/pull/3356) is live (`/dashboard/` **and** `/dashboard/settings/brokers/callback/` 200): add Auth redirect `https://digiquant.io/dashboard/auth/callback/` (keep olympus callback), Access on `/dashboard/*`, **then** redeploy settings EF. Do **not** redeploy EF while `/dashboard` 404s. Site `/build-info.json` is `3601f72df` (`2026-08-31T20:42:57Z`) after Python-only main hotfix [#3334](https://github.com/digithings-ai/digithings/pull/3334); `/olympus/build-info.json` 404. That rebuild does not ship `/dashboard/`. Do **not** weaken `public_app_urls_ok`; do **not** redeploy settings EF with `/dashboard` URLs until Pages ships that path. Forms still filled as `digithings@agentmail.to`; captchas still block Stripe (hCaptcha), Mailgun (reCAPTCHA), Alpaca (Turnstile). No vendor EF secrets set (`digithings-{stripe,mailgun,alpaca}.env` still absent). Staging E2E exit **3** (Observer `GET /settings/app-urls` path contract + redeem-invite **404** on settings v32); [#3375](https://github.com/digithings-ai/digithings/pull/3375) now logs the five remaining-hop blockers on that exit (`plan_tier_not_custom`, `no_alpaca_paper_oauth`, `overlay_not_succeeded`, `no_paper_fill`, `no_digest_log`) and still returns 3. After Pages+EF cutover the next miss is exit **2** (9 named secrets). Auth Pages live (#3231) — **GitHub login proven on prod** at `/olympus/login/`. Account Settings IA is on `develop` ([#3264](https://github.com/digithings-ai/digithings/pull/3264)) and remaining hops on Settings About ([#3269](https://github.com/digithings-ai/digithings/pull/3269)). House documents upsert hotfix [#3278](https://github.com/digithings-ai/digithings/pull/3278) on `main` (`2df473110`). Ledger stamp hotfix [#3331](https://github.com/digithings-ai/digithings/pull/3331) squash-merged to `main` as `9f898ec1d` (stamps house `workspace_id`, keeps `on_conflict=date`). UUID stringify hotfix [#3334](https://github.com/digithings-ai/digithings/pull/3334) squash-merged to `main` as `3601f72df` (`_json_safe` coerces UUID; develop port [#3335](https://github.com/digithings-ai/digithings/pull/3335)). Scheduled house GHA `33426508863` **failed** (`23502` then UUID `TypeError`; checkout `ref: main` from pre-#3331/#3334). Digest `horizon_hourse` + H6 `conviction_delta` clamp landed on `develop` as [#3353](https://github.com/digithings-ai/digithings/pull/3353) (`6f45d073f`); main cherry-pick [#3354](https://github.com/digithings-ai/digithings/pull/3354) is **human-merge only**. House fail-softs on `main` are **human-merge only** — order [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) then [#3340](https://github.com/digithings-ai/digithings/pull/3340) (`db-migrate` in `production` after 114). **Parallel** (do not stack): [#3356](https://github.com/digithings-ai/digithings/pull/3356) (Pages twin) and [#3359](https://github.com/digithings-ai/digithings/pull/3359) (H9 timeout). Authoring agent must not merge PRs into `main`. Monday 2026-08-31 house ledger was recovered operator-side (`8ab9840f-0946-4026-860b-cce20f75eb93`); H9 recovery CLI is [#3337](https://github.com/digithings-ai/digithings/pull/3337) on `develop` (`eb791dd99`) — do **not** merge [#3332](https://github.com/digithings-ai/digithings/pull/3332). Calendar authenticated SELECT is ledger **114** ([#3338](https://github.com/digithings-ai/digithings/pull/3338), `db3745b7e`) — do **not** merge [#3321](https://github.com/digithings-ai/digithings/pull/3321). Scheduled pipeline proof is still the next `cron: "0 12 * * *"` — do **not** `workflow_dispatch`. Overlay private books are fail-closed on `develop` ([#3277](https://github.com/digithings-ai/digithings/pull/3277), `legacy_book_unique`) until staged 113. Do **not** apply 113 while main writers are date-only. Do **not** merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) / [#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.

**Secret files (when obtained):** `.local/secrets/digithings-stripe.env`, `digithings-mailgun.env`, `digithings-alpaca.env` — **not** `cursor-cloud-agent-*.env`.  
**Vendor email:** `admin@digithings.ai` on Proton. No company Google account. Do not use Agentmail for vendor accounts. See [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md).  
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
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_pages_dashboard_gate.py
# when live /dashboard/ login/ auth/callback/ settings/
# and /dashboard/settings/brokers/callback/ are all 200:
# PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_pages_dashboard_gate.py --apply
# --apply also requires this checkout to pin /dashboard app URLs and
# POST /access/redeem-invite (exit 5 if run from main / olympus-pinned EF source)
# and each live settings/checkout/portal ESZIP to contain those markers
# (exit 6 while any bundle is still v32 /olympus).
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py
# when all three .local/secrets/digithings-{stripe,mailgun,alpaca}.env exist:
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py --apply
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_seal_byok.py
# when .local/secrets/digithings-byok.env exists (BYOK_PROVIDER + BYOK_API_KEY):
# PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_seal_byok.py --apply --workspace-id <entitled-uuid>
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_staging_e2e.py
# Observer also requires POST /settings/access/redeem-invite (short dummy →
# INVITE_INVALID). Live v32 404s that route until --apply.
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_house_pipeline_proof.py
# exit 5 while origin/main is still 3601f72df (merge #3343 → #3348 → #3351 → #3354
# before cron). Also prints failsofts= mergeability; never merge those PRs from
# this agent. Exit 3 until a counting 0 12 * * * schedule. Never workflow_dispatch.
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_route_cron.py --check
# --dry-run never submits. --all requires DIGIQUANT_EXECUTION_ROUTING=1 (default off → exit 3).
PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_cron_check.py
PATH="$PWD/.venv/bin:$PATH" make digiquant-cron-check
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

Scheduled probe (``.github/workflows/kairos-cron-check.yml``): fail-closed
`--check` / `--dry-run` only (overlay, sync, route, digest). Expected red until
GitHub secrets include `CORE_SUPABASE_*` plus Mailgun names. House daily stays
on `pipeline-olympus.yml`. Do not `workflow_dispatch` the house pipeline.

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
| `STRIPE_PRICE_BRIEF_MONTHLY` | `price_…` |
| `STRIPE_PRICE_DESK_MONTHLY` | `price_…` |
| `STRIPE_PRICE_STUDIO_MONTHLY` | `price_…` |
| `STRIPE_PRICE_BRIEF_ANNUAL` | `price_…` |
| `STRIPE_PRICE_DESK_ANNUAL` | `price_…` |
| `STRIPE_PRICE_STUDIO_ANNUAL` | `price_…` |
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

mig **107** + settings `ensureCallerWorkspace` — Agentmail JWT settings **200**. Personal workspace exists. Ops may elevate to `studio` for vault/overlay probes until Stripe prices land (document clearly — **not** Stripe-sourced). GitHub user’s personal WS remains **`free`** (2026-08-30 Settings E2E; ops elevate not applied). Notification prefs point at Agentmail inbox for digest when Mailgun lands.

---

## 1) Set remaining Supabase Edge Function secrets (`core`)

`sbp_…` PAT available. Remaining vendor keys still empty — set when obtained:

```bash
supabase secrets set \
  STRIPE_SECRET_KEY=… \
  STRIPE_WEBHOOK_SECRET=… \
  STRIPE_PRICE_BRIEF_MONTHLY=… \
  STRIPE_PRICE_DESK_MONTHLY=… \
  STRIPE_PRICE_STUDIO_MONTHLY=… \
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
2. `python scripts/digiquant_staging_e2e.py` — expect past named-secret loud-fail.
3. Update [`WAITING-ON-SECRETS.json`](WAITING-ON-SECRETS.json) status.
