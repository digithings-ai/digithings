# Task Spec Template

Copy this template when creating a GitHub Issue (`agent-task` label) or adding a backlog entry to `INDEX.md`.
Replace all `{placeholder}` values. Remove sections that don't apply.

---

## Goal

One sentence: what will be true when this task is done.

> Example: `POST /v1/orchestrator_tools` on digisearch returns a `digisearch_research_delegate` tool when the `[agent]` extra is installed.

---

## Component

- [ ] `digigraph`
- [ ] `digiquant`
- [ ] `digisearch`
- [ ] `digismith`
- [ ] `digiclaw`
- [ ] `digibase`
- [ ] `digikey`
- [ ] `digichat`
- [ ] cross-cutting

---

## Acceptance Criteria

Each criterion must be independently testable. If you can't write a test for it, it's not a criterion.

- [ ] {Criterion 1}
- [ ] {Criterion 2}
- [ ] {Criterion 3}

---

## Test Requirements

**Unit tests** (no stack required):
- `{test file path}` — what scenario it covers
- Mock any HTTP calls; never hit live services in unit tests

**Integration / E2E tests** (stack required, optional):
- Describe the end-to-end scenario if applicable

**Smoke test** (manual, after stack is up):
```bash
# Example commands to verify the feature manually
curl -s http://localhost:{port}/{endpoint}
```

---

## Documentation to Update

- [ ] `{component}/ARCHITECTURE.md` — section: {section name}
- [ ] `{component}/AGENTS.md` — section: Extension Patterns (if new capability added)
- [ ] `docs/agent-backlog/INDEX.md` — mark task as done

---

## Review Targets

Quality bar is **review**, not a self-score. Run `/review` (or an in-session
review) when [CODE_REVIEW_POLICY.md](../agents/CODE_REVIEW_POLICY.md) needs a
hatch. The self-score rubric (`docs/scoring/`, `make score`) was removed in
#4868 — do not set numeric score targets for the task.

---

## Out of Scope

Explicitly list what this task does NOT do, to prevent scope creep.

- {Out of scope item 1}
- {Out of scope item 2}

---

## Dependencies

Tasks that must be complete before this one starts, or that this task unblocks.

- Blocked by: {issue link or task description}
- Unblocks: {issue link or task description}

---

## Human Gate Required?

- [ ] Yes — this task touches auth, JWT, cryptography, or live-trading paths
- [ ] No — safe for autonomous agent execution

If yes, tag the PR with `needs-human-review` and do not apply `automerge-docs`.
