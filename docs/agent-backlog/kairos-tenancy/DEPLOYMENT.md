# Kairos + tenancy — deployment runbook

> **Preparation artifact only.** Nothing here is auto-applied. Execute steps in
> order when promoting the program to the live `core` Supabase project and
> digiquant.io. Cross-links:
> [EPIC](EPIC.md) ·
> [HUMAN-UNBLOCK](HUMAN-UNBLOCK.md) (ordered secret → EF → Auth → Stripe → Alpaca → flag) ·
> [issue pack README](README.md) ·
> [implementation spec](../../superpowers/specs/2026-08-29-kairos-tenancy-implementation-spec.md)
> (D1–D10 locked).

---

## 1. Merge-state snapshot (as of 2026-08-30)

### Code — all 12 WPs on `develop`

| WP | PR | Landed on | Notes |
|----|-----|-----------|-------|
| Plan / spec | [#3081](https://github.com/digithings-ai/digithings/pull/3081) | `develop` | Locked decisions |
| K0–K5, T0, T2, T4 | [#3141](https://github.com/digithings-ai/digithings/pull/3141) | `develop` | Module→develop promotion (backend) |
| T1 Auth login | [#3099](https://github.com/digithings-ai/digithings/pull/3099) | `develop` | Flag-gated UI; anon-drop deferred |
| T3 Settings UI | [#3120](https://github.com/digithings-ai/digithings/pull/3120) | `develop` | `settings` Edge Function |
| T5 Tier UI | [#3119](https://github.com/digithings-ai/digithings/pull/3119) | `develop` | |
| Chain + RLS harness | [#3140](https://github.com/digithings-ai/digithings/pull/3140) | `develop` via #3141 | 61/61 proof vs canonical chain |
| 103 trigger fix | [#3147](https://github.com/digithings-ai/digithings/pull/3147) | `develop` | `trigger_set_updated_at` (prod apply found the typo) |

### Schema on `core` (`rwagjbkvxkdwqmouagad`) — **096–110 + 112 applied (2026-09-01)**

Applied via the runbook §2 manual path (`execute_sql` / `apply_migration` +
`olympus_schema_migrations` stamps). `097` used the documented
`session_replication_role = replica` wrap (075/069 append-only triggers).
**Cutover `900` was not applied** (human-gated, §6).

| # | File | WP | Ledger |
|---|------|-----|--------|
| 096–098 | workspaces / tenant columns / RLS | T0 | stamped |
| 099 | `broker_connections` | K3 | stamped |
| 100–101 | Stripe claim sync + webhook ordering | T2 | stamped |
| 102 | `broker_orders` / executions / snapshots | K4 | stamped |
| 103 | `notification_prefs` + `notification_log` | K5 | stamped (fixed function name) |
| 104 | `workspace_provider_credentials` (BYOK) | T4 | stamped |
| 105 | `documents.workspace_id` | T4 | stamped |
| 106 | align prefs/log to canonical 103 columns | K5/T3 | **applied 2026-08-30** (empty-table rebuild; 103 IF NOT EXISTS had no-op'd on drift) |
| 107–110 | personal workspace trigger, entitlements, house teaser, anon house-only private books | T0/T1/T5 | stamped |
| 111 | reserved Group A unique-drop | — | **no file** |
| 112 | hashed FX Hub invite tables | product | **applied 2026-09-01** (`olympus_schema_migrations` `112_product_invite_codes.sql`; CLI name `112_product_invite_codes`; rows = 0) |
| (cutover 113) | staged `migrations/cutover/113_drop_legacy_book_uniques.sql` | overlay persist | **not applied** |
| 114 | `economic_calendar` authenticated SELECT | house | **not stamped** on olympus ledger; human [#3340](https://github.com/digithings-ai/digithings/pull/3340) `db-migrate` |
| (cutover) | staged `migrations/cutover/900_…` | human | **not applied** |

### Remaining (human / production gates)

```
§5 secrets + Auth providers + Stripe/Mailgun/Alpaca apps
  → Edge Function secrets (needs sbp_) + optional full monorepo settings redeploy
  → develop → main Pages promote (flag-off; no cutover 900) — human release gate (~199 commits)
  → §6 cutover (Access on → flag flip → anon-drop 900 → verify → Access off)
```

### Pages promote prep (2026-08-30, post-#3181)

| Item | Status |
|------|--------|
| `NEXT_PUBLIC_DASHBOARD_AUTH` | Narrow Auth Pages PR defaults **on** under `CF_PAGES=1` when unset (UI gate only; anon RLS remains). Set `=0` to force classic shell. Full tenancy still needs cutover `900` (human, §6) |
| Cutover `900` | **Not applied**; stays under `migrations/cutover/` (not top-level) |
| Branch | `cursor/promote-kairos-pages-3d52` = `origin/develop` tip (`f92a8810`, merge of #3181) |
| Draft PR develop→main | **Not opened** — agent `gh` token can merge/ready existing PRs + push branches, but **cannot** `createPullRequest` / comment / label (`Resource not accessible by integration`). **Parent:** open draft PR `base=main` `head=cursor/promote-kairos-pages-3d52` (title/body recipe in `COMPLETION_AUDIT.md`). |
| Review hatches | Findings drafted under `/opt/cursor/artifacts/kairos-reviews/pr-*-review.md` for #3147–#3181; **not posted** — same token 403. Parent with write token: post each body (must start with `<!-- in-session-review -->`) then `gh pr edit N --add-label reviewed:agent`. |
---

## 2. DB migrations 096–105 — apply path

### How `db-migrate.yml` actually triggers

Workflow: [`.github/workflows/db-migrate.yml`](../../../.github/workflows/db-migrate.yml).

1. **Trigger:** `push` to `main` with path `digiquant/supabase/migrations/**`, or
   `workflow_dispatch`.
2. **Environment:** `production` (required-reviewer gate — human must approve).
3. **Ledger:** table `olympus_schema_migrations (version text PRIMARY KEY)` —
   version = **full basename** (e.g. `096_workspaces_tenancy_tables.sql`).
4. **Discovery (inert for subdirs):**
   ```bash
   find digiquant/supabase/migrations -maxdepth 1 -name '*.sql' | sort
   ```
   Only top-level `NNN_*.sql` files. `migrations/cutover/` is never applied
   (same `-maxdepth 1` in `verify-supabase-migrations.sh`).
5. **Apply loop:** skip if ledger has the basename; else run file under
   `--single-transaction` (or self-`BEGIN` path) and `INSERT` the ledger row
   atomically with the DDL for unwrapped files.
6. **Secret:** `DIGI_CHECKPOINTER_POSTGRES_URI` (prod DB URI for project `core`).

So: merge migrations to `develop` → promote `develop` → `main` → approve the
`db-migrate` production run. Do **not** put the anon-drop file at top level until
cutover (§6).

### Manual alternative (`core` project `rwagjbkvxkdwqmouagad`)

Use only when the workflow cannot run (emergency) or for a staging clone.

```bash
# Link CLI to core (project ref from frontend/dashboard/lib/database.types.ts)
supabase link --project-ref rwagjbkvxkdwqmouagad

# Option A — Supabase CLI (applies pending files the CLI tracks; still prefer
# the GHA ledger path for prod so olympus_schema_migrations stays authoritative)
supabase db push

# Option B — psql against the same URI the workflow uses (one file at a time)
psql "$DIGI_CHECKPOINTER_POSTGRES_URI" -v ON_ERROR_STOP=1 --single-transaction <<'SQL'
-- paste one migration file body, then:
INSERT INTO olympus_schema_migrations(version)
VALUES ('096_workspaces_tenancy_tables.sql');
SQL
```

Apply **096 → 105 in numeric order**. Never stamp a ledger row without executing
the file (`db-migrate.yml` header / #1814).

Verify:

```sql
SELECT version, applied_at
FROM olympus_schema_migrations
WHERE version ~ '^(09[6-9]|10[0-5])_'
ORDER BY version;
```

---

## 3. Edge Function deploys

### Live status on `core` (2026-08-30, sbp unlock + settings v18)

| Function | Status | Notes |
|----------|--------|-------|
| `prices-live` | ACTIVE v8 | Pre-existing |
| `stripe-webhook` | ACTIVE (`verify_jwt=false`) | Awaits `STRIPE_WEBHOOK_SECRET` — unauth POST → `STRIPE_NOT_CONFIGURED` |
| `create-checkout-session` | ACTIVE | Runtime needs Stripe + `NEXT_PUBLIC_APP_URL` |
| `customer-portal` | ACTIVE | Runtime needs Stripe + `NEXT_PUBLIC_APP_URL` |
| `settings` | ACTIVE **v18** | Workspace `plan_tier` entitlement gate (#3196) + GET `/profile` + GET `/notifications` hydrate + PATCH. Smoke: missing/invalid JWT → gateway `401` (`settings-v18-smoke.log`). EF secrets set: `DIGIQUANT_VAULT_*`, `APP_URL`, `NEXT_PUBLIC_APP_URL` (Alpaca/Stripe/Mailgun still absent). Migration `106` stamped on `core`.

### Schema alignment (agent, 2026-08-30)

`103` was stamped while live tables already existed under a **different** column set
(`digest_enabled` / …). Empty tables were rebuilt to canonical 103 via
`106_notification_prefs_align_canonical.sql` (applied + stamped on `core`).
SQL prefs upsert smoke succeeded (service-role path).

### Deploy commands

Functions live under `digiquant/supabase/functions/`. Deploy from a checkout that
already contains the merged function code + migrations on the target DB.

**Pages `/dashboard` gate:** do **not** deploy `settings` / `create-checkout-session`
/ `customer-portal` with `/dashboard` URLs until live Pages serves that path.
Fail-closed probe (exit 3 while `/dashboard` 404s; `--apply` only after 200):

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_pages_dashboard_gate.py
# PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_pages_dashboard_gate.py --apply
```

```bash
cd digiquant/supabase
supabase link --project-ref rwagjbkvxkdwqmouagad

# Secrets first (names only — values from §5 human prerequisites)
supabase secrets set \
  STRIPE_SECRET_KEY=… \
  STRIPE_WEBHOOK_SECRET=… \
  STRIPE_PRICE_BASELINE_MONTHLY=… \
  STRIPE_PRICE_BASELINE_ANNUAL=… \
  STRIPE_PRICE_CUSTOM_MONTHLY=… \
  STRIPE_PRICE_CUSTOM_ANNUAL=… \
  NEXT_PUBLIC_APP_URL=… \
  APP_URL=… \
  DIGIQUANT_VAULT_MASTER_KEY=… \
  DIGIQUANT_VAULT_KEY_ID=v1 \
  ALPACA_OAUTH_CLIENT_ID=… \
  ALPACA_OAUTH_CLIENT_SECRET=…

# Deploys (order: webhook → checkout/portal → settings)
supabase functions deploy stripe-webhook --no-verify-jwt
supabase functions deploy create-checkout-session
supabase functions deploy customer-portal
# settings: BLOCKED until K3 + 096–099 are on the target (see functions/settings/README.md)
supabase functions deploy settings
```

### Secrets required per function (names only)

| Function | Secrets |
|----------|---------|
| `stripe-webhook` | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_BASELINE_MONTHLY`, `STRIPE_PRICE_BASELINE_ANNUAL`, `STRIPE_PRICE_CUSTOM_MONTHLY`, `STRIPE_PRICE_CUSTOM_ANNUAL` (+ platform `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`) |
| `create-checkout-session` | `STRIPE_SECRET_KEY`, `STRIPE_PRICE_*` (via tiers map), `NEXT_PUBLIC_APP_URL` |
| `customer-portal` | `STRIPE_SECRET_KEY`, `NEXT_PUBLIC_APP_URL` |
| `settings` | `DIGIQUANT_VAULT_MASTER_KEY`, `DIGIQUANT_VAULT_KEY_ID` (optional, default `v1`), `APP_URL` (or `NEXT_PUBLIC_APP_URL`), `ALPACA_OAUTH_CLIENT_ID`, `ALPACA_OAUTH_CLIENT_SECRET` |

`prices-live` is pre-existing (`FINNHUB_API_KEY`) — not part of this program’s
cutover, but leave it deployed.

Point Stripe Dashboard webhook →
`https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1/stripe-webhook`
(test mode first).

---

## 4. Olympus build / deploy (digiquant.io Cloudflare Pages)

Primary path: Cloudflare Pages git integration on `main`, build command
`bash scripts/build-digiquant.sh` (see
[`.github/workflows/deploy-digiquant-cloudflare.yml`](../../../.github/workflows/deploy-digiquant-cloudflare.yml)
— PR build-check only; dashboard owns production publish).

### Flag off (pre-cutover — default)

Cloudflare Pages env for the digiquant.io project:

| Var | Value |
|-----|-------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://rwagjbkvxkdwqmouagad.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | (anon publishable key) |
| `NEXT_PUBLIC_DASHBOARD_AUTH` | unset / empty |

Behavior: classic anon client; Cloudflare Access may still gate `/dashboard/*`.

### Flag on (cutover)

| Var | Value |
|-----|-------|
| `NEXT_PUBLIC_DASHBOARD_AUTH` | `1` |
| (same URL + anon key) | |

Then **Retry deployment** / push to `main` so `scripts/build-digiquant.sh`
rebuilds `frontend/dashboard` with the flag inlined (static export).

Local verify:

```bash
cd frontend/dashboard
NEXT_PUBLIC_DASHBOARD_AUTH=1 npm run build
# out/ must still be static-export clean
```

---

## 5. Prerequisites — agent progress vs still blocked (names only)

> **Human action order:** follow [`HUMAN-UNBLOCK.md`](HUMAN-UNBLOCK.md) (Cursor env
> secrets → EF secrets → redeploy → Auth providers → Stripe webhook → paper Alpaca →
> flag cutover). Do not merge [#3183](https://github.com/digithings-ai/digithings/pull/3183)
> until secrets are live and cutover is intentional.
>
> Secret **values** live in VM `.env` / `.local/secrets/` (gitignored) and must be
> copied into Supabase EF secrets + Cursor environment secret store. Never commit values.

| Prerequisite | Status (2026-08-30) | Blocks |
|--------------|---------------------|--------|
| Vault master key `DIGIQUANT_VAULT_MASTER_KEY` + `DIGIQUANT_VAULT_KEY_ID` | **SET in VM `.env`** and **pushed to `core` EF secrets** (2026-08-30 via `sbp_` + `supabase secrets set`). | K3 seal; settings brokers; T4 BYOK at runtime |
| `APP_URL` / `NEXT_PUBLIC_APP_URL` | **SET on `core` to `https://digiquant.io`** (2026-08-31). Observer `GET /settings/app-urls` returns Alpaca `…/olympus/settings/brokers/callback/` + billing `…/olympus/settings/?tab=billing` (no loopback; public client id empty until Alpaca secrets land). settings **v32**, checkout **v8**, portal **v9**. | OAuth redirect pin; checkout return URLs |
| Agent Mail inbox | **Available:** `digithings@agentmail.to` | Signup verification |
| Stripe test products/prices + `STRIPE_SECRET_KEY` + webhook secret | **Blocked** — signup hit hCaptcha; partial signup notes only in `.local/secrets/` (no live keys) | T2 EFs; checkout/portal; claim sync |
| Mailgun `MAILGUN_API_KEY` / `MAILGUN_DOMAIN` / `NOTIFY_FROM` | **Blocked** — values still **empty** in VM/Cursor env; smoke skipped. Fail-soft notify path OK. `sbp_` available now — paste nonempty Mailgun into EF secrets when obtained. | K5 digest / alerts |
| Supabase Auth providers (Google, GitHub) on `core` | **Partial** — **GitHub Enabled** (OAuth App still named `digiquant olympus` in the vendor console + callback). Site URL `https://digiquant.io` + `/dashboard/auth/callback/` allow-list. **Google Disabled** (skipped captcha console). | T1 login when flag on (GitHub path ready; Google still human) |
| Alpaca OAuth / paper (`ALPACA_OAUTH_CLIENT_ID` / `_SECRET`) | **Blocked** — half-finished signup notes in `.local/secrets/`; no API secrets to push. | Product broker connect |
| `SUPABASE_ACCESS_TOKEN` (`sbp_…`) | **Unlocked (agent VM)** — PAT on disk as `.local/secrets/digithings-supabase-pat` (label **digithings**; old “cursor cloud agent” naming retired). Management API `secrets list` OK. EF vault/`APP_URL` intact. **Human:** re-paste `sbp_…` into Cursor env labeled **digithings**. See [`DIGITHINGS-IDENTITY.md`](DIGITHINGS-IDENTITY.md). | EF secrets; CLI deploy |
| IBKR vendor / OAuth 1.0a onboarding | **Human / vendor** — not attempted; do not fake | K2 live verify |
| Cloudflare Access (D7) | Unchanged — keep prod Access on through §6 | Ungated prod URL |
| Legal read on adviser status | Human / counsel | Any **live** trading epic |
| PR [#3161](https://github.com/digithings-ai/digithings/pull/3161) … [#3181](https://github.com/digithings-ai/digithings/pull/3181) | **Merged** to `develop` (2026-08-30; tip `f92a8810`) | notifications + schema/docs + audits; settings EF was **v11** |
| PR [#3184](https://github.com/digithings-ai/digithings/pull/3184) | **Merged** to `develop` (2026-08-30; tip `732a77d0`) | GET `/notifications` + NotifyTab hydrate; settings EF **v12** thin pin; smoke 401. No `sbp_` / no EF secrets. #3183 draft promote left open. |
| PR [#3187](https://github.com/digithings-ai/digithings/pull/3187) | **Merged** to `develop` (2026-08-30; tip `17a84b30`) | GET `/profile` + ProfileTab hydrate; settings EF **v13** thin pin; smoke 401. No `sbp_` / no EF secrets. #3183 draft promote left open. |
| PR [#3196](https://github.com/digithings-ai/digithings/pull/3196) | **Merged** to `develop` (2026-08-30; tip `5b526914`) | Settings entitlement prefers `workspaces.plan_tier` (no JWT fail-open); settings EF **v14** thin pin; smoke 401. No `sbp_` / no EF secrets. |
| Agent unlock (2026-08-30) | **Partial** — `sbp_` + vault/APP_URL + settings **v22** + checkout **v5** + GitHub Auth + Agentmail + bootstrap (mig 107) + loud-fail `scripts/kairos_staging_e2e.py`; JWT settings **200**; uuid-bind [#3225](https://github.com/digithings-ai/digithings/pull/3225) merged | Waiting `PARTIAL_UNLOCK`. Checkout `PRICE_NOT_CONFIGURED`. Vendors still empty. #3183 left draft. |
| Live-retry (2026-08-30) | **Partial** — re-scan 0 vendor EF secrets; free→`TIER_FORBIDDEN`→ops custom; vault seal; notify prefs→Agentmail; `MAILGUN_NOT_CONFIGURED` CLI; overlay/router 45 unit; local Olympus Auth+GitHub OAuth UI | Staging E2E still blocked. Branch `cursor/kairos-live-retry-3d52`. Audit `/opt/cursor/artifacts/kairos-completion-audit-live-retry.md`. |
| PR [#3183](https://github.com/digithings-ai/digithings/pull/3183) | **Draft** promote `develop`→`main` | **Do not merge** until secrets live **and** intentional Pages cutover. |
---

## 6. Cutover checklist

Execute only after §1 queue is on `main`, §2 migrations 096–105 are in the
ledger, §3 functions are live, and §5 rows needed for launch are green.

**Safe order (do not reorder):** Access stays on → flag flip → login smoke →
apply staged SQL → verification (anon + free JWT) → frontend research-view
cutover PR merged/deployed → **then** remove Access.

- [ ] **Keep Cloudflare Access ON** for production `/dashboard/*` (staging overlay
      retained throughout).
- [ ] **Flag flip:** set `NEXT_PUBLIC_DASHBOARD_AUTH=1` on Cloudflare Pages; rebuild
      digiquant.io (`scripts/build-digiquant.sh`).
- [ ] **Smoke login:** Google + GitHub PKCE → `/dashboard/auth/callback/` → session
      (Access still in front).
- [ ] **Anon-drop + weight/NAV close (manual):**
      1. Confirm preconditions in
         [`digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql`](../../../digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql)
         header (Access must still be on).
      2. Copy to `digiquant/supabase/migrations/<next>_drop_anon_read_cutover.sql`
         (next free after 105).
      3. PR → `main` → approve `db-migrate` **or** apply via psql + ledger INSERT.
- [ ] **RLS isolation harness** (post-apply): run [`scripts/rls_proof/`](../../../scripts/rls_proof/) against the production DB (or a branch clone with the same policies) after cutover SQL is applied — `LOG=/opt/cursor/artifacts/rls_isolation_proof.log ./scripts/rls_proof/run.sh` must exit 0 (59/59 assertions).
- [ ] **Verification queries** (staged SQL verification block):
      - As `anon`: `positions`, `position_events`, `nav_history`,
        `portfolio_metrics`, `current_book_lookback`, `daily_snapshots` (base),
        `public_portfolio_positions`, `public_nav_history`, `pm-rebalance` docs,
        non-house docs → **0**; `public_daily_research` → rows and
        `research_snapshot ? 'portfolio'` is false.
      - As free-tier JWT: same weight/NAV views + `pm-rebalance` → **0**;
        `public_daily_research` + research docs (`analyst/*`, etc.) → readable.
- [ ] **Authenticated Baseline+ smoke:** JWT with `plan_tier=baseline` reads
      weight-bearing docs; cannot read another workspace’s private rows.
- [ ] **Frontend research-view cutover** (named task below) merged and Pages
      redeployed — Observer/anon paths no longer `.from('daily_snapshots')` for
      payload.
- [ ] **Cloudflare Access removal (LAST):** remove production `/dashboard/*`
      application; keep staging overlay (D7).

### Named follow-up — frontend (T1-train; do **not** land on this branch)

Cutover SQL revokes base `daily_snapshots` SELECT from anon/authenticated and
exposes research via `public_daily_research`. Inventory of reads that break
until the dashboard switches (file: `frontend/dashboard/lib/`):

| Call site | Current read | Cutover change |
|-----------|--------------|----------------|
| `queries.ts` ~713 | `daily_snapshots` select `snapshot,digest_markdown` (latest) | Observer/free → `public_daily_research` (`research_snapshot`); Baseline+ house book still from positions/NAV (or BFF) — never raw snapshot portfolio |
| `queries.ts` ~740 | `daily_snapshots` select `date,run_type` (history) | Switch to `public_daily_research` (same columns) |
| `queries.ts` ~1816 | `digest_markdown, snapshot` for digest render | Research path: render from `research_snapshot`; do not fetch `digest_markdown` for free/anon |
| `queries.ts` ~1908, ~1921 | `daily_snapshots` meta / prev date | Use `public_daily_research` |
| `queries.ts` ~1986 | `date, snapshot, digest_markdown` history | Use `public_daily_research`; drop digest_markdown for unentitled tiers |
| `queries.ts` ~2063 | `date, run_type, snapshot` | Use `public_daily_research` |
| `snapshot-fetch.ts` ~232 | latest `daily_snapshots` row → `SnapshotEnvelope` | Parse `research_snapshot` for Observer; Baseline+ weight UI must not use this envelope’s stripped digest for book weights |
| `queries.ts` ~749 | prefetch `documents` `pm-rebalance` | Gate with `can(tier, 'house_weights_nav')`; free must not fetch (RLS will empty, but skip the request) |

Track as a single agent-task issue, e.g. `[agent] cutover — Olympus reads public_daily_research`.
No frontend edits on the cutover-kit branch.

### Named follow-up — tier-gated house book views (honest smaller scope)

Cutover SQL **REVOKEs** `public_portfolio_positions`, `public_nav_history`, and
accounting NAV/attribution views from **both** `anon` and `authenticated`
(definer views — base RLS does not protect them). That fail-closes free JWT.

Why no staged `901_tier_gated_view_policies.sql` in this kit: restoring Baseline+
SELECT on those views without a proven claim gate (or a BFF that checks
`plan_tier` then reads via `service_role`) would re-open the free-JWT leak.
T5 UI already skips unentitled fetches; the data plane must stay fail-closed
until one of:

1. **BFF / Edge Function** — JWT → tier check → `service_role` select of curated
   columns; or
2. **Later migration** — re-GRANT to `authenticated` only after a
   `auth.jwt()->app_metadata->>plan_tier` policy (or security_invoker rewrite
   over workspace-scoped base tables) is tested against claim-sync lag.

Document the chosen approach on the epic before re-exposing the views.

---

## 7. E2E acceptance script skeleton

Per [EPIC.md](EPIC.md) program-level acceptance (staging / Stripe test mode):

Agent-runnable loud-fail gate (names missing secrets; **never** paper-fakes):

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/kairos_staging_e2e.py
# or: pytest -m staging_e2e tests/dq/olympus/kairos/test_staging_e2e.py
```

Full manual chain once secrets land on Cursor env **and** core EF:

```bash
# Skeleton — fill URLs/keys from staging; do not commit secrets.
set -euo pipefail
SUPABASE_FUNCTIONS="${SUPABASE_FUNCTIONS:-https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1}"
# 1) Signup / login (Supabase Auth GitHub or Email/Agentmail) — manual browser or supabase-js
# 2) Subscribe (Stripe test Checkout → Baseline or Custom)
curl -sS -X POST "$SUPABASE_FUNCTIONS/create-checkout-session" \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{"tier":"baseline","interval":"monthly"}'
# Complete Checkout in browser; wait for stripe-webhook → plan_tier claim
# 3) Connect Alpaca paper (Settings → brokers; OAuth — needs ALPACA_OAUTH_CLIENT_*)
# 4) Overlay run (T4): `OLYMPUS_OVERLAY_PERSIST=1 python -m digiquant.olympus.overlay --execute --workspace-id <uuid>`
#    Persist is safe after migration **110** (not 900). `--execute` refuses without the flag
#    (`OVERLAY_EXECUTE_NOT_CONFIGURED: OLYMPUS_OVERLAY_PERSIST`) so the hop cannot be
#    `persist_disabled`. Requires BYOK present_and_unsealable. Never `--execute --all`.
# 5) Routed order (K4): order_intent → broker_orders status accepted/filled (paper)
# 6) Mirrored fill: broker_executions row; broker_position_snapshots updated
# 7) Digest email (K5): enable notification_prefs.daily_digest; run
#    python -m digiquant.notify.dispatch ; assert Mailgun accept + notification_log
echo "E2E skeleton complete — attach screenshots / Mailgun event ids to the epic"
```

House regression (every promotion):

```bash
PATH="$PWD/.venv/bin:$PATH" pytest -m unit tests/dq/olympus/ -q
```

---

## 8. Rollback notes (per phase)

| Phase | Failure mode | Rollback |
|-------|--------------|----------|
| Migrations 096–105 on `main` | Apply error mid-chain | Fix forward (new migration). Do **not** delete ledger rows. Self-wrapping / IF NOT EXISTS files are replay-safe; cancel-in-progress only loses a ledger INSERT (next run retries). |
| Edge Functions | Bad deploy / secret miss | `supabase functions deploy <name>` prior known-good SHA; unset bad secrets carefully. Stripe webhook: disable endpoint in Dashboard if signatures fail. |
| Auth flag on | Login broken / empty chrome | Set `NEXT_PUBLIC_DASHBOARD_AUTH=` empty; rebuild Pages → anon path restored **only if** anon policies still exist. |
| Anon-drop applied | Dashboard blank for Observer / research broken | Keep Access on; roll forward with `public_daily_research` frontend switch. Do not rewrite history. Emergency: forward migration re-creating old anon policies only while Access still gates the URL. |
| Cloudflare Access removed too early | Public URL + anon/free JWT still reads weights/NAV | Re-enable Access on `/dashboard/*` immediately; finish verification before removing again. |
| Stripe / vault | Wrong keys | Rotate Stripe webhook secret; generate new vault key only with a re-seal plan (K3 rotation out of scope — avoid rotating after seal without a job). |

**Ordering tip:** Access on → flag flip → login smoke → apply cutover SQL →
verify anon **and** free JWT see zero weights/NAV → ship frontend
`public_daily_research` switch → **then** remove Access.

---

## Related

- Staged SQL:
  [`digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql`](../../../digiquant/supabase/migrations/cutover/900_drop_anon_read_cutover.sql)
- T1 cutover notes: [`frontend/dashboard/AUTH.md`](../../../frontend/dashboard/AUTH.md)
- db-migrate mechanics: [`digiquant/supabase/README.md`](../../../digiquant/supabase/README.md)
