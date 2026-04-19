---
description: Triage CI failures on a PR — bucket by type (lint/doc-links/test/compose/other) and propose a minimal fix command for each bucket.
---

Use the `ci-triage` skill. The argument after `/triage` is the PR number. If no number is given, ask the user for it before proceeding.

Invoke as: `/triage <pr-number>`

Steps:
1. Run `gh pr checks <pr-number> --log-failed` to collect failure output.
2. Follow the ci-triage skill instructions to bucket failures and emit fix commands.
3. If all checks pass, report success and stop.
