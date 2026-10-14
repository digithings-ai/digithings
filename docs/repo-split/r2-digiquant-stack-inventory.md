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

## 1. Exact R2 file inventory

Totals: **432 files** across the six blocks below.

| # | block | measured | plan said |
|---|---|---|---|
| 1 | `apps/digiquant-runner/` | 21 | 21 |
| 2 | `apps/dashboard-api/` | **127** | 117 |
| 3 | `digiquant/supabase/` | 184 | 184 |
| 4 | `digiquant/scripts/` | 78 | 78 |
| 5 | `digiquant/src/digiquant/research/config/` | **18** | 19 |
| 6 | `digiquant/config/` + `digiquant/docs/` | 1 + 11 | not counted |

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

## 2. R2 workflows — 12 files, plus one shared pipeline file

`.github/workflows/` holds 64 files. Exactly 12 belong to R2. All 12 exist at the tip.

    deploy-digiquant-runner.yml              pipeline-digiquant.yml
    pipeline-checkpoint-archive.yml          pipeline-market-data-refresh.yml
    pipeline-digiquant-allocation-shadow.yml pipeline-research-metrics.yml
    pipeline-digiquant-onchain.yml           sync-digiquant-runner-digikey-secret.yml
    pipeline-digiquant-prices.yml            sync-digiquant-runner-mail-secrets.yml
    pipeline-digiquant-tearsheets.yml        test-digiquant.yml

Plus `.github/digiquant-pipeline.yml` (2658 bytes, 0 secret references). It is a non-secret
tunable set loaded into `$GITHUB_ENV` by `pipeline-digiquant.yml` only (2 references; the other
11 workflows carry 0). `Dockerfile.digiquant-runner` line 67 copies it into the runner image.

Trigger shape, which decides repo membership:

* `paths:` filter present on **`deploy-digiquant-runner.yml`** only, and it has no `schedule`.
* The other 11 have `schedule:` or `workflow_dispatch`. Their trigger does **not** scope them to
  one repo, so membership is decided by **what they call**, not by their trigger.
* No R2 workflow calls another workflow with `uses: ./…`, so no intra-R2 `uses:` edge exists.

`ci.yml` break, measured: of the `uses:` targets in `ci.yml` that reference a workflow moving to
R2, there is exactly **one — `test-digiquant.yml`**. The other 21 `ci.yml` `uses:` targets stay in
R0. Two consequences: drop that one `uses:` line, and drop its `scripts/ci_paths.yaml` entry.

## 3. Secrets that move — 20 names

Names only. No value was read, printed, or stored for this document. Extracted from the 12 R2
workflows by scanning each blob for `secrets.<NAME>`.

| workflow | secret names |
|---|---|
| deploy-digiquant-runner | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN |
| pipeline-digiquant | CHEAPERINFERENCE_API_BASE, CHEAPERINFERENCE_API_KEY, CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, DIGIQUANT_DIGIKEY_API_KEY, **GITHUB_TOKEN**, LANGSMITH_API_KEY, OPENROUTER_API_KEY, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-checkpoint-archive | CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-market-data-refresh | CORE_POSTGRES_URI, CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-research-metrics | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-digiquant-prices | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL, R2_ACCESS_KEY_ID, R2_ACCOUNT_ID, R2_BUCKET, R2_SECRET_ACCESS_KEY |
| pipeline-digiquant-onchain | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL |
| pipeline-digiquant-tearsheets | CORE_SUPABASE_SERVICE_KEY, CORE_SUPABASE_URL |
| sync-digiquant-runner-digikey-secret | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, DIGIQUANT_DIGIKEY_API_KEY, LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY |
| sync-digiquant-runner-mail-secrets | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_EMAIL_API_TOKEN, NOTIFY_FROM |
| pipeline-digiquant-allocation-shadow | none |
| test-digiquant | none |

Distinct, sorted, 20:

    CHEAPERINFERENCE_API_BASE   CHEAPERINFERENCE_API_KEY     CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN        CLOUDFLARE_EMAIL_API_TOKEN   CORE_POSTGRES_URI
    CORE_SUPABASE_SERVICE_KEY   CORE_SUPABASE_URL            DIGIQUANT_DIGIKEY_API_KEY
    GITHUB_TOKEN                LANGFUSE_BASE_URL            LANGFUSE_PUBLIC_KEY
    LANGFUSE_SECRET_KEY         LANGSMITH_API_KEY            NOTIFY_FROM
    OPENROUTER_API_KEY          R2_ACCESS_KEY_ID             R2_ACCOUNT_ID
    R2_BUCKET                   R2_SECRET_ACCESS_KEY

The plan lists 16. **The plan omits `GITHUB_TOKEN`.** It is used by `pipeline-digiquant.yml`, so
whatever repository hosts that workflow needs it. `GITHUB_TOKEN` is auto-provided by GitHub
Actions to `contents: read` workflows, so "moves" here means the **required permission scope**,
not a stored value: if R2 is a separate repository, R2's `ci.yml` and pipeline workflows must keep
`contents: read` or narrower. That makes its scope R2 **and** R7 (plan 1g), which is why it cannot
be settled inside R2 alone.

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

## 7. What an executor changes in R0 when R2 is created

Minimum, measured:

1. `ci.yml`: remove the one `uses: ./.github/workflows/test-digiquant.yml` reference.
2. `scripts/ci_paths.yaml`: remove the `test-digiquant.yml` path-filter entry.
3. Nothing else in `ci.yml`. The other 21 `uses:` targets stay.
4. Re-point `Dockerfile.digiquant-runner` lines 39-45 from sibling directories to the released
   package pins.
5. Re-point the R5 `Dockerfile.digichat-cloudflare:33` reference, subject to decision 6.1.

## 8. Explicitly not done

Under the board driver's limits, this run did **not**: create any repository on Cursor Origin or
GitHub; move or rewrite any git history; change any Cloudflare configuration; merge into `main`
or `develop`; restart Paperclip; or read, print, or store any secret value. Items 6.1 through 6.5
need a ruling before a copy step can be written, and 6.1 in particular needs Chris because it
crosses two repositories.
