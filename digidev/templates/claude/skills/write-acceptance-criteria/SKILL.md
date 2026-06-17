---
name: write-acceptance-criteria
description: Use when the user asks to define acceptance criteria, write a spec for a task, clarify what "done" looks like, or translate a vague goal into testable requirements. Triggers on "acceptance criteria", "definition of done", "how will we know this works", "spec for".
---

# Write acceptance criteria

Translate a goal or feature description into a concrete, testable acceptance checklist.

## Format

Use Given/When/Then for each criterion:

```
- [ ] Given <context>, when <action>, then <observable outcome>
```

Each criterion must be:
- **Testable** — a human or automated test can verify it without ambiguity.
- **Specific** — names exact values, error codes, response shapes, or UI states.
- **Atomic** — one observable outcome per bullet.

## Procedure

1. Ask (or infer) the goal in one sentence: *"What should be true when this is done?"*
2. Identify the component from `agents.yml` → `components`.
3. Look up that component's test command in its `AGENTS.md`.
4. Draft criteria covering:
   - **Happy path** — the primary success scenario.
   - **Edge cases** — empty input, boundary values, concurrent calls.
   - **Error path** — invalid input, upstream failure, auth rejection.
   - **Non-regression** — existing adjacent behaviour still works.
5. Add infrastructure criteria:
   - `- [ ] Unit tests pass: <test command>`
   - `- [ ] {component}/ARCHITECTURE.md updated if interface changed`

## Example

**Goal:** Add a `/health` endpoint to the API service.

```
- [ ] Given the service is running, when GET /health is called, then it returns 200 OK with body `{"status":"ok"}`.
- [ ] Given the database is unreachable, when GET /health is called, then it returns 503 with body `{"status":"degraded","detail":"db"}`.
- [ ] Given an authenticated request, when GET /health is called, then it returns the same response (no auth required).
- [ ] Unit tests pass: pytest -m unit -k health -v
- [ ] ARCHITECTURE.md updated with the new endpoint.
```

## Output

Paste the criteria directly into the GitHub issue body under `### Acceptance criteria`, or hand them to the `spec-writer` agent to produce a full issue body.
