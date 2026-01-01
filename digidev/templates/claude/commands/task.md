Invoke the `worktree-task-start` skill for the issue number the user provides.

Steps:
1. Confirm the issue number from the user's message (ask if not supplied).
2. Run the pre-flight checklist: check for existing worktree, fetch origin, confirm base branch is current.
3. Run `make task ISSUE=<N>`.
4. After the worktree is created, read `{component}/AGENTS.md` and `{component}/ARCHITECTURE.md`.
5. Confirm the test suite is green on the fresh branch.
6. Begin the red/green/refactor loop using the `test-first-implementer` agent.
