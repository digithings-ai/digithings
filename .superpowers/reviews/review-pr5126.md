# Review — PR #5126: DIG-843 L1: normalize_series honest-rate denominator normalizer

- reviewer: Code Reviewer agent (`c59332b4-a0ef-4a6a-8027-5c081486f899`), read-only, fresh-context. Session-level independence: authored none of this diff. gh login `chrizefan` is both PR author and sole write account (the single-maintainer arrangement `AGENTS.md` accepts); the independence that matters is that a distinct session reviewed the code.
- subject: `digithings-ai/digithings#5126`, base `module/digiquant` @ `108ed0882e60cb6cad2baacd1fa7025502efaca8`, head `3f9a6a9ac5f0ae6fabb41792ea8d130f0e28d67b`, branch `task/5116-l1-----honest-rate-normalizer--stats-ser`, author Backend 1 (`84d0c55c` / `chrizefan`), OPEN and not a draft at review time
- epic: leaf L1 of DIG-474; own card DIG-843; card DIG-862
- verdict: **APPROVE-WITH-CHANGES** — not a blocker
- severity counts: Blocker 0 / Critical 0 / Important 2 / Minor 1
- scope: this PR's diff only — 3 files, +181 / −0. Promotion, `module/digiquant` branch policy, and the repo's own coverage-gate implementation are out of scope.
- finding comments: `5994839246` (initial pass), `5995289055` (adversarial challenge pass). Both open with `<!-- in-session-review -->`. Label `reviewed:agent` applied.

> This file was first written into a throwaway review worktree under the run scratch dir and lost when the run scratch was recycled by a harness restart. Re-created here at the repo's existing local convention (`.superpowers/reviews/review-pr<N>.md`). Content is the same record.

## What the change does

New stdlib-only module `digiquant/src/digiquant/stats/series.py` exporting `normalize_series(series) -> tuple[list[str], list[float]] | None`. It duck-types a series (`.values`+`.index` → `.to_list()` → `.tolist()` → plain iterable), keeps only finite floats, pairs them with date strings (index entries truncated to 10 chars for the pandas shape, positional strings otherwise), and returns `None` when the input is `None`, empty, all-null, or when anything at all raises mid-iteration. `stats/__init__.py` gains exactly two lines: the import and the `__all__` entry. No production caller exists yet — that is expected for L1 of a multi-leaf epic.

Its whole point, per the module docstring, is that "a rate, a chart and a guard can never disagree about N". So the denominator must be computed identically no matter which container arrives.

## Diff

```
 M digiquant/src/digiquant/stats/__init__.py   |   2 +
 A digiquant/src/digiquant/stats/series.py      |  62 +
 A tests/dq/test_honesty_series.py              | 117 +
```

Two commits, split test-first:
- `3dcce237897e0a3e6509c3cf961dc15ac7b16e50` test(digiquant): failing cases for normalize_series honest-rate normalizer (DIG-843)
- `3f9a6a9ac5f0ae6fabb41792ea8d130f0e28d67b` feat(digiquant): add normalize_series honest-rate denominator normalizer (DIG-843)

`git merge-base` of the two pinned SHAs is `108ed0882e` — clean linear diff, no creep, no stray files.

## Verification performed (all re-run by the reviewer, not taken on the author's word)

| Command | Result |
|---|---|
| `pytest -m unit tests/dq/test_honesty_series.py` | 11 passed |
| `pytest -m unit tests/dq/test_honesty_series.py tests/dq/test_honesty.py` | 26 passed |
| `ruff check digiquant/src/digiquant/stats/ tests/dq/test_honesty_series.py` | All checks passed |
| `ruff format --check digiquant/src/digiquant/stats/` | 3 files already formatted |
| `dt-gate all --base module/digiquant --allow <3 files>` | PASS, exit 0 |

**TDD order proven, not assumed.** The EM had disclosed on DIG-843 that the failing test could not be pre-committed, so the commit split was the only available evidence. At the test-only commit `3dcce2378`, `stats/` contains no `series.py`, no `normalize_series` export, and `tests/dq/test_honesty_series.py` fails at collection with `ImportError: cannot import name 'normalize_series'`. The red state is real.

**Author's disclosed environment noise reproduced and unrelated.** 68 wide-suite failures occur with and without the branch, all `ModuleNotFoundError: No module named 'pandas'` from digifetch/digillm collection in this worktree's venv; `make test-baseline` errors on 87 collection files for the same reason and gives no signal. `ruff check digiquant/` has 1 pre-existing I001 in `scripts/recover_ledger.py` plus 21 pre-existing format failures, none in these 3 files.

## Frozen required set — intact

All 9 required cases are present, individually named, unmerged, unparametrised, none deleted or weakened, plus 2 additive extras. 11 tests total.

| # | Required case | Test |
|---|---|---|
| 1 | `None` → `None` | `test_none_returns_none` |
| 2 | empty iterable → `None` | `test_empty_iterable_returns_none` (`[]` and `iter(())`) |
| 3 | all-null → `None` | `test_all_null_returns_none` |
| 4 | NaN/`inf` dropped, `inf` never escapes | `test_non_finite_values_are_dropped_and_inf_never_escapes` |
| 5 | pandas shape reads `.values`/`.index`, dates truncated to 10 chars | `test_pandas_shape_reads_values_index_and_truncates_dates` |
| 6 | polars `.to_list()` | `test_polars_shape_uses_to_list_with_sequential_dates` (asserts dates `["0","2"]` around a dropped NaN) |
| 7 | plain list | `test_plain_list_uses_sequential_dates` |
| 8 | generator consumed exactly once | `test_generator_is_consumed_exactly_once` (also asserts `list(generator) == []`) |
| 9 | raising mid-iteration → `None`, never raises | `test_failure_mid_iteration_returns_none_without_raising` |
| + | non-numeric strings as null | `test_non_numeric_strings_are_treated_as_null` |
| + | regex scan pinning no-pandas/no-polars | `test_no_pandas_or_polars_import_in_stats_package` |

Cases 8 and 9 are load-bearing, not smoke tests: 8 proves single consumption by asserting the generator is exhausted afterwards, and 9 passes *only* because the outer guard exists. (Case 9 exercises the plain-iterable branch; a raising `.values`/`.to_list()` shape would take the same outer `try`.)

**Line budget.** 181 lines against a `10 + 11 × 9 = 109` budget. The overage is docstring prose plus three small duck-type fakes (`_FakePandasShape`, `_FakePolars`, the `_exploding()` generator) needed to test the pandas and polars shapes without the banned imports. Author trimmed 243 → 193 → 186 → 181 and stopped rather than cut a required case. **No trim requested.**

## Findings

### Important 1 — `digiquant/src/digiquant/stats/series.py:20`, `OverflowError` collapses the whole series to `None`

`_finite_or_none` catches only `(TypeError, ValueError)`:

```python
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
```

`float()` also raises `OverflowError`. That escapes the helper, is swallowed by the outer `except Exception: return None`, and returns `None` for the **entire** series instead of dropping the one bad point.

Reproduced (stdlib only, no pandas/polars/numpy needed):

```
normalize_series([1.0, 2.0, 10**400])   -> None        # expected (['0','1'], [1.0, 2.0])
float(10**400)                          -> OverflowError: int too large to convert to float
```

Same for `2**2000` and `Fraction(10**500, 1)`, and for any object whose `__float__` raises. Controls that behave correctly and drop only one point: `nan`, `inf`, `Decimal('1e400')`, `'abc'` → all `(['0','1'], [1.0, 2.0])`. (`Decimal('1e400')` converts to `inf`, which `math.isfinite` already catches — only raw big `int` hits `OverflowError`.)

**Reachability (first pass asserted this; the challenge pass measured it).** Polars genuinely cannot produce the value — `pl.Series([1.0, 2.0, 10**400])` raises at construct and `read_json` raises `ComputeError` — so the `.to_list()` branch is unreachable. The reachable branch is the pandas one, and it holds via **object-dtype** numpy (verified with real numpy 2.5.3):

```
np.array([0.01, 10**400, -0.02])                -> dtype object, holds the raw int
normalize_series(Shape(that_array, dates))     -> None
normalize_series(Shape(nan_in_same_slot, ...)) -> (['2024-01-01', '2024-01-03'], [0.01, -0.02])
```

A float64 array converts it to `inf`, which `math.isfinite` already catches, so it is specifically the object-dtype case that bites. `json.loads` also yields arbitrary-precision `int` for any caller that feeds parsed JSON.

**Why Important and not Critical.** The honesty layer contains it: `wilson()` returns `None` for `n <= 0`, and both the `guards.refused` branch and the `w is None` branch render `REFUSED — n < 10 (n=0)`. Worst case is a false refusal / a lost rate, never a fabricated percentage. L1 also has no production caller yet.

**Fix.** Add `OverflowError` to the except tuple. **Regression test:** `normalize_series([1.0, 2.0, 10**400]) == (["0", "1"], [1.0, 2.0])`.

### Important 2 — `digiquant/src/digiquant/stats/series.py:16`, the `bool` guard disagrees with `_extract_frame` about N

This was filed as a dismissed curiosity in the first pass. That was wrong — it was compared only against `normalize_series`, never against the function it is meant to replace. `charts/common.py::_extract_frame` (`digiquant/src/digiquant/charts/common.py:14`, imported by `charts/{equity,returns,drawdown,trades}.py`) casts via `pl.Series(...).cast(pl.Float64, strict=False)`, and polars maps `Boolean → Float64` to `1.0/0.0`, so the reference **keeps** bools while this normalizer **drops** them (`series.py:16`, `if value is None or isinstance(value, bool): return None`).

Measured side by side against the real `_extract_frame`:

| input | `_extract_frame` | `normalize_series` |
|---|---|---|
| `pl.Series([True, False, True])` | `n=3` `[1.0, 0.0, 1.0]` | `n=0` `None` |
| `[True, False]` | `n=2` `[1.0, 0.0]` | `n=0` `None` |
| `[1.0, True, 2.0]` | `n=3` `[1.0, 1.0, 2.0]` | `n=2` `[1.0, 2.0]` |

The guard is also container-dependent — the same logical boolean series gives three different denominators depending on which branch fires:

```
list(np.array([True]))[0]    -> numpy.bool_ -> kept as 1.0
np.array([True]).tolist()[0] -> bool        -> dropped
pl.Boolean.to_list()[0]       -> bool        -> dropped
```

This is the finding that matters most, because the module's stated purpose is that "a rate, a chart and a guard can never disagree about N". A denominator disagreement between this function and `_extract_frame` is exactly the failure the epic exists to prevent, and it fires as soon as L2+ migrates `_extract_frame` callers here.

**Fix.** Drop the `isinstance(value, bool)` guard, or make the bool decision dtype-aware and container-independent.

### Minor 1 — `tests/dq/test_honesty_series.py:113`, the no-pandas guard stops at the first subpackage

```python
offenders = [p for p in Path(stats_pkg.__file__).parent.glob("*.py") ...]
```

`glob` is non-recursive. Demonstrated in a scratch dir: with pandas imported in both `top.py` and `sub/mod.py`, `glob` finds only `top.py`; `rglob` finds both. `stats/` is flat today (`__init__.py`, `honesty.py`, `series.py`), so the guard holds now and the pandas rule is independently enforced by the `digiquant/AGENTS.md` allowlist and `ruff`. Real but latent, and it is one of the two extras beyond the 9 required cases — hence Minor, not Important.

The regex itself is sound: it catches `import pandas`, `import polars as pl`, `from polars import DataFrame`, indented imports and `import pyarrow`, while correctly ignoring prose and the module's own docstring.

**Fix.** `glob("*.py")` → `rglob("*.py")`.

## Mutation testing — four mutants, four survivors

The real test file was run against four source mutants. All four leave the suite green:

| mutant | result |
|---|---|
| delete the `bool` guard | 11 passed — **survives** |
| delete the `.tolist()` branch | 11 passed — **survives** |
| `zip(strict=True)` → `strict=False` | 11 passed — **survives** |
| add `OverflowError` to the except tuple | 11 passed — **survives** |

- `series.py:45-46` (`elif hasattr(series, "tolist")`) is **never exercised** — `grep -n tolist tests/dq/test_honesty_series.py` returns nothing. A numpy array is exactly the object with `.tolist()` that is not a polars Series, so this is the branch real callers hit. Worth a test in the follow-up.
- `zip(..., strict=True)` at `series.py:54` is unpinned, but a gap rather than a defect: for length mismatches (3v2, 2v3), 2-D values and a `pl.DataFrame`, both implementations fail closed to `None`. (`_extract_frame` raises polars `ShapeError`; `normalize_series` raises `ValueError`; both land on `None`.)
- The last row means **no test covers Important 1 either**, hence the proposed regression test.

These gaps sit *in addition to* the 9 frozen required cases; none of them is fake or mergeable away, and no required case needs to be deleted or weakened.

## Verified clean

- `stats/__init__.py` is +2 lines, export only: `from .series import normalize_series` after the `.honesty` block (correctly alphabetised) and `"normalize_series",` in `__all__`. Nothing else touched.
- The duck-type order matches the historical `_extract_frame` exactly — the author's claim on that point is true.
- `normalize_series` is stdlib-only; no pandas/polars/pyarrow import anywhere in `stats/`.
- `normalize_series` has no production caller at head (`git grep` finds only the definition, the export, and the test) — expected for L1.
- Minor non-finding: the author reported `ruff format --check` reporting "4 files already formatted"; I measured 3. Cosmetic, no action.

## Not in scope (governance observations about the repo's own gate, not findings against this PR)

1. `scripts/check_review_coverage.py:281` `_agent_review_from_comments` matches `AGENT_REVIEW_MARKER` anywhere in a body and keeps the **last** match. The author's own comment `5993456145` quotes `in-session-review`, so it satisfies the findings-comment half of the hatch by itself — the marker is not anchored to the start of a body.
2. The documented direct-push hatch (marker + the commit's 8-char sha) looks effectively unreachable: `_sha_mentioned_in` searches `repo:… <8-hex-sha> in:comments`, and GitHub's index returns **0 results for bare 8-char hex tokens** — a long-standing sha `108ed088` also returns 0, while an ordinary word ("overflow") from the same comment returns 35. That is tokenization, not the eventual-consistency lag the helper's docstring anticipates.
3. Running the promotion gate over `108ed0882e..3f9a6a9a` prints ❌ for both commits because `resolve_pr_number` → `associated_pr_number` returns `None` while #5126 is unmerged. Expected pre-merge, not a review failure — these commits have a source pull request, and per `AGENTS.md` they are judged by #5126's own state, which is satisfied.

## Disposition

Approve with changes. Three mechanical fixes on the author's branch: `OverflowError` in the except tuple, `glob` → `rglob`, and align the bool behaviour with `_extract_frame`. Per repo policy ("fix what the review finds on the same branch before merge"), Backend 1 fixes all three on this branch and pushes. Re-review is a new loop, not part of card DIG-862.

The card was closed **done**, not `blocked`: no blocker was found, and the two severity halves of the definition of done (`<!-- in-session-review -->` findings comment + `reviewed:agent` label) are both satisfied.
