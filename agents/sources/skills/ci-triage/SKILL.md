---
name: ci-triage
description: Use when the user wants to investigate a failing CI run, diagnose PR check failures, or get fix suggestions for broken checks. Triggers on "/triage <pr-number>", "why is CI failing", "fix CI on PR N", "what failed on PR N".
---

# CI Triage

Given a PR number, diagnose all failing checks and propose the minimal fix command for each bucket.

## Workflow

1. Fetch failed check output:
   ```bash
   gh pr checks <PR> --log-failed 2>&1
   ```
   If `--log-failed` is unsupported by the installed gh version, fall back to:
   ```bash
   gh pr checks <PR> 2>&1
   ```

2. Parse the output and bucket each failure into one of:
   - **lint** — ruff errors, import issues, format violations
   - **doc-links** — broken internal markdown links (`make doc-check` failures)
   - **test** — pytest failures (unit or e2e)
   - **compose** — Docker Compose build or service startup failures
   - **agents-drift** — `scripts/agents_init.py --check` drift detected
   - **other** — anything that doesn't fit the above

3. For each bucket with failures, propose the **minimal** fix command:

   | Bucket | Proposed fix |
   |--------|-------------|
   | lint | `ruff check . --fix && ruff format .` |
   | doc-links | `make doc-check` (read output, fix broken links manually) |
   | test | `make test-unit` — read failures, fix the specific test or code |
   | compose | `make build` — read the Docker error, fix Dockerfile or config |
   | agents-drift | `make agents-init` — regenerate from `agents.yml` + `agents/sources/` |
   | other | Paste the raw error block and propose a targeted fix |

4. Summarize findings in this format:
   ```
   PR #<N> — <N> failing check(s)

   [lint] <check-name>
     Fix: ruff check . --fix && ruff format .

   [test] <check-name>
     Fix: make test-unit  (see failure: <test name>)

   [agents-drift] <check-name>
     Fix: make agents-init
   ```

## Constraints

- Never mark a check as passing if the raw output shows it failed.
- Do not propose fixes that modify protected paths (`SECURITY.md`, `.github/workflows/`, `docs/scoring/`) unless on a `task/N-*` branch.
- For **test** failures: read the specific test output to identify the failing assertion before proposing a fix — do not just say "run the tests".
- For **other** bucket: paste the first 40 lines of raw error output so the user has context.

## Related

- `/score` — score staged changes before pushing.
- `pr-reviewer` subagent — rubric-aware review after CI passes.
- `make agents-init` — fixes agents-drift bucket.
- `make doc-check` — validate internal markdown links.
