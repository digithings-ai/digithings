# Autonomous Agent Development Workflow

Protocol for agents working in the DigiThings monorepo.

---

## 1. Before writing code

1. Read `{component}/AGENTS.md` — pre-flight checklist and anti-patterns.
2. Read `{component}/ARCHITECTURE.md` — module map, API, data models, extension guide.
3. Use Glob/Grep to verify files exist. Read the existing implementation before proposing changes.
4. For changes > 3 files: write a 3–10 bullet plan and confirm it matches `ARCHITECTURE.md`. Update ARCHITECTURE.md first if there's a mismatch.
5. If the approach requires a novel pattern not in any existing doc, escalate before proceeding.

---

## 2. Test commands

| Component | Command |
|-----------|---------|
| digigraph | `pytest -m unit -k digigraph -v` |
| digiquant | `pytest -m unit -k digiquant -v` |
| digisearch | `pytest -m unit -k digisearch -v` |
| digismith / digiclaw / digibase / digikey | `pytest -m unit -k {component} -v` |
| digichat | `cd frontend/digichat && npm run lint && npm run test` |
| All | `make test-unit` |

Run `ruff check . && ruff format --check .` after all Python changes.

---

## 3. Execute

1. Make small, verifiable increments.
2. Run component tests after each logical chunk.
3. Update `{component}/ARCHITECTURE.md` before marking the task done — the doc must reflect the code.
4. Never commit half-finished work. If blocked, describe the blocker clearly.

---

## 4. Scoring gate

Before opening a PR, run `make score`. All dimensions must pass:

| Dimension    | Minimum | Rubric |
|--------------|---------|--------|
| Security     | ≥ 8     | `docs/scoring/SECURITY.md` |
| Quality      | ≥ 8     | `docs/scoring/QUALITY.md` |
| Optimization | ≥ 7     | `docs/scoring/OPTIMIZATION.md` |
| Accuracy     | ≥ 9     | `docs/scoring/ACCURACY.md` |

If any dimension fails: fix, re-stage, re-run. If it fails twice, escalate — do not open a PR with known violations.

---

## 5. PR requirements

Every PR must link to a backlog issue. Three accepted paths:

- **`task/<N>-<slug>` branch** — implicit link (created by `make task ISSUE=N`)
- **`Fixes #N` / `Closes #N` / `Resolves #N`** in the PR body or title
- **`module/<component>` umbrella PRs** — bypassed (underlying task PRs carry linkage)

Commit format: `type(component): short description`
Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

---

## 6. Human gate

Stop and request human input when:

| Trigger | Reason |
|---------|--------|
| Changes to `digikey/` (auth, JWT, crypto) | Auth integrity |
| Broker adapters or live-trading paths | Live-trading risk |
| New `0.0.0.0` binding or external service dependency | Security perimeter |
| Score below threshold after two fix attempts | Quality gate |
| Novel architecture not in any `ARCHITECTURE.md` | ADR required |
| Test failures you can't diagnose within two attempts | Escalate |

When escalating: describe what you were doing, what you found, and what decision is needed.

---

## 7. Isolated task pipeline

```bash
make status              # list open agent-task issues
make task ISSUE=N        # create worktree, implement, test, score, PR
```

Always implement in the worktree (`make task` creates it at `.worktrees/task-N-slug/`). Stage all changes before the score step. If score fails twice, escalate.

---

## 8. Post-merge

1. Close or update the linked GitHub Issue.
2. If the change introduced a new pattern, add it to `{component}/AGENTS.md` under Extension Patterns.
3. If the change revealed an anti-pattern, add it to `{component}/AGENTS.md` under Anti-Patterns.
