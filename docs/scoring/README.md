# Scoring Rubrics — DigiThings Agentic Development

Agents use these rubrics to **self-score** code changes before opening a pull request. Scores are honest assessments, not optimistic guesses. The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) references these thresholds.

---

## The Four Dimensions

| Rubric | File | Target Score | Block Merge If |
|--------|------|-------------|----------------|
| Security | [SECURITY.md](SECURITY.md) | ≥ 8 / 10 | < 8 |
| Quality | [QUALITY.md](QUALITY.md) | ≥ 8 / 10 | < 8 |
| Optimization | [OPTIMIZATION.md](OPTIMIZATION.md) | ≥ 7 / 10 | < 7 |
| Accuracy | [ACCURACY.md](ACCURACY.md) | ≥ 9 / 10 | < 9 |

Thresholds match [`agents.yml`](../../agents.yml) `scoring_gate` and root `CLAUDE.md` (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9).

---

## How to Use

1. **Before opening a PR**, read each rubric and evaluate each criterion honestly.
2. **Mark checkboxes** in the PR template for criteria you pass.
3. **Write a short note** for any criterion you cannot pass and explain why it is acceptable.
4. **Do not self-approve** on criteria you are unsure about — leave the checkbox empty and note it.

### Score Bands

| Score | Meaning | Action |
|-------|---------|--------|
| 9–10 | Excellent — meets or exceeds standard | Merge (if CI passes) |
| 7–8 | Good — minor gaps, documented | Merge with note |
| 5–6 | Needs work — gaps that need tracking | Revise or open follow-up issue |
| < 5 | Blocking — do not merge | Fix before PR |

---

## Auto-Merge Eligibility

A PR is eligible for auto-merge (label `automerge-docs`) when:
- It is **doc-only** (paths match policy in `docs/agent-backlog/AUTOMERGE.md`)

A code PR is eligible for reviewer fast-track when:
- All four scores are at or above target
- CI passes
- No human-gate items are checked (no live-trading, auth crypto, or novel architecture changes)

A code PR **requires human review** when:
- Any score is below target
- The PR touches auth, crypto, live-trading, DigiKey signing keys, or DigiClaw execution gates
- Novel architecture is introduced that isn't described in an existing ARCHITECTURE.md

---

## Who Maintains These Rubrics

These rubrics evolve with the codebase. If you discover a new class of bug or anti-pattern that should be scored, add it here and note the rationale. Keep each rubric ≤ 10 criteria so scores remain meaningful.
