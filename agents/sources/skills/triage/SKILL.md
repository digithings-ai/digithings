---
name: triage
description: Triage CI failures on a PR — bucket by type (lint/doc-links/test/compose/other) and propose a minimal fix command for each bucket. Triggers on "triage", "why is CI failing", "fix PR checks", "/triage".
---

# Triage

Fetch CI check results for a PR, bucket every failure by type, and propose the narrowest possible fix command for each bucket.

## Steps

1. **Fetch failed checks.**

   ```bash
   gh pr checks <N> --log-failed 2>&1 | head -200
   ```

   If `--log-failed` returns nothing (all checks pass), say so and stop.

2. **Bucket failures** into exactly one category:

   | Bucket | Signal phrases in output |
   |--------|--------------------------|
   | `lint` | `ruff`, `flake8`, `eslint`, `prettier`, `format`, `import` |
   | `doc-links` | `doc-check`, `broken link`, `markdown`, `mkdocs` |
   | `test` | `pytest`, `vitest`, `FAILED`, `AssertionError`, `ERRORS` |
   | `agents-init` | `agents_init`, `idempotent`, `source file`, `declaration` |
   | `compose` | `docker compose`, `healthz`, `service`, `port`, `connection refused` |
   | `other` | anything that doesn't match above |

3. **For each non-empty bucket**, output:

   ```
   ## <bucket> failures
   <one-line summary of what failed>
   Proposed fix:
   <exact shell command>
   ```

   Fix commands by bucket:

   | Bucket | Fix command |
   |--------|-------------|
   | `lint` | `ruff check . --fix && ruff format .` (Python) or `cd frontend/digichat && npm run lint -- --fix` (TS) |
   | `doc-links` | `make doc-check` then repair the broken link |
   | `test` | `pytest <path>::<test> -v` or `cd frontend/digichat && npm run test -- <file>` |
   | `agents-init` | `python3 scripts/agents_init.py --check && make agents-init && git add .claude/ agents/sources/ .github/copilot-instructions.md .cursor/ && git commit -m "chore(root): sync agents-init"` |
   | `compose` | `make down && make build && make up` then `curl -s http://127.0.0.1:<port>/healthz` |
   | `other` | `gh run view <run-id> --log` |

4. **Never guess.** If the log is truncated or ambiguous, say so and suggest `gh run view <run-id> --log` for the full output.

5. **Human-gate reminder.** If any failure touches `digikey/`, `live_trading`, or `.github/workflows/`, append:
   > Warning: this failure touches a human-gate path. Do not merge without explicit human sign-off.
