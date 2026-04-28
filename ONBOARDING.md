# Onboarding — Developing on DigiThings

Welcome. This guide is how Chris develops on this monorepo with Claude Code. It's the companion to [CLAUDE.md](CLAUDE.md) (repo-wide agent rules) and [AGENTS.md](AGENTS.md) (stack-wide non-negotiables) — read both once, then come back here to see how the pieces connect day-to-day.

If you're a new human contributor, skim this front-to-back and run the one-time setup.
If you're a Claude Code session picking this up fresh, the later sections are the playbook.

---

## 1. One-time setup

```bash
git clone https://github.com/digithings-ai/digithings
cd digithings
make agents-init         # regenerates .claude/, .cursor/rules, .github/copilot-instructions.md from agents.yml
make hooks-install       # installs .git/hooks/pre-push guardrails
gh auth login            # GitHub CLI — required for make pr and issue workflow
```

Per-user Claude Code overrides (tokens, extra allowed Bash commands, personal hooks) belong in `.claude/settings.local.json` (gitignored) — create it on demand; never edit the committed `.claude/settings.json`. Docker Desktop must be running for `make up` and the e2e tests.

### MCP servers (first-session authentication)

Both Claude Code (`.mcp.json`) and Cursor (`.cursor/mcp.json`) are wired to the Supabase MCP server for this project. On your first session, run `/mcp` (Claude Code) or the Cursor equivalent, select **supabase**, and complete the OAuth flow — the token binds to your Supabase account (read-only by default; service-role queries still require the env credentials). This unlocks `execute_sql`, `list_tables`, `apply_migration`, etc. directly from any agent session, so Cursor/Copilot-dispatched agents can inspect DB state when contributing.

---

## 2. How Claude Code is wired into this repo

Everything in `.claude/` is committed and auto-loaded at session start. Do **not** hand-edit anything under `.claude/` — it's generated. The single source of truth is:

- `agents.yml` — declarations (which agents/skills/commands exist)
- `agents/sources/{subagents,skills,commands}/` — prose content for each

`make agents-init` regenerates `.claude/`, `.cursor/rules/digithings.mdc`, and `.github/copilot-instructions.md` from these. CI enforces no drift via `scripts/agents_init.py --check`.

### Guardrails (PreToolUse hooks — enforced by the harness, not bypassable by the model)

Configured in `.claude/settings.json`; scripts under `scripts/claude-hooks/`:

- `project-root-guard.sh` — blocks writes outside the project root.
- `protected-path-guard.sh` — blocks edits to `SECURITY.md`, `.github/workflows/`, `docs/scoring/`, live-trading paths unless on a `task/N-*` branch.
- `component-router-preflight.sh` — blocks writes that don't belong to the current component.
- `branch-warn.sh` — warns when the task protocol expects a task branch and you're not on one.
- `network-host-guard.sh` — blocks network calls to non-allowlisted hosts.
- `remote-guard.sh` — paired with `scripts/hooks/pre-push.sh`; blocks pushes to non-origin remotes and pushes touching live-trading paths without a `Human-Approved-By:` commit trailer.

### Repo-committed agent surface

All regenerated from `agents.yml` + `agents/sources/*`. Cursor and Copilot don't support structured subagents/skills, so `.cursor/rules/digithings.mdc` and `.github/copilot-instructions.md` contain prose summaries describing *when* to invoke each.

**Subagents** (`.claude/agents/`) — invoked automatically when their description matches, or explicitly:

- `component-router` — maps a described change onto the right component + reading list + test command.
- `dictation-normalizer` — reshapes rambling/dictated input (also `/normalize`).
- `spec-writer` — emits GitHub Issue bodies matching `.github/ISSUE_TEMPLATE/agent_task.yml` (also `/spec`).
- `pr-reviewer` — rubric-aware PR review aligned with `docs/scoring/`.
- `test-first-implementer` — red/green/refactor TDD loop bound to the component test command.

**Skills** (`.claude/skills/`) — workflows triggered by name:

- `worktree-task-start` — pre-flight checklist wrapping `make task ISSUE=N`.
- `score-and-fix` — run `make score`, walk rubric fixes for each failing dimension.
- `write-acceptance-criteria` — Given/When/Then format + test command mapping.
- `ci-triage` / `triage` — diagnose red CI on a PR; bucket failures, give fix commands.

**Slash commands** (`.claude/commands/`):

- `/task` — start a backlog task end-to-end (`make task ISSUE=N`).
- `/spec` — generate a GitHub Issue body from a goal.
- `/score` — run the 4-dimension scoring gate on staged changes.
- `/triage` — CI triage on the current PR.
- `/normalize` — reshape rambling input into a structured instruction block.

Built-in Claude Code agents (`Plan`, `Explore`, `general-purpose`) and user-level global skills (`simplify`, `review`, `security-review`, `loop`, `schedule`, `batch`, `init`, `claude-api`, `update-config`, etc.) are available in every session but are not committed to this repo.

---

## 3. Branching model — three tiers

```
main  ←  develop  ←  module/<component>  ←  task/<N>-<slug>
```

| Branch | When to use |
|---|---|
| `main` | Releases only. Never push directly. |
| `develop` | Cross-cutting work: tooling, CI, docs, SITAAS, Atlas, releases. |
| `module/<component>` | Focused session on a single module (`digigraph`, `digiquant`, `digichat`, `digisearch`, `digikey`, `digismith`, `digiclaw`, `digibase`). |
| `task/<N>-<slug>` | Individual backlog task. Auto-created by `make task ISSUE=N`. |

**Rules:**

- Never do module-specific work directly on `develop` — use the module branch.
- `task/N-slug` branches always PR into their module branch (not develop). `scripts/create_pr.sh` enforces this via `scripts/project_routing.json`.
- Module branches PR into `develop` when the sprint is complete — **one PR per module per sprint**.
- Cross-cutting tasks (`component:root`, `component:website`) branch from `develop` directly.

**Common commands:**

```bash
make module-switch MODULE=digiquant   # checkout module/digiquant
make task ISSUE=149                   # auto-branches task/149-<slug> from the module
make module-status                    # all module branches vs develop (ahead/behind)
make module-sync                      # fast-forward all module branches from develop
make module-pr MODULE=digiquant       # open the one PR: module/digiquant → develop
```

---

## 4. Task lifecycle — from issue to merge

Every code change must trace to an issue on [Project #1](https://github.com/orgs/digithings-ai/projects/1). Two ways to satisfy it:

1. `make task ISSUE=N` — puts you on `task/<N>-<slug>` (auto-links). This is the normal path.
2. Or open a PR whose body contains `Fixes #N` / `Closes #N` / `Resolves #N`.

`.github/workflows/pr-linkage.yml` fails PRs that satisfy neither.

### The normal loop

```bash
make status                         # list open agent-task issues (or: /task → worktree-task-start skill)
make task ISSUE=N                   # branches task/N-<slug> in an isolated worktree
# ... do the work ...
ruff check . && ruff format .
make test-unit                      # pytest -m unit
make score                          # 4-dimension gate; MUST pass before commit
make commit MSG="feat(digiquant): short imperative subject (#N)"
make pr                             # opens the PR with template pre-filled (requires gh)
```

`make commit` runs conventional-commit validation + scoring. `make pr` uses `scripts/create_pr.sh`, which routes the PR into the correct base branch via `scripts/project_routing.json`.

### Scoring gate — `make score`

Four dimensions, hard thresholds. PRs that fall below fail CI:

| Dimension | Minimum |
|---|---|
| Security | ≥ 8 |
| Quality | ≥ 8 |
| Optimization | ≥ 7 |
| Accuracy | ≥ 9 |

Rubric lives in `docs/scoring/`. Use `/score-and-fix` (or the `score-and-fix` skill) to walk failures dimension-by-dimension.

### GitHub project automation

- `scripts/create_issue.sh` auto-adds new issues to Project #1.
- `.github/workflows/route-issues-to-projects.yml` routes each issue to its module project based on `component:*` label (epics + cross-cutting → Project #1); also the backup for UI-filed issues.
- `.github/workflows/pr-linkage.yml` enforces issue↔PR linkage.

---

## 5. PR review flow

1. **Pre-push**: local `pre-push` hook blocks pushes to non-origin remotes, pushes to `main` without `ALLOW_MAIN_PUSH=1`, and live-trading-path pushes without a `Human-Approved-By:` trailer.
2. **CI on open**: lint, unit tests, scoring gate, doc-link check, agents-init drift check.
3. **Review**: invoke `/review` (pr-reviewer subagent) on your own PR before asking a human. The subagent mirrors the 4-dimension rubric.
4. **CI red?** `/triage <N>` buckets failures by type and proposes minimal fix commands.
5. **Security-sensitive changes**: run `/security-review` on the branch before requesting review.

---

## 6. Non-negotiables (short form)

Full list in [AGENTS.md](AGENTS.md). The ones that most often trip new contributors:

- **Polars only** — never pandas, anywhere in the stack.
- **NautilusTrader** for quant; no homegrown backtest loops.
- **LangGraph supervisor + sub-graphs** for orchestration; no ad-hoc chains.
- **LiteLLM with caching** — all LLM calls route through the proxy; direct provider SDKs are a violation outside of the proxy itself.
- **Pydantic v2 structured outputs** — no raw dicts crossing module boundaries.
- **Loopback binding** for local dev servers; never `0.0.0.0` by default.
- **Human gates before any live trade** — the live-trading path guard is hard-wired into the pre-push hook.
- **`projects/` is confidential** — never push to public remotes. For committed public dogfood projects, use `docs/projects/` (see [ADR-0006](docs/adr/0006-public-dogfood-projects.md)).

### Before touching a component

- Read `{component}/AGENTS.md` — pre-flight checklist.
- Read the relevant `{component}/ARCHITECTURE.md` section.
- For Nautilus strategy / backtest changes, also read `digiquant/docs/NAUTILUS_NAVIGATION.md`.
- Update `{component}/ARCHITECTURE.md` after any interface or behavior change.
- Commit early and often.

---

## 7. Common Make targets

```bash
# Stack
make build                          # build all service images
make up / make down                 # start/stop core stack
make up-heartbeat                   # with heartbeat profile
make up-digichat / make down-digichat

# Tests
make test                           # unit + e2e (needs stack up)
make test-unit                      # pytest -m unit (no stack)
make test-e2e                       # pytest -m e2e
make test-cov                       # coverage (needs `pip install -e` for each service — see CLAUDE.md)

# Agent dev kit
make status [COMPONENT=x]           # open agent-task issues
make batch-candidates               # group open tasks for parallel execution
make new-task                       # interactive issue creation
make task ISSUE=N                   # start backlog task in isolated worktree
make parse-error                    # identify component from a Python traceback
make score                          # self-score staged changes
make commit MSG="feat(x):…"         # validated conventional commit
make pr                             # open PR with template

# Housekeeping
make doc-check                      # validate internal markdown links
make openapi-digigraph              # regenerate OpenAPI schema
make agents-init                    # regenerate .claude/, cursor, copilot from agents.yml
make hooks-install                  # (re)install pre-push hook
make clean-imports [APPLY=1]        # remove unused imports
make find-stale                     # find stale branches / artifacts
```

---

## 8. Gotchas

- **Nested git repos under the monorepo root** (e.g. a cloned `digichat/` alongside `frontend/digichat/`) will trip cleanup scripts and pollute `git status`. If you see one, check whether it's stranded work before deleting. Everything that ships lives inside the monorepo tree — clones outside `frontend/` or `apps/` are almost always stale.
- **Stray `node_modules/` at the repo root** means you ran `npm install` in the wrong directory. Workspace installs must happen under `frontend/` (design workspace root) or a specific app dir.
- **Atlas frontend regeneration**: `frontend/atlas/next-env.d.ts` and `tsconfig.json` are rewritten by Next.js / your IDE. Discard those diffs unless the change is deliberate.
- **Task branches are worktrees** — `make task ISSUE=N` creates a worktree under `.claude/worktrees/` (gitignored). Don't `cd` out of it mid-task; close with `git worktree remove` after the PR merges.
- **`make score` requires the editable installs** — `pip install -e "digigraph[dev]" -e "digiquant[dev]" -e "digismith"` once per environment.

---

## 9. Where to find more

- [CLAUDE.md](CLAUDE.md) — repo-wide instructions for Claude Code sessions.
- [AGENTS.md](AGENTS.md) — stack-wide non-negotiable rules (applies to every IDE / agent).
- [docs/VISION.md](docs/VISION.md) — product strategy and roadmap.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram.
- [docs/adr/](docs/adr/) — architecture decision records. 0002 (two-domain plan), 0006 (public dogfood projects), 0009 (frontend umbrella) are the most referenced.
- [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md) — orchestrated / backlog-driven work.
- [docs/scoring/](docs/scoring/) — scoring rubric used by `make score` and `/review`.
- `scripts/claude-hooks/` + `scripts/hooks/pre-push.sh` — the guardrail scripts themselves; read them to understand exactly what's blocked and why.

Questions, or something in here out of date? Fix it in the same PR as whatever made you notice — this file belongs to the contributors who are actively using it.
