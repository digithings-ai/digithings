## Overlay runs

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

T4 overlay pipeline (`digiquant/src/digiquant/dashboard/overlay/`) gives entitled
Studio/Enterprise workspaces a scheduled run of the **one** dashboard graph (no
`run_type` fork, no planner changes).

**Dispatch (`dispatch.py`).** Entitlement is paid Studio/Enterprise
(`plan_tier ∈ {studio, enterprise}` AND `subscription_status = active`) **or**
D1 `entitlement_grants.plan_floor ∈ {studio, enterprise}` (creator/ops without
Stripe), **and** BYOK present-and-unsealable. Misses write a
`job_runs` row `skipped` with `error` = `not_entitled` / `no_credentials` (visible,
never silent). Idempotency key is `{workspace_id}:overlay_daily:{run_date}`; claim
is insert-first + skip-locked (first claimer wins). Production persistence is
`SupabaseJobRunStore` (`INSERT … ON CONFLICT (idempotency_key) DO NOTHING`);
`MemoryJobRunStore` is the test seam. Overlay failures never write house job rows.

**Cron CLI (`cron.py`, `python -m digiquant.dashboard.overlay`).** Production
entry that writes `job_runs` via `SupabaseJobRunStore`. House and system
workspace ids are never overlay targets (even if seeded `enterprise`/`active`).
`--check` exits **2** with `OVERLAY_STORE_NOT_CONFIGURED` listing missing env
*names* (`SUPABASE_URL` / `CORE_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` /
`CORE_SUPABASE_SERVICE_KEY`). `--dry-run` prints candidate counts
(`considered`, `targets`, `billing_active`, `byok_present`) and writes nothing.
`byok_present` counts active `workspace_provider_credentials` rows among
billing-entitled targets (presence only; no unseal). Apply requires
`--workspace-id` or `--all` (refuses implicit writes).
`--all` against a free workspace inserts a visible `skipped`/`not_entitled`
row; it does not invoke the graph. Dispatch-only claims leave the row
`running`. `--execute` runs claimed jobs through the **one** dashboard graph
(`overlay/graph_invoke.py` → `run_research_then_portfolio(..., manage_usage=False)`
so overlay's `overlay_usage_scope` owns WP1 capture). `chain=None` is
refused (`OverlayExecuteRequiresChain` / `chain_required`) because
`execute_overlay(chain=None)` would mark `succeeded` without a book. A
missing overlay `olympus_profile_config` pin fails closed
(`profile_pin_missing`) — the house default is never used. A graph or runner
exception fails that claimed row (`job_runs.error` = structured code or
exception type name, never the payload) and continues the batch. Persist-off
finishes `persist_disabled`, which the staging harness does **not** treat
as proven (hop requires `succeeded` only). `--execute` apply also requires
`DIGIQUANT_VAULT_MASTER_KEY` and `DIGIQUANT_OVERLAY_PERSIST=1` (documents-safe
after migration 110; positions/NAV/ledger still blocked by legacy single-tenant
UNIQUEs until P6 — see Persist flag; `OVERLAY_EXECUTE_NOT_CONFIGURED` if either
is missing) so a
production cron cannot finish `persist_disabled` and look like a hop. Do not run
`--all` / `--execute --all` against Observer until Stripe + BYOK land;
skipped rows are not a remaining-hop proof. The cron module does
not import `byok`/`digillm` (digiquant-only CI). Production apply passes
`byok=None` so `dispatch_overlay_daily` lazy-probes per workspace.

**Scheduled probe (separate process).** Overlay must never share
`pipeline-digiquant.yml`'s portfolio chain job (`usage.start` is process-global).
The fail-closed GHA spec is
`docs/agent-backlog/execution-tenancy/execution-cron-check.workflow.yml`
(`15 12 * * *`, `make digiquant-cron-check` / overlay `--dry-run` / sync
`--dry-run`). `cursor/*` cannot write `.github/workflows/`; the installed
job still runs `scripts/execution_cron_check.py` (wrapper) until a `chore/` or
`feat/` hop copies a renamed spec. Missing
`CORE_SUPABASE_*` / notify GitHub secrets fail closed (exit 2). That job
must never pass `--execute`, `--all`, or invoke `portfolio.chain`.

**Omitted `workspace_id` means the house.** Scannable developer guide:
[`docs/ops/HOUSE_BOOK_SCOPE.md`](../../../docs/ops/HOUSE_BOOK_SCOPE.md). Readers and
writers that leave the argument off (`load_prior_book`,
`load_portfolio_performance_snapshot`, `_prior_nav`, `_recent_navs` /
`breaker_scale_from_nav_history`, `opening_snapshot` Group A reads,
`_prune_orphan_positions`, `_rows_for_date`, `_pending_order_heads`,
`refresh_attribution.py` positions, and `finalize_period_accounting.py` Group A
nav/positions) filter **and** stamp `house_workspace_id()`. They never mean
"every row". House research ops readers (`repair_supabase_portfolio_data`,
`seed_ledger_opening_snapshot`, `backfill_position_events`,
`ensure_position_activity_through_today`, `backfill_positions_entry_from_events`,
`validate_db_first` Group A checks and house ``documents`` presence
(`_has_research_*` / `house_digest_on_date`), `backfill_export_state` positions
and documents export, `backfill_pm_rebalance_and_activity` thesis map,
`backfill_position_event_reasons` house event pages and document payload
lookups, `materialize_snapshot.house_digest_documents` (digest sync must not
copy overlay ``DIGEST.md`` into house ``daily_snapshots.digest_markdown``),
`fold_document_deltas` house delta/base payloads (overlay deltas must not
publish into the house book), `validate_pipeline_step.fetch_document_rows`,
`backfill_pm_rebalance_and_activity` document payload lookups,
`pipeline_review_to_github` / `pipeline_meta_review` house pipeline-review
docs (overlay reviews must not file GitHub issues),
`format_deliberation_transcripts_chat` house transcripts (overlay rows must
not be rewritten by id), `normalize_supabase_documents.fetch_all_documents`
(overlay rows must not be rewritten by id), `fetch_research_library` house
research notes, `verify_supabase_canonical` house leftover ``outputs/`` keys,
`publish_research.house_research_library_rows` (overlay notes must not dump as
the house library), `backfill_research_state` house inventory pages (overlay
rows must not seed the in-memory research-state store),
`audit_activity_coverage_api` Group A max-dates) pin via
`eq_house_workspace()`
(omitted id = house). House MCP `query_research` / `digiquant_query_research`
stamps house `workspace_id` on those same Group A tables when `eq` omits it
(`HOUSE_BOOK_READ_TABLES` in `research/data/queries.py`). House preflight
`load_prior_context` / analyst and deliberation continuity / beliefs /
institutional-absence documents also pin house so overlay private docs cannot
seed the house graph. The dashboard Group A readers (`apps/dashboard/lib/queries.ts`, `observability-queries.ts`)
go through `houseBook()` (`lib/house-workspace.ts`) so a signed-in Custom
member's overlay rows cannot mix into Brief / Holdings / Performance. Accounting NAV still uses
`public_accounting_nav_history` (security definer; house-only until a later
view rewrite).

**Test-fake vs PostgREST `eq` (workspace_id).** The in-memory `_FakeQuery` in
`tests/dq/research/test_supabase_io.py` treats a missing `workspace_id` column as
matching `house_workspace_id()` when filtering — a **TEST-FAKE courtesy** for
legacy house fixtures only. Production PostgREST does not: `.eq("workspace_id",
house)` matches only rows where the column equals `house`. Migration 097's
backfill stamps `workspace_id` on live tables; pre-097 rows without the column
are invisible to scoped readers, which is correct post-backfill (PostgREST `eq`
semantics, not the fake's).

**Runner (`runner.py`).** ProfileConfig pin (`requested_version_id` + `workspace_id`
at the preflight seam — the pin loader is unchanged) → publish-if-missing into the
shared corpus under `theme:` / `asset:` / `segment:` keys → private direction–commit book.
A write-time assertion rejects any corpus key containing the workspace or user id.
House callers that omit `workspace_id` keep the T0 house stamp (byte-identical).
Overlay commit manifests use `overlay-commit/{workspace_id}/…` **only** when
`is_private_workspace(workspace_id)` is true. House UUID and omitted
`workspace_id` keep `commit-run/{run_id}` — a truthy house id must not flip the
prefix (same rule as `portfolio_document_key`). `load_commit_manifests` pins
`documents.workspace_id` on the PostgREST path so an overlay same-date row
cannot satisfy a house `commit-run/%` like. direction/sizing document keys use
`overlay/{workspace_id}/pm-direction-memo` (and the same prefix for
`pm-rebalance`, `analyst/…`, `deliberation/…`) so they cannot collide with house
keys after the documents unique is `(workspace_id, date, document_key)`.

**Documents tenancy (migration 105).** `documents.workspace_id` is NOT NULL
(backfilled house). The legacy `UNIQUE(date, document_key)` is **replaced** by
`UNIQUE(workspace_id, date, document_key)` — keeping both would still collide
overlay+house same-key rows. Authenticated own-workspace SELECT is added for
non-house/non-system rows; **migration 110** narrows ``anon_read`` on
workspace-scoped private books to house (documents: house+system) so overlay
rows cannot leak to anon. Cutover 900 still DROPs those policies.

**Persist flag.** Overlay private-phase **document** writes require
`DIGIQUANT_OVERLAY_PERSIST=1` (default off). Production may enable that flag
**after migration 110** is applied on the target (anon house-only on private
books) so overlay `documents` rows do not leak through `anon_read`. Overlay
**positions / nav_history / portfolio_metrics / ledger** writes remain refused
(`legacy_book_unique`) while migration 097's legacy `UNIQUE(date)` /
`UNIQUE(date, ticker)` / `PRIMARY KEY (date)` and ledger
`uq_portfolio_ledger_commits_one_root (run_date)` still sit beside the widened
keys — commit `commit_io`, `portfolio_materialize`, and `refresh_performance_metrics`
now upsert the widened `(workspace_id, …)` targets, as do the remaining house
ops scripts (`update_tearsheet` Group A plus documents
`on_conflict=workspace_id,date,document_key`, `sync_positions_from_rebalance`,
`materialize_snapshot` positions, `backfill_execution_prices`,
`reconcile_position_events_from_positions`). Overlay private books still refuse
(`legacy_book_unique`) until staged cutover **113**
(`digiquant/supabase/migrations/cutover/113_drop_legacy_book_uniques.sql`) is
**applied** on `core`. That file DROPs the 097 leftover keys and widens 069
one-root indexes to `(workspace_id, run_date[, symbol])`. It is **not**
auto-applied (`db-migrate.yml` `-maxdepth 1`). Do not copy it to top-level
until `main`'s house GHA writers are on the widened conflict (documents
hotfix #3278; `origin/main` `commit_io` / `portfolio_materialize` still
`on_conflict=date` / `date,ticker`). Staging 113 does **not** lift
`require_overlay_legacy_book_safe`. `daily_snapshots` stays `UNIQUE(date)`
(house-only). Until 113 is applied, overlay persist-on cannot prove the
remaining hop: `execute_overlay` refuses succeeded after the chain for a
private workspace (documents-only / fail-soft commit used to finish succeeded).
Settings About and the staging harness name `overlay_legacy_book_unique`
when `job_runs.error` is `legacy_book_unique` (persist-disabled still wins).
`_safe_invoke_graph` re-raises `OverlayLegacyBookBlocked` instead of
swallowing it. Overlay publish
**skips** `daily_snapshots` (house-only `UNIQUE(date)` — an overlay upsert would
overwrite the house Brief). Overlay thesis–analyst / Phase 9D **skip** `theses`,
`analyst_coverage`, and `thesis_vehicles` for a private workspace
(`skip_overlay_shared_register`): those tables have no `workspace_id` column
and leftover `UNIQUE(date, …)` keys, so persist-on would last-writer-win the
house corpus. Overlay `preflight_reflect` / `persist_pending` likewise **skip**
`decision_log` (`UNIQUE(run_date, ticker)` — resolving would stamp house
reflections by id). Overlay research preflight **skips** the
`onchain_cohort_positioning` upsert (`UNIQUE(date, market)`) the same way; the
compact summary still lands in in-memory `market_context` for that overlay run.
Overlay `run_research_then_portfolio` **skips** `_run_beliefs_fold` for a private
workspace — distillation reads every unfolded house `decision_log` row and
stamps `beliefs_folded_at` by id, and the chain still reaches that fold after
a fail-soft commit `legacy_book_unique`. Overlay identity is seeded onto
`initial_state` from the preflight `config_loader` before graph invoke, so an
research crash that returns last-good state cannot fold as house
(`workspace_id=None`). Staged cutover 113 does not change that.
Private overlay remains
direction–commit book only (T4). Cutover 900 is still required before dropping
the house teaser for anon / free JWTs; it is not the persist precondition.
With the flag off, research/corpus phases still run; private-phase
persistence refuses and the job row is `persist_disabled`.

**Budget (`budget.py`).** At overlay start the runner calls
`digigraph.usage.start(run_id=<job id>)`, which clears process-global `_CALLS`,
then reads `snapshot()["cost_usd"]`. `usage.start` / `usage.reset` are
**process-global** — overlay jobs must run in a **separate process** from the
house run, else house WP1 capture is clobbered; a run-scoped ledger is the
future fix if co-residence is ever needed. Budget is checked after each corpus
pin **and after the chain**. Crossing `ProfileConfig.research_budget_usd` skips
remaining research, commits what is already consistent, and marks the job
`budget_exhausted`. Post-chain overrun: the chain has already returned, so
whatever it persisted stays; the job is `budget_exhausted` rather than
`succeeded`.

**BYOK (`byok.py`).** Sealed rows in `workspace_provider_credentials` (migration 104)
reuse the K3 AES-256-GCM envelope. AAD is `workspace_id:provider:llm`. Overlay LLM
clients are constructed only inside `digillm.client.byok` — house `OPENAI_API_KEY` /
LiteLLM proxy keys are never a fallback. `_invoke_chain` / `invoke_overlay_chain`
with `credential is None` refuses (`no_credentials`) and never calls `chain()`.
A prefixed model not covered by the unsealed provider (`anthropic/…` with an
openai BYOK row) refuses `byok_provider_mismatch` rather than falling through
to house env keys. Missing or unsealable user key ⇒ skip.

**BYOK seal CLI (`byok_seal.py`, `scripts/digiquant_seal_byok.py`).** Resume path when
a real user LLM key lands and Settings Keys is not yet on production Pages.
Default `--check` requires gitignored `.local/secrets/digithings-byok.env`
(`BYOK_PROVIDER` + `BYOK_API_KEY`, names only in logs). `--apply` seals with
the K3 vault (AAD `workspace_id:provider:llm`), verifies unseal, and inserts
one active `workspace_provider_credentials` row (unique-conflict = revoke then
insert, same as the settings Edge Function). House/system and non-entitled
workspaces (Observer free without `plan_floor`) are refused. Do not seal a
placeholder or a house process-env key. Overlay `--execute` still requires
`present_and_unsealable` plus `DIGIQUANT_OVERLAY_PERSIST=1` after migration 110
(documents only; book/ledger stay `legacy_book_unique` until staged cutover 113
is applied on the target).

**Venue.** K4 `policy.py` (review-fix `9b4e9c86`) hard-codes `PAPER_INTERNAL`
for `None` / house / system UUIDs. Overlay tenant routing threads
`workspace_id` into `_pending_order_heads` after those gates.

**Authority note (ledger / paper fills).** Overlay's runner path writes the
shared corpus (tenant-agnostic keys), the pin-seam `workspace_id` on
`ResearchConfigBundle`, commit manifests (`overlay-commit/{workspace_id}/…`),
the private book / NAV (`commit_io`), and the ledger chain (`ledger_io` models
receive `workspace_id=` when overlay; house constructors stay on
`house_workspace_id()`). It does **not** call `execution_io.execute_pending_orders`
or `execution.router.route_pending_orders`. Those stay on their existing authorities:
house paper fills are the `execute_at_open` job (date-scoped, house stamp on
writes; Group A reads filter `workspace_id` so an overlay same-date row cannot
shape HOLD/EXIT). The house GHA chain (`portfolio.chain`) Group A reads
(`commit_io._prior_nav`, `portfolio_materialize._prior_nav`,
`load_portfolio_performance_snapshot`, `breaker_scale_from_nav_history`,
`opening_snapshot` positions/NAV) likewise filter `workspace_id` so overlay
NAV/positions cannot compound the house index, trip the breaker, or seed lots.
External venue submit is K4's router (`9b4e9c86` gates first: None/house/system →
`PAPER_INTERNAL`, live-env raise before submit; then overlay `workspace_id` is
threaded into `_pending_order_heads` / `_directions_by_order`; missing ledger
`workspace_id` → `ForeignWorkspaceIntentError`). Omitted `workspace_id` on those
helpers is house (same as `_rows_for_date`). `documents.workspace_id` landed in
migration 105; overlay isolation is the column plus the
`overlay/{workspace_id}/…` key prefix.

Tests: `tests/dq/dashboard/overlay/`.

