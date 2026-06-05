# CI Conventions

Conventions and inventory for `.github/workflows/` in the DigiThings monorepo.

Tracked in issue [#292](https://github.com/digithings-ai/digithings/issues/292).

---

## Workflow Inventory

44 workflow files as of 2026-06-05.

| File | Name | Trigger | Purpose | Status | Path filter |
|------|------|---------|---------|--------|-------------|
| `agent-backlog-snapshot.yml` | Agent backlog snapshot | schedule (Mon 06:00), dispatch | Refresh `docs/agent-backlog/generated-snapshot.md` from open agent-task issues; opens auto-merge PR | Working | none |
| `agent-quota-reset.yml` | Agent quota reset | schedule (1st of month 09:00), dispatch | Clear `quota:*` labels on state issue #387; re-dispatch `pending:quota` tasks | Working | none |
| `apply-label-drift-fix.yml` | Apply label drift fix | dispatch | One-shot label patch for issue #505 drift. Can be deleted or reused for future sprints | Working | none |
| `atlas-baseline.yml` | atlas baseline | schedule (Sat 12:00), dispatch | Full 9-phase Atlas/Hermes baseline research run | Working | none |
| `atlas-delta.yml` | atlas delta | schedule (weekdays 12:00), dispatch | Weekday delta run (45 min ceiling) resolving latest baseline | Working | none |
| `atlas-graph-ci.yml` | atlas graph ci | push (main/develop), PR | Unit tests + lint for Atlas + Hermes trees; installs full workspace via `install-workspace.sh` | Working | `digiquant/src/digiquant/{atlas,hermes}/**`, `tests/dq/{atlas,hermes}/**`, `atlas-*.yml` |
| `atlas-monthly.yml` | atlas monthly | schedule (28-31 of month 14:00), dispatch | Monthly synthesis; guard job gates to last weekday of month | Working | none |
| `auto-stub-project-fields.yml` | Auto-stub project fields TSV | issues labeled | Appends inferred row to `scripts/project_fields.tsv` when `agent-task` or `phase-N` label applied | Working | none |
| `automerge-docs.yml` | Doc auto-merge | PR events | Enable squash auto-merge for PRs with `automerge-docs` label after doc-only path verification | Working | none |
| `ci-failure-triage.yml` | CI failure triage | workflow_run (completed) | Create `copilot` + `ci:failure` issue when a PR workflow fails; guarded by `DIGITHINGS_PROJECT_TOKEN` | Fixed (#292) | none |
| `ci.yml` | CI | push (main/develop), PR | Orchestrator: per-component tests + score + nautilus-smoke + atlas-graph + pip-audit + ruff + compose-validate | Working | none |
| `e2e.yml` | e2e stack tests | workflow_dispatch, push (develop) | Optional compose-up `pytest -m e2e`; `continue-on-error` (non-blocking) | Working | `tests/test_e2e.py`, compose |
| `nautilus-smoke.yml` | nautilus smoke | workflow_call, PR | Linux `digiquant[nautilus]` smoke subset | Working | `digiquant/**`, `tests/dq/**` |
| `olympus-test.yml` | olympus tests | workflow_call, push (main/develop), PR | Olympus lint + vitest + build | Working | `frontend/olympus/**`, design |
| `score-pr.yml` | score | workflow_call, PR | `make score` on PR diff (4 dimensions) | Working | none |
| `claude-code-dispatch.yml` | Claude Code dispatch | issues labeled | Acknowledge `exec:claude` label; post local-dispatch instructions (cloud dispatch disabled by policy) | Working | none |
| `claude-code-review.yml` | Claude Code review | PR (opened/sync/ready/reopened) | Auto PR review via Claude `/code-review`; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | paths-ignore: `**.md`, `docs/**`, issue templates |
| `claude.yml` | Claude Code | issue_comment, PR review comment, issues | Respond to `@claude` mentions from repo members | Working | none |
| `continuous-improvement.yml` | Continuous improvement digest | schedule (Sun 22:00), dispatch | Weekly Claude-synthesized digest of activity patterns; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `copilot-quota-gate.yml` | Copilot quota gate | issues assigned | Intercept `@Copilot` assignment when `quota:copilot-exhausted` is set; escalate or park | Working | none |
| `cursor-agent-dispatch.yml` | Cursor agent dispatch | issues labeled | Dispatch Cursor background agent on `exec:cursor`; pre-flight checks quota state issue #387 | Working | none |
| `digibase-test.yml` | digibase tests | workflow_call, push (main/develop), PR | digibase unit tests | Working | `digibase/**`, `tests/db/**` |
| `digichat-test.yml` | digichat tests | workflow_call, push (main/develop), PR | digichat (Next.js) lint + tests | Working | `frontend/digichat/**`, `frontend/design/**`, `package.json` |
| `digiclaw-test.yml` | digiclaw tests | workflow_call, push (main/develop), PR | digiclaw unit tests | Working | `digiclaw/**`, `tests/dc/**` |
| `digigraph-test.yml` | digigraph tests | workflow_call, push (main/develop), PR | digigraph unit tests | Working | `digigraph/**`, `tests/dg/**` |
| `digikey-test.yml` | digikey tests | workflow_call, push (main/develop), PR | digikey unit tests | Working | `digikey/**`, `tests/dk/**` |
| `digiquant-prices.yml` | DigiQuant prices pipeline | schedule (intraday: */15 13-20 weekdays; EOD: 21:00 weekdays), dispatch | Price + technicals ingest; guarded by `SUPABASE_URL` | Working | none |
| `digiquant-test.yml` | digiquant tests | workflow_call, push (main/develop), PR | digiquant unit tests | Working | `digiquant/**`, `tests/dq/**` |
| `digisearch-test.yml` | digisearch tests | workflow_call, push (main/develop), PR | digisearch unit tests | Working | `digisearch/**`, `tests/ds/**` |
| `digismith-test.yml` | digismith tests | workflow_call, push (main/develop), PR | digismith unit tests | Working | `digismith/**`, `tests/dsm/**` |
| `docs.yml` | Docs | push (main/develop), PR | Internal markdown link check + agents-init drift check | Working | none |
| `enforce-project-assignment.yml` | Enforce project board assignment | schedule (daily 09:00), dispatch | Comment on issues not assigned to any project board; guarded by `DIGITHINGS_PROJECT_TOKEN` | Fixed (#292) | none |
| `gitleaks.yml` | gitleaks | push (main/develop), PR | Secrets scan — PR diff or full history; pinned OSS CLI (not the paid action) | Working | none |
| `pip-audit.yml` | pip-audit | workflow_call, PR, push (main/develop), schedule (Mon 06:00) | CVE audit per Python component; blocks on HIGH/CRITICAL | Working | none |
| `pr-linkage.yml` | PR issue linkage | PR events | Require `Fixes #N` in body or `task/N-*` branch; bypass for `module/*` umbrella PRs | Working | none |
| `project-fields-coverage.yml` | Project fields coverage | PR, schedule (daily 06:00), dispatch | Fail if any `agent-task` issue is missing from `project_fields.tsv` or has invalid values | Working | `scripts/project_fields.tsv`, this workflow |
| `project-status-automation.yml` | Project status automation | issues, PR, push (task/cursor/claude branches) | Move issues through project board pipeline (Todo → In Progress → Review → Done) | Working | none |
| `provider-review.yml` | Provider review | schedule (Sun 00:00), dispatch | Weekly LLM provider probe + Claude agent analysis; guarded by `CLAUDE_CODE_OAUTH_TOKEN` | Working | none |
| `reindex-digithings-guide.yml` | Reindex DigiThings-guide | push (develop) | Re-index docs into DigiSearch; dry-run always; apply step requires `DIGISEARCH_URL` | Working | many doc paths |
| `route-issues-to-projects.yml` | Route issues to projects | issues (opened/reopened/transferred/labeled) | Route issues to module project boards based on `component:*` label; requires `DIGITHINGS_PROJECT_TOKEN` | Working | none |
| `scheduled-maintenance.yml` | Scheduled maintenance | schedule (Mon 08:00), dispatch | Weekly sweep: CVE audit, stale branches, broken doc links, agents-init drift, stale issues/PRs, label coverage, workflow health | Working | none |
| `static.yml` | Deploy static content to Pages (retired) | dispatch only (RETIRED guard) | Legacy GitHub Pages deploy — now replaced by Cloudflare Pages | Retired (kept for history) | none |
| `type-check.yml` | Type Check (digibase + digikey) | push (main/develop), PR | mypy type checking for digibase + digikey | Working | `digibase/**`, `digikey/**`, `mypy.ini` |

---

## Secrets and Variables Reference

| Secret / Variable | Used by | Required or optional |
|-------------------|---------|---------------------|
| `DIGITHINGS_PROJECT_TOKEN` | project-status-automation, enforce-project-assignment, ci-failure-triage, route-issues-to-projects, scheduled-maintenance, agent-quota-reset, cursor-agent-dispatch, copilot-quota-gate, continuous-improvement, auto-stub-project-fields, apply-label-drift-fix | Required for project-board mutations; workflows degrade gracefully when absent |
| `CLAUDE_CODE_OAUTH_TOKEN` | claude.yml, claude-code-review.yml, claude-code-dispatch.yml, continuous-improvement.yml, provider-review.yml | Optional — features disabled when absent |
| `CURSOR_API_KEY` | cursor-agent-dispatch.yml | Optional — dispatch skipped when absent |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | atlas-baseline, atlas-delta, atlas-monthly, digiquant-prices | Required for production runs |
| `GEMINI_API_KEY` | atlas-baseline, atlas-delta, atlas-monthly | Required for Atlas/Hermes LLM calls |
| `OLLAMA_API_KEY` | atlas-baseline, atlas-delta, atlas-monthly | Required for reasoning tier (phases 7, 7D) |
| `DIGISEARCH_URL` | reindex-digithings-guide | Optional — apply step skipped when absent |
| `vars.DIGI_MAINTENANCE_PROJECT_NUMBER` | scheduled-maintenance, ci-failure-triage, enforce-project-assignment | Optional — project-add step skipped when absent |

---

## Conventions

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

This pattern is used throughout the Atlas/Hermes workflows (`atlas-baseline.yml`, `atlas-delta.yml`, `atlas-monthly.yml`) and is now required for all new issue/comment creation steps.

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

Per-component test workflows (`digibase-test.yml`, etc.) use `workflow_call` so `ci.yml` can invoke them unconditionally, while the direct push/PR triggers are path-filtered. This is the correct pattern.

### 7. Concurrency

Use `concurrency:` to cancel stale runs on rapid pushes:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

For production pipelines where mid-run cancellation would corrupt state (Atlas baseline, monthly synthesis), set `cancel-in-progress: false` and use a named group without `${{ github.ref }}`.

### 8. workflow_run triggers and workflow names

`ci-failure-triage.yml` uses `workflow_run` and lists workflow names explicitly. If a watched workflow is renamed, update this list to match. The names in `workflows:` must exactly match the `name:` field of the target workflow.

Current watched workflows in `ci-failure-triage.yml`:
- `Docs` → `docs.yml`
- `CI` → `ci.yml`
- `PR quality gate` → (no matching file; legacy name — see Known Issues)
- `digibase tests` → `digibase-test.yml`
- `digichat tests` → `digichat-test.yml`
- `digiclaw tests` → `digiclaw-test.yml`
- `digigraph tests` → `digigraph-test.yml`
- `digikey tests` → `digikey-test.yml`
- `digiquant tests` → `digiquant-test.yml`
- `digisearch tests` → `digisearch-test.yml`
- `digismith tests` → `digismith-test.yml`

---

## Known Issues

| File | Issue | Action needed |
|------|-------|---------------|
| `ci-failure-triage.yml` | Lists `PR quality gate` in `workflow_run.workflows` but no workflow with that name exists in the repo. The trigger silently does nothing for that entry. | Remove `PR quality gate` from the list when the name is confirmed obsolete, or rename the appropriate workflow to match. |
| `ci-failure-triage.yml` | Was producing a YAML parse error (multi-line `BODY=` string with unindented continuation lines). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `enforce-project-assignment.yml` | Was producing a YAML parse error (heredoc content with `⚠️` at column 0 inside `run: |`). Fixed in #292 using `printf` + `--body-file`. | Resolved. |
| `gitleaks.yml` | Runs full history scan on every push to `develop` — this can fail if any historical commit contains a pattern matching the ruleset. False positives should be added to `.gitleaks.toml` allowlist. | Operational — not a workflow defect. |
| `static.yml` | Retired workflow kept for historical reference. Cloudflare Pages now handles deployment. | Can be deleted in a future cleanup sprint. The `workflow_dispatch` guard with a `RETIRED` confirmation input prevents accidental runs. |
| `apply-label-drift-fix.yml` | One-shot workflow for issue #505. Has served its purpose. | Can be deleted in a future cleanup sprint. |
| `DIGITHINGS_PROJECT_TOKEN` | Several workflows degrade gracefully when this token is absent, but project-board mutations (routing, status automation, enforce-project-assignment) will not work. | Ensure the token is configured as an org secret with `project` + `repo` scopes. Token rotation is a manual operation. |
| `copilot-pr-review.yml` | Referenced in issue #292 as broken, but this file does not exist. The workflow was replaced by `claude-code-review.yml` (which uses Claude's `/code-review` plugin instead of GitHub Copilot). | No action needed — the replacement is in place. |

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
