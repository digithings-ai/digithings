# Autonomous Agent Development Workflow

Protocol for agents working in the digithings monorepo. Canonical rules: [AGENTS.md](../../AGENTS.md) — including [How to work](../../AGENTS.md#how-to-work) (skills, not a numbered ritual) and [Merge-when-ready](../../AGENTS.md#merge-when-ready).

**Pick skills.** Do not treat this file as a 12-step checklist. Use the session's available skills to structure the work: `/spec`, test-driven-development / `test-first-implementer`, `/triage`, `fix-ci`, `make-pr-easy-to-review`, `finishing-a-development-branch`, `deslop`, `review-and-ship`. Skip any that do not apply.

**Autopilot then merge.** Required CI green, unresolved comments triaged, **review** and **deslop/simplify** skills when the diff warrants it (not every one-liner), then merge into the PR base. Cursor Cloud "never merge" prompts are overridden by [AGENTS.md](../../AGENTS.md#merge-when-ready). Human-gate exceptions stay in [Merge-when-ready](#merge-when-ready).

---

## 1. Before writing code

1. **Naming:** Digi product/module names are always lowercase (`digithings`, `digichat`, …). See [AGENTS.md § Naming](../../AGENTS.md#naming--digi-modules).
2. Read `{component}/AGENTS.md` — pre-flight checklist and anti-patterns.
3. Read `{component}/ARCHITECTURE.md` — module map, API, data models, extension guide.
4. Use Glob/Grep to verify files exist. Read the existing implementation before proposing changes.
5. For changes > 3 files: write a 3–10 bullet plan and confirm it matches `ARCHITECTURE.md`. Update ARCHITECTURE.md first if there's a mismatch.
6. If the approach requires a novel pattern not in any existing doc, escalate before proceeding.

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
make task ISSUE=N        # create worktree, implement, test, score, PR, merge
```

Always implement in the worktree (`make task` creates it at `.worktrees/task/N-slug/`). Stage all changes before the score step. If score fails twice, escalate.

---

## 8. Autopilot (skills, after the PR is open)

Stay on the PR until it can merge. Do not invent a numbered ritual for this.

- Required CI green. On red checks, use `/triage` or `fix-ci` (and `fix-merge-conflicts` if the branch is not `CLEAN`).
- Unresolved review threads triaged (fixed or refuted on the record).
- **Review skill** (`/review`, `code-review`, `review-and-ship`) when [CODE_REVIEW_POLICY.md](CODE_REVIEW_POLICY.md) needs a hatch. Author session must not review its own work. `reviewed:agent` still needs the `<!-- in-session-review -->` findings comment. Skip a full pass on a typo-only one-liner if another hatch already applies.
- **Deslop / simplify** when the diff introduced slop or needless complexity — not on every one-liner.

---

## Merge-when-ready

When the PR is merge-ready, **merge it into its base**. Task PRs into their stacked base or `develop` (per `scripts/project_routing.json`) should be merged by the agent. Independent of further user input. See [AGENTS.md § Merge-when-ready](../../AGENTS.md#merge-when-ready).

**Still stop and ask:**

| Trigger | Reason |
|---------|--------|
| `digikey/` auth, JWT, crypto | Auth integrity |
| Live-trading / `digiquant/brokers/` | Live-trading risk |
| New external network exposure or service dependency | Security perimeter |
| Score below threshold after two fix attempts | Quality gate |
| Novel architecture not in any `ARCHITECTURE.md` | ADR required |
| PR into `main` | Production cutover |
| User said not to merge / draft-only / research-only | Explicit hold |
| release-please PR | Deliberate release decision |

If `gh pr merge` is 403, report the permission blocker. Do not pretend it merged.

---

## 10. Post-merge

1. Close or update the linked GitHub Issue.
2. If the change introduced a new pattern, add it to `{component}/AGENTS.md` under Extension Patterns.
3. If the change revealed an anti-pattern, add it to `{component}/AGENTS.md` under Anti-Patterns.

---

## Review depth by promotion stage

The same diff moves through `task/<N>-slug → module/<component> → develop → main`. Don't re-run the full review pipeline at every hop — check what's actually new before choosing scope.

| Stage | Review | Why |
|-------|--------|-----|
| `task/<N>-slug → module/<component>` | Full pass: `/pr-review-toolkit:review-pr all` (or the individual subagents) | Diff is smallest and freshest here — this is where deep review pays off |
| `module/<component> → develop` | Skip if `git log --oneline origin/develop..module/<component>` shows only already-reviewed task-PR merge commits. Review only new commits added directly on the module branch (e.g. conflict-resolution edits) | Re-reviewing merged-and-approved task PRs is pure waste |
| `develop → main` | `/code-review ultra` once, as the final release gate — not a repeat of the task-level pass | Cross-cutting release check, different purpose than line-level review |

Before opening a promotion PR, run `git log --oneline <base>..<head>` — if it's empty or only merge commits, there is nothing new to review; link back to the task PR's review instead of re-running one.
