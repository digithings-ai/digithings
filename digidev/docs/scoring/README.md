# Scoring rubrics

Every PR is scored on four dimensions before it can be merged. Agents self-score using these rubrics. The PR template's self-score checklist reflects these dimensions.

Run `make score` to see your current scores against staged changes.

| Dimension | File | Default minimum |
|---|---|---|
| Security | [SECURITY.md](SECURITY.md) | 8/10 |
| Quality | [QUALITY.md](QUALITY.md) | 8/10 |
| Optimization | [OPTIMIZATION.md](OPTIMIZATION.md) | 7/10 |
| Accuracy | [ACCURACY.md](ACCURACY.md) | 9/10 |

Thresholds are configured in `agents.yml` under `scoring_thresholds`.

## How scoring works

Each rubric has 10 criteria. Each criterion is worth 1 point. Score = number of criteria met.

Score yourself **honestly**. An inflated score that sneaks past review costs more to fix later than a low score that prompts a targeted fix now.

A criterion that is **not applicable** (N/A) to your change still counts — mark it as met (the criterion is satisfied by the absence of the issue). Only mark criteria as unmet when they apply and you know you haven't satisfied them.

## Common failure patterns

**Security < 8:** Missing input validation on a new endpoint, hardcoded secret found, new route missing auth check, error message leaks internal detail.

**Quality < 8:** New behavior without a test, removed symbol still referenced elsewhere, new file over 400 lines, missing type annotations on public interface.

**Optimization < 7:** N+1 query in a loop, blocking I/O in an async handler, redundant LLM calls that could be cached.

**Accuracy < 9:** Output doesn't match the spec in the issue acceptance criteria, existing test broken, state machine transition incorrect, API contract changed without versioning.
