# Workflow audit — findings and follow-up plan

Snapshot taken during project-management reorg session.

## Current state (27 workflows)

**CI orchestration + tests (10):**
- `ci.yml` — master orchestrator, calls the 8 module test workflows via `workflow_call`, plus `pip-audit`, `ruff-and-scripts`, `compose-validate`.
- `digibase-test.yml`, `digichat-test.yml`, `digiclaw-test.yml`, `digigraph-test.yml`, `digikey-test.yml`, `digiquant-test.yml`, `digisearch-test.yml`, `digismith-test.yml` — per-module tests. Triggers: `workflow_call` + path-filtered `push/pull_request` (intentional dual-trigger; path filters keep it efficient).
- `type-check.yml` — mypy for digibase + digikey.

**Security (2):**
- `gitleaks.yml`, `pip-audit.yml`.

**Docs + deploys (3):**
- `docs.yml` — doc-links + agents-init-idempotent.
- `static.yml` — Pages deploy for digithings.ai.
- `reindex-digithings-guide.yml` — DigiSearch index rebuild for docs.

**Scheduled jobs (3):**
- `digiquant-prices.yml` — DigiQuant prices pipeline (scheduled intraday + EOD).
- `scheduled-maintenance.yml` — stale branches, doc-links, agents-drift, dep-audit (daily).
- `agent-backlog-snapshot.yml` — scheduled backlog export.

**Agent / project hygiene (7):**
- `route-issues-to-projects.yml` — **new this session**, consolidates old `issue-to-project` + `issue-to-digiquant-project`.
- `auto-stub-project-fields.yml` — creates `bot/stub-tsv-*` PRs to append rows to `scripts/project_fields.tsv` when issues get labels.
- `project-fields-coverage.yml` — PR check enforcing project_fields.tsv coverage.
- `enforce-project-assignment.yml` — daily orphan-check: issues not on any board get a warning comment.
- `pr-linkage.yml` — PR body must reference an issue.
- `pr-quality-gate.yml` — task/* branch PRs must have `/simplify` and `/review` checkboxes ticked.
- `copilot-pr-review.yml` — assists Copilot PR review comments.
- `ci-failure-triage.yml` — creates a Copilot issue when a workflow run fails.
- `automerge-docs.yml` — auto-merge for docs-only PRs.

## Changes made this session

- ✅ Consolidated `issue-to-project.yml` + `issue-to-digiquant-project.yml` → `route-issues-to-projects.yml`. Per-module routing for all 8 modules (previously only digiquant had its own route). Net: -1 workflow.
- ✅ No other workflows deleted — everything else is intentional and active.

## Follow-up work (to be filed as a maintenance epic)

### 1. TSV-based project-field stubbing vs direct-board writes
`auto-stub-project-fields.yml` stubs rows in `scripts/project_fields.tsv` via a PR. `project-fields-coverage.yml` then validates coverage. This is a legacy approach: it exists because the original workflow didn't have direct API access to set project fields.

This session introduced `docs/plans/backlog-reshape/project-backfill.py` and `project-reorg.py` which write directly to project boards without the TSV round-trip.

**Decision needed:**
- **Option A** — retire TSV: delete `auto-stub-project-fields.yml` + `project-fields-coverage.yml`, wire `project-reorg.py` into a scheduled workflow.
- **Option B** — keep TSV: TSV is source of truth, scheduled workflow syncs it to the board.
- **Option C** — hybrid: TSV for initial stub review (human-in-the-loop), board as runtime truth.

Recommend A — direct board writes are simpler, TSV is intermediate state nobody actually reads.

### 2. Rename for clarity
- `static.yml` → `deploy-digithings-pages.yml` (ambiguous name; will get more confusing once digiquant.io deploy workflow lands via #301).
- `ci.yml` → `tests.yml` (it's the test orchestrator, not full CI).
- `type-check.yml` → `mypy.yml` (or expand to all modules rather than digibase+digikey only).
- `docs.yml` → `doc-checks.yml`.

Each rename touches any references — at minimum `CLAUDE.md`, `AGENTS.md`, docs that mention the workflow name.

### 3. Audit per-module test trigger efficiency
`ci.yml` invokes every module test unconditionally; module workflows also fire directly on path-filtered push/PR. Cross-check whether PR runs ever execute the same module twice (once via ci.yml, once via direct path-filter). If so, pick one trigger path and standardize.

### 4. Ensure every merge to `develop` runs the required suite
Verify the branch protection rules on `develop` actually require the right status checks (tests, type-check, gitleaks, pip-audit, docs). Not visible from workflow files alone — check `gh api repos/.../branches/develop/protection`.

### 5. Decide on experimental workflows
- `copilot-pr-review.yml` — how much value is this adding vs the internal `.claude/agents/pr-reviewer`?
- `ci-failure-triage.yml` — working? Or generating noise?

Either promote to maintained or retire.

## Not changed this session

None of these 27 workflows read as "temporary" — all were built with intent and are active. User's expectation of dead workflows to sweep up did not materialize. The real cleanup opportunities are structural (consolidation, naming, trigger efficiency) rather than deletion-based.

## To file as a GitHub issue when graphql quota returns

**Title:** `[Epic] Workflow audit — consolidation, naming, trigger efficiency, TSV retirement`
**Labels:** `epic, component:root, priority:medium, type:infra`
**Project:** #11 maintenance
**Body:** this file's "Follow-up work" section.
