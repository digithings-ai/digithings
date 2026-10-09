# Fresh-context review — PR #5134, commits `19baa0c31`…`30c1f9757`

- **Reviewer:** subagent (fresh context, did not author this code)
- **Subject:** the board ruling (a) and the #5126 union carried onto this branch
- **Head reviewed:** `53f6a58cc8` (the two fixes for review 2's findings are inside it)
- **Worktree:** `.worktrees/task/937-l1-corrective`, branch `task/937-l1-corrective-normalizer-sees-analyzer-records`
- **Scope:** two narrow single-question reviews, run as separate sessions so neither anchors on the other.
- **Verdict:** review 1 (union commits) **CLEAN, 0 blockers**. Review 2 (the ruling's ordered steps) **BLOCKER — the ruling's test file was untracked — plus one false docstring claim. Both findings are now fixed and verified; see Review 2 below.

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

**Reviewer:** subagent, fresh context. **Verdict returned: BLOCKER** — one blocker and one false claim, both fixed. The mutations all came back CAUGHT, so the blocker was not a gap in the tests: it was that the tests were not in the repository.

### The blocker — `tests/dq/test_honesty_series.py` was untracked

The reviewer ran the mutants twice: once against the file on disk, and once against **only the tracked digiquant tests** that CI was actually selecting (`test_charts.py`, `test_honesty.py`, `test_tearsheet_honesty.py`).

```
against this file on disk     pristine 41 passed;  a,b,e -> 3 failed;  c -> 1 failed;  d -> 1 failed
against the tracked set only  73 passed  for every mutant, including all five
```

So the ruling's semantics were sound and its tests killed all five mutants — and none of that was enforced, because `git ls-files --error-unmatch tests/dq/test_honesty_series.py` failed. `CI` selected that path from `scripts/ci_paths.yaml`; every mutation the ruling exists to prevent would have merged green.

**Cause, established from timestamps rather than guessed.** `5b7160bc3` (a docstring-only commit) recorded `D` for that path and nothing else. The working copy was on disk the whole time: its mtime is `15:26:13` and the commit is stamped `15:26:28`, fifteen seconds later, and the on-disk file differed from `a88e6b55e` by exactly the docstring hunk that commit was meant to contain. The file was present, so this was not a missing file — the index did not carry the path at commit time. I cannot reconstruct which command did that from the repository, and I am not going to invent one.

**Fixed** in `2d61ffaebf`: the file is restored byte-for-byte and tracked. `git ls-files --error-unmatch` now succeeds, the tracked test count is back to 532, and the four mutants were re-run against the **tracked tree** to confirm coverage is real rather than restored-on-paper:

| mutation | against this file (now tracked) | against the three pre-existing tracked files |
|---|---|---|
| M1 sum before dedupe | **4 failed**, 37 passed | 0 failed, 73 passed |
| M2 dedupe keeps first | **3 failed**, 38 passed | 0 failed, 73 passed |
| M4 first leg's stamp | **3 failed**, 38 passed | 0 failed, 73 passed |
| M5 no summing | **6 failed**, 35 passed | 0 failed, 73 passed |

### The false claim — the position date is input order, not chronology

The `_from_records` docstring justified the label with *"a position's realized PnL is only complete when the final leg closes"*, but `stamps[key] = ts_event` overwrites per record, so the **last row in the input** wins regardless of timestamp. Measured: rows in event order give `2023-11-15`; the same rows reversed give `2023-11-14`. Both engine builds that emit `ts_event` emit rows in event order, so the divergence is latent, not live.

**Fixed** in `53f6a58cc8`: the docstring now says input order, and `test_a_summed_position_is_labelled_by_input_order_not_by_timestamp` pins it with literal rows and no analyzer, so it runs in every lane including the one that installs without the nautilus extra. Red confirmed — changing the code to `max(ts_event, ...)` fails it. Sorting was **not** chosen: which of the two a caller wants is a labelling decision this leaf was not given, and the ruling was about the denominator.

### Reviewer's other measurements, accepted as reported

- Both board-required tests present and correct. `test_case_9` fails on pre-ruling code with `assert 3 == 2` on `len([6.0, 4.0, -5.0])` — the exact prediction the EM made when answering card `622e0016`.
- Reading rules hold on a fixture with two winning legs cancelling to `0.0`, a `0.0` row, a negative row and a repeated pair: `n=5`, `k=2` computed by production's own `count_winning_trades`, `k <= n`, summed zero uncounted, repeated pair taking the recorded value.
- `honest_rate(6, 5)` raises `ValueError`, so `k > n` cannot render.
- The 1.228.0 shapes the docstrings cite were verified against the real build: `realized_pnls` → `dict`, `returns()` → `dict` of ns→float, `record_trade` absent. All three local skips are genuine 1.230.0-only gates.

### Residual, recorded not fixed

- `normalize_series` ends in `except Exception: return None`, so a bug in either ruling step would present as an **absent** denominator rather than a wrong one. Fail-closed is right and `honest_rate` refuses on `n=0`, so nothing is fabricated — but a regression would degrade silently in production.
- `_build_win_rate_donut` clamps `wins = min(num_trades, max(0, num_wins))`, which would shrink `k` rather than surface a disagreement if the rate path and the chart path ever diverged again.

### Severity counts

| Severity | Count |
|---|---|
| blocker | 1 (found by review, fixed in `2d61ffaebf`) |
| important | 0 |
| minor | 1 (found by review, fixed in `53f6a58cc8`) |
| nit | 0 |

### Disposition

**APPROVE.** Review 1 was already CLEAN. Review 2's two findings are both fixed and both verified red-then-green. Two residuals above are recorded rather than fixed, for the reasons given.
