---
description: Triage failing CI checks on a PR — buckets failures (lint/doc-links/test/compose/other) and proposes the minimal fix for each.
argument-hint: <pr-number>
---

Use the `ci-triage` skill. Run `gh pr checks $ARGUMENTS --log-failed` to fetch failing check output for PR #$ARGUMENTS, bucket each failure by type, and propose the minimal fix command for each bucket.
