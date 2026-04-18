# Contributing to DigiThings

Thanks for your interest in contributing to **DigiThings** (digithings.ai) — the open-core agentic stack.

All AI coding agents read [AGENTS.md](AGENTS.md) first. Human contributors: the rules below apply to you too.

## Required reading

1. [README.md](README.md) — repo overview.
2. [docs/VISION.md](docs/VISION.md) — strategy and strategic decisions.
3. [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram and interfaces.
4. [ROADMAP.md](ROADMAP.md) — phases and current priorities.
5. [SECURITY.md](SECURITY.md) — non-negotiable security defaults.
6. The `ARCHITECTURE.md` and `AGENTS.md` in the component you're touching (e.g. `digigraph/`).

## Hard rules (non-negotiable)

- **MCP-first** — every new capability is a discoverable MCP tool.
- **Polars only** — never pandas.
- **NautilusTrader core** — all backtest/optimize/live execution goes through Nautilus.
- **LiteLLM with caching** — token efficiency is mandatory.
- **Dockerized** — every component runs via the root `docker-compose.yml`.
- **LangGraph supervisor + sub-graph** — all agent logic in DigiGraph follows this pattern.
- **Security** — follow every rule in [SECURITY.md](SECURITY.md): loopback by default, least privilege, human gates before any live trade.
- **Projects** — anything under `projects/` is confidential client/pilot work. Never push to public remotes.

## Code style

- Python 3.12+ with strict type hints.
- ruff-compliant (line length 100, target `py312`).
- All LLM outputs use Pydantic v2 models, never raw strings.
- File layout matches the component's existing structure.
- Update the relevant `{component}/ARCHITECTURE.md` when interfaces change.

## Workflow

1. Pick or open an issue on the [GitHub Project](https://github.com/orgs/digithings-ai/projects/1). Scope the work.
2. Branch: `feature/<short-description>` or `fix/<short-description>`.
3. Implement with small, focused commits (conventional commit messages — `make commit MSG="feat(x): ..."` helps).
4. Run `make score` and pass the PR gate (Security ≥ 8, Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9). Rubrics: [docs/scoring/](docs/scoring/).
5. Open a PR with the template. Include: what changed, why, how it was tested.
6. CI runs lint, unit tests, and doc-link checks. Fix failures before requesting review.

For agent-driven work, the full end-to-end workflow is in [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md).

## Testing

- Unit tests for every new MCP tool, LangGraph node, and HTTP endpoint.
- Real tests only — no `assert True`, no smoke stubs, no tests that mock out the entire code path being claimed as "tested."
- End-to-end: `chat idea → backtest → cached strategy` continues to pass.
- Performance: 10 M-row Nautilus backtest stays under 2 s.

## Always requires human review

- Auth, JWT, or cryptography code.
- Broker adapters or live-trading paths.
- Any score below threshold on any dimension.
- New external service or infrastructure dependency.
- Novel architectural decisions not covered by an ADR — open an ADR in `docs/adr/` first.

## Questions

- Default to the most conservative, secure, and token-efficient option.
- If unclear, open an issue on the [GitHub Project](https://github.com/orgs/digithings-ai/projects/1) referencing the relevant `ARCHITECTURE.md` section.

By contributing, you agree to the technical constraints above and the license terms in [LICENSE](LICENSE).
