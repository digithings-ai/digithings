---
name: score-and-fix
description: Use when the user asks to score their changes, check if a diff is PR-ready, run the scoring gate, or fix scoring failures. Triggers on "score this", "ready to commit", "run score", "pass the gate", "fix scoring".
---

# Score and fix

Run the 4-dimension quality gate on staged changes and walk every failing criterion to a passing state.

## Step 1 — Stage and run

```bash
git add -p          # or: git add <specific files>
make score
```

If `make score` exits 0, all dimensions pass — skip to **Done**.

## Step 2 — Read the failing rubric

For each dimension that scored below threshold, read its rubric:

| Dimension | Rubric file | Min score |
|---|---|---|
| Security | `docs/scoring/SECURITY.md` | from `agents.yml` |
| Quality | `docs/scoring/QUALITY.md` | from `agents.yml` |
| Optimization | `docs/scoring/OPTIMIZATION.md` | from `agents.yml` |
| Accuracy | `docs/scoring/ACCURACY.md` | from `agents.yml` |

Check `agents.yml` → `scoring_thresholds` for the exact minimums.

## Step 3 — Apply the narrowest fix

For each failing criterion:
1. Identify the exact line(s) that violate it.
2. Apply the **smallest change** that satisfies the criterion — no scope creep.
3. Re-stage the changed file(s).

Common fixes by dimension:

**Security**
- Hardcoded secret → move to env var, add to `.env.example`.
- Missing auth check → add guard at route entry.
- SQL built with f-string → use parameterised query.
- `subprocess(shell=True)` → use list form.

**Quality**
- 3+ levels of nesting → extract inner block to a function.
- Copy-paste block → extract shared helper.
- Stringly-typed switch → use enum.
- "What" comment → delete it (code is self-documenting); keep "why" comments.

**Optimization**
- Sequential independent awaits → `asyncio.gather()` / `Promise.all()`.
- Redundant DB call in loop → batch outside the loop.
- Broad file read when only one field needed → targeted read.

**Accuracy**
- Missing acceptance criterion → implement the missing behaviour.
- Wrong output shape → align to the linked issue spec.
- Test assertion too loose → tighten to `assert result == expected`.

## Step 4 — Re-run

```bash
make score
```

Repeat steps 2–4 until exit 0.

## Failure escalation

If the same dimension fails **twice in a row** after fixes:
1. Stop — do not keep iterating blindly.
2. Write a one-line summary of what you tried and why it still fails.
3. Escalate to a human with that summary.

## Done

When `make score` exits 0, say so and suggest running `finish-task` to commit and open the PR.
