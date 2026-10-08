# Fresh-context review — PR #5134, commits `19baa0c31`…`30c1f9757`

- **Reviewer:** subagent (fresh context, did not author this code)
- **Subject:** the board ruling (a) and the #5126 union carried onto this branch
- **Head reviewed:** `30c1f9757`
- **Worktree:** `.worktrees/task/937-l1-corrective`, branch `task/937-l1-corrective-normalizer-sees-analyzer-records`
- **Scope:** two narrow single-question reviews, run as separate sessions so neither anchors on the other.
- **Verdict:** review 1 (union commits) **CLEAN, 0 blockers**. Review 2 (the ruling's ordered steps) **in flight at the time of writing — no verdict recorded, deliberately.**

---

## Review 1 — the union commits `89e812f03` + `0e64f6f63`

### Question asked

Do the two Important findings from the #5126 review actually hold fixed on this branch, do the carried tests mean the same thing they meant there, does the rate path still agree with the chart path about N, and can the narrowed `add_trade` arity gate swallow a genuine engine `TypeError`?

### Findings, measured

**Finding 1 — a raw big `int` no longer nulls the whole series.** `[0.01, 10**400, -0.02]` → `(['0', '2'], [0.01, -0.02])`. Two rows survive, the labels stay aligned to the rows that were kept, and the unrepresentable row is the only one dropped. Red against the unmodified parent: **3 failed, 1 passed**.

**Finding 3 — bools are kept as 1.0/0.0.** `[True, False, True]` → `(['0', '1', '2'], [1.0, 0.0, 1.0])`.

**The carried tests mean the same thing here as on #5126.** `_finite_or_none` differs from `2d89cddba` by **one hunk of docstring prose; not one byte of executable code differs.** The four carried tests differ from their originals by **one added docstring line — no assertion changed.**

**The rate path and the chart path agree about N, 14/14.** Compared `len(normalize_series(x)[1])` against `_extract_frame(x).height` over polars Boolean / Float64 / Int64 / with-NaN / with-inf, numpy `bool_` / `float64` / `int64`, plain python bool lists, both analyzer dict shapes, and 1.230-style row lists. **0 disagreements.** `_extract_frame` delegates — `"normalize_series" in _extract_frame.__code__.co_names` is true — so the agreement is structural, not coincidental.

**The arity gate cannot swallow a genuine engine `TypeError`.** The only `try`/`except` in the whole test file is at lines 160/162, wrapping the 3-argument `add_trade` call, and the 2-argument fallback sits **lexically outside** it. A `TypeError` raised while converting a position id or timestamp therefore propagates and fails the test loudly rather than being absorbed into a skip.

Its one residual, stated as fail-safe rather than defect: a future build with a *variadic* `add_trade` signature would produce a **false skip** — reported as skipped, never a silent pass.

### Severity counts

| Severity | Count |
|---|---|
| blocker | 0 |
| important | 0 |
| minor | 3 (all documentation) |
| nit | 0 |

### Disposition

**APPROVE.**

One of the three minor findings was a false statement about the code and is **fixed** in `30c1f9757` (docstring only): `test_bools_are_kept_as_one_and_zero_in_every_container` claimed `charts/common.py::_extract_frame` casts with polars `strict=False`. That cast was removed in `2802bd4e2` — the chart path delegates to `normalize_series` now — so the disagreement the docstring described is history, not a live mechanism. Rewritten to say so.

The other two are prose-only and would require rewriting commits CI has already reported on: a commit message whose pass/skip counts describe the two-file run rather than the module, and the carried test text differing by one added docstring line. Declined deliberately.

---

## Review 2 — the ruling's ordered steps, `19baa0c31` + `4a663234a`

**No verdict is recorded here because none has returned.** The review was asked to:

- mutation-test `_from_records` five ways — sum-before-dedupe, dedupe-keep-first, keep-partial-total, first-leg-date, no-summing — and record for each whether the committed tests **catch** it (fail) or **miss** it (pass);
- check the reading rules: `n` is the number of closed positions, `k` counts positions whose summed value is `> 0`, a summed `0` is a loss, `k <= n` holds by construction;
- confirm both board-required tests exist and **fail against pre-ruling code** (`4a663234a~1`);
- hunt false docstring claims in the changed files.

This is the review of the most significant commits in the leaf. It is owed before the leaf is called reviewed, and this section will be filled in when it returns — not before.
