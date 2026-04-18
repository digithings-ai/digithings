---
name: write-acceptance-criteria
description: Use when the user asks to define acceptance criteria, write a spec for a task, clarify what "done" looks like, or translate a vague goal into testable requirements. Triggers on phrases like "acceptance criteria", "definition of done", "how will we know this works", "spec for".
---

# Write acceptance criteria

Your job: take a rough goal and produce a short, testable acceptance criteria block that plugs into `docs/agent-backlog/SPEC_TEMPLATE.md` and the `.github/ISSUE_TEMPLATE/agent_task.yml` form.

## Rules

- **Testable over aspirational.** "Cold-start under 200ms" beats "fast startup." If the user's goal isn't measurable, ask one clarifying question before writing.
- **Given / When / Then structure**, but compact. One line per scenario unless the setup genuinely needs prose.
- **Name the test command that would verify it.** Reuse test infrastructure that already exists — check `docs/agents/AGENT_WORKFLOW.md` § "Test Commands by Component" for the right pytest invocation.
- **Map to a component.** Every criterion should name a component (digigraph / digiquant / digisearch / digismith / digiclaw / digibase / digikey / digichat) so the router and scorer know where tests live.
- **Out-of-scope is as important as in-scope.** List 1–3 things the task explicitly does *not* do.

## Output format

```
## Acceptance criteria (component: <name>)

1. **Given** <precondition>, **when** <action>, **then** <observable result>.
   _Test:_ `pytest -m unit -k <selector>` (path: `<file>`)

2. ...

## Out of scope

- …

## Open questions (if any)

- …
```

## When to reuse vs. write new

Before proposing new tests, grep `tests/` for an existing test that covers the same surface. If one exists, extend it — note the file and function name in the criterion. New test files should live next to existing ones for the same component.

## Escalate

If the goal touches a human-gate trigger (`live_trading|execute_trade|place_order|auth|SECURITY`), say so explicitly in the output and recommend the user flag the issue as `risk: high`.
