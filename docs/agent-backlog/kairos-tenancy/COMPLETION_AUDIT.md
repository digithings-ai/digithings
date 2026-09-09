# Kairos epic — completion audit (GitHub Auth proven, 2026-08-30T21:18Z)

**Verdict: DELIVERED (owner closed 2026-09-01)** — live E2E and house schedule proof were **not** obtained. Follow-up [#3391](https://github.com/digithings-ai/digithings/issues/3391) stays open: pick it up after the next `pipeline-olympus.yml` `cron: "17 9/10/11/12 * * *"` schedule and stamp this file with the run id and probe exits. Do not claim house GHA or staging E2E passed. Do not re-open the epic unless a probe contradicts delivery.

**2026-09-01T10:04Z — main stack squash-merged (owner asked).** Order [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) → [#3387](https://github.com/digithings-ai/digithings/pull/3387) → [#3356](https://github.com/digithings-ai/digithings/pull/3356) → [#3359](https://github.com/digithings-ai/digithings/pull/3359) → [#3340](https://github.com/digithings-ai/digithings/pull/3340). `origin/main` is `c532fc096`. Live house proof now exit **3** (`waiting for next schedule after 2026-09-01T10:03:42+00:00`); `--dispatch` **4**; pages gate **3** (all `/dashboard/*` still 404 — Pages rebuild not live yet). Do not `workflow_dispatch`. Do not `--apply` until `/dashboard/` **and** `/dashboard/settings/brokers/callback/` are 200. Do not apply 113 until a counting scheduled run proves the widened upserts. Draft promotions [#3183](https://github.com/digithings-ai/digithings/pull/3183) / [#3256](https://github.com/digithings-ai/digithings/pull/3256) left open.

**2026-09-01T09:45Z — live-proof issue retarget.** [#3388](https://github.com/digithings-ai/digithings/issues/3388) auto-closed when [#3390](https://github.com/digithings-ai/digithings/pull/3390) squash-merged (`close` in the subject plus `#3388`). Replacement [#3391](https://github.com/digithings-ai/digithings/issues/3391) is the open follow-up. Agent token cannot reopen #3388.

**2026-09-01T09:30Z — owner close.** Issue [#3388](https://github.com/digithings-ai/digithings/issues/3388) opened (`[agent] validate execution/tenancy on next house pipeline run`), later replaced by #3391. Epic / INDEX / HUMAN-UNBLOCK stamped delivered on `develop` (`9a3b7d2cf`, [#3390](https://github.com/digithings-ai/digithings/pull/3390)). Last live probes (still true, **not** proof): house proof exit **5** (`failsofts=#3343 OPEN MERGEABLE CLEAN #3348 OPEN MERGEABLE CLEAN #3351 OPEN MERGEABLE CLEAN #3354 OPEN MERGEABLE CLEAN stack ready (do not merge from authoring agent)`); `--dispatch` **4**; pages gate **3** (all `/dashboard/*` 404 including Alpaca callback; `/olympus/.../callback/` **200**); route `--check` **0** (`routing_enabled=false`); overlay `--check` **0**; cron check **2** (`MAILGUN_NOT_CONFIGURED`). `origin/main` still `3601f72df`. Unique-conflict writers [#3387](https://github.com/digithings-ai/digithings/pull/3387) are draft on `main` — merge **after** fail-softs, never from the authoring agent. Labels / Project #1 add on the follow-up issue failed from this agent token.

**2026-09-01T09:00Z — [#3356](https://github.com/digithings-ai/digithings/pull/3356) HEAD `ebbb311b5`.** Pages twin now fail-closes unless `dist/dashboard/settings/brokers/callback/` exports with `alpaca-oauth-callback`. CI green (review coverage + `bash scripts/build-digiquant.sh`); Next listed `○ /settings/brokers/callback` on both `/olympus` and `/dashboard` passes. Live `/olympus/settings/brokers/callback/` **200**, `/dashboard/.../callback/` **404**. **Human-merge only** (parallel to house fail-softs). Do not `--apply` until live `/dashboard/` **and** `/dashboard/settings/brokers/callback/` are 200. Authoring agent must not merge #3356.

**2026-09-01T08:41Z — [#3384](https://github.com/digithings-ai/digithings/pull/3384) squash-merged to `develop` (`5574b9394`).** House proof exit 5 now prints `failsofts=#3343 OPEN MERGEABLE CLEAN #3348 OPEN MERGEABLE CLEAN #3351 OPEN MERGEABLE CLEAN #3354 OPEN MERGEABLE CLEAN stack ready (do not merge from authoring agent)`. Live re-probe: house **5**; `--dispatch` **4**; pages gate **3** (all `/dashboard` 404); route `--check` **0**; overlay `--check` **0**; cron check **2** (`MAILGUN_NOT_CONFIGURED`). `origin/main` still `3601f72df`. Main PRs still OPEN MERGEABLE CLEAN: #3343 → #3348 → #3351 → #3354 then #3340; parallel #3356 / #3359. Authoring agent must not merge those. Do not `workflow_dispatch`. Do not `--apply`.

**2026-09-01T08:30Z — house proof fail-soft mergeability line** (landed as [#3384](https://github.com/digithings-ai/digithings/pull/3384)). On exit 5 the CLI also prints `failsofts=` from `gh pr view`. Still exit **5**. Never merges those PRs. [#3383](https://github.com/digithings-ai/digithings/pull/3383) already squash-merged to `develop` as `6785c44d4`. Main [#3354](https://github.com/digithings-ai/digithings/pull/3354) stack-clean HEAD `54fd0e7b4`. Do not merge #3343/#3348/#3351/#3354/#3340/#3356/#3359 from the authoring agent. Do not `workflow_dispatch`. Do not `--apply`.

**2026-09-01T07:52Z — [#3383](https://github.com/digithings-ai/digithings/pull/3383) squash-merged to `develop` (`6785c44d4`).** House proof CLI fail-closes while `origin/main` is UUID-hotfix `3601f72df` (live exit **5**; `--dispatch` exit **4**). `gh run list` `headSha` is the develop trigger, so counting uses `created_at` vs `origin/main` committer time, not the trigger SHA. Pages gate **3**; route `--check` **0**; overlay `--check` **0**; cron check **2** (`MAILGUN_NOT_CONFIGURED`). Do not merge #3343/#3348/#3351/#3354/#3340/#3356/#3359 from the authoring agent. Do not `workflow_dispatch`. Do not `--apply`.

**2026-09-01T07:33Z — [#3381](https://github.com/digithings-ai/digithings/pull/3381) squash-merged to `develop` (`a463d0b10`).** Canonical operator secrets/CLIs are `DIGIQUANT_*` / `scripts/digiquant_*.py`. Retired `OLYMPUS_*` / `KAIROS_*` / `ATLAS_*` names stay readable aliases. Live re-probe: pages gate **3** (`/olympus/` 200 `/dashboard/` 404, `/build-info.json` `3601f72df`); house proof **3**; route `--check` **0** (`routing_enabled=false`); overlay `--check` **0**; cron check **2** (`MAILGUN_NOT_CONFIGURED`). `pipeline-olympus.yml` + `kairos-cron-check.yml` filenames unchanged. Do not set `DIGIQUANT_EXECUTION_ROUTING=1`. Do not merge #3356 / fail-softs / #3359 from the authoring agent. Do not `--apply` until `/dashboard` 200.

**2026-09-01T05:13Z — [#3375](https://github.com/digithings-ai/digithings/pull/3375) on `develop` (`ca4e15a3b`).** Staging E2E logs remaining-hop product-state after Observer hops, then still exits **3** when those hops fail. Live re-probe 2026-09-01T05:12Z: pages gate **3** (`/dashboard` 404 on `/` login/ callback/ settings/); house proof **3**; route `--check` **0** (`routing_enabled=false`); cron check **2** (`MAILGUN_NOT_CONFIGURED`); staging E2E **3** with blockers `plan_tier_not_custom`, `no_alpaca_paper_oauth`, `overlay_not_succeeded`, `no_paper_fill`, `no_digest_log` (redeem-invite 404, app-urls `/olympus`). [#3374](https://github.com/digithings-ai/digithings/pull/3374) (`11665a789`) recorded #3372/#3373 on `develop`. Local dual-export re-proof of [#3356](https://github.com/digithings-ai/digithings/pull/3356) `332265428`: `dist/olympus/` + `dist/dashboard/` present; dashboard HTML `_next` prefixes are `/dashboard/_next` only. Do not merge #3356 from the authoring agent. Do not `--apply` until `/dashboard` 200.

**2026-09-01T04:05Z — [#3373](https://github.com/digithings-ai/digithings/pull/3373) on `develop` (`35826445e`).** Persist-on private overlay with a no-op / fail-soft H9 chain can no longer finish `succeeded`. `execute_overlay` calls `require_overlay_legacy_book_safe` after the chain; `_safe_invoke_graph` re-raises `OverlayLegacyBookBlocked`. Remaining hop `overlay_daily_claimed` stays unproven until staged 113. Does not apply 113.

**2026-09-01T03:42Z — [#3372](https://github.com/digithings-ai/digithings/pull/3372) on `develop` (`8bc46d220`).** Settings About / staging harness name `overlay_legacy_book_unique` when overlay_daily `job_runs.error` is `legacy_book_unique`. `persist_disabled` still wins. Still five remaining hops.

**2026-09-01T03:22Z — [#3370](https://github.com/digithings-ai/digithings/pull/3370) on `develop` (`3b4e71c18`).** Combined `kairos_cron_check.py` includes route `--check`. Live probe still **exit 2** (`MAILGUN_NOT_CONFIGURED`). Overlay + sync + route store probes pass. Staging E2E exit **3**; pages gate exit **3**; house proof exit **3**.

**2026-09-01T03:11Z — [#3369](https://github.com/digithings-ai/digithings/pull/3369) on `develop` (`986082b76`).** Overlay route cron is the production submit seam for `route_pending_orders` (was library-only). Live `python scripts/kairos_route_cron.py --check` exit **0** (`routing_enabled=false`). `--all` still exit **3** (`KAIROS_ROUTING_DISABLED`) without `submit_order`. Enabling `OLYMPUS_KAIROS_ROUTING=1` in any real environment is a **human** decision. Does not move live E2E until vendor secrets + Pages/EF cutover. House proof still exit **3**; Pages `/olympus/` **200** `/dashboard/` **404**; `/build-info.json` `3601f72df`.

**2026-09-01T02:40Z — [#3367](https://github.com/digithings-ai/digithings/pull/3367) on `develop` (`207dd0a68`).** House GHA proof CLI is on `develop`. Live probe exit **3**: latest schedule is still `33426508863` at 18:42Z (before exclusive cutoff `2026-08-31T20:39:00Z`). Staging E2E exit **3** (app-urls `/olympus` vs `/dashboard`; redeem-invite `404 NOT_FOUND`). Pages `/olympus/` **200** `/dashboard/` **404**; `/build-info.json` `3601f72df`. **Human before 12:00 UTC Sep 1:** merge fail-softs [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) so the cron checks out those writers; otherwise Gemini schema failures from `33426508863` can still fail the proof run. After fail-softs: [#3340](https://github.com/digithings-ai/digithings/pull/3340) (`db-migrate` in `production`). Parallel (do not stack): [#3356](https://github.com/digithings-ai/digithings/pull/3356) Pages twin, [#3359](https://github.com/digithings-ai/digithings/pull/3359) H9 timeout. Authoring agent must not merge `main`. Do not `workflow_dispatch`. Do not `--apply` until `/dashboard` 200.

**2026-09-01T02:20Z — Observer redeem-invite hop.** Staging E2E POSTs `/settings/access/redeem-invite` with `{code: short}` (under Deno min length — no grant, no attempt row). Mounted handlers return `INVITE_INVALID` / `EMAIL_REQUIRED`. Live v32 404s. This is a runtime proof of the 112 route after `--apply`, not a sixth remaining hop. Do not `--apply` until [#3356](https://github.com/digithings-ai/digithings/pull/3356) is live.

**2026-09-01T01:55Z — [#3364](https://github.com/digithings-ai/digithings/pull/3364) on `develop` (`c5c098631`):** `--apply` fetches the live settings ESZIP after deploy and exits **6** unless that bundle has executable POST redeem-invite + `/dashboard` pins. Follow-up: prove checkout + portal ESZIPs too (live v32 pins `/olympus` on all three). Do not `--apply` until [#3356](https://github.com/digithings-ai/digithings/pull/3356) is live.

**2026-09-01T01:45Z — live settings ESZIP proof on `--apply`.** `kairos_pages_dashboard_gate.py --apply` still refuses while Pages `/dashboard` 404s (exit 3) and while checkout source lacks redeem-invite / still pins `/olympus` (exit 5). After a deploy it now fetches the live settings ESZIP (`GET …/functions/settings/body`) and exits **6** unless that bundle contains executable `POST /access/redeem-invite` plus `/dashboard` app-url pins. Live core is still settings **v32** (no redeem-invite, `/olympus` callbacks). Do **not** `--apply` until #3356 is live. Do not mark the epic complete.

**2026-09-01T01:10Z — core migration 112 applied.** `112_product_invite_codes.sql` is on `core` (`rwagjbkvxkdwqmouagad`): tables `product_invite_codes` / `product_invite_redemptions` / `product_invite_attempts` exist, RLS on, anon/authenticated grants **none**, `service_role` granted. Anon PostgREST `SELECT` → **401** `42501` permission denied on all three. `olympus_schema_migrations` stamped `112_product_invite_codes.sql`. CLI ledger name `112_product_invite_codes` (no `.sql` suffix). Invite rows = **0** (operator has not inserted hashes). Live settings EF **v32** does **not** mount `POST /access/redeem-invite` (develop handlers do). Redeem waits on the same Pages+EF `/dashboard` cutover — do **not** redeploy settings while `/dashboard` 404s. This does **not** prove FX Hub redeem E2E. Do **not** apply staged cutover 113 or 900. Do **not** stamp or apply repo **114** via MCP — [#3340](https://github.com/digithings-ai/digithings/pull/3340) is the human `db-migrate` path. CLI also has a row named `113_economic_calendar_authenticated_select` — that is the **calendar SELECT under the wrong number**, not the unique-drop. Live Pages still `/olympus/` **200** `/dashboard/` **404**; staging E2E exit **3**; `kairos_pages_dashboard_gate.py` exit **3**. Overlay `--check`/`--dry-run` exit 0 (`byok_present=0 persist_enabled=0`). Vendor `digithings-{stripe,mailgun,alpaca,byok}.env` still absent.

**2026-09-01T00:47Z — H9 PostgREST timeout:** [#3360](https://github.com/digithings-ai/digithings/pull/3360) on `develop` (`f0fa15dc4`); [#3359](https://github.com/digithings-ai/digithings/pull/3359) on `main` (`5bf6e90de`) is CI-green (39 checks) and **human-merge only**. `ThreadPoolExecutor` workers are non-daemon; `shutdown(wait=False)` returned to the caller but process exit still joined a hung query (`after_raise=0.051`, `parent_wall=30.028`). Daemon thread + subprocess proof: `parent_wall=0.073`. **Parallel** to house fail-softs and [#3356](https://github.com/digithings-ai/digithings/pull/3356) — do not stack. Authoring agent must not merge #3359. House merge order unchanged: [#3343](https://github.com/digithings-ai/digithings/pull/3343) → [#3348](https://github.com/digithings-ai/digithings/pull/3348) → [#3351](https://github.com/digithings-ai/digithings/pull/3351) → [#3354](https://github.com/digithings-ai/digithings/pull/3354) then [#3340](https://github.com/digithings-ai/digithings/pull/3340). Do not `workflow_dispatch`. Do not apply 113 or 900.

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
| Staging E2E | exit **3** — not proven; deferred to [#3391](https://github.com/digithings-ai/digithings/issues/3391) |
| Mailgun notify loud-fail | exit **2** — `MAILGUN_NOT_CONFIGURED` |
| Olympus Auth Pages (#3231) | live on prod Pages |
| **GitHub Auth login** | **PROVEN** on `digiquant.io` + `core` DB |
| mig 107 personal workspace | **fired** for GitHub user (`plan_tier=free`, owner) |
| Email/password on login UI | **absent** (Google + GitHub only) — cannot use digithings@ Agentmail password path |
| Draft [#3183](https://github.com/digithings-ai/digithings/pull/3183) | left draft |
| Cutover `900` | **not applied** |
| Epic | **DELIVERED** (owner closed 2026-09-01) — live house/E2E proof is [#3391](https://github.com/digithings-ai/digithings/issues/3391) |

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

## Next steps (live proof — [#3391](https://github.com/digithings-ai/digithings/issues/3391))

The epic is delivered. On the next house schedule, pick up #3391:

1. Run `python scripts/digiquant_house_pipeline_proof.py` (never `workflow_dispatch`; `--dispatch` must stay **4**). Stamp the schedule run id and exit.
2. Re-probe Pages gate, staging E2E (`python scripts/digiquant_staging_e2e.py`), route/overlay/cron. Do not `--apply` while `/dashboard/` or the Alpaca callback 404. Do not weaken `public_app_urls_ok`.
3. Record whether fail-softs #3343 → #3348 → #3351 → #3354 and unique-conflict #3387 are MERGED (authoring agent must not merge them).
4. Human solves vendor captchas when ready → agent writes `digithings-*.env` + EF `secrets set`. Staging E2E still expects exit **3** until Pages+EF `/dashboard` cutover, then **2** while vendor secrets are empty. Exit **0** only when the five remaining hops are proven. Optional: elevate a test workspace `plan_tier` only via documented ops path — GitHub user’s personal WS stays `free` until Stripe checkout.
5. Do not re-open the epic unless a probe contradicts delivery.

## Docs branch

`cursor/kairos-live-proof-issue-3391-3d52` — compare  
https://github.com/digithings-ai/digithings/compare/develop...cursor/kairos-live-proof-issue-3391-3d52
