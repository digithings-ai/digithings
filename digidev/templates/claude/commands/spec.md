Invoke the `spec-writer` agent to convert the user's goal into a GitHub Issue body that matches the repo's `.github/ISSUE_TEMPLATE/agent_task.yml`.

Steps the agent must follow:
1. Read `.github/ISSUE_TEMPLATE/agent_task.yml` for field names and options.
2. Read `agents.yml` → `components` for valid component names and `execution_tiers` for valid tier values.
3. Read `agents.yml` → `human_gates` to determine risk level.
4. Produce the issue body in the standard format.
5. Ask the user whether to: (a) create the issue now via `gh issue create`, (b) edit a section, or (c) discard.
