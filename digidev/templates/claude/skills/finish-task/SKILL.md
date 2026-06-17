---
name: finish-task
description: Use when implementation is done and the task is ready to commit and PR. Runs simplify → review → score → commit → PR in sequence. Triggers on "finish task", "ready to PR", "wrap up", "close out", "done implementing", "submit PR".
---

# Finish a task

Run this close-out sequence **after** implementation is complete. All steps must pass before the PR is created.

## Sequence

### 1. Simplify

Review the changed files for:
- **Reuse** — any new function that duplicates existing utilities? Flag it.
- **Quality** — redundant state, copy-paste blocks, stringly-typed code, unnecessary nesting (3+ levels), comments that explain WHAT instead of WHY.
- **Efficiency** — redundant computations, missed concurrency (independent ops run sequentially), overly broad file reads.

Fix every non-trivial finding before continuing.

### 2. Review

Use the `pr-reviewer` subagent (if available) or manually review against each rubric in `docs/scoring/`:

| Dimension | Min | Rubric |
|---|---|---|
| Security | ≥ threshold | `docs/scoring/SECURITY.md` |
| Quality | ≥ threshold | `docs/scoring/QUALITY.md` |
| Optimization | ≥ threshold | `docs/scoring/OPTIMIZATION.md` |
| Accuracy | ≥ threshold | `docs/scoring/ACCURACY.md` |

Thresholds are in `agents.yml` → `scoring_thresholds`. Address all findings before continuing.

### 3. Score

```bash
make score
```

Must exit 0. If any dimension fails: read the rubric, apply the narrowest fix, re-stage, re-run. If score fails twice, stop and escalate — do not open the PR with known violations.

### 4. Commit

```bash
make commit MSG="type(component): short description (#N)"
```

Conventional commit format required. Include the issue number.

### 5. PR

```bash
make pr
```

Fill in the PR template's self-score checklist honestly. Check any applicable human gate boxes. Do not merge without human review if a gate is triggered.

## Failure paths

- **Simplify finds issues** → fix, re-stage, continue to review.
- **Review finds issues** → fix, re-stage, re-run score.
- **Score fails once** → fix the narrowest failing criterion, re-stage, re-run.
- **Score fails twice** → stop. Note the blocker. Escalate to a human.
- **`make pr` fails** → check `gh auth status`. Push and PR manually if needed.
