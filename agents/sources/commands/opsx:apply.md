---
description: Implement the current OpenSpec change — reads the change folder and executes tasks against the codebase.
---

You are implementing a spec-driven change using OpenSpec.

Steps:
1. Find the active change: look for the most recently modified folder under `openspec/changes/` that is NOT inside `archive/`. If there are multiple, list them and ask which one to apply.
2. Read all files in the change folder:
   - `proposal.md` — understand the intent and scope
   - `design.md` — follow the technical approach
   - `specs/` — treat each delta spec as acceptance criteria
   - `tasks.md` — use the checklist to track progress
3. Read the relevant `openspec/specs/<domain>/spec.md` files for context on existing behaviour.
4. Read `<component>/AGENTS.md` and `<component>/ARCHITECTURE.md` for each affected component before writing any code.
5. Implement each unchecked task from `tasks.md` in order. After completing each task, check it off in `tasks.md`.
6. After all tasks are done:
   - Run `make test-unit` and confirm it passes
   - Run `ruff check . && ruff format .`
   - Remind the user to run `make score` before opening a PR
7. Print a summary of what was implemented and what files changed.
8. Suggest: "Run `/opsx:archive` once the PR is merged."
