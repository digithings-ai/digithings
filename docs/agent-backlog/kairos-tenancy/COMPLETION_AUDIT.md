# Kairos epic — completion audit (GitHub Auth proven, 2026-08-30T21:18Z)

**Verdict: NOT COMPLETE** — do not mark goal complete. Staging E2E still blocked on vendor captchas / secrets. Observer `GET /settings/app-urls` currently fails the develop `/dashboard` pin against live `/olympus` Pages+EF (exit 3). Scheduled house GHA book-commit is still unproven (last schedule failed; #3331 stamp + #3334 UUID stringify are on `main` awaiting next cron). Monday 2026-08-31 ledger was recovered operator-side (`8ab9840f-0946-4026-860b-cce20f75eb93` / `commit-run/52066e03-6c50-44bb-af18-e263664eacd4`); that is not a green `pipeline-olympus.yml` run.

**2026-09-01T00:20Z — [#3356](https://github.com/digithings-ai/digithings/pull/3356) is CI-green and ready, still human-merge only.** HEAD `332265428` (empty coverage retrigger on `6ea1846ec`). Dual-export `bash scripts/build-digiquant.sh` **passed** on both SHAs; review coverage **passed** (`reviewed:agent` + in-session comment). Live still `/olympus/` **200** `/dashboard/` **404**. Fail-closed resume: `python scripts/kairos_pages_dashboard_gate.py` (exit **3** while 404; `--apply` deploys settings/checkout/portal only after all four `/dashboard` paths are 200). Do **not** merge #3356 from the authoring agent. Do **not** `--apply` the gate while Pages 404s.

**2026-09-01T00:05Z — Pages `/dashboard` twin on `main` is [#3356](https://github.com/digithings-ai/digithings/pull/3356) (`6ea1846ec`), human-merge only.** Dual-exports `frontend/olympus` at `/olympus` then `/dashboard` (pin `OLYMPUS_BASE_PATH`, wipe `.next` between passes, CSP `/dashboard*`). Prior SHA `35aae1b27` `bash scripts/build-digiquant.sh` **passed** (~2m33s); both trees exported (`dist/olympus/404.html` 31296 vs `dist/dashboard/404.html` 31588). **Parallel** to house Python hotfixes — do not stack. After merge + live `/dashboard` **200**: human adds Auth redirect `https://digiquant.io/dashboard/auth/callback/` (keep olympus callback) and Access on `/dashboard/*`; **then** `kairos_pages_dashboard_gate.py --apply`. Do **not** redeploy EF while live `/dashboard` is 404. Do **not** merge this from the authoring agent. House merge order unchanged: [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) then [#3340](https://github.com/digithings-ai/digithings/pull/3340). Do not `workflow_dispatch`. Do not apply 113 or 900.

**2026-08-31T23:45Z — digest `horizon_hourse` + H6 `conviction_delta` clamp.** [#3353](https://github.com/digithings-ai/digithings/pull/3353) squash-merged to `develop` (`6f45d073f`). Main cherry-pick [#3354](https://github.com/digithings-ai/digithings/pull/3354) (`1fbc37fe2`) is **human-merge only**. Dual-key radar rows take the typo; JSON `true` is rejected. Merge order: [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) then [#3340](https://github.com/digithings-ai/digithings/pull/3340). Do not `workflow_dispatch`. Do not apply 113 or 900.

**2026-08-31T23:17Z — four `main` hotfixes CI-green, human-merge only.** Merge order: [#3343](https://github.com/digithings-ai/digithings/pull/3343) (`bf6360855`, bias/reason) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) (`dd62373b6`, PatchOp add + Finding coerce + pair-list) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) (`59153b167`, H6 ForecastTerms unwrap + tenor) then [#3340](https://github.com/digithings-ai/digithings/pull/3340) (`6fdf156a7`, calendar 114; `db-migrate` waits in `production`). Authoring agent must not merge PRs into `main`. Live Pages: `/olympus/` **200**, `/dashboard/` **404**, `/build-info.json` commit `3601f72df` (`2026-08-31T20:42:57Z`). Core `olympus_schema_migrations` still through **110** (no 112/113/114). Overlay `--check` exit 0; `--dry-run` `considered=6 targets=4 billing_active=1 byok_present=0 persist_enabled=0`. `kairos_cron_check.py` exit **2** (`MAILGUN_NOT_CONFIGURED`). Staging E2E exit **3** (`public_app_urls_ok`). Do not `workflow_dispatch`. Do not apply 113 or 900. Do not weaken `public_app_urls_ok`. Do not redeploy settings EF with `/dashboard` URLs while Pages 404 that path.

**2026-08-31T23:06Z — [#3349](https://github.com/digithings-ai/digithings/pull/3349) on `develop` (`b7cc98fad`):** remaining 33426508863 fail-softs. Gemini Finding/Source `properties`/`fields` pair-lists flatten; H6 `ForecastTerms` unwraps `{terms: {...}}` and copies only missing tenor from the H5 base (GLD/SLV/IAU). Main: [#3348](https://github.com/digithings-ai/digithings/pull/3348) (add + Finding coerce + pair-list) is **human-merge only**, independent of [#3343](https://github.com/digithings-ai/digithings/pull/3343) (bias/reason) and [#3340](https://github.com/digithings-ai/digithings/pull/3340) (calendar 114). Do not `workflow_dispatch`. Do not apply 113.

**2026-08-31T22:19Z — [#3342](https://github.com/digithings-ai/digithings/pull/3342) on `develop` (`3f3119988`):** house GHA fail-softs from `33426508863`. Dedicated `bias` validator maps `cautious` → `neutral` (and consults `_LITERAL_SYNONYMS`); H6 amendment `reason` truncated to 2000 at the registry write boundary (079 CHECK). Main cherry-pick [#3343](https://github.com/digithings-ai/digithings/pull/3343) is **human-merge only** so the next `0 12 * * *` cron picks them up. Do not `workflow_dispatch`. Do not apply 113.

**2026-08-31T21:43Z — [#3338](https://github.com/digithings-ai/digithings/pull/3338) on `develop` (`db3745b7e`):** repo ledger `114_economic_calendar_authenticated_select.sql` (authenticated SELECT on the shared macro calendar). Live `core` already had the policy; `olympus_schema_migrations` still through 110. Do **not** steal top-level `113_*.sql` (staged cutover stays under `migrations/cutover/`). Do **not** merge [#3321](https://github.com/digithings-ai/digithings/pull/3321) (that numbering failed `test_cutover_stays_under_cutover_dir`).

**2026-08-31T21:24Z — [#3337](https://github.com/digithings-ai/digithings/pull/3337) on `develop` (`eb791dd99`):** H9 recovery CLI from booked positions (no H8/LLM). Allowlists `recover_ledger` as a third `append_commit_chain(` site. Do **not** merge conflicting [#3332](https://github.com/digithings-ai/digithings/pull/3332).

**2026-08-31T20:50Z — Monday ledger recovered on `core` (not GHA):** house `portfolio_ledger_commits` `8ab9840f-0946-4026-860b-cce20f75eb93` + `documents` `commit-run/52066e03-6c50-44bb-af18-e263664eacd4` for 2026-08-31. Positions match the booked book (VGK 25 / XLF 20 / CASH 20.663). Operator recovery used the CLI that later landed as #3337; that is not a green `pipeline-olympus.yml` run.

**2026-08-31T20:39Z — [#3334](https://github.com/digithings-ai/digithings/pull/3334) on `main` (`3601f72df`):** `_json_safe` stringifies `UUID` at the PostgREST write boundary (same helper that already coerced `date`/`datetime`). Fixes the `33426508863` retry `TypeError` in `publish_document`. Keeps `on_conflict=date`. Do **not** apply 113. Do **not** `workflow_dispatch`.

**2026-08-31T20:10Z — [#3331](https://github.com/digithings-ai/digithings/pull/3331) on `main` (`9f898ec1d`):** stamps house `workspace_id` on H9 ledger / nav / positions / metrics writers; **keeps** `on_conflict=date`. `pipeline-olympus.yml` checks out `ref: main` even when the schedule event is on default `develop`. Last schedule `33426508863` failed `23502` on pre-#3331 main. Next `0 12 * * *` cron is the live proof.

**2026-08-31 — [#3325](https://github.com/digithings-ai/digithings/pull/3325) on `develop` (`a8bd41741`):** public path `/dashboard/` only; workspace `frontend/dashboard`; `NEXT_PUBLIC_DASHBOARD_*`. Live Pages still `/olympus` 200 / `/dashboard` 404. Site `/build-info.json` is `9f898ec1d` (`2026-08-31T20:13:43Z`); `/olympus/build-info.json` is 404 HTML. Do not weaken `public_app_urls_ok`. Do not redeploy settings EF with `/dashboard` until Pages ships that path.

**2026-08-31T14:30Z staged unique-drop 113:** `digiquant/supabase/migrations/cutover/113_drop_legacy_book_uniques.sql` (not auto-applied). Do not apply on `core` while `origin/main` house writers still upsert `on_conflict=date`. `require_overlay_legacy_book_safe` stays.

**2026-08-31T11:42Z overlay fail-closed:** [#3277](https://github.com/digithings-ai/digithings/pull/3277) on `develop` (`11d45bfb0`). Persist-on private book writes raise `legacy_book_unique` until staged 113 is applied.

**2026-08-31T11:24Z house upsert:** live `pipeline-olympus` on `main` failed `42P10` after core 105 replaced `UNIQUE(date, document_key)`. [#3278](https://github.com/digithings-ai/digithings/pull/3278) squash-merged to `main` (`2df473110`, hotfix CI 36/36). Overlay **documents** are anon-safe after 110; **positions/nav/ledger** still collide on 097 `UNIQUE(date)` — persist-on cannot prove `overlay_daily` `succeeded` until 113 is applied. Ledger `23502` on the 2026-08-31 schedule is a separate miss; [#3331](https://github.com/digithings-ai/digithings/pull/3331) is the stamp (still awaiting next cron).

**2026-08-30 product-gates follow-up:** creator/ops `entitlement_grants` + free-teaser + FX Hub
`client_product_grants` implemented on branch `cursor/kairos-product-gates-3d52` (migration 108).
Full gap: [`KAIROS-ALPACA-FINALIZE-GAP.md`](KAIROS-ALPACA-FINALIZE-GAP.md) and
`/opt/cursor/artifacts/kairos-alpaca-finalize-gap.md`. Still **not** epic-complete.

Full artifact: `/opt/cursor/artifacts/kairos-github-auth-prod-proof.md`  
Human ask: `/opt/cursor/artifacts/HUMAN-CAPTCHA-ALL-VENDORS.md`  
Prior vendor recheck: `/opt/cursor/artifacts/kairos-completion-audit-vendor-recheck.md`  
Captcha-ask docs: [#3239](https://github.com/digithings-ai/digithings/pull/3239) merged into `develop` (superseded here with GitHub proof refresh).

## Summary

| Gate | Status |
|------|--------|
| Identity | **digithings** ([#3236](https://github.com/digithings-ai/digithings/pull/3236) merged) |
| Stripe / Mailgun / Alpaca API secrets | **MISSING** — captchas (forms re-filled digithings@) |
| Core EF vendor secrets | **not set** (vault / APP_URL / SUPABASE_* only) |
| Staging E2E | exit **3** — live EF `/olympus` vs develop `/dashboard` pin; next miss exit **2** (9 named secrets) |
| Mailgun notify loud-fail | exit **2** — `MAILGUN_NOT_CONFIGURED` |
| Olympus Auth Pages (#3231) | live on prod Pages |
| **GitHub Auth login** | **PROVEN** on `digiquant.io` + `core` DB |
| mig 107 personal workspace | **fired** for GitHub user (`plan_tier=free`, owner) |
| Email/password on login UI | **absent** (Google + GitHub only) — cannot use digithings@ Agentmail password path |
| Draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) | left draft |
| Cutover `900` | **not applied** |

## GitHub Auth — prod evidence (no secrets)

Project `rwagjbkvxkdwqmouagad` (`core`), PAT label **digithings**:

| Fact | Value |
|------|-------|
| `auth.users` count | **2** |
| Providers | **1× github**, **1× email** |
| GitHub user id | `0408ba97-caba-44d3-b2d0-5690ab5160a9` |
| GitHub email | `chris.stefan@proton.me` |
| GitHub login | `chrizefan` |
| Created / last sign-in | `2026-08-30T21:14:44Z` / `2026-08-30T21:15:48Z` |
| Personal workspace | `4700ff6e-…` slug `u-0408ba97caba44d3b2d05690ab5160a9` |
| Membership | owner |
| `plan_tier` | `free` (default; not Stripe-sourced) |
| Trigger | `on_auth_user_created_ensure_workspace` enabled; row timestamps match user insert |
| Bootstrap fix | **not needed** |

Unauth smoke: `https://digiquant.io/olympus/login` → **308** → `/olympus/login/` **200** (Continue with Google / Continue with GitHub).

Authed browser (agent desktop session still open): sidebar shows GitHub user email + Sign out; `/olympus/settings/` data source `rwagjbkvxkdwqmouagad.supabase.co`.

## Secrets obtained (names only)

None of the staging-required vendor API secrets. Present locally (not EF vendors): `digithings-supabase-pat`, `digithings-github-oauth.env`, signup password files only.

## Captcha still needed?

**Yes — all three.** Reply `Stripe captcha done` / `Mailgun captcha done` / `Alpaca turnstile done` after solving in open Cloud Agent browser tabs (do not close sibling vendor tabs).

## Next steps (staging E2E)

1. Human solves vendor captchas → agent writes `digithings-*.env` + EF `secrets set`.
2. Re-run `scripts/kairos_staging_e2e.py` (expect exit **2** while vendor secrets are empty and remaining hops are unproven; once secrets land expect exit **4** + `KAIROS_STAGING_E2E_REMAINING_HOPS` until product-state reads prove Stripe (`active` **and** `has_stripe_subscription`), Alpaca paper OAuth, overlay, fill, and digest log **plus** inbox confirmation. House `active` without Stripe ids does not prove checkout. Exit **0** only when those five hops are proven).
3. Optional: elevate a test workspace `plan_tier` only via documented ops path — GitHub user’s personal WS stays `free` until Stripe checkout.

## Docs branch

`cursor/kairos-github-auth-proof-3d52` — compare  
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-github-auth-proof-3d52
