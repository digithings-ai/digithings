# AGENTS.md — {{PROJECT_NAME}}

Guidance for coding agents (Claude Code, Cursor, GitHub Copilot) working in this repository.

This document is auto-generated from `agents.yml`. For the full workflow guide, see `dividev/AGENT_GUIDE.md`.

## Quick rules

- Read `{component}/AGENTS.md` before editing any file in that component.
- Read the relevant `ARCHITECTURE.md` section before adding or changing interfaces.
- Run `make test-unit` — must pass zero failures before scoring.
- Run `make score` — must meet all thresholds before opening a PR.
- Open PRs with `make pr` — template pre-filled with self-score checklist.
- Use `make task ISSUE=N` to start work on a backlog issue.

## Non-negotiable

See `agents.yml` under `rules` for the current list. Short form:

- Score ≥{{SCORE_SECURITY}} Security, ≥{{SCORE_QUALITY}} Quality, ≥{{SCORE_OPTIMIZATION}} Optimization, ≥{{SCORE_ACCURACY}} Accuracy before PR.
- Never touch human-gate paths without explicit human approval (see `agents.yml` → `human_gates`).
- Never push directly to `{{MAIN_BRANCH}}`.

## Workflow summary

```
make task ISSUE=N       → create worktree, branch task/N-slug
{component}/AGENTS.md   → pre-flight checklist
implement + test        → make test-unit
score                   → make score
commit                  → make commit MSG="type(component): description"
pr                      → make pr
cleanup                 → worktree removed automatically
```

## Execution tiers

| Label | Tier | Who executes | Scope |
|---|---|---|---|
| `exec:copilot` | 1 | GitHub Copilot (auto) | Housekeeping, fixed rules only |
| `exec:cursor` | 2 | Cursor cloud agent (auto) | Clear spec, single component |
| `exec:claude` | 3 | Claude Code (local, human) | Judgment, cross-module, human-gated |

## Components

{{COMPONENTS_SPACE}}

Each component has its own `{component}/AGENTS.md` with a pre-flight checklist, rules, and test command.

## Scoring thresholds

| Dimension | Minimum |
|---|---|
| Security | {{SCORE_SECURITY}}/10 |
| Quality | {{SCORE_QUALITY}}/10 |
| Optimization | {{SCORE_OPTIMIZATION}}/10 |
| Accuracy | {{SCORE_ACCURACY}}/10 |

Rubrics: `dividev/docs/scoring/`

## Before modifying a component

1. Read `{component}/AGENTS.md` — pre-flight checklist.
2. Read the relevant `ARCHITECTURE.md` section.
3. Run the component's test command to establish a green baseline.
4. Implement and test.
5. `make score` — fix any failing dimension.
6. `make commit` + `make pr`.
