# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

For full agent rules (applies to every IDE / coding agent), see [AGENTS.md](AGENTS.md). For strategy, see [docs/VISION.md](docs/VISION.md). For the system diagram, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Project at a glance

**DigiThings** — open-core modular agentic stack. Flagship vertical: quantitative finance. Same stack powers RAG, document search, and general agent workflows.

Services (Python):
- **digigraph/** — orchestration brain (LangGraph, MCP tools, OpenAI-compatible API).
- **digiquant/** — quant engine (NautilusTrader, strategy registry, **Atlas research sub-graph + Hermes analysis sub-graph**).
- **digisearch/** — RAG / search (ingest, chunking, embedding, vector search).
- **digikey/** — JWT + scoped API keys (RS256, JWKS).
- **digismith/** — tracing helpers + `/v1/status`.
- **digiclaw/** — heartbeat / audit / MCP skill.
- **digibase/** — shared HTTP/audit library.

Atlas + Hermes are sibling sub-graphs inside the digiquant module:
- **Atlas** (research): `digiquant/src/digiquant/atlas/` is fully self-contained — code + `skills/` + `templates/` + `config/` + `docs/` all under one tree. Tests at `tests/dq/atlas/`; frontend at `frontend/atlas/`. Phases 1–7a; terminates at `phase7_synthesis`. Folded into digiquant in epic [#297](https://github.com/digithings-ai/digithings/issues/297) (2026-04, [ADR-0014](docs/adr/0014-atlas-in-digiquant.md)).
- **Hermes** (analysis + PM + reflection): `digiquant/src/digiquant/hermes/` is also fully self-contained — code + `skills/` + `templates/` + `docs/`. Tests at `tests/dq/hermes/`. Phases 7c (4-axis analyst), 7cd (Bull/Bear debate), 7d (risk + PM allocation), 9 (closed-loop reflection). Split out of Atlas in epic [#471](https://github.com/digithings-ai/digithings/issues/471) (2026-04, [ADR-0015](docs/adr/0015-atlas-vs-hermes.md)) — handoff seam is `digiquant.atlas.snapshot.DigestPayload`. Layouts consolidated into the package in [#486](https://github.com/digithings-ai/digithings/issues/486).

End-to-end production CLI: `python -m digiquant.hermes.chain --run-type baseline|delta|monthly` (the cron workflows use this). Standalone research-only: `python -m digiquant.atlas.graph`. Standalone Hermes from a saved digest: `python -m digiquant.hermes.graph --from-digest <state.json>`.

The old `apps/digiquant-atlas/` tree is gone — if you see it in a doc, that doc is either historical (ADRs, `docs/plans/`) or stale.

Frontend umbrella (see [ADR-0009](docs/adr/0009-frontend-umbrella.md)):
- **frontend/design/** — `@digithings/design` workspace package (shared tokens, CSS primitives, vanilla-JS modules).
- **frontend/digithings/** — static landing page at digithings.ai.
- **frontend/digiquant/** — static landing page at digiquant.io.
- **frontend/digichat/** — Next.js chat UI at chat.digithings.ai.
- **frontend/atlas/** — Next.js Atlas dashboard (research / portfolio surface).

## Commands

### Docker (primary workflow)

```bash
make build          # build all service images
make up             # start core stack (8000/8001/8002/8003, LiteLLM 4000, DigiKey 8005)
make down           # stop stack
make up-heartbeat   # start with heartbeat profile
make up-digichat    # core stack + DigiChat (profile digichat, host port 3005)
make down-digichat  # stop DigiChat profile
```

### Smoke test

```bash
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}' \
  | python3 -m json.tool
```

### Tests

```bash
make test           # unit + e2e (if stack up)
make test-unit      # pytest -m unit (no stack required)
make test-e2e       # pytest -m e2e (requires stack running)
make test-cov       # coverage report
make test-cov-html  # HTML coverage (htmlcov/)

# single test
pytest tests/<suite>/test_file.py::test_name -v
pytest -m unit -k "keyword" -v
```

Note: `make test-cov` requires editable installs — `pip install -e "digigraph[dev]" -e "digiquant[dev]" -e "digismith"`.

### Lint + format

```bash
ruff check .
ruff format .
```

### Local dev without Docker

```bash
scripts/run_local.sh     # DigiGraph (18000) + DigiQuant (18001) locally
make stack-local         # full local stack (all services)
make stack-local-stop
python -m digiclaw       # heartbeat/audit from repo root
```

### DigiChat (Next.js, from frontend/digichat/)

```bash
make digichat-dev             # dev server on port 3000
npm run lint                  # ESLint
npm run test                  # Vitest
npm run db:migrate            # Drizzle migrations
npm run db:seed
npm run db:create-key -- <tenant_slug> <key_name>
```

### Other useful targets

```bash
make doc-check            # validate internal markdown links
make openapi-digigraph    # generate OpenAPI schema to docs/openapi/
make agents-init          # regenerate .claude/, .cursor/rules, and .github/copilot-instructions.md from agents.yml + agents/sources/
make clean-imports [APPLY=1]
make find-stale
```

### Agent development kit

```bash
make status [COMPONENT=x]    # list open agent-task GitHub issues
make batch-candidates        # group open agent-task issues by phase/area for parallel execution
make new-task                # interactive issue creation
make task ISSUE=N            # run backlog task in an isolated worktree
make parse-error             # identify component from a Python traceback
make score                   # self-score staged changes (4 dimensions)
make commit MSG="feat(x):…"  # validated conventional commit
make pr                      # open PR with template pre-filled (requires gh)
make hooks-install           # install .git/hooks/pre-push (also auto-runs on agents-init)
```

### Module branch workflow (multi-session / multi-contributor)

DigiThings uses a three-tier branching model:

```
main  ←  develop  ←  module/<component>  ←  task/<N>-<slug>
```

**When to use each branch:**
- `develop` — cross-cutting work, tooling, CI, docs, SITAAS, Atlas, releases
- `module/<component>` — focused session on a single module (digigraph, digiquant, digichat, etc.)
- `task/<N>-<slug>` — individual backlog task; auto-created by `make task ISSUE=N`

**Starting a focused module session:**
```bash
make module-switch MODULE=digiquant   # checkout module/digiquant
make task ISSUE=149                   # branches task/149-... from module/digiquant automatically
```

**Finishing a module sprint (merge back to develop):**
```bash
make module-pr MODULE=digiquant       # opens one PR: module/digiquant → develop
```

**Other module commands:**
```bash
make module-status          # show all module branches vs develop (ahead/behind)
make module-sync            # fast-forward all module branches from develop
```

**Rules:**
- Never do module-specific work directly on `develop` — use the module branch.
- `task/N-slug` branches always PR into their module branch (not develop). The `create_pr.sh` script handles this automatically based on `scripts/project_routing.json`.
- Module branches PR into `develop` when the sprint is complete — one PR per module per sprint.
- Cross-cutting tasks (component:root, component:website) branch from `develop` directly.

### Claude Code surface (`.claude/`)

Committed Claude Code configuration. Auto-loaded in every Claude Code session.

**Guardrails** (PreToolUse hooks, enforced by the harness — not bypassable by the model):
- `.claude/settings.json` → `scripts/claude-hooks/` scripts block writes outside the project root, `git push` to non-origin remotes, edits to protected paths (`SECURITY.md`, `.github/workflows/`, `docs/scoring/`, live-trading paths) when not on a `task-N-*` branch, and network calls to non-allowlisted hosts.
- `scripts/hooks/pre-push.sh` → installed into `.git/hooks/pre-push` by `make hooks-install`. Blocks pushes to non-origin remotes, pushes to `main` without `ALLOW_MAIN_PUSH=1`, and pushes touching live-trading paths without a `Human-Approved-By:` commit trailer.

**Subagents** (`.claude/agents/`):
- `dictation-normalizer` — reshape rambling dictated input into a structured block; invoke via `/normalize`.
- `component-router` — map a described change onto the right component + reading list + test command.
- `spec-writer` — emit issue bodies matching `.github/ISSUE_TEMPLATE/agent_task.yml`; invoke via `/spec`.
- `pr-reviewer` — rubric-aware review aligned with `docs/scoring/`.
- `test-first-implementer` — red/green/refactor TDD loop bound to the component test command.

**Skills** (`.claude/skills/`):
- `batch` — spawn parallel worktree agents for 3+ independent tasks; use `make batch-candidates` to identify candidates.
- `write-acceptance-criteria` — Given/When/Then format + test command mapping.
- `worktree-task-start` — pre-flight checklist wrapping `make task ISSUE=N`.
- `score-and-fix` — run `make score`, walk rubric fixes for each failing dimension.

**Slash commands** (`.claude/commands/`): `/normalize`, `/spec`, `/score`, `/task`.

Single source of truth: `agents.yml` (declarations) + `agents/sources/{subagents,skills,commands}/` (content). `make agents-init` regenerates everything under `.claude/`, `.cursor/rules/digithings.mdc`, and `.github/copilot-instructions.md`. Cursor and Copilot don't support structured subagents/skills — they receive prose summaries that describe *when* to invoke each so they can emulate the intent. Drift is caught in CI by `scripts/agents_init.py --check`.

### Issue-linkage discipline (Phase 0 — epic #34)

Every code change must trace to an issue on [Project #1](https://github.com/orgs/digithings-ai/projects/1). Two ways to satisfy:

1. Run `make task ISSUE=N` → puts you on branch `task/<N>-<slug>` (auto-links).
2. Or open a PR whose body contains `Fixes #N` / `Closes #N` / `Resolves #N`.

`scripts/create_issue.sh` auto-adds new issues to Project #1; `.github/workflows/issue-to-project.yml` is the backup for UI-filed issues; `.github/workflows/pr-linkage.yml` fails PRs that don't satisfy either rule.

## Non-negotiable rules

Full rules in [AGENTS.md](AGENTS.md). Short form:

- Polars only (never pandas).
- NautilusTrader for quant.
- LangGraph supervisor + sub-graphs.
- LiteLLM with caching.
- Pydantic v2 structured outputs.
- Loopback binding, human gates before any live trade.
- PR scoring gate: Security ≥ 8, Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9 (run `make score`).
- Never touch live-trading code without explicit human approval.

## Before modifying a component

- Read `{component}/AGENTS.md` first — pre-flight checklist.
- Read the relevant `{component}/ARCHITECTURE.md` section for your area.
- For Nautilus strategy / backtest changes, also read `digiquant/docs/NAUTILUS_NAVIGATION.md`.
- For orchestrated / backlog-driven work, follow [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md).
- Update `{component}/ARCHITECTURE.md` after any interface or behavior change.
- Commit early and often.
- `projects/` is confidential — never push to public remotes. For committed public dogfood projects, use `docs/projects/` instead. See [ADR-0006](docs/adr/0006-public-dogfood-projects.md).

## Patterns worth knowing

- **Tool discovery:** MCP registry (`digigraph/orchestration/registry.py`). Capabilities are either builtins (`digigraph/orchestration/builtin.py`) or verticals that expose `POST /v1/orchestrator_tools`.
- **LLM routing:** LiteLLM via `config/litellm.yaml`. DigiGraph Bearer from `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY`. Mode from `DIGI_LLM_MODE` (`test` / `medium` / `best`).
- **Checkpointing:** LangGraph checkpoint backend via `DIGI_CHECKPOINTER` (`memory` / `sqlite` / `postgres`).
- **Audit:** immutable JSONL logs via `digibase.audit.redact_mapping`. Never persist raw prompts, keys, or doc bodies.
- **Tracing:** DigiSmith spans must carry `workflow_id`, `request_id`, `session_id`. `/v1/status` is public — keep it secret-free.
- **DigiSearch naming:** drop the `Digi` prefix for entity names (`Document`, `Chunk`, `Query`, `Result`).

## Frontend umbrella

All web frontends live under `frontend/` as npm workspace members
(`frontend/*`). See [ADR-0009](docs/adr/0009-frontend-umbrella.md).

- **`frontend/design/`** — `@digithings/design` workspace package. Shared tokens, CSS primitives, starfield / scroll-trigger / typewriter modules, favicons, OG image.
- **`frontend/digithings/`** — static landing page at digithings.ai (vanilla HTML/CSS/JS, canvas starfield). References the design via `../design/…`. Deployed via `.github/workflows/static.yml` — Pages on this monorepo, custom domain `digithings.ai`.
- **`frontend/digiquant/`** — static landing page at digiquant.io. Same design source of truth. Deployed via `.github/workflows/deploy-digiquant.yml` — builds `dist/` and pushes to the separate [`digithings-ai/digiquant.io`](https://github.com/digithings-ai/digiquant.io) publish repo (GitHub Pages supports one custom domain per repo, see [ADR-0012](docs/adr/0012-digiquant-io-split-repo.md)).
- **`frontend/digichat/`** — production Next.js + React chat UI + BFF for DigiGraph. Deployed to `chat.digithings.ai`. Docker Compose profile `digichat`. Imports `@digithings/design` as a workspace dependency.
- **`frontend/atlas/`** — Next.js Atlas dashboard (research + portfolio surface). Imports `@digithings/design` as a workspace dependency.

See [ADR-0002](docs/adr/0002-domain-unification.md) for the two-domain plan (amended by ADR-0009 and ADR-0012).
