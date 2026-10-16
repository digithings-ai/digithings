# Execution Tiers

Three tiers control which agent is allowed to pick up which task. The tier is a **ceiling**, not a preference — a lower tier must never pick up a higher-tier task.

---

## Tier 1 — GitHub Copilot (`exec:copilot`)

**Execution:** Triggered automatically when the `exec:copilot` label is applied to an issue. The `auto-assign-copilot.yml` workflow assigns `@Copilot`.

**Scope:** Fixed-rule automation. No judgment. No multi-file changes.

**Appropriate for:**
- Dependency bumps (Dependabot, pip-audit)
- Security CVE fixes in lock files
- Format auto-fixes (`ruff format`, `eslint --fix`)
- Stale issue/PR cleanup comments
- Coverage PR comments
- Structured CI failure triage comments (describe the failure, don't fix it)

**Never:**
- Correctness judgments
- Changes spanning more than 2–3 files
- Auth, crypto, or sensitive code
- Anything requiring architectural understanding

---

## Tier 2 — Cursor Cloud Agent (`exec:cursor`)

**Execution:** Triggered automatically via Cursor's cloud agent integration. Issue must have clear acceptance criteria (the agent cannot ask clarifying questions mid-task).

**Scope:** One-paragraph spec, clear acceptance, single component.

**Appropriate for:**
- Bug fixes with a concrete repro (exact file, line, expected vs actual)
- Unit tests for a specified module
- Adding typed models or docstrings
- Small scoped refactors inside a single component
- Simple new functions with well-defined inputs/outputs

**Never:**
- Cross-component integration
- Ambiguous success criteria
- Architectural decisions or novel design
- Tasks requiring mid-task dialogue

**Writing good Tier 2 issues:**
> Add a `GET /healthz` endpoint to the `api` component. It should return `{"status": "ok", "version": "<package version>"}` with a 200 status. Acceptance: unit test passes, endpoint returns correct shape, no new dependencies added.

---

## Tier 3 — Claude Code (`exec:claude`)

**Execution:** Local only. A human runs `make task ISSUE=N` on their workstation. When the `exec:claude` label is applied to an issue, the `claude-code-dispatch.yml` workflow posts a comment with copy-paste-ready execution instructions — but does **not** auto-execute.

**Scope:** Interactive, cross-module, architectural, or human-gated work.

**Appropriate for:**
- Architecture scaffolding and new-module design
- Complex debugging across multiple components
- Security review and auth implementation
- Optimization requiring deep context
- Decomposing milestones into Tier 1/2 tasks
- Reviewing and iterating on agent PRs
- Any task with a human gate

**Never:**
- Auto-execution from a GitHub label
- Unattended cloud execution (no human in the loop)

---

## Tier routing heuristics

When a task creator hasn't classified explicitly, default routing applies:

| Condition | Assigned tier |
|---|---|
| `risk:high` | exec:claude |
| `human_gate:yes` | exec:claude |
| Cross-component integration | exec:claude |
| Auth / crypto / sensitive code | exec:claude |
| `housekeeping:deps` | exec:copilot |
| `housekeeping:format` | exec:copilot |
| `stale` | exec:copilot |
| Everything else | exec:cursor |

---

## Escalation

If a Copilot task turns out to require judgment, it should be re-labelled `exec:cursor` or `exec:claude`. Never have a lower-tier agent attempt work beyond its scope — the result will require more cleanup than starting at the right tier.

If Copilot quota is exhausted and the issue is `priority:high` or `priority:critical`, the `auto-assign-copilot.yml` workflow automatically swaps the label to `exec:claude` and posts a comment.
