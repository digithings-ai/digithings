# CI Conventions

Conventions and inventory for `.github/workflows/` in the digithings monorepo.

Tracked in issue [#292](https://github.com/digithings-ai/digithings/issues/292).

Queue starvation and org runner limits: [CI-QUEUE.md](CI-QUEUE.md).

---

## Workflow Inventory

Workflow `.yml` files only (gh-aw `.md` / `.lock.yml` sources retired with Copilot automation — see §0). Every file has a row in the inventory below.

**GHA leftover sweep (2026-10-01, develop after #4970):** `.github/workflows` on `develop` has **zero** `on.schedule` keys (pinned by `tests/scripts/test_no_gha_schedules.py`). Production clocks fire from `apps/digithings-cron`. Keep `workflow_dispatch` / `repository_dispatch`. `digisearch_parity` is not a workflow in this repo. Trigger cells below that still say `schedule` are historical GHA clocks now owned by Cloudflare, or files that exist only on `main`.

| File | Name | Trigger | Purpose | Status | Path filter |
|------|------|---------|---------|--------|-------------|
| `agent-backlog-snapshot.yml` | Agent: backlog snapshot | dispatch (CF clock Mon 06:13 UTC) | Refresh `docs/agent-backlog/generated-snapshot.md` from open agent-task issues; opens auto-merge PR | Working | none |
| `pipeline-digiquant.yml` | Pipeline: dashboard research | schedule (`17 9/10/11/12 * * *`, off-peak retries before NY open), `repository_dispatch` `digiquant-baseline`, dispatch | Unified research+portfolio pipeline; skip-if-already-succeeded on later crons; `resolve` picks Sunday `all` / else `none` | Working | none |
| *(spec, not installed)* `docs/agent-backlog/execution-tenancy/kairos-cron-check.workflow.yml` | Pipeline: execution cron check | schedule (daily 12:15 UTC), dispatch | Overlay + execution sync + notify `--check`/`--dry-run` probe; **must not** share the house portfolio job. Copy to `.github/workflows/execution-cron-check.yml` on a `chore/`/`feat/` branch (`cursor/*` cannot write workflows) | Spec pinned by `tests/scripts/test_digiquant_cron_workflow.py` | none |
| `test-research-graph.yml` | Test: research graph | workflow_call | Unit tests + lint for research + portfolio trees; installs the full workspace from `uv.lock` (`uv sync --frozen`) | Working | `digiquant/src/digiquant/{research,portfolio}/**`, `tests/dq/{research,portfolio}/**`, `pipeline-digiquant.yml` |
| `ci.yml` | CI | push (main/develop), PR | Orchestrator: per-component tests + e2e-contract + nautilus-smoke + research-graph + pip-audit + ruff/scripts/baseline/provider_review + compose-validate + `actionlint` (repo-wide workflow lint) + `frontend-canon` (unconditional canon guard, #1434) | Working | none |
| `test-e2e.yml` | Test: e2e stack | workflow_call, workflow_dispatch, push (develop) | PR gate: `e2e-contract` via `ci.yml`; compose `pytest -m e2e` on develop push/dispatch only (`continue-on-error`) | Working | `tests/test_e2e*.py`, compose |
| `test-nautilus.yml` | Test: Nautilus smoke | workflow_call | Linux `digiquant[nautilus]` smoke subset | Working | `digiquant/**`, `tests/dq/**` |
| `test-dashboard.yml` | Test: dashboard | workflow_call | Dashboard lint + vitest + build | Working | `apps/dashboard/**`, design |
| `test-web.yml` | Test: web apps | workflow_call | Lint `digithings-web` + `digiquant-web` + `design-reference` (root workspaces); typecheck `design-reference` (`tsc --noEmit`); vitest for `digithings-web`, `@digithings/ui`, `@digithings/digichat-ui`; frontend canon guard (`check_frontend_canon.py`) | Working | `apps/{digithings-web,digiquant-web,dashboard,reference,digichat}/**`, `packages/{ui,design,digichat-ui}/**`, `package.json`/lock |
| `pipeline-continuous-improvement.yml` | Pipeline: continuous improvement | schedule (Sun 22:00), dispatch | Weekly Claude-synthesized digest of activity patterns; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `test-digibase.yml` | Test: digibase | workflow_call | digibase unit tests | Working | `digibase/**`, `tests/db/**` |
| `test-digichat.yml` | Test: digichat | workflow_call | digichat (Next.js) lint + tests | Working | `apps/digichat/**`, `packages/design/**`, `package.json` |
| `publish-digichat-image.yml` | Publish: digichat image | push (tag `digichat-v*`), dispatch (`tag`) | Build + push the digichat image to GHCR from a `digichat-vX.Y.Z` tag; refuses when the tag's version ≠ `apps/digichat/package.json`, no-ops on an already-published version, passes `DIGICHAT_REVISION=<tag commit>`, then re-verifies the pushed image with `scripts/check_digichat_image_binding.py`. Restored in DIG-1294 (lane A of [docs/ops/digichat-datatap-aca.md](../ops/digichat-datatap-aca.md)) — **build only**: no `azure/login`, no `id-token: write`, no `environment:`, so it holds no credential that could reach a customer Container App. | Working (restored) | `apps/digichat/**` |
| `test-digiclaw.yml` | Test: digiclaw | workflow_call | digiclaw unit tests | Working | `digiclaw/**`, `tests/dc/**` |
| `test-digigraph.yml` | Test: digigraph | workflow_call | digigraph unit tests | Working | `digigraph/**`, `tests/dg/**` |
| `test-digikey.yml` | Test: digikey | workflow_call | digikey unit tests | Working | `digikey/**`, `tests/dk/**` |
| `pipeline-digiquant-prices.yml` | Pipeline: digiquant prices | dispatch only (Cloudflare Worker clock dispatches the at-open/EOD slots; schedules removed #3780/#4053) | Market-open `position_events` + calendar sync; macro writes gated behind `run_writers`; price/technicals ingest retired (#4053 — the R2 refresh owns it; Supabase tables dropped in 127) | Working | none |
| `pipeline-digiquant-tearsheets.yml` | Pipeline: digiquant tearsheets | schedule (daily 00:00 UTC), dispatch | Daily Slapper + BTC-SDCA tearsheet regen: Coinbase + M2/DXY siblings, Nautilus generate, upsert `strategy_tearsheets` (#1068, #3453). Checkout pinned to `main`. | Working | none |
| `test-digiquant.yml` | Test: digiquant | workflow_call | digiquant unit tests | Working | `digiquant/**`, `tests/dq/**` |
| `test-digisearch.yml` | Test: digisearch | workflow_call | digisearch unit tests | Working | `digisearch/**`, `tests/ds/**` |
| `test-digitrace.yml` | Test: digitrace | workflow_call | digitrace unit tests | Working | `digitrace/**`, `tests/dsm/**` |
| `ci-docs.yml` | CI: docs | push (main/develop), PR | Internal markdown link check + agents-init drift check (single job) | Working | markdown, agents surface |
| `project-enforce-assignment.yml` | Project: enforce assignment | dispatch (CF clock daily 09:23 UTC) | Comment on issues not assigned to any project board; guarded by `DIGITHINGS_PROJECT_TOKEN` | Fixed (#292) | none |
| `security-gitleaks.yml` | Security: gitleaks | push (main/develop), PR | Secrets scan — PR diff or full history; pinned OSS CLI (not the paid action) | Working | PR: paths-ignore `**.md`, `docs/**` |
| `security-pip-audit.yml` | Security: pip-audit | workflow_call, PR, push (main/develop), schedule (Mon 06:00) | CVE audit per Python component; blocks on HIGH/CRITICAL | Working | none |
| `ci-pr-hygiene.yml` | CI: PR hygiene | PR, schedule (daily 06:00), dispatch | Issue linkage (`Require Fixes`) + path-gated `project_fields.tsv` coverage | Working | TSV job: `project_fields.tsv` + this workflow |
| `ci-dco-sign-off.yml` | CI: DCO sign-off | PR (opened/sync/reopened), dispatch | Reject a PR whose non-merge commits lack `Signed-off-by` (DCO 1.1, forward-only from 2026-10-04). Merge commits are skipped — git writes them, so no amend can add a trailer. Not yet a required check — see #393, DIG-925 | Working | none |
| `pipeline-provider-review.yml` | Pipeline: provider review | schedule (Sun 00:00), dispatch | `pytest tests/provider_review/ -m unit` then weekly probe + Claude agent; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `pipeline-maintenance.yml` | Pipeline: scheduled maintenance | schedule (Mon 08:00), dispatch | Weekly sweep: CVE audit, stale branches, broken doc links, agents-init drift, stale issues/PRs, label coverage, workflow health | Working | none |
| `ci-type-check.yml` | CI: type check | push (main/develop), PR | mypy type checking for digibase + digikey | Working | `digibase/**`, `digikey/**`, `mypy.ini` |
| `test-digivault.yml` | Test: digivault | workflow_call | digivault unit tests | Working | `digivault/**`, `tests/dv/**` |
| `pipeline-research-metrics.yml` | Pipeline: research metrics refresh | schedule (daily, post-EOD), dispatch | Deterministic Polars/SQL recompute of `portfolio_metrics` + `position_attribution` the dashboard reads; zero LLM cost; runs after EOD price ingest | Working | none |
| ~~`pipeline-digiquant-backfill.yml`~~ | *(retired)* | — | Deleted in #4053: migration 127 dropped the Supabase `price_history`/`price_technicals` tables it backfilled; the R2 refresh/backfill owns ingest now | — | none |
| `deploy-digithings-cloudflare.yml` | Deploy: digithings.ai build check | PR (digithings.ai assets), dispatch | Gate/validate `scripts/build-digithings.sh`; primary deploy is Cloudflare Pages watching `main` | Working | digithings.ai assets |
| `deploy-digiquant-cloudflare.yml` | Deploy: digiquant.io build check | PR (digiquant.io assets), dispatch | Gate/validate `scripts/build-digiquant.sh` (ADR-0012); primary deploy is Cloudflare Pages watching `main` | Working | digiquant.io assets |
| ~~`deploy-digithings-stack-cloudflare.yml`~~ | *(deleted 2026-10-01)* | was PR check + `workflow_dispatch` | Deployed the `digithings-stack` Worker + Container (`graph.`/`key.`/`search.digithings.ai`). Deleted in `f54af7052` (#4919, Human Gate). Recoverable at `git show 'f54af7052^:<path>'`. The app still builds in `build-cloudflare-workers.yml`; it now ships **by hand** | **Missing — manual deploy** ([docs/DEPLOYMENT.md](../DEPLOYMENT.md#cloudflare-workers-and-containers)) | `apps/digithings-stack-cloudflare/**` |
| ~~`deploy-digichat-cloudflare-container.yml`~~ | *(deleted 2026-10-01)* | was push (`main`) + dispatch | Deployed the `digithings-digichat` Worker + Container behind `digithings.ai/embed*` and five sibling routes. Deleted in `f54af7052` (#4919, Human Gate). Recoverable at `git show 'f54af7052^:<path>'`. Still builds in `build-cloudflare-workers.yml`; ships **by hand** | **Missing — manual deploy** ([docs/DEPLOYMENT.md](../DEPLOYMENT.md#cloudflare-workers-and-containers)) | `apps/digichat-cloudflare/**` |
| `agent-pr-finalizer.yml` | Agent: PR finalizer | dispatch (CF clock daily 07:11 UTC) | Daily backstop for `cursor/*` PRs that missed the Cursor Automation merge path | Working | none |
| `refresh-repo-activity.yml` | Refresh: repo activity snapshot | dispatch (CF clock Mon 06:10 UTC) | Regenerates `apps/digithings-web/lib/repo-activity.json` and opens a `chore/` PR | Working | none |
| `book-pdf.yml` | Book: print the PDF | push, dispatch | Build the digibook's printed PDF as an artifact (DIG-2821) | Working | `paths:` filter |
| `ci-pr-title.yml` | CI: PR title | pull_request | Conventional Commit title lint with the module scope list; squash merges use the PR title | Working | none |
| `ci-review-coverage.yml` | CI: review coverage | pull_request | Gate before production: every PR in a promotion must carry a review | Working | none |
| `datatap-answer-check.yml` | Check: DataTap answer integrity | dispatch (CF clock) | Answer-integrity probe against DataTap production (DIG-306) | Working | none |
| `deploy-digiquant-runner.yml` | Deploy: digiquant-runner | push (`main`), dispatch | Deploy the private digiquant-runner Worker and container image (#4761) | Working | `paths:` filter |
| `deploy-digithings-cron.yml` | Deploy: digithings-cron | push (`main`), dispatch | Deploy the digithings-cron Worker that owns production clocks (#3579) | Working | `paths:` filter |
| `execution-cron-check.yml` | Pipeline: execution cron check | dispatch (CF clock) | Fail-closed probe for overlay dispatch env and execution sync; never `--execute` | Working | none |
| `occ-invite-key-rollout.yml` | Ops: OCC invite key rollout guards | pull_request, dispatch | OCC invite key rollout guards (DIG-1612); the key rotates on the Cloudflare side only | Working | `paths:` filter |
| `openwiki-update.yml` | OpenWiki Update | dispatch (CF clock) | Refresh `openwiki/` | Working | none |
| `pipeline-checkpoint-archive.yml` | Pipeline: checkpoint archive | dispatch (manual override; clock is digithings-cron → digiquant-runner) | Move checkpoint payloads to R2 (#3761) | Working | none |
| `pipeline-dependency-freshness.yml` | Pipeline: dependency freshness radar | dispatch (CF clock) | Compare `uv.lock` against PyPI latest (DIG-2277) | Working | none |
| `pipeline-digiquant-allocation-shadow.yml` | Pipeline: allocation shadow | workflow_run, dispatch | Write-denied shadow evaluation of allocation artifacts (#2762) | Working | none |
| `pipeline-digiquant-onchain.yml` | Pipeline: digiquant on-chain | dispatch (CF clock) | On-chain valuation ingest (#1086) | Working | none |
| `pipeline-market-data-refresh.yml` | market-data-refresh | dispatch (manual override; clock is digithings-cron → digiquant-runner) | Daily R2 market-data refresh (#3780) | Working | none |
| `production-deploy-gate-watchdog.yml` | Watch: production deploy gate latency | dispatch (CF clock) | Watch how long production deploys wait in the environment gate (DIG-1569) | Working | none |
| `publish-digillm-image.yml` | Publish: digillm image | pull_request, push, dispatch | Build, smoke-test and publish the digillm LiteLLM proxy image (DIG-1780) | Working | `paths:` filter |
| `secret-staleness-check.yml` | Ops: environment gate drift | dispatch (CF clock, monthly) | Compare `.github/environments.json` with live environment protection rules | Working | none |
| `security-npm-audit.yml` | Security: npm audit | workflow_call, dispatch | `npm audit` over the JS workspaces; sibling of `security-pip-audit.yml` | Working | none |
| `security-pii-scan.yml` | Security: customer PII scan | pull_request, push | Block committed customer PII (DIG-1498, DIG-2607) | Working | none |
| `self-host-parity.yml` | self-host-parity | pull_request, push, dispatch | Self-host vs hosted parity checks (DIG-2767) | Working | `paths:` filter |
| `sync-digiquant-runner-digikey-secret.yml` | Ops: sync digiquant-runner house secrets | dispatch | Put digikey and tracing secrets onto digiquant-runner (#4761); never prints values | Working | none |
| `sync-digiquant-runner-mail-secrets.yml` | Ops: sync digiquant-runner mail secrets | dispatch | Put mail/notify secrets onto digiquant-runner (#4761); never prints values | Working | none |
| `test-bun-suites.yml` | Test: bun suites | workflow_call (from `ci.yml`) | Run the `bun test` packages (DIG-2940) | Working | via `ci.yml` |
| `test-clients-tui.yml` | Test: clients (TUI) | workflow_call (from `ci.yml`) | Run the `clients/` bun packages (DIG-2072) | Working | via `ci.yml` |
| `test-digifetch.yml` | Test: digifetch | workflow_call (from `ci.yml`) | digifetch unit tests from the committed `uv.lock` | Working | via `ci.yml` |
| `test-digillm.yml` | Test: digillm | workflow_call (from `ci.yml`) | digillm unit tests from the committed `uv.lock` | Working | via `ci.yml` |
| `test-digivoice.yml` | Test: digivoice | workflow_call (from `ci.yml`) | digivoice unit tests from the committed `uv.lock` | Working | via `ci.yml` |
| `token-canary.yml` | Ops: token-validity canary | workflow_call, dispatch | Fail loudly when a scheduled-workflow credential expires (#3522) | Working | none |

**Deleted 2026-10-01 in #4919 (strict-essentials cut):** `agent-ci-failure-triage.yml`, `agent-claude-dispatch.yml`, `agent-claude-review.yml`, `agent-claude.yml`, `agent-dispatch-replay.yml`, `agent-docs-automerge.yml`, `agent-pr-autolabel.yml`, `agent-pr-automerge.yml`, `agent-quota-reset.yml`, `db-migrate.yml`, `docs-reindex-guide.yml`, `project-route-issues.yml`, `project-status.yml`, `project-stub-fields.yml`, `release-please-digichat.yml`, `smoke-langsmith.yml`, `smoke-site.yml`, `smoke-stack.yml`, `sync-architecture-vault.yml`. Their rows are gone from this table; `git show f54af7052` has the files. Other sections below that still name them describe how they worked.

---

## Secrets and Variables Reference

| Secret / Variable | Used by | Required or optional |
|-------------------|---------|---------------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | agent-claude.yml, agent-claude-review.yml, agent-claude-dispatch.yml, pipeline-continuous-improvement.yml, pipeline-provider-review.yml | Optional — features disabled when absent |
| `CURSOR_API_KEY` | agent-pr-finalizer.yml | Optional — Cursor fix dispatch skipped when absent |
| `DIGITHINGS_PROJECT_TOKEN` | project routing/status workflows, CI failure triage, PR finalizer, scheduled maintenance | Required for cross-project updates; guarded features skip when absent |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | research-baseline, research-delta, research-monthly, digiquant-prices | Required for production runs |
| `GEMINI_API_KEY` | research-baseline, research-delta, research-monthly | Required for research/portfolio LLM calls |
| `OLLAMA_API_KEY` | research-baseline, research-delta, research-monthly | Required for reasoning tier (phases 7, 7D) |
| `DIGISEARCH_URL` | pipeline-digiquant | Actions variable; falls back to the hosted `https://search.digithings.ai` |
| `vars.DIGI_MAINTENANCE_PROJECT_NUMBER` | scheduled-maintenance, ci-failure-triage, enforce-project-assignment | Optional — project-add step skipped when absent |

---

## Conventions

### 0. GitHub Agentic Workflows (gh-aw) — retired

**Status: retired (2026-08-05).** Copilot coding-agent automation and its gh-aw
sources (`.github/workflows/*.md` → `*.lock.yml`) were deleted in #1904.
ADR-0017 is superseded history — do not reintroduce `gh aw compile` without a
new ADR.

**Replacement CI drift check** (still in `ci-docs.yml`):

```bash
python scripts/agents_init.py --check   # or: make agents-init (then --check)
```

That job also runs markdown link integrity + `make vault-check`. There is no
`gh aw compile --trial` step anymore; the workflow header documents the removal
(#1182).

**Agent `test_cmd` alignment:** `agents.yml` `components[].test_cmd` values use
the same path selectors as `.github/workflows/test-<component>.yml` (for
example `pytest tests/ds/ -m unit …`, not `-k digisearch`). Enforced by
`tests/agents/test_agents_yml_test_cmds.py`.

**Local verify:**

```bash
python scripts/agents_init.py --check
pytest tests/agents/test_agents_yml_test_cmds.py -m unit -v --tb=short
```

---

### 1. Permissions — least privilege

Every workflow must declare a top-level `permissions:` block. Request only what the job needs.

```yaml
permissions:
  contents: read        # checkout only
  issues: write         # to comment or create issues
  pull-requests: write  # to comment on PRs
```

Never omit `permissions:`; the default grants read to most scopes and write to none, but being explicit prevents surprises when the repo default changes.

Do NOT grant `contents: write` unless the job commits or pushes. Prefer `pull-requests: write` scoped to the job that needs it.

### 2. Timeouts

Every job must set `timeout-minutes`. Pick a realistic ceiling, not the default (6 hours).

| Job type | Recommended ceiling |
|----------|---------------------|
| Lint / format check | 5 |
| Unit test suite | 15 |
| Integration / full install | 20 |
| LLM-driven scheduled pipelines | 45–240 (see job comment) |
| Maintenance sweeps | 10 |

### 3. Action version pinning

Pin GitHub-owned actions to the current major version tag (`@v4`, `@v5`). Use the version each action publishes — do not downgrade to @v4 if the action is on @v5.

| Action | Current pin |
|--------|-------------|
| `actions/checkout` | `@v4` |
| `actions/setup-python` | `@v5` |
| `actions/upload-artifact` | `@v4` |
| `actions/configure-pages` | `@v5` |
| `actions/upload-pages-artifact` | `@v3` |
| `actions/deploy-pages` | `@v4` |
| `peter-evans/create-pull-request` | `@v6` |
| `raven-actions/actionlint` | `@v2` (tool pinned: actionlint `1.7.12`, shellcheck `0.11.0` — see below) |
| `anthropics/claude-code-action` | `@v1` |

Third-party actions (non-GitHub-owned): pin to a full SHA for supply-chain integrity, or use a trusted major-version tag with a SHA comment. The `gitleaks` workflow demonstrates the preferred pattern for binary downloads: download from a pinned release URL and verify the SHA256 checksum.

### 4. Multi-line strings in run: | blocks

All content inside a `run: |` block must be indented at or beyond the block's indentation level. Heredoc content that begins at column 0 will be misinterpreted as a YAML top-level key.

**Wrong — heredoc content at column 0 breaks YAML:**

```yaml
      - run: |
          MSG="## Heading

**Bold text at column 0**    ← YAML parser sees this as a mapping key
"
```

**Correct — write to a temp file with printf:**

```yaml
      - run: |
          {
            printf '## Heading\n\n'
            printf '**Bold text**\n'
          } > /tmp/body.md
          gh issue create --body-file /tmp/body.md
```

This pattern is used by the dashboard pipeline workflow (`pipeline-digiquant.yml`) and is now required for all new issue/comment creation steps.

### 5. Secret guards

When a workflow depends on an optional secret, degrade gracefully rather than failing:

```yaml
- name: Check token present
  id: token
  env:
    TOKEN: ${{ secrets.DIGITHINGS_PROJECT_TOKEN }}
  run: |
    if [[ -n "${TOKEN:-}" ]]; then
      echo "present=true" >> "$GITHUB_OUTPUT"
    else
      echo "::warning::DIGITHINGS_PROJECT_TOKEN not set — skipping."
      echo "present=false" >> "$GITHUB_OUTPUT"
    fi

- name: Do the thing
  if: steps.token.outputs.present == 'true'
  ...
```

Always use `env:` to pull secrets into shell scope — never inline `${{ secrets.X }}` into a `run:` command.

### 6. Path filters

Workflows that only apply to specific components must declare `paths:` under both the `push` and `pull_request` triggers. Omitting `paths:` on `pull_request` causes the workflow to run on every PR regardless of which files changed.

Per-component test workflows (`test-digibase.yml`, etc.) use `workflow_call` so `ci.yml` can invoke them unconditionally, while the direct push/PR triggers are path-filtered. This is the correct pattern.

**Adding a lane to `ci.yml` is three edits, and the drift check only catches one of them.** `scripts/generate_ci_path_filters.py` rewrites *only* the block between the `CI_PATH_FILTERS` markers; the `changes:` job's `outputs:` map is hand-maintained. A filter added to `scripts/ci_paths.yaml` and regenerated, but never wired into `outputs:`, yields `needs.changes.outputs.<name> == ''` — the lane's `if:` is false on every run and it silently never fires, with `--check` green throughout.

1. Add the filter to `scripts/ci_paths.yaml`.
2. Run `python3 scripts/generate_ci_path_filters.py` (CI enforces `--check`).
3. **By hand:** add `<name>: ${{ steps.filter.outputs.<name> }}` to the `changes` job's `outputs:` map.

Then add the job with `needs: changes` and `if: needs.changes.outputs.<name> == 'true'`.

A lane whose gate can silently narrow deserves an assertion about its own coverage — see the `Assert every workflow was linted` step in the `actionlint` job. Coverage is files; a gate can also narrow by *rule*, which that step would not catch — `Assert SC2129 is live` in the same job probes for that.

### 7. Concurrency

Use `concurrency:` to cancel stale runs on rapid pushes:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

For production pipelines where mid-run cancellation would corrupt state (research baseline, monthly synthesis), set `cancel-in-progress: false` and use a named group without `${{ github.ref }}`.

**Exception — a job gated on an `environment` approval must not queue.** The rule above
assumes the run holding the group is *doing work*, so protecting it is worth a delay. A job
behind a required-reviewer rule holds the group while it does nothing, for as long as nobody
approves it, and `cancel-in-progress: false` protects that too — so a single unapproved run
stops the workflow indefinitely and every later run reports `cancelled` with zero jobs, which
looks like a cancelled deploy rather than a deploy that never happened. `db-migrate.yml` lost
15 days and migrations 066-070 to this (#2541). Such a workflow needs
`cancel-in-progress: true` in a **named** group: named, so applies still serialise; true, so
an unapproved run is superseded instead of blocking. That is only safe when the newest run's
work is a superset of what it displaces — db-migrate qualifies because its apply is purely
ledger-gated. If yours does not, keep the queue and add a scheduled staleness check instead;
what is never acceptable is a queue that can stall silently and forever.

### 8. workflow_run triggers and workflow names

`agent-ci-failure-triage.yml` uses `workflow_run` and lists workflow names explicitly. If a watched workflow is renamed, update this list to match. The names in `workflows:` must exactly match the `name:` field of the target workflow.

Current watched workflows in `agent-ci-failure-triage.yml`:
- `Docs` → `ci-docs.yml`
- `CI` → `ci.yml`
- `PR quality gate` → (no matching file; legacy name — see Known Issues)
- `digibase tests` → `test-digibase.yml`
- `digichat tests` → `test-digichat.yml`
- `digiclaw tests` → `test-digiclaw.yml`
- `digigraph tests` → `test-digigraph.yml`
- `digikey tests` → `test-digikey.yml`
- `digiquant tests` → `test-digiquant.yml`
- `digisearch tests` → `test-digisearch.yml`
- `digitrace tests` → `test-digitrace.yml`

---

## Known Issues

| File | Issue | Action needed |
|------|-------|---------------|
| `agent-ci-failure-triage.yml` | Previously listed `PR quality gate` in `workflow_run.workflows` after that workflow was removed (silent no-op). | Resolved — stale entry dropped; trigger now lists only live workflows. |
| `agent-ci-failure-triage.yml` | Was producing a YAML parse error (multi-line `BODY=` string with unindented continuation lines). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `project-enforce-assignment.yml` | Was producing a YAML parse error (heredoc content with `⚠️` at column 0 inside `run: |`). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `security-gitleaks.yml` | Runs full history scan on every push to `develop` — this can fail if any historical commit contains a pattern matching the ruleset. False positives should be added to `.gitleaks.toml` allowlist. | Operational — not a workflow defect. |
| `DIGITHINGS_PROJECT_TOKEN` | Several workflows degrade gracefully when this token is absent, but project-board mutations (routing, status automation, enforce-project-assignment) will not work. | Ensure the token is configured as an org secret with `project` + `repo` scopes. Token rotation is a manual operation. |

---

## Lint all workflows (actionlint)

`ci.yml`'s `actionlint` job runs this on every PR touching `.github/workflows/**`
(the `workflows` filter in `scripts/ci_paths.yaml`). Reproduce it locally with:

```bash
brew install actionlint shellcheck
actionlint
```

Install `shellcheck` as well — actionlint runs it over every `run:` block and
just skips those checks when the binary is missing, so a shellcheck-less run
looks clean while covering far less. **Both versions are pinned** and `brew`
currently matches CI: actionlint `1.7.12` (the action's `version:` input) and
shellcheck `0.11.0` (a checksum-verified release tarball installed before the
action runs, so its `which shellcheck` probe skips the apt install).

Pinning shellcheck is not belt-and-braces. Left to apt, the runner image
supplied 0.9.x, which reports `SC2002` and `SC2015` — both relaxed by upstream
in 0.11.0. A contributor on brew saw a clean tree while CI went red, and a
future image bump could flip the verdict again under unchanged code. Same class
as #1701/#1705/#1711.

Suppressions live in `.github/actionlint.yaml`, auto-discovered by both the CI
job and a bare local run. Two things to know before editing it:

- **actionlint silently ignores config keys it does not recognise.** A typo'd
  key, or a `paths:` section on a build predating that feature, exits 0 having
  applied nothing. This is why the job pins `version: "1.7.12"` instead of
  tracking `latest` — an unpinned change could void every suppression, or add
  checks, under a previously green build. Bump it deliberately, in its own PR.
- Suppress by SC code, with a written reason. The one current entry
  (`SC2016`, for jq/GraphQL `$var` in single quotes) carries one.
- `SC2129` was suppressed when this file was added and is no longer. Every
  `run:` block that appended repeatedly to `$GITHUB_OUTPUT` was restructured
  into a single `{ ... } >> "$GITHUB_OUTPUT"` group, so the rule is enforced
  rather than waived. A new occurrence should be grouped, not re-suppressed —
  the `Assert SC2129 is live` step fails the build if the ignore is re-added,
  or if a shellcheck bump retires the check the way 0.11.0 retired SC2002.

`*.lock.yml` is ignored in `.github/actionlint.yaml` as a belt-and-suspenders
holdover after gh-aw retirement — no lock files ship in-tree today (#1182).

## Validate all workflow YAML

Weaker than the above — a parse check only. Kept for quick offline use:

```bash
python3 -c "
import yaml, glob
errors = []
for f in sorted(glob.glob('.github/workflows/*.yml')):
    try:
        yaml.safe_load(open(f))
    except Exception as e:
        errors.append(f'{f}: {e}')
if errors:
    for e in errors: print('FAIL:', e)
else:
    print('All YAML OK')
"
```
