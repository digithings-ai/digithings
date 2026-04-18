# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

For full agent rules (applies to every IDE / coding agent), see [AGENTS.md](AGENTS.md). For strategy, see [docs/VISION.md](docs/VISION.md). For the system diagram, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Project at a glance

**DigiThings** — open-core modular agentic stack. Flagship vertical: quantitative finance. Same stack powers RAG, document search, and general agent workflows.

Components:
- **digigraph/** — orchestration brain (LangGraph, MCP tools, OpenAI-compatible API).
- **digiquant/** — quant engine (NautilusTrader, strategy registry).
- **digisearch/** — RAG / search (ingest, chunking, embedding, vector search).
- **digichat/** — Next.js BFF + chat UI (Auth.js, Drizzle, AI SDK).
- **digikey/** — JWT + scoped API keys (RS256, JWKS).
- **digismith/** — tracing helpers + `/v1/status`.
- **digiclaw/** — heartbeat / audit / MCP skill.
- **digibase/** — shared HTTP/audit library.

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

### DigiChat (Next.js, from digichat/)

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
make new-task                # interactive issue creation
make task ISSUE=N            # run backlog task in an isolated worktree
make parse-error             # identify component from a Python traceback
make score                   # self-score staged changes (4 dimensions)
make commit MSG="feat(x):…"  # validated conventional commit
make pr                      # open PR with template pre-filled (requires gh)
make hooks-install           # install .git/hooks/pre-push (also auto-runs on agents-init)
```

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
- `projects/` is confidential — never push to public remotes.

## Patterns worth knowing

- **Tool discovery:** MCP registry (`digigraph/orchestration/registry.py`). Capabilities are either builtins (`digigraph/orchestration/builtin.py`) or verticals that expose `POST /v1/orchestrator_tools`.
- **LLM routing:** LiteLLM via `config/litellm.yaml`. DigiGraph Bearer from `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY`. Mode from `DIGI_LLM_MODE` (`test` / `medium` / `best`).
- **Checkpointing:** LangGraph checkpoint backend via `DIGI_CHECKPOINTER` (`memory` / `sqlite` / `postgres`).
- **Audit:** immutable JSONL logs via `digibase.audit.redact_mapping`. Never persist raw prompts, keys, or doc bodies.
- **Tracing:** DigiSmith spans must carry `workflow_id`, `request_id`, `session_id`. `/v1/status` is public — keep it secret-free.
- **DigiSearch naming:** drop the `Digi` prefix for entity names (`Document`, `Chunk`, `Query`, `Result`).

## Website and DigiChat layout

- **`website/`** — static landing page at digithings.ai (vanilla HTML/CSS/JS, canvas starfield). Nav links out to `https://chat.digithings.ai`.
- **`digichat/`** — production Next.js + React chat UI + BFF for DigiGraph. Deployed to `chat.digithings.ai`. Docker Compose profile `digichat`.

See [docs/adr/0002-domain-unification.md](docs/adr/0002-domain-unification.md) for the two-domain plan.
