<!-- title: [epic] Olympus client-ready: Kairos execution + user tenancy -->

## Goal

Ship the two remaining Olympus milestones so the product can take paying clients: **Kairos**
(paper-first broker execution: Alpaca connect, IBKR read-first) and **user tenancy** (Supabase
Auth login, Stripe tiers, private per-user books, overlay pipelines with BYOK, email digests).

Authoritative spec: `docs/superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md`
(decisions D1–D10 are locked there; do not re-litigate in child issues).

## Locked shape (summary)

- Tiers: Observer (free; Atlas + narrative, no weights/NAV) → Baseline (full house book, read) →
  Custom (overlays, private book, broker connect, BYOK) → Enterprise (manual).
- Payments: **Stripe** (ADR-0004). Identity: **Supabase Auth**; digikey untouched.
- Olympus stays a static export; enforcement = RLS + Supabase Edge Functions.
- Brokers: Alpaca OAuth2/paper first; IBKR OAuth 1.0a read-first, orders feature-flagged off.
- External venues: broker is authoritative; append-only mirror tables (`broker_*`); internal
  `portfolio_ledger_*` stays authoritative only for `paper_internal`.
- **No live trading in this epic.** Live cutover is a separate, human-gated epic.

## Child work packages

Wave A
- [x] K0 — Kairos execution contracts
- [x] T0 — Workspaces + RLS privacy boundary

Wave B (after K0)
- [x] K1 — Alpaca paper adapter (policy gate: broker adapter)
- [x] K2 — IBKR Web API read-first adapter (policy gate: broker adapter)
- [x] T1 — Supabase Auth login (human gate: auth flow)

Wave C (K3 after K1)
- [x] K3 — Broker credential vault (human gate: cryptography)
- [x] T2 — Stripe plan tiers (human gate: webhook secret handling)
- [x] T5 — Tier-gated Olympus UI

Wave D
- [x] K4 — Order-intent router + broker mirror sync (after K1+K3)
- [x] T3 — Settings: profile, brokers, notifications (after T1+K3)

Wave E
- [x] K5 — Daily digest + holding-change email v0 (after K4)
- [x] T4 — Overlay pipeline runs, private books (after T0+T2+K4)

## Program-level acceptance

- [x] House pipeline regression: `pytest -m unit tests/dq/olympus/` behavior unchanged by every child PR.
      Live GHA (`pipeline-olympus.yml` `ref: main`) was red 2026-08-30 after core
      105 dropped `UNIQUE(date, document_key)` — [#3278](https://github.com/digithings-ai/digithings/pull/3278)
      squash-merged to `main` as `2df473110` (2026-08-31T11:24Z). Scheduled
      house daily `33426508863` (2026-08-31 12:00 UTC cron; started 18:42Z) is
      the live publish proof — observe only; do not `workflow_dispatch`. Do not
      treat unit green as a substitute for that run. `origin/main` book writers
      still upsert `on_conflict=date`; do not apply staged 113.
- [x] RLS proof (local harness vs canonical 001–110 + staged 900 A2 membership-only: 59/59 2026-08-31; 109 house teaser is pre-cutover only; 110 narrows anon private-book reads to house so overlay persist cannot leak; post-T1 anon-drop on `core` still human §6): user A cannot read user B's private rows; anon reads zero private rows post-900; free JWT sees 0 house weights/NAV/fills. Never apply 900 to `core` from this work.
- [ ] E2E (staging): sign up → subscribe (Stripe test) → connect Alpaca paper → overlay run →
      order routed to paper venue → fill mirrored → digest email received.
- [x] No live `submit_order` reachable without env flag + human-gated code path (test-pinned).

## Human-owned prerequisites (tracked here, not blocking child code)

- [ ] Alpaca Connect OAuth app registration submitted (long pole for product connect)
- [ ] IBKR OAuth 1.0a vendor onboarding email sent (longest pole; scope to include trading)
- [ ] Stripe test-mode products (Baseline, Custom) + webhook secret provisioned
- [ ] Mailgun API key fixed + sending domain confirmed
- [ ] Supabase Auth providers (Google, GitHub) enabled on `core`
- [x] `DIGIQUANT_VAULT_MASTER_KEY` generated into deploy secrets
- [ ] Legal read on investment-adviser status before any live-cutover epic


## Agent delivery status (2026-08-31, remaining hops + cron CLIs)

**Verdict: NOT COMPLETE** — staging E2E still blocked on Stripe/Mailgun/Alpaca OAuth
captchas and Google Auth. All 12 WPs have code on `develop`. This branch adds
production cron CLIs, remaining-hop proofs from Settings product state, staged
900 §A2 membership-only restore, and a fail-closed GHA **spec** (not installed:
`cursor/*` cannot write `.github/workflows/`).

**Schema (`core`):** migrations **096–110** applied (`110_anon_house_only_private_books`
narrows `anon_read` on private books to house; documents house+system). Live probe
2026-08-31: overlay doc visible to service (1) and hidden from `anon` (0); house
`positions` still 323 for anon. Cutover **900 not applied**. Local RLS harness
(throwaway DB + 001–110 + staged 900 A2): **pre-cutover 110 8/8 + post-cutover 59/59 PASS** (2026-08-31).

**Edge Functions (`core`):** `settings` **v32 ACTIVE** (`verify_jwt=true`, includes
`GET /jobs` `/fills` `/notifications/log` `/app-urls` + public Alpaca client id).
ESZIP source matches this branch (no redeploy this pass). Checkout **v8** / portal
**v9** / webhook **v7** (`verify_jwt=false`). Checkout/portal await Stripe price
secrets (`PRICE_NOT_CONFIGURED`). EF secret **names** on core: vault + `APP_URL` +
Finnhub + platform `SUPABASE_*`. Still **no** `STRIPE_*` / `MAILGUN_*` / `ALPACA_*`.
`APP_URL` / `NEXT_PUBLIC_APP_URL` on `core` is **`https://digiquant.io`** (verified
2026-08-31 via Observer `GET /settings/app-urls`: Alpaca callback + billing return
under **`/olympus`**, no loopback). Live Pages still serve `/olympus/*`
(`build-info.json` commit `2df473110` / `2026-08-31T11:27:05Z`); `/dashboard/*`
is **404**. Develop `app-url.ts` and the staging harness pin `/dashboard/...`.
**Do not redeploy** settings EF with `/dashboard` URLs while live Pages 404
that path — Alpaca/billing returns would miss. Do **not** weaken
`public_app_urls_ok` to accept `/olympus`; that is a deploy/path contract, not
a remaining hop. Checkout return URLs on the live EF are
`/olympus/settings/?tab=billing`. Brokers tab reads the **public** Alpaca OAuth
client id from `GET /app-urls` (empty until EF secrets land; never the secret)
so connect does not wait on a Pages `NEXT_PUBLIC_*` rebuild.

**Remaining hops (Observer JWT, re-audit 2026-08-31T08:36Z):** all five unproven.
Unproven hops now carry closed-vocabulary blocker codes in Settings About and
the staging harness (Observer live: `plan_tier_not_custom`,
`no_alpaca_paper_oauth` / `alpaca_api_key_not_oauth` on ops-custom, `overlay_not_succeeded`,
`no_paper_fill` / `fill_without_oauth`, `digest_inbox_unconfirmed`). Staging E2E **exit 2** (9 named vendor secrets); Observer hops all ok including
Custom checkout `PRICE_NOT_CONFIGURED`. `job_runs` / `broker_executions` /
`notification_log` / `stripe_events` / BYOK rows = **0**. One ops-custom workspace
has an Alpaca **paper `api_key`** connection (1 active + 2 revoked; not OAuth;
does not prove the remaining hop). House is `enterprise`/`active` **without**
Stripe ids — must not prove checkout. Baseline Stripe also must not (Custom-only
remaining-hop pin). Overlay `--dry-run` against core
(after D1 `plan_floor` honor): `considered=5 targets=3 billing_active=1` — the
creator GitHub workspace (`plan_tier=free`, `plan_floor=custom`). Dry-run now
also prints `byok_present` and `persist_enabled` (live core: `byok_present=0
persist_enabled=0`). Overlay `--execute` refuses without `OLYMPUS_OVERLAY_PERSIST=1`
(`OVERLAY_EXECUTE_NOT_CONFIGURED`) so a persist-off run cannot finish
`persist_disabled` and look like a hop. Migration 110 makes overlay **documents**
safe from anon leak; **positions / nav_history / ledger** still collide on 097's
legacy `UNIQUE(date)` / `UNIQUE(date,ticker)` / `PRIMARY KEY (date)` and 069's
one-root-per-run_date. House ops writers on `develop` now stamp house
`workspace_id` and target the widened UNIQUEs (#3280 materialize, #3281 metrics,
P6 ops-book PR). House GHA chain Group A **reads** (`commit_io._prior_nav`,
`portfolio_materialize._prior_nav`, `load_portfolio_performance_snapshot`,
`breaker_scale_from_nav_history`, `opening_snapshot` positions/NAV) now filter
house `workspace_id` so overlay NAV/positions cannot compound the house index.
House research/MCP `query_data` likewise defaults Group A tables to house
when `eq` omits `workspace_id` (overlay same-date rows cannot seed agents).
House ops `backfill_position_event_reasons` pages house `position_events`
only (overlay rows are not rewritten by id). `audit_activity_coverage_api`
max-dates ignore later overlay Group A rows. House preflight `documents`
reads (`load_prior_context` and related continuity loaders) pin house so
overlay private docs cannot seed the house graph.
Overlay same-day books still collide until those 097 keys are
**dropped** on `core` (after `main` house GHA writers are also widened). Staged
cutover **113** (`migrations/cutover/113_drop_legacy_book_uniques.sql`) holds
that DDL; it is **not** auto-applied and must **not** be copied to top-level
or applied on `core` while `origin/main` `commit_io` / `portfolio_materialize`
still upsert `on_conflict=date`. Staging 113 does **not** lift
`require_overlay_legacy_book_safe`. Do not set
`OLYMPUS_OVERLAY_PERSIST=1` expecting a private book — persist-on still cannot
prove the overlay remaining hop until 113 is applied on the target. BYOK rows on
that workspace are still **0**, so `--execute` would skip `no_credentials` even
with persist on. Settings Pipeline / Brokers / Notifications tabs now read
`GET /jobs` `/fills` `/notifications/log` so skip reasons and empty remaining
hops are visible in the UI. Settings About shows the five remaining hops from
member-scoped reads (Observer-visible; digest log without inbox confirmation
stays unproven). Overlay publish skips `daily_snapshots`. Flag still **unset**
because BYOK rows = **0** — do not `--execute`. Seal resume path:
`python scripts/kairos_seal_byok.py` → exit **2** until gitignored
`digithings-byok.env` exists. Do not seal a placeholder; `--apply` only against
an overlay-entitled workspace (GitHub creator `plan_floor=custom`, not Observer
free, not house/system, not ops-custom `custom`/`none` without a grant).

**Cron CLIs (do not run `--all` / `--execute --all` on Observer or the api_key row):**
- Overlay `--check` / `--dry-run` **exit 0** when `CORE_SUPABASE_URL` +
  `CORE_SUPABASE_SERVICE_KEY` are in the process env (Cloud Agent env does not
  ship them; load from a gitignored PAT-fetched file for this VM only).
- Sync `--check` / `--dry-run` **exit 0**; `auth_kind=api_key` is held
  (`alpaca_api_key_held`, reason `alpaca_api_key_does_not_prove_oauth_hop`).
  `--all` must not poll that row; `--connection-id` on it exits **3** with
  `ALPACA_API_KEY_SYNC_HELD`. Fill remaining-hop also requires Alpaca paper
  OAuth (an `api_key` fill cannot prove it).
- Combined `kairos_cron_check.py` still **exit 2** — Mailgun names empty. Overlay
  + sync store probes pass once `CORE_SUPABASE_*` are set.
- House GHA must still splice `pipeline-olympus-mailgun.env.yml` on a `chore/` /
  `feat/` branch. Scheduled probe spec still not installed under `.github/workflows/`.

**Auth (`core`):** GitHub Enabled + Email Enabled; **Google Disabled**. Mailgun MCP
still auth-fails. Canonical inbox `digithings@agentmail.to` has no vendor API-key mail.

**Harness:** `python scripts/kairos_staging_e2e.py` → exit **3** (Observer
`GET /settings/app-urls` fails `public_app_urls_ok`: live EF still returns
`/olympus/settings/...` while develop pins `/dashboard/settings/...`). Live
Pages `/olympus/settings/` **200**, `/dashboard/settings/` **404**. After the
Pages+EF path cutover lands together, the next expected miss is exit **2**
(9 named vendor secrets). Observer checkout hop and Phase C both POST
`tier=custom` (Baseline would leave
broker/overlay/fill `TIER_FORBIDDEN`). Settings Billing makes Custom the primary
checkout CTA for the same reason. Remaining-hop `browser_stripe_checkout`
requires Custom/enterprise **and** Stripe ids — Baseline Stripe does not prove
it. Observer `notification_prefs.daily_digest` is **true** (PATCH 200 on free; not
Custom-gated). Digest remaining-hop also requires that pref, plus log + inbox
(Settings About library matches Python; inbox confirm stays operator-only so
the UI hop stays unproven). `python -m digiquant.notify.dispatch --dry-run`
prints digest candidate counts without sending.
`python scripts/kairos_apply_vendor_secrets.py` → exit **2** until the three
gitignored `digithings-{stripe,mailgun,alpaca}.env` files exist (then `--apply`
pushes names onto core EF secrets). `python scripts/kairos_seal_byok.py` → exit
**2** until `digithings-byok.env` exists. Other Observer Settings hops (profile /
notifications / brokers / keys reads, PATCH digest on, TIER_FORBIDDEN on Custom
writes, checkout `PRICE_NOT_CONFIGURED`, wrong-path 404) still match. A fifth
personal workspace (`kairos-e2e-…+s3101@`, `plan_tier=free`) appeared on core;
it does not prove Stripe.

**Landed 2026-08-31 — [#3325](https://github.com/digithings-ai/digithings/pull/3325) on `develop` (`a8bd41741`):**
squash-merged from `cursor/dashboard-rebrand-rebase-3d52`. Combines #3320
(no `/olympus/` public path, no 308s, `NEXT_PUBLIC_DASHBOARD_*`) + #3297
(`frontend/olympus` → `frontend/dashboard`, npm package `dashboard`) + leftover-key
sweep. Open foreign PRs **#3293 / #3297 / #3320** are superseded. Pins:
`tests/scripts/test_build_digiquant_dashboard_path.py`,
`tests/scripts/test_frontend_dashboard_workspace.py`. Live Pages (`main`
`2df473110`) still serve `/olympus/` until a **human** coordinates Pages+EF
`/dashboard` cutover. **Do not** weaken `public_app_urls_ok` to `/olympus`.
House GHA `33426508863` (schedule, `ref: main`) is the live publish proof for
[#3278](https://github.com/digithings-ai/digithings/pull/3278) — observe only;
do not `workflow_dispatch`.

**Landed 2026-08-31T14:30Z (not epic-complete):** staged unique-drop **113**
under `digiquant/supabase/migrations/cutover/` (not auto-applied, not on
`core`). Overlay book fail-closed [#3277](https://github.com/digithings-ai/digithings/pull/3277)
on `develop` (`11d45bfb0`) still raises `legacy_book_unique` until 113 is
applied. House documents upsert hotfix [#3278](https://github.com/digithings-ai/digithings/pull/3278)
on `main` (`2df473110`). Live Pages `build-info.json` is `2df473110` /
`2026-08-31T11:27:05Z` (`/olympus` 200, `/dashboard` 404). Staging E2E exit
**3** (app-urls path contract). Vendor secrets still missing.

**Do not mark epic complete** until staging E2E + human/legal/IBKR gates clear.
Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) /
[#3256](https://github.com/digithings-ai/digithings/pull/3256). Never apply cutover 900.
Never apply staged 113 on `core` while `main` house writers are date-only.
