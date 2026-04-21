# Autonomous Agent Development Workflow

This document is the end-to-end protocol for agents (Cursor, Claude Code, Cline, or any AI coding assistant) developing features, fixing bugs, or making improvements in the DigiThings monorepo with minimal human intervention.

---

## 1. Picking a Task

1. Open `docs/agent-backlog/INDEX.md` — find a theme with status `todo` or `in_progress`.
2. If a GitHub Issue is linked, read it for context and acceptance criteria.
3. Confirm the task does not touch a **human-gate trigger** (see Section 7). If it does, escalate before starting.
4. Set the INDEX.md status to `in_progress` (or comment on the GitHub Issue).

---

## 2. Required Reading Order

Before writing a single line of code, read these documents in order:

1. `AGENTS.md` (root) — non-negotiable technical rules
2. `ROADMAP.md` — what phase we are in; do not implement Phase 3 work in a Phase 2 PR
3. `{component}/ARCHITECTURE.md` — the component you are modifying; covers module map, API, data models, config, extension guide, anti-patterns
4. `{component}/AGENTS.md` — component-specific rules, pre-flight checklist, test commands
5. `docs/agent-backlog/INDEX.md` — current backlog state; check for blocked dependencies
6. Root `ARCHITECTURE.md` — only if your change touches inter-service flows or auth

Do not skip steps. If a document is missing or stale, update it as part of your PR.

---

## 3. Explore → Plan → Execute Loop

### Explore

- Use Glob/Grep to find the relevant source files. Never assume a file exists — verify it.
- Read the existing implementation before proposing changes.
- Check test files to understand expected behavior.
- Look for existing patterns to reuse: error handling, audit logging, Pydantic models.

### Plan

For non-trivial changes (> 3 files or > 50 lines changed):

1. Write a short plan (3–10 bullet points) describing what you will change and why.
2. Identify which files will be created, modified, and deleted.
3. Confirm the plan matches `{component}/ARCHITECTURE.md`. If it doesn't, update ARCHITECTURE.md first.
4. If the approach is genuinely novel (new pattern not in any doc), escalate to human before proceeding.

### Execute

1. Make changes in small, verifiable increments.
2. Run component tests after each logical chunk (see Section 4).
3. Update `{component}/ARCHITECTURE.md` before marking the task complete — the doc must reflect the code.
4. Never commit half-finished work; if blocked, leave a clear `# TODO:` comment and describe the blocker in the PR.

---

## 4. Test Commands by Component

Run tests **before and after** your change. Both must pass.

| Component | Unit Test Command | E2E Test Command (requires stack) |
|-----------|------------------|----------------------------------|
| digigraph | `pytest tests/ -m unit -k "digigraph" -v` | `pytest tests/ -m e2e -k "digigraph"` |
| digiquant | `pytest tests/ -m unit -k "digiquant" -v` | `pytest tests/ -m e2e -k "digiquant"` |
| digisearch | `pytest tests/ -m unit -k "digisearch" -v` | `pytest tests/ -m e2e -k "digisearch"` |
| digismith | `pytest tests/ -m unit -k "digismith" -v` | — |
| digiclaw | `pytest tests/ -m unit -k "digiclaw" -v` | — |
| digibase | `pytest tests/ -m unit -k "digibase" -v` | — |
| digikey | `pytest tests/ -m unit -k "digikey" -v` | — |
| digichat | `cd digichat && npm run test` | — |
| All | `make test-unit` | `make test-e2e` |

Also run lint: `ruff check . && ruff format --check .`

---

## 5. Parallel Execution (/batch)

### When to batch

Use `/batch` when you have **3 or more independent tasks** that touch different files. Independent means:
- Different phase/area combinations, OR
- Same phase/area but no shared files between tasks

Run `make batch-candidates` to see current open issues grouped by phase+area, annotated with recommended model (sonnet/opus).

### Rules for safe batching

1. **Every worker uses `isolation: "worktree"`** — agents work on isolated git copies; no shared state.
2. **Units must be independently mergeable** — a unit cannot depend on another unit's PR landing first.
3. **Model selection**: use the issue's `model` field. `sonnet` for standard tasks; `opus` for complex/high-risk tasks (risk:high label).
4. **No more than 10 workers at once** — GitHub rate limits and context windows have ceilings.
5. **After all workers report**, run `/simplify` on the combined diff, then `/review` each PR before merging.

### Post-batch flow

```
/batch → N parallel agents → each opens PR
    → coordinator runs /review on each PR
    → fix any findings in the worktree
    → merge in dependency order (deepest first)
    → clean up worktrees
```

### Worker prompt template

Every worker prompt must include:
- The overall goal + this unit's specific task
- Files to touch (no more than the unit's scope)
- The e2e test recipe
- Instruction to run /simplify, tests, score, then open PR with Fixes #N
- End with: `PR: <url>`

---

## 6. Self-Scoring

Before opening a PR, score the change honestly using the four rubrics in `docs/scoring/`:

| Rubric | File | Target | Minimum |
|--------|------|--------|---------|
| Security | `docs/scoring/SECURITY.md` | 8/10 | 7/10 |
| Quality | `docs/scoring/QUALITY.md` | 8/10 | 7/10 |
| Optimization | `docs/scoring/OPTIMIZATION.md` | 7/10 | 6/10 |
| Accuracy | `docs/scoring/ACCURACY.md` | 9/10 | 8/10 |

**If any score is below the minimum:** fix the issues before opening the PR. Do not open a PR with known violations and hope for the best.

**If a criterion doesn't apply:** score it as 1 and note "N/A — [reason]" in the PR body.

---

## 6. Pre-PR Checklist (task/* branches)

Before pushing and opening a PR, run these steps in order:

1. **`make test-unit`** — all unit tests pass
2. **`make score`** — Security ≥ 8, Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9
3. **`/simplify`** — 3-agent code review pass; fix any findings
4. **`/review`** — PR review against scoring rubric; address findings
5. **Check both boxes** in the PR body — CI will block merge if unchecked

CI enforces steps 4–5 via `.github/workflows/pr-quality-gate.yml`.

---

## 7. Opening the PR

1. Use the PR template (`.github/PULL_REQUEST_TEMPLATE.md`) — fill every section.
2. Include the test output (`make test-unit` output) in the Testing Evidence section.
3. Check all criteria you passed; leave unchecked any you didn't.
4. Set the Human Gate flag honestly.

### Issue linkage (enforced by `pr-linkage.yml`)

Every PR must link to a backlog issue. The workflow accepts three paths:

- **`task/<N>-<slug>` branch** — implicit link via branch name (created by `make task ISSUE=N`).
- **`Fixes #N` / `Closes #N` / `Resolves #N`** in the PR body or title.
- **`module/<component>` umbrella PRs** — bypassed. These roll up a module
  sprint into `develop`; the underlying `task/N-*` PRs already carried
  individual issue linkage, so the roll-up doesn't need its own `Fixes #N`.

### Commit message format

```
type(component): short description

- Detail 1
- Detail 2

Closes #<issue number> (if applicable)
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Examples:
- `feat(digisearch): add LanceDB backend with filtering support`
- `fix(digigraph): correct state field initialization in research subgraph`
- `docs(digiquant): update ARCHITECTURE.md with v1 jobs API`

---

## 8. Auto-Merge Eligibility

### Eligible for auto-merge (`automerge-docs` label)

- PR changes **only** documentation files matching the allowlist in `docs/agent-backlog/AUTOMERGE.md`
- CI link-check passes (`python3 scripts/check_doc_links.py`)
- No SECURITY.md or auth workflow files changed

### Eligible for reviewer fast-track (code PR)

- All four scores are at or above **target** (not just minimum)
- `make test-unit` passes with zero failures
- Human gate is **not** triggered (see below)
- PR description clearly explains what changed and why

### Human Review Required (always)

The following changes **always** require a human reviewer, regardless of score:

| Trigger | Why |
|---------|-----|
| Any change to `digiclaw/` execution paths or broker adapters | Live-trading risk |
| Any change to `digikey/` crypto, signing, or JWT generation | Auth integrity |
| Any new DigiKey scope added to a route | Security perimeter change |
| `DIGI_ALLOW_CODE_EXEC` gate modified | Sandboxing bypass risk |
| New `0.0.0.0` binding or network exposure | Security perimeter change |
| New external service dependency added | Supply chain risk |
| Changes to `SECURITY.md` | Policy change |
| Novel architecture pattern not in any ARCHITECTURE.md | Architecture decision required |

---

## 9. Post-Merge

1. Update `docs/agent-backlog/INDEX.md`: change the theme status to `done` (or update partial progress).
2. Close or update the GitHub Issue if one was linked.
3. If the change introduced a new pattern worth generalizing, add it to `{component}/AGENTS.md` under Extension Patterns.
4. If the change revealed an anti-pattern, add it to `{component}/AGENTS.md` under Anti-Patterns.

---

## 10. When to Escalate

Stop and request human input when:

- You encounter any human-gate trigger (Section 7)
- The required change contradicts a rule in `AGENTS.md` or `{component}/ARCHITECTURE.md`
- Tests fail in a way you cannot diagnose within 2 attempts
- The correct approach requires an Architecture Decision Record (ADR) — see `docs/adr/`
- You are about to modify a file you haven't read completely

When escalating: write a clear description of what you were trying to do, what you found, and what decision is needed. Do not make a guess and proceed.

---

## 11. Worktree Execution (Isolated Task Pipeline)

Use `make task ISSUE=N` to run the full autonomous pipeline for a backlog task. This creates an isolated git worktree so the main branch stays clean while you implement.

### Full pipeline

```bash
make status                          # see open tasks
scripts/fetch_task.sh 42             # read the spec
make task ISSUE=42                   # execute full pipeline
```

### What the pipeline does

1. `scripts/fetch_task.sh N` — fetches spec (goal, acceptance criteria, component)
2. `scripts/worktree_task.sh create N` — creates `.worktrees/task-N-slug/` on branch `task-N-slug`
3. **PAUSE** — you implement in the worktree; pipeline waits for Enter
4. `pytest -m unit -k {component} -v --tb=short` — component tests must pass
5. `make score` — all 4 scoring dimensions must meet threshold
6. `make commit MSG="feat({component}): {title} (#{issue})"` — validated commit
7. `git push origin task-N-slug` — push the branch
8. `make pr` — open PR with template pre-filled
9. `scripts/worktree_task.sh remove N` — cleanup worktree

### Worktree rules

- **Always implement in the worktree**, never on the main branch
- Read `{component}/AGENTS.md` and `{component}/ARCHITECTURE.md` before touching code
- Stage all changes (`git add`) before pressing Enter at the pause step
- If score fails twice: escalate to human (do not force-continue)

### Manual worktree management

```bash
scripts/worktree_task.sh create 42   # create worktree for issue #42
scripts/worktree_task.sh list        # see all active worktrees
scripts/worktree_task.sh remove 42   # remove when done
```

---

## 12. Error Ingestion

When a user pastes a Python stack trace, use the error ingestion workflow to identify the affected component and create a targeted bug issue.

### Pipeline

```bash
# From a file
make parse-error TRACEBACK=error.log

# From stdin
cat error.log | python3 scripts/parse_traceback.py

# JSON output (for automation)
python3 scripts/parse_traceback.py --input error.log --format json
```

### Output

```
Component: digisearch | File: digisearch/src/digisearch/ingest.py:42 | Error: ValueError: chunk size must be > 0
```

### After identifying the component

1. Read `{component}/AGENTS.md` — pre-flight checklist
2. Open the identified file at the reported line
3. Create a bug issue: `scripts/create_issue.sh --component {component} --type fix --title "fix({component}): {error_type} at {file}:{line}"`
4. Offer to execute: `make task ISSUE=N`

### Escalation

If the error originates in `digikey/` (auth/crypto) or a live-trading path, escalate to human before proceeding.

---

## Agent-instruction surface map

DigiThings supports four IDE / agent surfaces. **`agents.yml`** is the only hand-edited source of truth; everything else is either generated from it or is authoritative hand-written prose.

| Surface | File | Status | Audience |
|---------|------|--------|----------|
| `agents.yml` | repo root | **Hand-edited source of truth** | `scripts/agents_init.py` |
| `AGENTS.md` | repo root | Authoritative hand-written | Every agent (all IDEs) |
| `CLAUDE.md` | repo root | Authoritative hand-written | Claude Code specifically |
| `.github/copilot-instructions.md` | `.github/` | **Generated — do not edit** | GitHub Copilot |
| `.cursor/rules/digithings.mdc` | `.cursor/rules/` | **Generated — do not edit** | Cursor |
| `.cursorrules` | repo root | Hand-written quick reference | Cursor (legacy fallback) |
| `{component}/AGENTS.md` | each component | Authoritative hand-written | Every agent when touching that component |

### When to edit what

- **New rule, new component, new capability:** edit `agents.yml`, then run `make agents-init`. Commit `agents.yml` + both regenerated surfaces.
- **Claude-specific command or pattern:** edit `CLAUDE.md` directly.
- **Stack-wide rule prose:** edit `AGENTS.md` directly.
- **Per-component workflow:** edit `{component}/AGENTS.md` directly.
- **Never edit** `.github/copilot-instructions.md` or `.cursor/rules/digithings.mdc` by hand — the CI job `agents-init-idempotent` will fail the PR. Use `make agents-init` and commit the result.

### Regeneration

```bash
make agents-init   # runs scripts/agents_init.py
```

CI enforces idempotence: the `Docs` workflow fails if `agents.yml` and the generated surfaces are out of sync.
