---
name: score-and-fix
description: Use when the user asks to score their changes, check if a diff is PR-ready, run the scoring gate, or fix scoring failures. Triggers on "score this", "ready to commit", "run score", "pass the gate", "fix scoring".
---

# Score and fix

The project enforces a 4-dimension scoring gate before every PR:

| Dimension | Threshold | Rubric |
|-----------|-----------|--------|
| Security | ≥8 | `docs/scoring/SECURITY.md` |
| Quality | ≥8 | `docs/scoring/QUALITY.md` |
| Optimization | ≥7 | `docs/scoring/OPTIMIZATION.md` |
| Accuracy | ≥9 | `docs/scoring/ACCURACY.md` |

Runner: `make score` (wraps `python3 scripts/score.py --staged`).

## Workflow

1. Run `make score-delta` first. This compares staged changes against the `origin/develop` baseline per dimension and exits non-zero if any dimension regressed (even if still above the pass threshold). Fix any regression before continuing.
2. Run `make score`. If exit 0 — done, changes are PR-eligible; tell the user.
3. If any dimension fails, for each failing dimension:
   a. Read the corresponding `docs/scoring/<DIMENSION>.md` rubric.
   b. For each finding (file + line + description), propose the **narrowest** fix that satisfies the rubric. Do not bundle unrelated refactors.
   c. Apply the fix, re-stage, re-run `make score`.
4. If score still fails after two iterations, stop and escalate per `docs/agents/AGENT_WORKFLOW.md`. Do not keep trying — repeated failures mean the change is structurally wrong or the rubric needs discussion.

## Common false positives

- **`Any` in type hints inside library wrappers** is often unavoidable — add `# noqa` with a one-line reason.
- **`TODO` in docs or templates** (e.g., `.github/PULL_REQUEST_TEMPLATE.md`) is expected; ignore when the file is a template.
- **`pd.` in a comment discussing pandas** is a false positive; move the mention outside a code block or rename the variable.
- **`live_trading` in a doc explaining the human-gate regex** (e.g., `agents.yml`, `docs/scoring/SECURITY.md`) is expected; the hook still blocks actual edits to live-trading paths on non-task branches.

## Escalation

Any true-positive finding in dimension **Security** that the user wants to override must have a `Human-Approved-By: <name>` trailer in the commit. Quality / Optimization / Accuracy can be discussed; Security cannot.

## Related

- `make score-delta` — regression detector; run first to catch slippage vs develop.
- `/score` — slash-command shortcut.
- `pr-reviewer` subagent — use after scoring passes for a second-pass review before opening the PR.
