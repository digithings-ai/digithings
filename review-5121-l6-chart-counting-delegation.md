# In-session review — L6 chart path delegates counting to `normalize_series`

| | |
|---|---|
| **Subject** | PR #5132 — `feat(digiquant): delegate chart path counting to normalize_series (DIG-848)` |
| **Branch** | `task/5121-l6-----chart-path-delegates-counting-to-` → `module/digiquant` (stacked on #5126) |
| **Tracking issue** | #5121 (leaf L6 of DIG-474, lane M) |
| **Reviewed revision** | `2802bd4e2` (fixes in `e631d9a32`) |
| **Reviewer** | independent fresh-context read-only subagent (`general`, session `ses_ef36f2e1fffeHJ2XrbU7q9Ut0n`). The author session did not review its own work. |
| **Verdict** | **APPROVE AFTER FIXES** — 0 blocker / 3 major / 2 minor / 2 nit; both majors fixed in `e631d9a32`, the minor that mattered fixed, nits addressed, one minor deliberately left open and stated |

> **Not committed, by design.** The L6 brief allows exactly three files
> (`charts/common.py`, `charts/trades.py`, `tests/dq/test_charts.py`). This file is
> deliberately left untracked so the PR diff stays inside that scope; the findings
> also live on the PR as the `<!-- in-session-review -->` comment, which is what the
> coverage gate reads.

## Summary

The delegation itself is correct and the reviewer could not break it. The weak part was the
**test locks**: two of the four required anti-drift cases did not actually pin what they
claimed, and three plausible regressions survived the required cases *and* the wider two-file
suite.

## Shas changed after the review

The DCO sign-off gate (`.github/workflows/ci-dco-sign-off.yml`) requires a `Signed-off-by`
trailer on every commit in the PR range. None of the five had one, so the stack was rebased
with `--signoff` and force-pushed after the review completed. The patches are byte-identical
(`git patch-id --stable` matches for all five: `3dcce2378`→`3ad034f1b`, `3f9a6a9ac`→`0714d0c73`,
`6f7bfac70`→`829ea9b9f`, `36d49dc95`→`2802bd4e2`, `adabbae27`→`e631d9a32`); only the trailers
differ. Every finding below applies unchanged to the content under the new shas.

## Findings and resolutions

| # | Sev | Finding | Resolution |
|---|---|---|---|
| MAJOR-1 | major | `tests/dq/test_charts.py:389` `_MESSY` held no `0.0`, so `sum(1 for v in values if v > 0)` was indistinguishable from `>= 0`. Mutant M2 survived the wider suite. A breakeven trade is a more realistic input than `inf`, and the flip inflates the win numerator while the denominator still counts the zero — exactly the chart-vs-model drift this leaf exists to prevent. | **Fixed in `e631d9a32`.** `_MESSY` gained a trailing `0.0`; new `test_breakeven_trade_is_not_a_win` pins `[1.0, 0.0, -1.0] == 1` and `[0.0, 0.0] == 0`. M2 now **caught** (5 failed). |
| MAJOR-2 | major | Cases 1 and 3 compared dates by `len` only, so dropping `normalize_series`' `[:10]` truncation (M5) or reversing date order (M6) both survived. The fixture used `datetime.date`, whose `str()` is already 10 chars, making the truncation a no-op that could not fail. `charts/returns.py` parses this column with `%Y-%m-%d, strict=False` and silently drops unparseable rows, so losing the truncation makes monthly and yearly charts vanish on a real `DatetimeIndex`. | **Fixed in `e631d9a32`.** `_MESSY_DATES` is now tz-aware `datetime` (25 chars, like a real `pd.Timestamp`); the expected dates are written out as **literals** (`_KEPT_DATES` / `_KEPT_POSITIONS`) because a lock that compares the chart path only against `normalize_series` moves on both sides when the normalizer changes. M5 and M6 now **caught**. |
| MAJOR-3 | major | Line-budget overrun unstated. Budget is `10 + 11 × 4 = 60` changed lines; the diff was 88 added / 44 removed. | **Fixed.** Stated in the PR body and in the `e631d9a32` commit message, with the new number (128 added / 44 removed) and the reason. No required case was deleted or weakened to fit. |
| MINOR-1 | minor | `count_winning_trades` None conditions changed for two unrealistic inputs: a bool series (`[True, False, True]`: old `2` → new `None`, because `_finite_or_none` rejects `bool`) and a ragged list (`[1.0, [2.0, 3.0]]`: old `None` → new `1`, because bad elements are now dropped individually instead of failing the whole cast). | **Open, deliberately.** A 31-class differential showed every realistic shape byte-identical old vs new, including date values and schema. Not a live regression, out of the line budget, and not pinned either way. Flagged to L7 / DIG-937 as known input-contract drift. |
| MINOR-2 | minor | `_extract_frame` returned `None` via an incidental `TypeError` from unpacking `normalize_series(None)`, not by explicit design. | **Fixed in `e631d9a32`.** The None path is now explicit. Reverting it is an *equivalent mutant by construction* (both paths return `None`), so no test can distinguish it — the edit is for clarity, not behaviour, and the PR says so rather than claiming a test covers it. |
| NIT-1 | nit | `# pragma: no cover` sat on the `raise` line while the sibling `test_tearsheet_honesty.py:212` puts it on the `def`. Reviewer verified under coverage.py that both placements exclude correctly. | **Fixed in `e631d9a32`.** Moved to the `def` line with a comment matching the sibling. |
| NIT-2 | nit | Case 3 had no hardcoded expected count, so in isolation it was self-consistency only. | **Fixed in `e631d9a32`.** `_SHAPES` now carries literal `(rows, dates, wins)` per shape. |

## Verified, not defects

- **Import direction is clean**, proven two ways: an AST walk over all of `digiquant/stats/`
  finds no `digiquant.charts` import, and at runtime `import digiquant.stats` leaves
  `'digiquant.charts'` absent from `sys.modules`. No cycle.
- **`_build_win_rate_donut` untouched**, as required — its wrong `n` is L7's call-site fix.
  The `trades.py` diff is a single hunk `@@ -12,27 +12,22 @@` covering only the import and
  `count_winning_trades`.
- **The delegation preserves the old contract** for every shape charts actually receive: a
  31-class differential against the pre-L6 implementation reconstructed from `0714d0c73`
  (None, empty, floats, None/NaN/±inf, all-junk, ints, numeric strings, non-numeric,
  generator, tuple, set, polars incl. nulls, `to_list`-over-`tolist` priority, and 8
  pandas-shape variants) is byte-identical, dates included, schema
  `{date: Utf8, value: Float64}` throughout. Only the two MINOR-1 classes differ.
- **Dropping `count_winning_trades`'s own `try/except` is safe** — `normalize_series` has an
  internal `except Exception`, and `sum()` over finite floats cannot raise (checked with
  `10**400` and `Decimal("1e999")`).
- **Case 4 is genuinely load-bearing**: routing either function through `.to_pandas()` is
  caught, because the `_NoPyarrow` fixture offers no other escape hatch.
- **No scope violation.** Only the three allowed files changed; `test_tearsheet_honesty.py`
  and `test_nautilus_runner.py` diffs are 0 lines, so `TestHonestStatusOnExtractionFailure` is
  not extended and no real Nautilus engine is loaded.
- Nothing is tautological: the calibration mutant "always return None" **is** caught (8 failed).

## Mutation spot-checks after the fixes

Re-run with a module-path probe (a mutant tree on `pythonpath`, a copy with `__pycache__`
cleared, and an assertion that the loaded module really is the mutant) — otherwise a run
reports false survivors.

| Mutant | Result |
|---|---|
| C0 unmutated copy (must pass) | 55 passed |
| M2 `count_winning_trades`: `>= 0` instead of `> 0` | **caught** (5 failed) |
| M5 `normalize_series`: drop the `[:10]` date truncation | **caught** (1 failed) |
| M6 `_extract_frame`: reverse the date order | **caught** (4 failed) |
| M11 revert the explicit `None` check | survives — equivalent mutant, see MINOR-2 |
| C1 calibration: always return `None` | **caught** (8 failed) |

## Gates

- `uv run --frozen pytest -m unit tests/dq/test_charts.py tests/dq/test_tearsheet_honesty.py` → **55 passed**
- `ruff check` + `ruff format --check` on the three touched files → clean
- `make test-baseline` → fails identically on a pristine `origin/module/digiquant`
  worktree (345 vs 347 collection errors, a pytest duplicate-basename import mismatch in
  two files that are byte-identical to base). Pre-existing, out of scope.
