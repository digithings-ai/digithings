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

import subprocess
import sys

REPOS = ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "delete")

# Ordered (prefix, repo, reason). First match wins. Prefixes are matched as
# exact file paths or as directory prefixes ("foo/" matches "foo/bar").
# More specific paths MUST come before the general ones covering them.
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
    ("Dockerfile.digiquant-runner", "R2", "runner image"),
    # ---- R3: Brief desk + digiquant.io ----
    ("apps/dashboard/app/twelve-x/", "R7", "twelve-x desk pages live under the Brief desk tree"),
    (
        "apps/dashboard/components/twelve-x/",
        "R7",
        "twelve-x desk pages live under the Brief desk tree",
    ),
    ("apps/dashboard/", "R3", "Brief desk /app (private per Chris 01:26)"),
    ("apps/digiquant-web/", "R3", "digiquant.io"),
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
    ("apps/digithings-cron/", "R5", "cron"),
    ("infra/digichat-release/", "R5", "release infra"),
    ("config/litellm.yaml", "R5", "litellm config"),
    ("config/litellm.cheaperinference.yaml", "R5", "litellm config"),
    ("config/litellm.dev.yaml", "R5", "litellm config"),
    ("config/litellm.omniroute.yaml", "R5", "litellm config"),
    ("Dockerfile.digithings-stack-cloudflare", "R5", "stack image"),
    ("Dockerfile.digichat-cloudflare", "R5", "digichat image"),
    ("Dockerfile.digitrace-langfuse-web", "R5", "langfuse image"),
    ("Dockerfile.digitrace-langfuse-worker", "R5", "langfuse image"),
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
    ("agents.yml", "R0", "agent wiring (open)"),
    ("conftest.py", "R0", "root test config (open)"),
    ("docker-compose.yml", "R0", "local stack (open)"),
    ("eslint.base.mjs", "R0", "root config (open)"),
    ("mypy.ini", "R0", "root config (open)"),
    ("npm-audit-ignore.txt", "R0", "root config (open)"),
    ("opencode.json", "R0", "agent wiring (open)"),
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
    ("digiquant/Dockerfile", "R0", "digiquant engine image (open)"),
    ("digiquant/Dockerfile.mcp", "R0", "digiquant engine image (open)"),
    ("digiquant/Dockerfile.sandbox", "R0", "digiquant engine image (open)"),
    ("digiquant/pyproject.toml", "R0", "digiquant package config (open)"),
    ("digiquant/requirements.sandbox.txt", "R0", "digiquant package config (open)"),
    # ---- R0: public OSS (default for everything below) ----
    ("digiquant/src/digiquant/", "R0", "digiquant engine core (open)"),
    ("digiquant/scripts/research/", "R0", "research engine (open)"),
    ("digiquant/scripts/", "R0", "digiquant scripts (open)"),
    ("digiquant/docs/", "R0", "digiquant docs (open)"),
    ("digiquant/sandbox/", "R0", "digiquant sandbox (open)"),
    ("digiquant/data/", "R0", "digiquant data dir (open)"),
    ("digiquant/config/", "R0", "digiquant config (open)"),
    ("apps/digichat/", "R0", "digichat engine (open)"),
    ("apps/reference/", "R0", "reference app (open)"),
    ("packages/design/", "R0", "design tokens (open)"),
    ("packages/ui/", "R0", "shared UI (open)"),
    ("packages/digichat-ui/", "R0", "digichat UI (open)"),
    ("packages/hero-banner/", "R0", "hero banner (open)"),
    ("packages/surface-config/", "R0", "surface config (open)"),
    ("clients/", "R0", "TUI clients (open)"),
    ("digibase/", "R0", "OSS module"),
    ("digikey/", "R0", "OSS module"),
    ("digifetch/", "R0", "OSS module"),
    ("digigraph/", "R0", "OSS module"),
    ("digillm/", "R0", "OSS module"),
    ("digisearch/", "R0", "OSS module"),
    ("digivault/", "R0", "OSS module"),
    ("digitrace/", "R0", "OSS module"),
    ("digiclaw/", "R0", "OSS module"),
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
    ("agents/", "R0", "agent wiring (open)"),
    (".claude/", "R0", "agent wiring (open)"),
    (".cursor/", "R0", "agent wiring (open)"),
    ("projects/", "R0", "projects (open)"),
    ("Dockerfile.digillm", "R0", "open image"),
]


def match_rule(path: str) -> tuple[str, str] | None:
    """Return (repo, reason) for the first matching rule, else None."""
    for prefix, repo, reason in RULES:
        if prefix.endswith("/"):
            if path == prefix[:-1] or path.startswith(prefix):
                return repo, reason
        elif path == prefix:
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
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--check":
            check = True
        elif a == "--stat":
            stat = True
        elif a == "--ref" and i + 1 < len(argv):
            ref = argv[i + 1]
            i += 1
        elif a == "--repo" and i + 1 < len(argv):
            repo = argv[i + 1]
            i += 1
        i += 1
    paths = tracked_paths(ref, repo)
    mapping, unassigned = build_manifest(paths)
    if stat or check:
        counts: dict[str, int] = {r: 0 for r in REPOS}
        for repo in mapping.values():
            counts[repo] += 1
        for repo in REPOS:
            print(f"{repo}: {counts[repo]}")
        print(f"unassigned: {len(unassigned)}")
        for p in unassigned[:50]:
            print(f"  UNASSIGNED {p}")
    else:
        for p in paths:
            print(f"{mapping.get(p, 'UNASSIGNED')}\t{p}")
    if check and unassigned:
        print(f"FAIL: {len(unassigned)} unassigned paths", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
