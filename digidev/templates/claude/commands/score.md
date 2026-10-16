Invoke the `score-and-fix` skill on the current staged changes.

Steps:
1. Run `make score`.
2. If it exits 0, report all dimensions passing and suggest `finish-task`.
3. If any dimension fails, read the rubric in `docs/scoring/<DIMENSION>.md`, identify the narrowest fix for each failing criterion, apply it, re-stage, and re-run `make score`.
4. Repeat until exit 0 or until the same dimension fails twice (escalate to human if so).
