# QA mutation evidence — DIG-2383 (PR #5232 test kit at `dbbbcc9fb`)

Companion to `docs/agents/REVIEW-pr-5232-test-kit-dbbcc9fb.md`.

**Reproduce.** Run from the author's worktree
(`.paperclip/worktrees/DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync`,
HEAD `dbbbcc9fb`) with
`PYTHONPATH="$PWD/digiquant/src:$PWD/digibase/src:$PWD/digikey/src:$PWD/digidata/src"`.

- `mut.py` / `mut2.py` — the harness. Applies one edit from a batch JSON, runs the suite,
  reverts with `git checkout --`. `mut2.py` additionally parses `FAILED <nodeid>` lines so a
  verdict records *how many* tests caught the mutant, not just that one did.
- `g1-g7.json` — batch 1, the 12 mutants for G1–G7 plus controls.
- `batch2.json` — batch 2, 12 mutants for the two open items.
- `batch3a.json`, `batch3b.json` — batches 3a and 3b, 19 mutants over the shared helpers
  (`causal_rolling_z`, `align_to_dates`) and every family's sign flip.
- `*.results.json` — harness output, one verdict per mutant.

**Equivalent-mutant adjudication.** Every survivor was checked for equivalence before being
named a gap. That discipline is the correction to the G6 mistake, where an equivalent mutant
was reported as a test gap.

- `g6_equiv_check.py` — G6. 144 claim-checks. Result: 0 observable. G6 was my bad finding.
- `batch3a_survivor_check.py` — CZ4 (equivalent), AD4 (equivalent), AD1 (real, G9).
- `fcv3_check.py`, `fcv3_where.py` — G11. Not equivalent: first non-null 26 -> 21, 64
  differing positions.
- `fcv_sign_check.py`, `g8_actionable.py` — G8 root cause, then the search for an assertion
  that passes the original and rejects the sign-flip mutant.
- `on2_log_check.py` — G10 root cause.

Every mutation was reverted immediately. The author's worktree was `TREE CLEAN` at `dbbbcc9fb`
before, during and after.
