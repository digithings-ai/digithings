---
description: Generate a GitHub Issue body matching .github/ISSUE_TEMPLATE/agent_task.yml from a goal description.
---

Invoke the `spec-writer` subagent to produce a complete issue body for the following goal. The output must be valid, ready to paste into `gh issue create --body-file`.

After generating the spec, ask the user whether to:
1. Save to a file and run `gh issue create`
2. Edit a section
3. Discard

Goal:

$ARGUMENTS
