---
name: triage
description: Triage CI failures on a PR — bucket by type (lint/doc-links/test/compose/other) and propose a minimal fix command for each bucket. Triggers on "triage", "why is CI failing", "fix PR checks", "/triage".
---

# Triage

Use the `ci-triage` skill. The argument is the PR number. If no PR number is given, ask for it before proceeding.

## Steps

1. Run `gh pr checks <PR> --log-failed 2>&1 | head -200` to collect failure output.
2. Follow the `ci-triage` skill instructions to bucket failures and emit the narrowest possible fix command for each bucket.
3. If all checks pass, report success and stop.

## Bucket reference

| Bucket | Signal phrases |
|--------|----------------|
| `lint` | ruff, eslint, prettier, format, import |
| `doc-links` | doc-check, broken link, markdown |
| `test` | pytest, vitest, FAILED, AssertionError |
| `agents-init` | agents_init, idempotent, source file, declaration |
| `compose` | docker compose, healthz, port, connection refused |
| `quality-gate` | /simplify, /review, checkbox, quality gate |
| `other` | anything else |

## agents-init bucket fix

When `agents-init-idempotent` fails, the source file declared in `agents.yml` is missing or the generated file in `.claude/` is out of sync. Fix:

```bash
python3 scripts/agents_init.py --check   # see what's missing
make agents-init                          # regenerate
git add .claude/ agents/sources/
git commit -m "chore(root): sync agents-init generated files"
```
