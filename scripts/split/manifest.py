"""Repo-split path manifest (DIG-3690, parent DIG-3518, goal G07).

Maps every tracked path to exactly one of R0-R7/delete.

Target repos (docs/repo-split, PR #5695):
  R0 digithings (public)            OSS modules, SDKs, UI packages, digichat engine, MCP tooling
  R1 digiquant-strategies (priv)    proprietary strategies + optimiser (plugin)
  R2 digiquant-stack (priv)         production backend (runner, desk API, schema, pipeline)
  R3 digiquant-web (priv)           Brief desk (apps/dashboard) + digiquant.io
  R4 digithings-web (priv)          digithings.ai, digibook, brand
  R5 digithings-stack (priv)        shared prod platform (stack, digichat Worker, langfuse, cron)
  R6 digichat-tenants (priv)        client corpora + rollout tooling (writes KV/R2)
  R7 twelve-x (exists, priv)        client desk + digidata-api
  delete                            paths that move nowhere (replaced tooling)

Chris's 01:26 calls (15 Oct, baked in below):
  - apps/dashboard and the digiquant core pipeline are PRIVATE (R2/R3).
  - .github/workflows/* map to delete/DIG-3605, never to a private repo.

Usage:
  python3 scripts/split/manifest.py [--check] [--ref <git-ref>] [--stat]

  --check  exit 1 on any unassigned path (local-ci gate). Double assignment is
           impossible by construction (first matching rule wins) and is
           re-verified by the self-test.
  --ref    enumerate tracked paths at a git ref (default: working tree via
           `git ls-files`, else the given ref via `git ls-tree`).
  --stat   print per-repo counts.

  Replaces the `overlaps-known.txt` whitelist (removed): no path is allowed to
  sit in two repos, so there is nothing to whitelist.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys

REPOS = ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "delete")

# Ordered (prefix, repo, reason). First match wins. Prefixes are matched as
# exact file paths or as directory prefixes ("foo/" matches "foo/bar").
# More specific paths MUST come before the general ones covering them.
# A prefix containing "*" is an fnmatch glob; it exists only for the few
# client/vendor paths that may not be written literally in this public file
# (the R0 client-literals guard, DIG-3689, scans every line here).
RULES: list[tuple[str, str, str]] = [
    # ---- delete: replaced tooling (DIG-3605; never a private repo) ----
    (
        ".github/workflows/",
        "delete",
        "GHA exit (DIG-3605): workflows move to local-ci/Cloudflare cron, never to a private repo",
    ),
    # ---- R1: proprietary strategies + optimiser ----
    ("digiquant/src/digiquant/strategies/sdca/", "R1", "proprietary SDCA strategy"),
    ("digiquant/src/digiquant/strategies/rotation/", "R1", "proprietary rotation strategy"),
    ("digiquant/src/digiquant/strategies/pinescript/", "R1", "proprietary pinescript strategies"),
    ("digiquant/src/digiquant/strategies/slapper.py", "R1", "proprietary slapper strategy"),
    (
        "digiquant/src/digiquant/strategies/m2_liquidity.py",
        "R1",
        "proprietary m2_liquidity strategy",
    ),
    (
        "digiquant/src/digiquant/strategies/calibrations_loader.py",
        "R1",
        "proprietary calibrations loader",
    ),
    (
        "digiquant/src/digiquant/strategies/calibrations.example.json",
        "R1",
        "proprietary calibrations example",
    ),
    ("digiquant/src/digiquant/strategies/settings.json", "R1", "proprietary strategy settings"),
    ("digiquant/src/digiquant/optimize.py", "R1", "optimiser (plugin)"),
    ("digiquant/src/digiquant/optimize_bayesian.py", "R1", "optimiser (plugin)"),
    ("digiquant/src/digiquant/sdca_mcp.py", "R1", "SDCA MCP tool (plugin)"),
    ("digiquant/src/digiquant/charts/sdca.py", "R1", "SDCA charts"),
    ("digiquant/scripts/sync_strategy_calibrations.py", "R1", "strategy calibration sync"),
    (
        "digiquant/scripts/verify_strategy_calibrations_rls.py",
        "R1",
        "strategy calibration RLS check",
    ),
    ("digiquant/scripts/plot_sdca_tearsheet.py", "R1", "SDCA tearsheet plot"),
    ("digiquant/scripts/export_sdca_macro.py", "R1", "SDCA macro export"),
    # ---- R2: production backend + private core pipeline (Chris 01:26) ----
    ("apps/digiquant-runner/", "R2", "production runner"),
    ("apps/dashboard-api/", "R2", "desk API (own Worker)"),
    ("digiquant/supabase/", "R2", "production schema + migrations"),
    (
        "digiquant/src/digiquant/execution/",
        "R2",
        "house pipeline incl. staging_secrets.py and vendor_secret_* (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/data/gloomberb/",
        "R2",
        "vendor data client gloomberb (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/data/luxalgo/",
        "R2",
        "vendor data client luxalgo (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/data/prices/gloomberb_macro.py",
        "R2",
        "vendor data client gloomberb (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/brokers/luxalgo_mirror.py",
        "R2",
        "vendor data client luxalgo (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/brokers/luxalgo_coinbase_mirror.py",
        "R2",
        "vendor data client luxalgo (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/brokers/luxalgo_kraken_mirror.py",
        "R2",
        "vendor data client luxalgo (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/brokers/luxalgo_tradier_mirror.py",
        "R2",
        "vendor data client luxalgo (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/cli/gloomberb.py",
        "R2",
        "vendor data client gloomberb (private per Chris 01:26)",
    ),
    (
        "digiquant/src/digiquant/research/docs/RUNBOOK.md",
        "R2",
        "research/docs/RUNBOOK.md (private per Chris 01:26)",
    ),
    ("config/contract/secrets.yaml", "R2", "contract secrets (private per Chris 01:26)"),
    ("scripts/digiquant_apply_vendor_secrets.py", "R2", "vendor secret applier"),
    ("scripts/digiquant_house_pipeline_proof.py", "R2", "house pipeline proof"),
    ("scripts/digiquant_route_cron.py", "R2", "house pipeline cron routing"),
    ("scripts/digiquant_cron_check.py", "R2", "house pipeline cron check"),
    ("scripts/digiquant_staging_e2e.py", "R2", "staging pipeline e2e"),
    ("scripts/digiquant_pages_dashboard_gate.py", "R2", "desk deploy gate"),
    ("scripts/digiquant_archive_checkpoints.py", "R2", "pipeline checkpoint archiver"),
    ("scripts/digiquant_checkpoint_size_gate.py", "R2", "pipeline checkpoint gate"),
    ("scripts/digiquant_seal_byok.py", "R2", "desk BYOK sealer"),
    ("infra/docker/Dockerfile.digiquant-runner", "R2", "runner image"),
    # ---- R3: Brief desk + digiquant.io ----
    ("apps/dashboard/app/twelve-x/", "R7", "twelve-x desk pages live under the Brief desk tree"),
    (
        "apps/dashboard/components/twelve-x/",
        "R7",
        "twelve-x desk pages live under the Brief desk tree",
    ),
    ("apps/dashboard/", "R3", "Brief desk /app (private per Chris 01:26)"),
    ("apps/digiquant-web/", "R3", "digiquant.io"),
    ("apps/digiquant-app/", "R3", "digiquant operator app (provisional; confirm in file:line plan table)"),
    # ---- R4: digithings.ai, digibook, brand ----
    ("apps/digithings-web/", "R4", "digithings.ai + digibook"),
    ("packages/brand/", "R4", "brand assets"),
    # ---- R5: shared prod platform ----
    (
        "apps/digithings-stack-cloudflare/container/seed/",
        "R6",
        "client corpora + seeds (R6 lives inside the stack container tree)",
    ),
    ("apps/digithings-stack-cloudflare/", "R5", "stack Worker + container"),
    ("apps/digichat-cloudflare/", "R5", "digichat Worker"),
    ("apps/digitrace-langfuse/", "R5", "langfuse"),
    ("apps/digitrace-ingest/", "R5", "telemetry ingest Worker (platform)"),
    ("apps/digithings-cron/", "R5", "cron"),
    ("apps/corpus-index/", "R5", "corpus indexer Worker (provisional; indexes tenant corpora - confirm in file:line plan table)"),
    ("infra/digichat-release/", "R5", "release infra"),
    ("config/litellm.yaml", "R5", "litellm config"),
    ("config/litellm.cheaperinference.yaml", "R5", "litellm config"),
    ("config/litellm.dev.yaml", "R5", "litellm config"),
    ("config/litellm.omniroute.yaml", "R5", "litellm config"),
    ("infra/docker/Dockerfile.digithings-stack-cloudflare", "R5", "stack image"),
    ("infra/docker/Dockerfile.digichat-cloudflare", "R5", "digichat image"),
    ("infra/docker/Dockerfile.digitrace-langfuse-web", "R5", "langfuse image"),
    ("infra/docker/Dockerfile.digitrace-langfuse-worker", "R5", "langfuse image"),
    # ---- R6: client corpora + rollout tooling ----
    ("docs/projects/online-compliance-center/", "R6", "client corpus"),
    ("docs/ops/OCC_INVITE_KEY.md", "R6", "rollout tooling doc"),
    ("scripts/occ_invite_key_rollout.sh", "R6", "rollout tooling"),
    ("scripts/verify_occ_invite_key.sh", "R6", "rollout tooling"),
    ("scripts/occ_invite_key_fixture_server.mjs", "R6", "rollout tooling"),
    ("scripts/check_occ_rollout_auth_guard.py", "R6", "rollout tooling"),
    ("scripts/test_occ_rollout_scope_guard.sh", "R6", "rollout tooling"),
    ("scripts/test_verify_occ_invite_key.sh", "R6", "rollout tooling"),
    ("scripts/datatap_answer_integrity_check.py", "R6", "answer-check tooling"),
    ("scripts/check_tenant_corpus_map.py", "R6", "tenant corpus map check"),
    # ---- R7: client desk + digidata-api ----
    ("apps/digidata-api/", "R7", "digidata-api (D1 twelvex)"),
    ("apps/twelvex-runner/", "R7", "twelve-x runner container (R7)"),
    # ---- R0: repo root files (open) ----
    (".coderabbit.yaml", "R0", "root config (open)"),
    (".cursorrules", "R0", "root config (open)"),
    (".dockerignore", "R0", "root config (open)"),
    (".editorconfig", "R0", "root config (open)"),
    (".env.example", "R0", "root config (open)"),
    (".gitattributes", "R0", "root config (open)"),
    (".gitignore", "R0", "root config (open)"),
    (".gitleaks.toml", "R0", "root config (open)"),
    (".gitleaksignore", "R0", "root config (open)"),
    (".python-version", "R0", "root config (open)"),
    (".sctl.yml", "R0", "root config (open)"),
    (".mcp.json", "R0", "root config (open)"),
    (".opencode/", "R0", "agent wiring (open)"),
    (".prettierignore", "R0", "root config (open)"),
    (".prettierrc.json", "R0", "root config (open)"),
    (".release-please-manifest.json", "R0", "release config (open)"),
    (".release-please-manifest-digiskills.json", "R0", "release config (open)"),
    (".vscode/", "R0", "editor config (open)"),
    (".vulture_whitelist.py", "R0", "root config (open)"),
    ("AGENTS.md", "R0", "root docs (open)"),
    ("ARCHITECTURE.md", "R0", "root docs (open)"),
    ("BRANCHING.md", "R0", "root docs (open)"),
    ("CLAUDE.md", "R0", "root docs (open)"),
    ("CODEOWNERS", "R0", "root config (open)"),
    ("CODE_OF_CONDUCT.md", "R0", "root docs (open)"),
    ("CONTRIBUTING.md", "R0", "root docs (open)"),
    ("LICENSE", "R0", "root licence (open)"),
    ("Makefile", "R0", "root build (open)"),
    ("ONBOARDING.md", "R0", "root docs (open)"),
    ("README.md", "R0", "root docs (open)"),
    ("RELEASES.md", "R0", "root docs (open)"),
    ("ROADMAP.md", "R0", "root docs (open)"),
    ("SECURITY.md", "R0", "root docs (open)"),
    ("TRADEMARKS.md", "R0", "root docs (open)"),
    ("conftest.py", "R0", "root test config (open)"),
    ("docker-compose.yml", "R0", "local stack (open)"),
    ("eslint.base.mjs", "R0", "root config (open)"),
    ("mypy.ini", "R0", "root config (open)"),
    ("npm-audit-ignore.txt", "R0", "root config (open)"),
    ("package.json", "R0", "npm workspace root (open)"),
    ("package-lock.json", "R0", "npm workspace root (open)"),
    ("pip-audit-ignore.txt", "R0", "root config (open)"),
    ("pyproject.toml", "R0", "root config (open)"),
    ("pytest.ini", "R0", "root config (open)"),
    ("release-please-config.json", "R0", "release config (open)"),
    ("release-please-config-digiskills.json", "R0", "release config (open)"),
    ("renovate.json", "R0", "root config (open)"),
    ("ruff.toml", "R0", "root config (open)"),
    ("tsconfig.base.json", "R0", "root config (open)"),
    ("uv.lock", "R0", "root config (open)"),
    ("digiquant/.dockerignore", "R0", "digiquant package config (open)"),
    ("digiquant/AGENTS.md", "R0", "digiquant docs (open)"),
    ("digiquant/ARCHITECTURE.md", "R0", "digiquant docs (open)"),
    ("digiquant/conftest.py", "R0", "digiquant test config (open)"),
    ("digiquant/Dockerfile", "R0", "digiquant engine image (open)"),
    ("digiquant/Dockerfile.mcp", "R0", "digiquant engine image (open)"),
    ("digiquant/Dockerfile.sandbox", "R0", "digiquant engine image (open)"),
    ("digiquant/pyproject.toml", "R0", "digiquant package config (open)"),
    ("digiquant/requirements.sandbox.txt", "R0", "digiquant package config (open)"),
    # ---- Specific rules for move-list entries (DIG-3518 item (a)) ----
    # These were previously absorbed by the broad catch-alls (docs/, config/, scripts/,
    # tests/dq/, apps/digichat/, digiquant/src/digiquant/) and made the manifest disagree
    # with extraction on 294 paths. Each entry mirrors scripts/repo-split/move-lists/rN.paths.
    ("apps/digichat/src/lib/embed-suggestion-pools.test.ts", "R6", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("apps/digichat/src/lib/embed-suggestion-pools.ts", "R6", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    # One-config slice 1 (#6500): a tenant's complete deployment document and
    # the equivalence test that pins its live KV row carry client data, so they
    # move with the client corpus instead of into public R0. Same destination as
    # the client test above and the OCC example under apps/digichat/config/.
    ("apps/digichat/config/occ.yaml", "R6", "client tenant deployment document (one-config slice 1)"),
    ("apps/digichat/src/lib/deploy-config/tenant-documents.equivalence.test.ts", "R6", "pins the live tenant row (one-config slice 1)"),
    ("config/byok-providers.json", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("config/digiquant-model-prices.json", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("config/digiquant_models.yaml", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("config/dogfood-digiproject.yaml", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("config/model-policy.json", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("digiquant/src/digiquant/research/config/", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/2026-10-06-stranded-branch-triage.tsv", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/2026-10-06-stranded-work-and-backup-report.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/2026-10-06-t2-branch-decisions.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/CLIENT_PIPELINES.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/SECRETS_INVENTORY.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/SECRETS_ROTATION.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/branch-hygiene-policy.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/credential-ownership.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/*-az-guard.md", "R5", "vendor guard runbook (r5.paths; DIG-3518 (a)); was falling into a broad catch-all; name withheld from this public file"),
    ("docs/ops/digichat-aca-secret-fingerprints.json", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/*-aca.md", "R5", "vendor ACA runbook (r5.paths; DIG-3518 (a)); was falling into a broad catch-all; name withheld from this public file"),
    ("docs/ops/digifetch-post-deploy-verification.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/digiquant-digikey-service-key.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/digiquant-runner.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/digithings-cron.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/digitrace-langfuse.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/gloomberb-session-cookie.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/local-deploy-parity.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/paperclip-routine-watch.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/policy-check-credential.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/supabase-exit-twelve-x-cutover-runbook.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/ops/vectorize-cutover.md", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/research/equity-valuation-for-sdca.md", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/research/equity_valuation_sdca_check.py", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/research/sdca-btc-onchain-valuation.md", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("docs/research/sdca-indicator-pool.md", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/backfill_market_data_r2.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/bench_market_data.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/build-digiquant.sh", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/build-digithings.sh", "R4", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/export_research_snapshot_schema.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/index_occ_tickets.py", "R6", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/merge_litellm_cheaperinference.py", "R5", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/production_deploy_gate_latency.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/record_market_data_goldens.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/rls_proof/", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/seed_digiquant_demo.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/setup_digiquant_project.sh", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/supabase_exit/", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/validate_digiquant_pools.py", "R2", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("scripts/*_mcp/", "R5", "vendor helpdesk MCP helper (r5.paths; DIG-3518 (a)); was falling into a broad catch-all; name withheld from this public file"),
    ("tests/dq/strategies/", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),
    ("tests/dq/test_mcp_sdca_risk_index.py", "R1", "move-list entry (DIG-3518 (a)); was falling into a broad catch-all"),

    # ---- Delete set beyond .github/workflows/ (proposal §3; DIG-3518 item (c)) ----
    # Broad delete rules; the specific R6 rule for the client corpus under
    # docs/projects/ (above) wins by first-match. Agent-wiring paths are
    # delete/private-ops.
    ("docs/superpowers/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/agent-backlog/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/reviews/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/plans/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/projects/", "delete", "proposal delete set (DIG-3392); R6 OCC path ruled above"),
    ("docs/dig-2041/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/backlog/", "delete", "proposal delete set (DIG-3392)"),
    ("docs/scoring/", "delete", "proposal delete set (DIG-3392)"),
    ("review-5061-digichat-mcp-tool-allowlist.md", "delete", "proposal delete set"),
    (".claude/", "delete", "agent wiring (delete/private ops)"),
    (".cursor/", "delete", "agent wiring (delete/private ops)"),
    ("agents/", "delete", "agent wiring (delete/private ops)"),
    ("agents.yml", "delete", "agent wiring (delete/private ops)"),
    ("opencode.json", "delete", "agent wiring (delete/private ops)"),
    ("projects/", "delete", "agent wiring (delete/private ops)"),

    # ---- R0: public OSS (default for everything below) ----
    ("digiquant/src/digiquant/", "R0", "digiquant engine core (open)"),
    ("digiquant/scripts/research/", "R0", "research engine (open)"),
    ("digiquant/scripts/", "R0", "digiquant scripts (open)"),
    ("digiquant/docs/", "R0", "digiquant docs (open)"),
    ("digiquant/sandbox/", "R0", "digiquant sandbox (open)"),
    ("digiquant/data/", "R0", "digiquant data dir (open)"),
    ("digiquant/config/", "R0", "digiquant config (open)"),
    ("apps/digichat/", "R0", "digichat engine (open)"),
    ("apps/digiweb/", "R0", "reference app (open)"),
    ("packages/design/", "R0", "design tokens (open)"),
    ("packages/ui/", "R0", "shared UI (open)"),
    ("packages/digichat-ui/", "R0", "digichat UI (open)"),
    ("packages/hero-banner/", "R0", "hero banner (open)"),
    ("packages/surface-config/", "R0", "surface config (open)"),
    ("packages/contract/", "R0", "shared contract (open)"),
    ("packages/catalog/", "R0", "shared catalog package (open)"),
    ("packages/durable-object-reconnect/", "R0", "shared reconnect package (open)"),
    ("packages/tui-frame/", "R0", "shared TUI frame package (open)"),
    ("clients/", "R0", "TUI clients (open)"),
    ("digibase/", "R0", "OSS module"),
    ("digikey/", "R0", "OSS module"),
    ("digifetch/", "R0", "OSS module"),
    ("digigraph/", "R0", "OSS module"),
    ("digillm/", "R0", "OSS module"),
    ("digisearch/", "R0", "OSS module"),
    ("digivault/", "R0", "OSS module"),
    ("digitrace/", "R0", "OSS module"),
    ("digibot/", "R0", "OSS module"),
    ("digivoice/", "R0", "OSS module"),
    ("digiskills/", "R0", "OSS module"),
    ("digidev/", "R0", "OSS module"),
    ("docs/research/sdca_weekly_oscillator_corr.py", "R1", "proprietary strategy research"),
    ("docs/", "R0", "docs (open)"),
    ("openwiki/", "R0", "openwiki (open)"),
    ("tests/dq/strategies/sdca/", "R1", "tests of the proprietary SDCA strategy"),
    ("tests/dq/test_strategies.py", "R1", "tests proprietary strategies"),
    ("tests/dq/test_optimize_bayesian.py", "R1", "tests the optimiser"),
    ("tests/dq/test_optimize_export.py", "R1", "tests the optimiser"),
    ("tests/dq/test_tearsheet_isolation.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_tearsheet_sdca_publish.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_tearsheet_signal_delay.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_mcp_tearsheet_tool.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_calibrations_loader.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_export_sdca_macro.py", "R1", "tests proprietary calibrations"),
    ("tests/dq/test_mcp_sdca_platform.py", "R1", "tests the SDCA platform"),
    (
        "tests/dq/test_mcp_gloomberb_tools.py",
        "R2",
        "tests vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/test_gloomberb_mcp_prefix.py",
        "R2",
        "tests vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/test_luxalgo_trackers_dataset_allowlist.py",
        "R2",
        "tests vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/test_congress_trades_statute_and_ingest_provenance.py",
        "R2",
        "tests vendor data clients (private per Chris 01:26)",
    ),
    (
        "tests/dq/test_mcp_server_scope.py",
        "R2",
        "tests vendor client gates (private per Chris 01:26)",
    ),
    (
        "tests/dq/indicators/test_macro_liquidity.py",
        "R2",
        "tests vendor macro feed (private per Chris 01:26)",
    ),
    (
        "tests/dq/research/test_phase_tool_flags.py",
        "R2",
        "tests vendor macro feed (private per Chris 01:26)",
    ),
    (
        "tests/dq/research/test_build_grounding_digifetch.py",
        "R2",
        "tests vendor session gate (private per Chris 01:26)",
    ),
    (
        "tests/dq/portfolio/test_digifetch_grounding.py",
        "R2",
        "tests vendor session gate (private per Chris 01:26)",
    ),
    ("tests/dq/notify/test_sync_hook.py", "R2", "tests the house pipeline"),
    ("tests/dq/dashboard/test_envcompat.py", "R2", "tests the house pipeline"),
    (
        "tests/dq/dashboard/test_envcompat_repo_inventory.py",
        "R2",
        "tests the house pipeline",
    ),
    ("tests/integration/test_execution_tenancy_chain.py", "R2", "tests the house pipeline"),
    (
        "tests/scripts/test_gloomberb_session_cookie_runbook.py",
        "R2",
        "tests vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/scripts/test_macro_series_cadence_declared.py",
        "R2",
        "tests vendor macro feed (private per Chris 01:26)",
    ),
    (
        "tests/scripts/test_probe_gloomberb_macro_panel.py",
        "R2",
        "tests vendor macro feed (private per Chris 01:26)",
    ),
    (
        "scripts/check_luxalgo_license_boundary.py",
        "R2",
        "vendor client luxalgo guard (private per Chris 01:26)",
    ),
    ("scripts/execution_cron_check.py", "R2", "house pipeline cron check"),
    (
        "scripts/probe_gloomberb_macro_panel.py",
        "R2",
        "vendor macro probe (private per Chris 01:26)",
    ),
    ("scripts/refresh_market_data_r2.py", "R2", "vendor macro feed (private per Chris 01:26)"),
    ("tests/dq/strategies/test_m2_liquidity_config.py", "R1", "tests of a proprietary strategy"),
    ("tests/dq/strategies/test_rs_rotation.py", "R1", "tests of a proprietary strategy"),
    ("tests/dq/strategies/test_slapper_backtest.py", "R1", "tests of a proprietary strategy"),
    ("tests/dq/strategies/test_slapper_config.py", "R1", "tests of a proprietary strategy"),
    ("tests/dq/execution/", "R2", "tests of the house pipeline"),
    ("tests/dq/dashboard/execution/", "R2", "tests of the house pipeline"),
    (
        "tests/dq/brokers/test_luxalgo_mirror.py",
        "R2",
        "tests of vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/brokers/test_luxalgo_coinbase_mirror.py",
        "R2",
        "tests of vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/brokers/test_luxalgo_kraken_mirror.py",
        "R2",
        "tests of vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/brokers/test_luxalgo_tradier_mirror.py",
        "R2",
        "tests of vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/brokers/luxalgo_mirror_cases.py",
        "R2",
        "tests of vendor client luxalgo (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_agent_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_calc_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_calculators.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_cli.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_client.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_client_quotes.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_client_history.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_client_macro.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_client_research.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/gloomberb_client_support.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_macro.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_models.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_normalizers.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_portfolio_math_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_prediction_markets.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/gloomberb_prediction_fixtures.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_probe_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_session_gate.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_tos_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    (
        "tests/dq/data/test_gloomberb_workspace_broker_tools.py",
        "R2",
        "tests of vendor client gloomberb (private per Chris 01:26)",
    ),
    ("tests/dq/", "R0", "digiquant engine tests (open)"),
    ("tests/", "R0", "tests (open)"),
    ("scripts/split/", "R0", "split tooling itself (open)"),
    ("scripts/", "R0", "scripts (open)"),
    ("config/", "R0", "config (open)"),
    ("infra/", "R0", "infra (open)"),
    (".github/", "R0", "repo automation (open; workflows/ deleted above)"),
    ("openspec/", "R0", "openspec (open)"),
    ("infra/docker/Dockerfile.digillm", "R0", "open image"),
]


def match_rule(path: str) -> tuple[str, str] | None:
    """Return (repo, reason) for the first matching rule, else None.

    A rule containing "*" is an fnmatch glob. A glob ending in "/" also covers
    the paths below the matched directory, the same way a literal directory
    prefix does; without that, "scripts/*_mcp/" would match nothing because git
    tracks files, not directories.
    """
    for pattern, repo, reason in RULES:
        if "*" in pattern:
            if fnmatch.fnmatchcase(path, pattern.rstrip("/")) or (
                pattern.endswith("/") and fnmatch.fnmatchcase(path, pattern + "*")
            ):
                return repo, reason
        elif pattern.endswith("/"):
            if path == pattern[:-1] or path.startswith(pattern):
                return repo, reason
        elif path == pattern:
            return repo, reason
    return None


def tracked_paths(ref: str | None = None, repo: str | None = None) -> list[str]:
    base = ["git"]
    if repo:
        base += ["-C", repo]
    if ref:
        out = subprocess.run(
            base + ["ls-tree", "-r", "--name-only", ref],
            capture_output=True,
            text=True,
            check=True,
        )
    else:
        out = subprocess.run(
            base + ["ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
    return sorted(p for p in out.stdout.splitlines() if p)


def build_manifest(paths: list[str]) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    unassigned: list[str] = []
    for p in paths:
        hit = match_rule(p)
        if hit is None:
            unassigned.append(p)
        else:
            mapping[p] = hit[0]
    return mapping, unassigned


def main(argv: list[str]) -> int:
    ref: str | None = None
    repo: str | None = None
    check = False
    stat = False
    emit_r0: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--check":
            check = True
        elif a == "--stat":
            stat = True
        elif a == "--emit-r0" and i + 1 < len(argv):
            emit_r0 = argv[i + 1]
            i += 1
        elif a == "--ref" and i + 1 < len(argv):
            ref = argv[i + 1]
            i += 1
        elif a == "--repo" and i + 1 < len(argv):
            repo = argv[i + 1]
            i += 1
        i += 1
    paths = tracked_paths(ref, repo)
    mapping, unassigned = build_manifest(paths)
    if emit_r0 is not None:
        r0_paths = sorted(p for p, r in mapping.items() if r == "R0")
        with open(emit_r0, "w", encoding="utf-8") as f:
            for pp in r0_paths:
                f.write(pp + "\n")
        print(f"emit-r0: wrote {len(r0_paths)} R0 paths to {emit_r0}")
    if stat or check:
        counts: dict[str, int] = {r: 0 for r in REPOS}
        for r in mapping.values():
            counts[r] += 1
        for r in REPOS:
            print(f"{r}: {counts[r]}")
        print(f"unassigned: {len(unassigned)}")
        for pp in unassigned[:50]:
            print(f"  UNASSIGNED {pp}")
    elif emit_r0 is None:
        for pp in paths:
            print(f"{mapping.get(pp, 'UNASSIGNED')}\t{pp}")
    if check and unassigned:
        print(f"FAIL: {len(unassigned)} unassigned paths", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
