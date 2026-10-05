# Review — Phase 3 Task 6 image bake

- Reviewer: fresh-context subagent (claude-opus), not the author session
- Subject: `task/4761-phase3-image-bake` vs `origin/develop` @ `088be9545`
- First commit reviewed: `358276693`
- Verdict on that commit: request changes (0 blocking)
- Severity: blocking 0, medium 1, low 3, informational 1

## Findings

1. Medium — `.github/workflows/pipeline-digiquant.yml` header said the clock is already digithings-cron → digiquant-runner. House jobs are still `repository_dispatch` until the cron flip. Fixed in the follow-up commit: the header now says the production clock is still `repository_dispatch`, and forbids adding `schedule:`.
2. Low — dockerignore re-include order was presence-only. The test now requires the two `!` lines to follow the `.github` exclude.
3. Low — Dockerfile needles for `config/byok-providers.json` and the pipeline file were bare substrings. They now require the `COPY` lines.
4. Low — `--inexact` also keeps `psycopg[binary]` from the research extra. Noted in the Dockerfile header.
5. Informational — `exec_job_test.py` still calls production `/healthz` during the suite. Pre-existing, not this diff.

Hard locks held: one `[[containers]]`, `DigiQuantRunnerContainer`, `standard-2`, `max_instances = 1`. No cron edit, no secrets, no deploy.
