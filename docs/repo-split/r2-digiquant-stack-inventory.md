# R2 digiquant-stack: file inventory and move list

Measured against `github/develop` = `d227b6ed526202aaa095b8e645804ef308dde813`
(2026-10-14T20:25:21+02:00, "feat(digiquant): make the desk settings page persist and apply (#5583)").
Tree census: `git ls-tree -r` = 6615 paths, 6615 unique.

Plan under review: PR #5695 `docs(root): repo split review and phased migration plan`
(branch `DIG-3518-repo-split-plan`) plus `~/Code/occ-backups/repo-split-docs/repo-split.md`.
Parent epic: DIG-3518, owner Software Architect (`c3bf0d65`), currently `blocked`.

**Scope of this document.** Inventory only. No repository was created, no history moved, no
Cloudflare configuration touched, nothing merged. Every number below is a measurement, not an
estimate from the plan. Where the plan and the tree disagree, both figures are given.

**Revision 2** (2026-10-15). Rewritten after Chris's approval comment `72461e61` of 2026-10-14
01:26. Six send-back items applied: core pipeline into R2 (section 1.8), no `.github` file moves
(section 2), the 489/432 reconciliation (section 1.11), `apps/dashboard-api` tied to DIG-3693
(section 5.4), runtime-generated secret fixtures under DIG-3698 (section 5.5), and the R1 registry
choice under DIG-3688 (section 6). Section 1.10 replaces the `overlaps-known.txt` whitelist with
one owner per file. This revision also corrects three errors of revision 1: a stated total of 432
that its own table did not sum to (section 1.11), a claim that the R2 workflows carry a
`schedule:` trigger (section 2), and an instruction to delete a `ci.yml` reference that must now
stay (section 7).

## 1. Exact R2 file inventory

Totals: **480 files** across the twelve blocks below. Revision 1 stated 432; that number was wrong.
Section 1.11 gives the arithmetic.

| # | block | measured | plan said | added by |
|---|---|---|---|---|
| 1 | `apps/digiquant-runner/` | 21 | 21 | - |
| 2 | `apps/dashboard-api/` | **127** | 117 | - |
| 3 | `digiquant/supabase/` | 184 | 184 | - |
| 4 | `digiquant/scripts/` | 78 | 78 | - |
| 5 | `digiquant/src/digiquant/research/config/` | **18** | 19 | - |
| 6 | `digiquant/config/` + `digiquant/docs/` | 1 + 11 | not counted | - |
| 7 | `digiquant/src/digiquant/execution/` | **15** | not listed | item 1 |
| 8 | `digiquant/src/digiquant/data/gloomberb/` | **10** | not listed | item 1 |
| 9 | `digiquant/src/digiquant/data/luxalgo/` | **7** | not listed | item 1 |
| 10 | `digiquant/src/digiquant/brokers/luxalgo*` (4 files) | **4** | not listed | item 1 |
| 11 | `cli/gloomberb.py`, `data/prices/gloomberb_macro.py`, `research/docs/RUNBOOK.md` | **3** | not listed | item 1 |
| 12 | `config/contract/secrets.yaml` | **1** | not listed | item 1 |

Sum: 21 + 127 + 184 + 78 + 18 + 12 = 440, plus 15 + 10 + 7 + 4 + 3 + 1 = 40, total **480**.
Blocks 1 to 6 are counted whole. Block 4 is split per file (section 1.10).

Regenerate any block exactly:

    git ls-tree -r <sha> --format='%(objectname) %(path)' -- <block>

### 1.1 `apps/digiquant-runner/` — 21 files, complete

    commands.json
    container/exec_job.py            container/exec_job_test.py
    container/house_chain_step.py     container/house_chain_step_test.py
    container/wake_stack.py           container/wake_stack_test.py
    container/web_search_preflight.py container/web_search_preflight_test.py
    package.json
    src/commands.test.ts   src/commands.ts   src/env.ts      src/index.ts
    src/runner-session.ts  src/runner.test.ts src/runner.ts
    test/cloudflare-workers-stub.ts
    tsconfig.json  vitest.config.ts  wrangler.toml

### 1.2 `apps/dashboard-api/` — 127 files

`src/` 102, `d1-local/` 13, `migrations-draft/` 3, plus 9 top-level files.
`src/` sub-buckets: `billing/` 16, `prices-live/` 12, `routes/` 12, `fx-hub/` 10,
and 52 root-level `src/` files.

Top level: `.dev.vars.example`, `.gitignore`, `CONTRACT.md`, `README.md`, `package.json`,
`tsconfig.json`, `vitest.config.ts`, `wrangler.local.toml`, `wrangler.toml`.

**The plan's 117 is stale by 10.** The +10 are `d1-local/` (13) and `migrations-draft/` (3)
in part, plus root files added since. An executor must count from the tree, not from the plan.

### 1.3 `digiquant/supabase/` — 184 files

* `migrations/` — 140 files.
  * 138 numbered migrations, `001_…` through `143_…`.
  * Number gaps at **37, 38, 59, 62** and **113**.
  * 113 is not missing. It is `migrations/cutover/113_drop_legacy_book_uniques.sql`.
  * `migrations/cutover/` — 2 files: `113_drop_legacy_book_uniques.sql`,
    `900_drop_anon_read_cutover.sql`.
  * **`cutover/` is inside `migrations/`, not a sibling directory.** The plan's tree diagram puts
    it beside `migrations/`. A copy step written from the plan misses both files.
  * Both cutover files are human-gated and are not auto-applied.
* `functions/` — 39 files across 9 entries: `_shared/` 22, `settings/` 4, `prices-live/` 3,
  `stripe-webhook/` 3, `create-checkout-session/` 2, `customer-portal/` 2, `README.md` 1,
  `deno.json` 1, `deno.lock` 1.
* Top level — 5 files: `.gitignore`, `README.md`, `SCHEMA.md`, `config.toml`, `seed.sql`.

### 1.4 `digiquant/scripts/` — 78 files

`research/` 68, top level 10:
`_env.py`, `export_sdca_macro.py`, `fetch_coinbase.py`, `fetch_nautilus_test_data.py`,
`fetch_real_ohlcv.py`, `generate_tearsheets.py`, `plot_sdca_tearsheet.py`, `recover_ledger.py`,
`sync_strategy_calibrations.py`, `verify_strategy_calibrations_rls.py`.

The plan says "per-file triage", which is correct and still owed. `generate_tearsheets.py` is
named in plan 1a as R1-or-R2. The four SDCA scripts are named R1. `digiquant/scripts/research/`
(68 files) was not triaged by the plan at all and is the largest untriaged block in R2.

### 1.5 `digiquant/src/digiquant/research/config/` — 18 files, complete

    MCP-SETUP.md                          ai_portfolio_accounts.yaml
    asset_classes.yaml                    data-sources.md
    email-research.md                     hedge-funds.md
    investment-policy.md                  investment-profile.md
    local.env.example                     macro_series.yaml
    mcp.claude-desktop.fragment.json      mcp.secrets.env.example
    portfolio.json                        preferences.md
    schedule.json                         search_domains.yaml
    sectors.yaml                          watchlist.md

The plan's 19 is stale by one. Two of these 18 are examples, not live config:
`local.env.example` and `mcp.secrets.env.example`.

### 1.6 `digiquant/config/` and `digiquant/docs/`

* `digiquant/config/` — 1 file: `research_policy.yaml`.
* `digiquant/docs/` — 11 files: `DIGIQUANT_CHAT_PRODUCT_GAP.md`, `NAUTILUS_NAVIGATION.md`,
  `NAUTILUS_QUICK_REF.md`, `NAUTILUS_STRATEGIES.md`, `brokers/IBKR-NOTES.md`,
  `profiles/README.md`, and `schemas/` holding `asset_preferences.v1.json`,
  `execution_policy.v1.json`, `investment_profile.v1.json`, `pipeline_schedule.v1.json`,
  `research_snapshot.v1.json`.

### 1.7 Root-level config and scripts that belong to R2

The plan names `config/{digiquant_models.yaml, digiquant-model-prices.json}`. **Both items need
correcting** — see section 4.

* Present and digiquant-named: `config/digiquant_models.yaml`,
  `config/digiquant-model-prices.json`, `config/byok-providers.json`, `config/model-policy.json`.
* `config/` holds 39 files. The remaining 35 include `config/contract/` (18 files),
  `config/generated/compose-contract.env`, and `config/self-host/parity-baseline.json`.
  These are cross-repository gates, not R2 content. Ownership is an open decision, section 5.

Root `scripts/` holds 221 files. R2 operational entry points (the names the plan lists, verified):

    backfill_market_data_r2.py              refresh_market_data_r2.py
    execution_cron_check.py                 digiquant_archive_checkpoints.py
    digiquant_checkpoint_size_gate.py       digiquant_apply_vendor_secrets.py
    digiquant_cron_check.py                 digiquant_route_cron.py
    digiquant_seal_byok.py                  digiquant_staging_e2e.py
    production_deploy_gate_latency.py       digiquant_house_pipeline_proof.py
    digiquant_pages_dashboard_gate.py       validate_digiquant_pools.py
    seed_digiquant_demo.py                  setup_digiquant_project.sh
    build-digiquant.sh                      export_research_snapshot_schema.py
    record_market_data_goldens.py           bench_market_data.py
    supabase_exit/{__init__,d1_import,d1_verify,migrate,pg_dump_split}.py
    rls_proof/00_supabase_shim.sql

Not R2, other owners: `merge_queue.py` and `merge_queue_policy.json` (repository-wide),
`merge_litellm_cheaperinference.py` and `zammad_mcp/` (9 files, R5),
`verify_agent_automerge_pr.py`.

### 1.8 The core pipeline moves to R2 (send-back item 1)

Chris's approval makes `apps/dashboard` and the digiquant core pipeline private. R2 therefore
absorbs the core pipeline, not only its configuration. Measured blocks, added to the table above:

* **House pipeline** — `digiquant/src/digiquant/execution/`, **15 files**, the whole package:
  `__init__.py`, `cron_check.py`, `house_pipeline_proof.py`, `market_hours.py`,
  `pages_dashboard_gate.py`, `policy.py`, `remaining_hops.py`, `route_cron.py`, `router.py`,
  `staging_e2e.py`, `staging_secrets.py`, `sync.py`, `sync_cron.py`, `vendor_secret_apply.py`,
  `vendor_secret_files.py`.
* **Vendor secret staging** — `staging_secrets.py`, `vendor_secret_apply.py` and
  `vendor_secret_files.py` sit inside that package. The operator entry point
  `scripts/digiquant_apply_vendor_secrets.py` was already listed in section 1.7.
* **Vendor data clients** — 23 files: `data/gloomberb/` (10), `data/luxalgo/` (7),
  `brokers/luxalgo_coinbase_mirror.py`, `brokers/luxalgo_kraken_mirror.py`,
  `brokers/luxalgo_mirror.py`, `brokers/luxalgo_tradier_mirror.py`, `cli/gloomberb.py`,
  `data/prices/gloomberb_macro.py`.
* **Pipeline runbook** — `digiquant/src/digiquant/research/docs/RUNBOOK.md`, 1 file.
* **Secret contract** — `config/contract/secrets.yaml`, 1 file. See the "contract split" decision
  in section 6.

Measured, the effect on R2's build: `Dockerfile.digiquant-runner` lines 62-66 copy six
`scripts/` entry points whose digiquant twins live in `execution/` (`cron_check`, `route_cron`,
`sync`, `staging_e2e`, `house_pipeline_proof`, `pages_dashboard_gate`), so the image and the
package are one unit after the split. `config/contract/secrets.yaml` is the only file in
`config/contract/` that names digiquant secrets, which is why it moves while the other 17 stay.

### 1.9 Public engine boundary — what stays in R0 and references the core pipeline

160 tracked files outside `digiquant/` and outside `docs/` reference the core pipeline. Grouped by
the repository that keeps them:

| block | files | destination |
|---|---|---|
| `tests/` | 68 | R0 (parity and contract) |
| `apps/` | 58 | R3, R4, R5 by file |
| `scripts/` | 14 | R0 |
| `packages/` | 4 | R0 |
| `.github/` | 4 | stays in R0, section 2 |
| `digisearch/`, `digigraph/`, `digifetch/`, `clients/` | 7 | R0 |
| `config/`, `.env.example`, `.gitleaks.toml`, `.gitleaksignore`, `package-lock.json` | 5 | R0 configuration surfaces |

Measure it with:

    git grep -l -E 'digiquant\.execution|house_pipeline|gloomberb|luxalgo|vendor_secret' \
      <sha> -- ':!digiquant/' ':!docs/'

Control: the same search scoped to `digiquant/` returns 45 files, so the matcher fires.

**The coupling is two-way and it is unresolved.** R0 keeps code that calls the pipeline; R2 keeps
the pipeline. Every entry above needs a published interface, a released package pin, or a deletion
before the copy step, and no single direction is safe yet. This census counts **references, not
import edges** — prose, allowlists and configuration hits are in it — so an executor must
classify each file before moving anything.

### 1.10 Overlap ownership — exactly one owner per file

The plan carried a whitelist file, `overlaps-known.txt`, for paths belonging to more than one
repository. **The whitelist is removed.** Every path gets exactly one owner, measured at the
anchored tip:

| path | owner | note |
|---|---|---|
| `digiquant/scripts/export_sdca_macro.py` | R1 | SDCA strategy export |
| `digiquant/scripts/plot_sdca_tearsheet.py` | R1 | SDCA tearsheet plot |
| `digiquant/src/digiquant/optimize.py` | split | SDCA parts R1, generic shell R2 |
| `digiquant/scripts/generate_tearsheets.py` | R2 | after the SDCA imports move to the plugin hook |
| `scripts/verify_occ_invite_key.sh` | R6 | |
| `scripts/occ_invite_key_fixture_server.mjs` | R6 | |
| `scripts/occ_invite_key_rollout.sh` | R6 | write-secret and KV half, after refactor 1.9 |
| `scripts/check_occ_rollout_auth_guard.py` | R6 | |
| `scripts/index_occ_tickets.py` | R6 | |
| `scripts/test_occ_rollout_scope_guard.sh` | R6 | |
| `docs/ops/OCC_INVITE_KEY.md` | R6 | |
| `apps/digithings-stack-cloudflare/container/seed_chroma.sh` | R5 | |

**Two corrections to the send-back's paths.**

* It cites `digiquant/scripts/optimize.py`. **That path does not exist.** Measured: two files are
  named `optimize.py` — `digiquant/src/digiquant/optimize.py` (382 lines, 7 top-level
  definitions) and `digiquant/src/digiquant/strategies/sdca/optimize.py`. The split applies to
  `digiquant/src/digiquant/optimize.py`. Its SDCA parts are the imports at lines 16-21, the dispatch
  branch at lines 205-206, `_sdca_trials` at line 297 and `_run_sdca_optimize` from line 342.
* It cites three SDCA import sites in `generate_tearsheets.py`, lines 66, 161 and 162.
  **The file has 10.** Lines 628, 629, 630, 780, 781, 786 and 806 also import
  `digiquant.strategies.sdca`. An executor who patches three sites leaves seven live SDCA imports
  inside an R2-owned file:

      66   161  162  628  629  630  780  781  786  806

### 1.11 Reconciling 489 against the earlier 432

Chris's send-back asks to reconcile 489 files in `r2.paths` against the 432 this document
declared. Measured outcome:

* **The stated 432 was wrong by 8.** The six original blocks sum to **440** (21 + 127 + 184 + 78 +
  18 + 12). Corrected in section 1.
* **The untriaged research directory was already counted.** `digiquant/scripts/research/` holds
  **68 files**: 60 at the top level, 8 under `lib/` and `sql/`. Those 68 sit inside block 4
  (`digiquant/scripts/` = 78), so they were part of the 440. They were never triaged file by file,
  which is why block 4 is marked "split" and not "R2" in section 1.
* **489 does not reproduce from any artefact I can reach.** `r2.paths` is not a path in the
  repository, not one of the six files in PR #5695, and not a token in
  `~/Code/occ-backups/repo-split-docs/repo-split.md`. The three candidate sums are 423 (the plan's
  R2 rows), 440 (this document's six blocks) and 480 (the six blocks plus the 40 core pipeline
  files). 489 equals none of them.

**The authoritative figure is 480**, derived block by block in section 1. Regenerate it with
`git ls-tree -r <sha> -- <block>`; do not carry a total across a revision without re-deriving it.
The "489 list" decision in section 6 asks the plan's owner to publish that list if it is real.

## 2. No `.github` file moves — 13 paths leave the R2 move list

**No `.github/workflows` file moves into R2, or into any private repository.** Each one becomes a
Cloudflare cron job, a local-ci job on Chris's Mac, or a deletion. DIG-3605 owns the mapping.
This document therefore carries **0 `.github` paths** in the R2 move list, and the inventory
total of 480 is unchanged by this rule because the 13 paths were never part of it.

13 paths drop out:

    .github/digiquant-pipeline.yml
    .github/workflows/deploy-digiquant-cloudflare.yml
    .github/workflows/deploy-digiquant-runner.yml
    .github/workflows/pipeline-checkpoint-archive.yml
    .github/workflows/pipeline-digiquant-allocation-shadow.yml
    .github/workflows/pipeline-digiquant-onchain.yml
    .github/workflows/pipeline-digiquant-prices.yml
    .github/workflows/pipeline-digiquant-tearsheets.yml
    .github/workflows/pipeline-digiquant.yml
    .github/workflows/pipeline-market-data-refresh.yml
    .github/workflows/pipeline-research-metrics.yml
    .github/workflows/sync-digiquant-runner-digikey-secret.yml
    .github/workflows/sync-digiquant-runner-mail-secrets.yml

The two `sync-digiquant-runner-*-secret*.yml` files drop under the same rule. Their job — staging
vendor secrets into the runner — is what `execution/vendor_secret_apply.py` and
`vendor_secret_files.py` do inside the runner image, so the code moves and the workflow does not.

**Measured trigger per file.** The trigger decides which of the three targets DIG-3605 must pick.

| workflow | trigger | mapping DIG-3605 must supply |
|---|---|---|
| `pipeline-digiquant.yml` | `repository_dispatch` (`digiquant-baseline`) + `workflow_dispatch` | already a Cloudflare cron |
| `deploy-digiquant-runner.yml` | `push` (branches + paths) + `workflow_dispatch` | cron or local-ci |
| `pipeline-digiquant-allocation-shadow.yml` | `workflow_run` (types `branches`) + `workflow_dispatch` | cron or local-ci |
| `pipeline-digiquant-prices.yml` | `workflow_dispatch` | cron or local-ci |
| `pipeline-research-metrics.yml` | `workflow_dispatch` | cron or local-ci |
| `pipeline-market-data-refresh.yml` | `workflow_dispatch` | cron or local-ci |
| `pipeline-checkpoint-archive.yml` | `workflow_dispatch` | cron or local-ci |
| `pipeline-digiquant-onchain.yml` | `workflow_dispatch` | cron or local-ci |
| `pipeline-digiquant-tearsheets.yml` | `workflow_dispatch` | cron or local-ci |
| `sync-digiquant-runner-digikey-secret.yml` | `workflow_dispatch` | delete — code moves to the image |
| `sync-digiquant-runner-mail-secrets.yml` | `workflow_dispatch` | delete — code moves to the image |
| `test-digiquant.yml` | **`workflow_call`** | local-ci on Chris's Mac |
| `.github/digiquant-pipeline.yml` | n/a (tunable set) | job config, section 2.1 |

**Correction to revision 1.** It wrote that the R2 workflows carry a `schedule:` trigger, or
`workflow_dispatch`. Measured: **`schedule:` is 0 of 12.** `pipeline-digiquant.yml` carries a
header instruction instead — *"Do not add `schedule:` ... `repository_dispatch` type
`digiquant-baseline` is still the production house clock from digithings-cron until the container
flip. Schedule removed #3579."* So the digiquant research pipeline is **already** on a Cloudflare
Worker clock (`apps/digithings-cron`), and DIG-3605's mapping for most of these files is a naming
and ownership question, not new infrastructure.

`test-digiquant.yml` is a **reusable** workflow (`workflow_call` only), called by `ci.yml` line
411, with its path filter at `ci.yml` line 95. `ci.yml` has 21 `uses: ./.github/workflows/`
references; this is the only one that touches an R2 file.

### 2.1 The tunables file becomes job config, and breaks two `COPY` lines

`.github/digiquant-pipeline.yml` (2658 bytes, 0 secret references) is a non-secret tunable set
that `pipeline-digiquant.yml` loads into `$GITHUB_ENV`. It stays in R0 as local-ci or cron job
config, so **R2's `Dockerfile.digiquant-runner` can no longer copy it.** Measured: line 67 copies
`.github/digiquant-pipeline.yml`, line 68 copies
`.github/workflows/pipeline-digiquant-allocation-shadow.yml`. Both `COPY` instructions must be
re-pointed at a committed copy inside R2, or the tunables must be passed as environment variables
by the cron job. These are the only two `.github` couplings inside an R2 image.

`config/digiquant_models.yaml` is still referenced as a policy source **from**
`.github/digiquant-pipeline.yml`. That reference stays valid because the file stays in R0, so the
file remains a CI-side input and not an image input — correction 5 in section 4 still holds.

## 3. Secret names — 19 names

Names only. No value was read, printed, or stored for this document. Measured by scanning each of
the 12 workflow blobs for `secrets.<NAME>`. **`GITHUB_TOKEN` is removed** (send-back item 2): it is
read only by `pipeline-digiquant.yml`, and that workflow does not move (section 2), so its scope
stays R0's.

Because no workflow moves, the list changes meaning. It is no longer "secrets the moved workflows
read"; it is **the secret names the R2 code paths read**, sourced from the 12 workflow blobs that
become local-ci or cron job config. The table names which replacement job needs which names.

| workflow | secret names |
|---|---|
| pipeline-digiquant | CHEAPERINFERENCE_API_BASE, CHEAPERINFERENCE_API_KEY, CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, DIGIQUANT_DIGIKEY_API_KEY, LANGSMITH_API_KEY, OPENROUTER_API_KEY, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| deploy-digiquant-runner | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN |
| sync-digiquant-runner-digikey-secret | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, DIGIQUANT_DIGIKEY_API_KEY, LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY |
| sync-digiquant-runner-mail-secrets | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_EMAIL_API_TOKEN, NOTIFY_FROM |
| pipeline-checkpoint-archive | CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-market-data-refresh | CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-digiquant-prices | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-research-metrics | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-digiquant-onchain | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL |
| pipeline-digiquant-tearsheets | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL |
| pipeline-digiquant-allocation-shadow | none |
| test-digiquant | none |

Distinct, sorted, 20 before the cut:

    CHEAPERINFERENCE_API_BASE   CHEAPERINFERENCE_API_KEY     CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN        CLOUDFLARE_EMAIL_API_TOKEN   CORE_POSTGRES_URI
    CORE_SUPABASE_SERVICE_KEY   CORE_SUPABASE_URL            DIGIQUANT_DIGIKEY_API_KEY
    GITHUB_TOKEN                LANGFUSE_BASE_URL            LANGFUSE_PUBLIC_KEY
    LANGFUSE_SECRET_KEY         LANGSMITH_API_KEY            NOTIFY_FROM
    OPENROUTER_API_KEY          R2_ACCESS_KEY_ID             R2_ACCOUNT_ID
    R2_BUCKET                   R2_SECRET_ACCESS_KEY

Remove `GITHUB_TOKEN` and **19** remain. That matches send-back item 2 exactly, and the
per-workflow derivation is the receipt.

The plan lists 16, and that count stays unreconciled: revision 1 resolved the gap by adding
`GITHUB_TOKEN`, and send-back item 2 resolves it by removing that name instead. Either the plan's
16 is wrong by three, or three of these names are not needed by the R2 code paths. This cannot be
settled from the workflow blobs alone — the "plan secret count" decision in section 6.

## 4. Corrections to the plan (measured, not inferred)

1. **`sync-digiquant-runner-mail-secret.yml` does not exist.** The file is
   **`sync-digiquant-runner-mail-secrets.yml`**, plural. An executor who copies the plan's name
   gets a dangling reference. The plan's count of 12 is right; one name is wrong.
2. **`apps/dashboard-api/` is 127 files, not 117.**
3. **`digiquant/src/digiquant/research/config/` is 18 files, not 19.**
4. **`GITHUB_TOKEN` is missing from the secret list** (section 3).
5. **The R2 `config/` contents are wrong for the runner.**
   `Dockerfile.digiquant-runner` copies, measured:
   line 46 `config/byok-providers.json`, line 50 `config/model-policy.json`,
   line 57 `config/digiquant-model-prices.json`.
   So the runner needs `byok-providers.json` and `model-policy.json`, and it does **not** copy
   `digiquant_models.yaml`. The plan lists `digiquant_models.yaml` and omits the other two.
   Note `config/digiquant_models.yaml` is still referenced as a policy source from
   `.github/digiquant-pipeline.yml`, so the file matters — but as a **CI-side** input, not an
   image input.
6. **`digiquant/scripts/research/validate-providers.py:239` is not a runtime config load.** The
   plan cites it as loading `research/config/supabase.env`. Measured, line 239 sits in a
   docstring/epilog example: `Tip: load your local env before running: export $(grep -v '^#'
   digiquant/src/digiquant/research/config/supabase.env | xargs)`. It is documentation for a
   developer. Classify it as a doc, not a code dependency.
7. **Two coupling files under `apps/dashboard/` reference `dashboard-api/src/`** and the plan does
   not list them: `apps/dashboard/components/desk/panes/brief/load.test.ts` and
   `apps/dashboard/lib/api-client.test.ts`. They are R3/R4-side couplings that break when
   `apps/dashboard-api/` leaves. (Full control list of files referencing `dashboard-api/src/`:
   `apps/digithings-stack-cloudflare/src/dashboard-api.ts`,
   `apps/digithings-stack-cloudflare/src/dashboard-api-mount.test.js`, the two `apps/dashboard/`
   files above, and `apps/dashboard-api/src/billing/README.md`.)

8. **This document's own stated total of 432 was wrong; its table summed to 440.** Corrected in
   section 1 and explained in section 1.11. A published total that does not reproduce against the
   quantities beside it is not a measurement.
9. **The claim that the R2 workflows carry a `schedule:` trigger is false.** Measured `schedule:` is
   0 of 12. `pipeline-digiquant.yml` carries a header instruction forbidding it, and names
   `digithings-cron` as the production clock (section 2).
10. **`test-digiquant.yml` is `workflow_call`, not `pull_request` or `push`.** Revision 1's
    section 7 told an executor to delete `ci.yml`'s `uses:` line and the `ci_paths.yaml` entry.
    Under send-back item 2 both files stay in R0, so that instruction is withdrawn (section 7).
11. **Two revision-1 secret rows were not measured and are replaced.** `pipeline-digiquant-prices`
    and `pipeline-research-metrics` were carried forward with incomplete name lists. Measured, the
    first reads six names including the four `R2_*`; the second reads six names without
    `CORE_POSTGRES_URI`. Section 3 carries the measured values.

## 5. Prerequisite refactors

### 5.1 Plan 1b — production config loaded by path

| config file | load site, measured | existing override |
|---|---|---|
| `digiquant/config/research_policy.yaml` | `digiquant/src/digiquant/dashboard/research_retrieval/planner.py:610` — `Path(__file__).resolve().parents[4] / "config" / "research_policy.yaml"` | **Yes.** `resolve_research_policy_path()` reads `env_lookup(RESEARCH_POLICY_PATH)` first. |
| `.../research/config/asset_classes.yaml` | `digiquant/src/digiquant/portfolio/sector_map.py:61-62` `_asset_classes_path()` → `parents[1]/"research"/"config"/"asset_classes.yaml"` | No |
| `.../research/config/sectors.yaml` | `digiquant/src/digiquant/research/sectors_config.py:42-43` `_config_path()` → `Path(__file__).resolve().parent / "config" / "sectors.yaml"` | No |

The plan's `:610` citation is **exact**. One correction: `RESEARCH_POLICY_PATH` already exists, so
a new `DIGIQUANT_CONFIG_DIR` is only needed for the **other two** paths. `DIGIQUANT_CONFIG_DIR` has
**0 occurrences** on develop (control: the `RESEARCH_POLICY_PATH` references do fire). `sector_map.py`
line 43 is `from digiquant.research.sectors_config import load_sectors`, so these two paths share
one loader family.

Plan note confirmed: `digiquant.dashboard` is imported by 65 core modules and
`digiquant.profiles` by 3, so both packages stay in R0.

### 5.2 Plan 1c — the stack Worker bundles the desk API source

Measured, all confirmed:

* `apps/digithings-stack-cloudflare/src/dashboard-api.ts` line 30
  `import dashboardApi, { type Env as DashboardApiEnv } from "../../dashboard-api/src/index";`
* same file, line 31
  `import { STANDALONE_MCP_TOOLS } from "../../dashboard-api/src/mcp";`
  The plan's `:30` and `:31` are **exact**.
* `apps/digithings-stack-cloudflare/src/dashboard-api-mount.test.js` asserts both imports at
  **lines 209-210**. The plan says 210-211: **off by one**. The same test also asserts the
  absence of `mountEnvelopeRoutes`, `registerBriefRoutes`, `tryHandleLedger`, `tryHandleTables`.
* `apps/dashboard-api/src/validation.test.ts` lines 50, 51, 52, 61, 67, 68, 74 import 7 modules
  from `../../dashboard/lib/`: `accounting-views`, `book-reconciliation`, `brief-book-event`,
  `performance-ssot`, `position-event-economics`, `types`, `benchmark-tickers`.
  The plan's `:50-74` range is **exact**.

So `apps/dashboard-api/` has consumers in three repos (R2 itself, R5, R3/R4), not one. The
`dashboard-api-mount.test.js` pin makes the R2/R5 edge machine-checked: after the move, running
that test in R5 must still pass, and it fails loudly if the import path breaks.

### 5.3 Plan 1f — Dockerfile cross-tree `COPY`

`Dockerfile.digiquant-runner` has 23 `COPY` instructions.

* Lines 39-45: `COPY digibase|digikey|digifetch|digiquant|digigraph|digillm|digitrace ./` —
  7 sibling package sources. These are the PyPI pins, so R2 must consume them as packages,
  not as sibling directories, after the split.
* Lines 46, 50, 57: `config/` — see correction 5 above.
* Lines 62-66: exactly 5 scripts — `refresh_market_data_r2.py`, `backfill_market_data_r2.py`,
  `execution_cron_check.py`, `digiquant_archive_checkpoints.py`,
  `digiquant_checkpoint_size_gate.py`. The plan's "checkpoint_size_gate" is really
  `digiquant_checkpoint_size_gate.py`.
* Line 67: `.github/digiquant-pipeline.yml`. Line 68:
  `.github/workflows/pipeline-digiquant-allocation-shadow.yml`. Lines 70-74: runner container
  files plus `commands.json`.

`Dockerfile.digichat-cloudflare` (R5):

* Line 16 `COPY apps/dashboard/package.json apps/dashboard/` — the plan's citation is **exact**.
* **Line 33 `COPY config/byok-providers.json`.** So `byok-providers.json` is needed by **both**
  the R2 runner and R5 digichat. The plan assigns it to neither explicitly. See section 6.

`Dockerfile.digithings-stack-cloudflare` (R5): lines 128, 130, 131, 134 are
`infra/digichat-release/config`, `config/litellm.cheaperinference.yaml`,
`scripts/merge_litellm_cheaperinference.py`, `scripts/zammad_mcp` — the plan's 128-134 is **exact**.
Lines 53-117 also copy 9 sibling package sources including `digisearch/seeds`, and line 149
copies `config/searxng/settings.yml`.

### 5.4 `apps/dashboard-api` consumers depend on DIG-3693, not on a sibling path (send-back item 4)

Send-back item 4 is applied: R3 and R5 consumers of `apps/dashboard-api` are gated on refactor 1.4,
tracked as **DIG-3693**. They are not a path a sibling leaf can absorb.

46 files outside `apps/dashboard-api/` reference it. Grouped by destination:

| block | files | destination | gate |
|---|---|---|---|
| `apps/dashboard/` | 10 | R3 | DIG-3693 |
| `apps/digithings-web/` | 6 | R4 | DIG-3693 |
| `apps/digithings-stack-cloudflare/` | 9 | R5 | DIG-3693 |
| `apps/digiquant-web/` | 5 | R3 | DIG-3693 |
| `packages/` | 4 | R0 | DIG-3693 |
| `scripts/` | 12 | R0 | DIG-3693 |

Measure with `git grep -l -E 'dashboard-api' <sha> -- apps/ packages/ scripts/`, then exclude
`apps/dashboard-api/`. Control: the same search scoped to `apps/dashboard-api/` returns 7 files.

The R2/R5 edge is already machine-checked: `apps/digithings-stack-cloudflare/src/dashboard-api-mount.test.js`
lines 209-210 pin both imports, so the move fails loudly if the path breaks. That test is the
cheapest available proof that DIG-3693 landed.

### 5.5 Two secret-shaped fixtures become runtime-generated (send-back item 5)

Item 5 is applied, tracked as **DIG-3698**. Two files hold key-shaped constants that must be
generated at run time rather than committed:

| path | status |
|---|---|
| `digiquant/src/digiquant/research/config/mcp.secrets.env.example` | exists, 1 file |
| `digiquant/supabase/functions/settings/settings.test.ts` | exists, 1 file |

A third candidate is **not** in scope: `apps/digiquant-web/components/desk/app-settings.test.ts`
also ends in `settings.test.ts` but carries no key-shaped constant, and it belongs to R3.

Both files move to R2 — the first inside block 5, the second inside block 3 — so DIG-3698 must land
before either copy step.

## 6. Open ownership decisions

These are decisions, not measurements. Each one blocks a clean copy step.

1. **`config/byok-providers.json` has two consumers, no owner.** `Dockerfile.digiquant-runner:46`
   (R2) and `Dockerfile.digichat-cloudflare:33` (R5) both copy it. Options: R2 owns it and R5
   consumes it as a released package; R5 owns it and R2 consumes it; or it stays in R0 and both
   read it from there. Needs a ruling before any copy script is written.
2. **`config/contract/` (18 files), `config/generated/compose-contract.env`,
   `config/self-host/parity-baseline.json` are cross-repo gates.** They pin every `[vars]` key
   per worker and are checked by a required CI job. They are not in the plan's R2 contents. If
   R2 becomes its own repository, either the gate stays in R0 and reads R2's committed config, or
   the gate is split and each repo keeps a slice. Unowned today.
3. **`deploy-digiquant-cloudflare.yml` is not in the plan's R2 list.** Measured, it deploys
   `apps/digiquant-web/**`, `clients/digiquant-tui`, and calls `scripts/build-digiquant.sh`
   (which section 1.7 puts in R2). So an R2 script is invoked by a non-R2 workflow. The plan
   should say explicitly whether this workflow stays in R0/R5 or moves.
4. **`digiquant/scripts/research/` — 68 files, untriaged by the plan.** The plan triages the
   block's 10 top-level files and says nothing about the 68. This is the largest remaining
   unknown inside R2's own tree.
5. **`apps/dashboard/**` cross-tree test imports** (correction 7). R3/R4 tests import
   `apps/dashboard-api/`. Moving `apps/dashboard-api/` breaks them; a fix is a decision for
   whoever owns those two files.

**Decisions added by revision 2.** Each one blocks a copy step and has no current owner.

* **The contract split.** `config/contract/secrets.yaml` now moves to R2 (section 1.8) while the
  other 17 files in `config/contract/` stay in R0. The gate job that reads all 18 must therefore
  run in R0 and read R2's committed copy. It is the only one of the 18 that names digiquant
  secrets. Confirm with the plan's owner that splitting the contract this way is acceptable.
* **The registry for R1** (send-back item 6). R1 is consumed from a registry, and the registry is
  **DIG-3688's** choice. Not GitHub Packages. `digiquant-strategies` must be published to whichever
  registry DIG-3688 selects, with signed release tags, before any R0 or R2 code can pin it. Until
  DIG-3688 answers, the pin syntax in every affected `Dockerfile` and `pyproject.toml` is
  unwritable.
* **The plan secret count** (section 3). The plan says 16; the measured derivation is 19 after the
  instructed removal. Either the plan is wrong by three, or three names are not needed by the R2
  code paths. Not settleable from the workflow blobs alone.
* **The 489 list.** If a sibling leaf produced a real 489-file `r2.paths` list, its owner must
  publish it. Until then 480 is the derived figure (section 1.11).

## 7. What an executor changes in R0 when R2 is created

Minimum, measured. **Revision 1's first three items are withdrawn**: no `.github` file moves, so
`ci.yml` keeps its `uses: ./.github/workflows/test-digiquant.yml` reference at line 411 and
`scripts/ci_paths.yaml` keeps its entry at line 95. Caller and callee stay together in R0
(section 2).

1. `Dockerfile.digiquant-runner` lines 39-45: re-point the 7 `COPY` instructions from sibling
   package directories to the released package pins.
2. `Dockerfile.digiquant-runner` lines 67-68: re-point or remove the two `.github` `COPY`
   instructions (section 2.1). They cannot work once the workflows stay in R0.
3. Re-point the R5 `Dockerfile.digichat-cloudflare:33` reference to `config/byok-providers.json`,
   subject to decision 1 in section 6.
4. Land DIG-3693 (section 5.4) before moving `apps/dashboard-api/`, or R3, R4 and R5 all break in
   the same commit.
5. Land DIG-3698 (section 5.5) before moving either key-shaped fixture.
6. Land DIG-3688 before publishing R1, or there is nothing to pin.
7. Nothing else in `ci.yml`. The other 20 `uses:` targets stay.

## 8. Explicitly not done

Under the board driver's limits, this run did **not**: create any repository on Cursor Origin or
GitHub; move or rewrite any git history; change any Cloudflare configuration; merge into `main`
or `develop`; restart Paperclip; or read, print, or store any secret value. Items 6.1 through 6.5
need a ruling before a copy step can be written, and 6.1 in particular needs Chris because it
crosses two repositories.

Revision 2 adds: DIG-3605 owns the 13 `.github` mappings, DIG-3693 owns the `dashboard-api`
consumers, DIG-3698 owns the two key-shaped fixtures, and DIG-3688 owns the registry R1 publishes
into. This run created no repository, moved no history, changed no Cloudflare configuration, merged
nothing, and read no secret value. It also created **no new file**: PR #5716 carries one document,
now at revision 2.
