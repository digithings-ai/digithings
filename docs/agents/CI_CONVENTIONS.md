# CI Conventions

Conventions and inventory for `.github/workflows/` in the DigiThings monorepo.

Tracked in issue [#292](https://github.com/digithings-ai/digithings/issues/292).

Queue starvation and org runner limits: [CI-QUEUE.md](CI-QUEUE.md).

---

## Workflow Inventory

59 workflow `.yml` files as of 2026-07-09 (plus 2 gh-aw `.md` sources that compile to `.lock.yml`). Every file has a row in the inventory below.

| File | Name | Trigger | Purpose | Status | Path filter |
|------|------|---------|---------|--------|-------------|
| `agent-backlog-snapshot.yml` | Agent: backlog snapshot | schedule (Mon 06:00), dispatch | Refresh `docs/agent-backlog/generated-snapshot.md` from open agent-task issues; opens auto-merge PR | Working | none |
| `agent-quota-reset.yml` | Agent: quota reset | schedule (1st of month 09:00), dispatch | Clear `quota:*` labels on state issue #387; re-dispatch `pending:quota` tasks | Working | none |
| `pipeline-olympus.yml` | Pipeline: Olympus research | schedule (MON-SAT 12:00 + 28-31 of month 14:00), dispatch | Unified Atlas+Hermes pipeline; `resolve` job picks baseline (Sat) / delta (weekday) / monthly (last weekday), integrates fed-odds ingest | Working | none |
| `test-atlas-graph.yml` | Test: Atlas graph | workflow_call | Unit tests + lint for Atlas + Hermes trees; installs full workspace via `install-workspace.sh` | Working | `digiquant/src/digiquant/{atlas,hermes}/**`, `tests/dq/{atlas,hermes}/**`, `pipeline-olympus.yml` |
| `project-stub-fields.yml` | Project: stub fields TSV | issues labeled | Appends inferred row to `scripts/project_fields.tsv` when `agent-task` or `phase-N` label applied | Working | none |
| `agent-docs-automerge.yml` | Agent: doc auto-merge | PR events | Enable squash auto-merge for PRs with `automerge-docs` label after doc-only path verification | Working | none |
| `agent-ci-failure-triage.yml` | Agent: CI failure triage | workflow_run (completed) | Create `copilot` + `ci:failure` issue when a PR workflow fails; guarded by `DIGITHINGS_PROJECT_TOKEN` | Fixed (#292) | none |
| `ci.yml` | CI | push (main/develop), PR | Orchestrator: per-component tests + score + e2e-contract + nautilus-smoke + atlas-graph + pip-audit + ruff/scripts/baseline/provider_review + compose-validate | Working | none |
| `test-e2e.yml` | Test: e2e stack | workflow_call, workflow_dispatch, push (develop) | PR gate: `e2e-contract` via `ci.yml`; compose `pytest -m e2e` on develop push/dispatch only (`continue-on-error`) | Working | `tests/test_e2e*.py`, compose |
| `test-nautilus.yml` | Test: Nautilus smoke | workflow_call | Linux `digiquant[nautilus]` smoke subset | Working | `digiquant/**`, `tests/dq/**` |
| `test-olympus.yml` | Test: olympus | workflow_call | Olympus lint + vitest + build | Working | `frontend/olympus/**`, design |
| `test-web.yml` | Test: web apps | workflow_call | Lint `digithings-web` + `digiquant-web` (root workspaces) + frontend canon guard (`check_frontend_canon.py`) | Working | `frontend/{digithings-web,digiquant-web,digiweb/web,digiweb/design}/**`, `package.json`/lock |
| `test-score.yml` | Test: score PR diff | workflow_call | `make score` on PR diff (4 dimensions) | Working | none |
| `agent-claude-dispatch.yml` | Agent: Claude dispatch | issues labeled | Acknowledge `exec:claude` label; post local-dispatch instructions (cloud dispatch disabled by policy) | Working | none |
| `agent-claude-review.yml` | Agent: Claude review | PR (opened/sync/ready/reopened) | Auto PR review via Claude `/code-review`; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | paths-ignore: `**.md`, `docs/**`, issue templates |
| `agent-claude.yml` | Agent: Claude Code | issue_comment, PR review comment, issues | Respond to `@claude` mentions from repo members | Working | none |
| `pipeline-continuous-improvement.yml` | Pipeline: continuous improvement | schedule (Sun 22:00), dispatch | Weekly Claude-synthesized digest of activity patterns; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `copilot-quota-gate.yml` | Copilot: quota gate | issues assigned | Intercept `@Copilot` assignment when `quota:copilot-exhausted` is set; escalate or park | Working | none |
| `copilot-issue-dispatch.lock.yml` | Copilot: issue dispatch | issues labeled/opened | Assign `@Copilot` via `assign-to-agent` safe output when quota allows | Working | none |
| `copilot-pr-lifecycle.lock.yml` | Copilot: PR lifecycle | schedule (10 min), dispatch | End-to-end `copilot/*` loop: issue link, mark-ready, CI, review, fix rounds, automerge | Working | none |
| `copilot-pr-mark-ready.yml` | Copilot: PR mark ready | workflow_dispatch (dispatched by lifecycle) | Marks a draft `copilot/*` PR ready for review | Working | none |
| `test-digibase.yml` | Test: digibase | workflow_call | digibase unit tests | Working | `digibase/**`, `tests/db/**` |
| `test-digichat.yml` | Test: digichat | workflow_call | digichat (Next.js) lint + tests | Working | `frontend/digichat/**`, `frontend/digiweb/design/**`, `package.json` |
| `release-please-digichat.yml` | Release please: digichat | push (`module/digichat`) | Track digichat version + changelog from Conventional Commits on `module/digichat` (decoupled from image publish, #1343) | Working | `frontend/digichat/**`, release-please config/manifest |
| `publish-digichat-image.yml` | Publish: digichat image | push (`main`), dispatch | Build + push digichat image to GHCR once a version reaches `main`; skips if that version tag already exists (#1343) | Working | `frontend/digichat/**` |
| `test-digiclaw.yml` | Test: digiclaw | workflow_call | digiclaw unit tests | Working | `digiclaw/**`, `tests/dc/**` |
| `test-digigraph.yml` | Test: digigraph | workflow_call | digigraph unit tests | Working | `digigraph/**`, `tests/dg/**` |
| `test-digikey.yml` | Test: digikey | workflow_call | digikey unit tests | Working | `digikey/**`, `tests/dk/**` |
| `pipeline-digiquant-prices.yml` | Pipeline: DigiQuant prices | schedule (intraday: */15 13-20 weekdays; EOD: 21:00 weekdays), dispatch | Price + technicals ingest; guarded by `SUPABASE_URL` | Working | none |
| `pipeline-digiquant-tearsheets.yml` | Pipeline: DigiQuant tearsheets | schedule (daily 00:00 UTC), dispatch | Daily Slapper tearsheet regen for digiquant.io: backtest with Supabase calibrations, commit `frontend/digiquant-web/public/strategies/*.json`, upsert `strategy_tearsheets` (#1068) | Working | none |
| `test-digiquant.yml` | Test: digiquant | workflow_call | digiquant unit tests | Working | `digiquant/**`, `tests/dq/**` |
| `test-digisearch.yml` | Test: digisearch | workflow_call | digisearch unit tests | Working | `digisearch/**`, `tests/ds/**` |
| `test-digismith.yml` | Test: digismith | workflow_call | digismith unit tests | Working | `digismith/**`, `tests/dsm/**` |
| `ci-docs.yml` | CI: docs | push (main/develop), PR | Internal markdown link check + agents-init drift check (single job) | Working | markdown, agents surface |
| `project-enforce-assignment.yml` | Project: enforce assignment | schedule (daily 09:00), dispatch | Comment on issues not assigned to any project board; guarded by `DIGITHINGS_PROJECT_TOKEN` | Fixed (#292) | none |
| `security-gitleaks.yml` | Security: gitleaks | push (main/develop), PR | Secrets scan — PR diff or full history; pinned OSS CLI (not the paid action) | Working | PR: paths-ignore `**.md`, `docs/**` |
| `security-pip-audit.yml` | Security: pip-audit | workflow_call, PR, push (main/develop), schedule (Mon 06:00) | CVE audit per Python component; blocks on HIGH/CRITICAL | Working | none |
| `ci-pr-hygiene.yml` | CI: PR hygiene | PR, schedule (daily 06:00), dispatch | Issue linkage (`Require Fixes`) + path-gated `project_fields.tsv` coverage | Working | TSV job: `project_fields.tsv` + this workflow |
| `project-status.yml` | Project: status automation | issues, PR closed (merge), push (task/cursor/claude branches) | Move issues through project board pipeline (Todo → In Progress → Done) | Working | PR: merge/close only |
| `pipeline-provider-review.yml` | Pipeline: provider review | schedule (Sun 00:00), dispatch | `pytest tests/provider_review/ -m unit` then weekly probe + Claude agent; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `docs-reindex-guide.yml` | Docs: reindex guide | push (develop) | Re-index docs into DigiSearch; dry-run always; apply step requires `DIGISEARCH_URL` | Working | many doc paths |
| `sync-architecture-vault.yml` | sync-architecture-vault | push (`main`), dispatch | Mirror DigiVault-managed `docs/vision/**` → Supabase `public.architecture_notes` for the digithings.ai docs chat; `production` env (human gate); needs migration 048 | Working | `docs/vision/**`, sync script |
| `project-route-issues.yml` | Project: route issues | issues (opened/reopened/transferred/labeled) | Route issues to module project boards based on `component:*` label; requires `DIGITHINGS_PROJECT_TOKEN` | Working | none |
| `pipeline-maintenance.yml` | Pipeline: scheduled maintenance | schedule (Mon 08:00), dispatch | Weekly sweep: CVE audit, stale branches, broken doc links, agents-init drift, stale issues/PRs, label coverage, workflow health | Working | none |
| `smoke-stack.yml` | Smoke: stack | schedule (daily 07:00 UTC), dispatch | `docker compose up --wait` + `/healthz` on digikey/digigraph/digiquant/digisearch/digismith | Working | none |
| `ci-type-check.yml` | CI: type check | push (main/develop), PR | mypy type checking for digibase + digikey | Working | `digibase/**`, `digikey/**`, `mypy.ini` |
| `test-digivault.yml` | Test: digivault | workflow_call | digivault unit tests | Working | `digivault/**`, `tests/dv/**` |
| `smoke-site.yml` | Smoke: site | schedule (daily 06:17), dispatch | Post-deploy probe of digithings.ai + digiquant.io: homepages, prerendered `/modules/digigraph/`, stable `/design/assets/og.png` canary (SPA-fallback MIME masking, #671) | Working | none |
| `smoke-langsmith.yml` | Smoke: LangSmith | dispatch only | Readiness check (#687): `LANGSMITH_API_KEY` auth + `@traceable` nesting before enabling tracing on atlas workflows | Working | none |
| `pipeline-atlas-metrics.yml` | Pipeline: Atlas metrics refresh | schedule (daily, post-EOD), dispatch | Deterministic Polars/SQL recompute of `portfolio_metrics` + `position_attribution` the Olympus dashboard reads; zero LLM cost; runs after EOD price ingest | Working | none |
| `pipeline-digiquant-backfill.yml` | Pipeline: DigiQuant backfill | dispatch only | One-shot full-history (≤40y) price + technicals + macro backfill into Supabase `price_history` | Working (on-demand) | none |
| `db-migrate.yml` | db-migrate | push (`main`), dispatch | Apply pending Olympus Supabase migrations to prod; baseline-aware, forward-only, one transaction per file; `production` env (human gate) (#1016) | Working | `digiquant/supabase/migrations/**` |
| `deploy-digithings-cloudflare.yml` | Deploy: digithings.ai build check | PR (digithings.ai assets), dispatch | Gate/validate `scripts/build-digithings.sh`; primary deploy is Cloudflare Pages watching `main` | Working | digithings.ai assets |
| `deploy-digiquant-cloudflare.yml` | Deploy: digiquant.io build check | PR (digiquant.io assets), dispatch | Gate/validate `scripts/build-digiquant.sh` (ADR-0012); primary deploy is Cloudflare Pages watching `main` | Working | digiquant.io assets |
| `agent-pr-autolabel.yml` | Agent: PR autolabel | workflow_run (CI, Copilot targeted CI) | Add `automerge-agent` to low-risk agent-branch PRs once CI is green | Working | none |
| `agent-pr-automerge.yml` | Agent: PR auto-merge | pull_request, workflow_run (CI, Copilot targeted CI) | Enable squash auto-merge for PRs labeled `automerge-agent` | Working | none |
| `agent-pr-finalizer.yml` | Agent: PR finalizer | schedule (daily 07:00), dispatch | Daily backstop for `cursor/*` PRs that missed the Cursor Automation merge path (copilot/* handled by gh-aw lifecycle) | Working | none |
| `agent-dispatch-replay.yml` | Agent: dispatch replay | dispatch only | Re-fire `exec:*` dispatch for issues labeled at creation time (GitHub skips `issues:labeled` for `gh issue create` labels) | Working (on-demand) | none |
| `copilot-pr-targeted-ci.yml` | Copilot: targeted CI | dispatch only (by lifecycle) | Trusted-actor CI for `copilot/*` PRs; bypasses the bot `pull_request` action_required gate | Working | none |

---

## Secrets and Variables Reference

| Secret / Variable | Used by | Required or optional |
|-------------------|---------|---------------------|
| `DIGITHINGS_PROJECT_TOKEN` | project-status-automation, enforce-project-assignment, ci-failure-triage, route-issues-to-projects, scheduled-maintenance, agent-quota-reset, copilot-quota-gate, continuous-improvement, auto-stub-project-fields, agent-pr-finalizer | Required for project-board mutations; workflows degrade gracefully when absent |
| `CLAUDE_CODE_OAUTH_TOKEN` | agent-claude.yml, agent-claude-review.yml, agent-claude-dispatch.yml, pipeline-continuous-improvement.yml, pipeline-provider-review.yml | Optional — features disabled when absent |
| `CURSOR_API_KEY` | agent-pr-finalizer.yml | Optional — Cursor fix dispatch skipped when absent |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | atlas-baseline, atlas-delta, atlas-monthly, digiquant-prices | Required for production runs |
| `GEMINI_API_KEY` | atlas-baseline, atlas-delta, atlas-monthly | Required for Atlas/Hermes LLM calls |
| `OLLAMA_API_KEY` | atlas-baseline, atlas-delta, atlas-monthly | Required for reasoning tier (phases 7, 7D) |
| `DIGISEARCH_URL` | reindex-digithings-guide | Optional — apply step skipped when absent |
| `vars.DIGI_MAINTENANCE_PROJECT_NUMBER` | scheduled-maintenance, ci-failure-triage, enforce-project-assignment | Optional — project-add step skipped when absent |

---

## Conventions

### 0. GitHub Agentic Workflows (gh-aw)

Agentic workflow sources live as `.md` files in `.github/workflows/`. The compiled outputs are `.lock.yml` files generated by the `gh aw` extension. **Never hand-edit the `.lock.yml` files.**

**Compile locally:**
```bash
gh extension install github/gh-aw   # one-time
gh aw compile                        # compile all .md workflows
```

**CI drift check:** `ci-docs.yml` runs `gh aw compile --trial` on any PR that touches `*.md` files in `.github/workflows/`. A compilation error or diff in a `.lock.yml` fails the CI job with instructions to re-run `gh aw compile` locally and push the updated lock files.

Extension version in use: `v0.77.5` (pinned in `docs/agents/CI_CONVENTIONS.md`).

To upgrade: `gh extension upgrade github/gh-aw` then re-compile all workflows and verify the lock file diff is intentional.

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
| `raven-actions/actionlint` | `@v2` |
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

This pattern is used by the Olympus pipeline workflow (`pipeline-olympus.yml`) and is now required for all new issue/comment creation steps.

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

### 7. Concurrency

Use `concurrency:` to cancel stale runs on rapid pushes:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

For production pipelines where mid-run cancellation would corrupt state (Atlas baseline, monthly synthesis), set `cancel-in-progress: false` and use a named group without `${{ github.ref }}`.

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
- `digismith tests` → `test-digismith.yml`

---

## Known Issues

| File | Issue | Action needed |
|------|-------|---------------|
| `agent-ci-failure-triage.yml` | Previously listed `PR quality gate` in `workflow_run.workflows` after that workflow was removed (silent no-op). | Resolved — stale entry dropped; trigger now lists only live workflows. |
| `agent-ci-failure-triage.yml` | Was producing a YAML parse error (multi-line `BODY=` string with unindented continuation lines). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `project-enforce-assignment.yml` | Was producing a YAML parse error (heredoc content with `⚠️` at column 0 inside `run: |`). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `security-gitleaks.yml` | Runs full history scan on every push to `develop` — this can fail if any historical commit contains a pattern matching the ruleset. False positives should be added to `.gitleaks.toml` allowlist. | Operational — not a workflow defect. |
| `DIGITHINGS_PROJECT_TOKEN` | Several workflows degrade gracefully when this token is absent, but project-board mutations (routing, status automation, enforce-project-assignment) will not work. | Ensure the token is configured as an org secret with `project` + `repo` scopes. Token rotation is a manual operation. |
| `copilot-pr-review.yml` | Removed (REM-098). **PR review:** `ci.yml` → `request-copilot-review` only (idempotent `gh pr edit --add-reviewer Copilot`). **Issue dispatch:** `copilot-issue-dispatch.lock.yml` (gh-aw) + `copilot-quota-gate.yml`. **Cursor dispatch:** Cursor Automation (cloud). **Secondary review:** `agent-claude-review.yml` when `ENABLE_CLAUDE_PR_REVIEW=true`. | Do not add a second Copilot PR-review workflow. |

---

## Validate all workflow YAML

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
