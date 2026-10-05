# Review — PR #5134 · `normalize_series` must accept analyzer records (DIG-937)

Reviewed: `8c847bcb6` (the fix) → findings fixed in `3777ca4e7`
Base: `e631d9a32` (L6 / DIG-848, PR #5132) · stacked under L1 / DIG-843 (PR #5126)
Reviewer: fresh-context subagent (`general`), read-only, no fixes; every finding below
reproduced by the author before and after the change.

The branch was rebased onto a rewritten L6 tip while this review was in flight. Shas
before that rebase: the fix was `808f54869`, the fixes-for-this-review were `4c3157fe`,
on a base of `36d49dc95`. Same content — `series.py` and `trades.py` are byte-identical
across the rewrite — and the full gate was re-run green on the new base.

**Verdict: SHIP WITH FIXES** → both majors fixed in `4c3157fe`, both re-verified. Ship.

---

## What the leaf is

`normalize_series` is meant to be the single honest denominator: it decides which points
of a returns/PnL series count toward a sample size, so a rate, a chart and a guard can
never disagree about N. It shipped in DIG-843 (L1) with a **series-only** contract
(`.values`+`.index` → `.to_list()` → `.tolist()` → `list(iterable)`).

Its real caller, `nautilus_runner.py:366-368`, stores the Rust/pyo3
`PortfolioAnalyzer.realized_pnls(USD)` output unconverted: a `dict {position_id: pnl}`
through 1.228.0, `list[(pid, ts_event, pnl)]` on 1.230.0. A `dict` fell through to
`list(series)`, yielded position-id **strings**, `float()` failed on every row, and the
function returned `None` — so `honest_rate.n` was `None` on every build.

The fix recognises records *before* the series probes. `N` = distinct
`(position_id, ts_event)` keys, last occurrence wins, non-finite rows dropped.
`nautilus_runner.py` deliberately untouched.

---

## Findings

### MAJOR 1 — an int row-index was read as an epoch timestamp · FIXED `4c3157fe`

`_record_date` fell back to treating `key` as nanoseconds when `ts_event` was absent, so
**any** 2-column row with a small integer first column became a fabricated epoch date.

```
N([(0,1.0),(1,2.0)])    before  (['1970-01-01','1970-01-01'], [1.0, 2.0])
                      after   (['0','1'], [1.0, 2.0])
N([[1,2],[3,4],[5,6]])  before  (['1970-01-01']*3, [2.0, 4.0, 6.0])
                      after   (['0','1','2'], [2.0, 4.0, 6.0])
```

Impact: `charts/returns.py` and `drawdown.py` bucket those dates, so real history
collapses into a single 1970 bucket. `n` stayed correct, so the honesty guard passed
while the chart was wrong. Not reachable from the analyzer (a `position_id` is a string),
but the pre-change function returned `None` for all three inputs — this was a **new**
wrong-answer path, i.e. the leaf briefly introduced the exact class of defect it exists
to remove.

Fix: `_ns_stamp()` accepts an `int` only at or above `_MIN_NS_STAMP = 1e12` ns (1000 s).
Below that it is a row index, and the row gets a position label.

### MAJOR 2 — three chart builders never called `normalize_series` · FIXED `4c3157fe`

The PR body and the brief both said `charts/trades.py` "already delegates, so it is
corrected by `normalize_series`". True of `_extract_frame` and `count_winning_trades`.
False of `_build_trade_pnl_distribution_chart`, `_build_per_trade_pnl_bars` and
`_build_cumulative_trade_pnl`, which each re-read their input through
`.to_pandas()` → `.values.tolist()` → `.tolist()` → `list(raw)`. On a `dict`,
`.values` is a bound method, so `.tolist()` raised `AttributeError`:

```
before   distribution / per_trade_bars / cumulative_trade_pnl -> ChartUnavailable
after    realized_pnl_chart / distribution / per_trade_bars /
         cumulative_trade_pnl                                 -> Figure   (x4)
```

Not a regression — `trades.py` was byte-identical at base and head — but the claim on the
record was false, and a downstream leaf would have assumed those charts were covered. All
three now go through a shared `_finite_values()` that delegates to `normalize_series`.

### MINOR — `_records_from` checked only `rows[0]` · FIXED

It probed the first row and then reinterpreted *every* row by that shape, so a 4-column
row silently yielded its last element as a PnL. Every row is checked now; an
unrecognised row drops the batch back to the series path, where it fails closed.
`N([('a',1.0),('b',2,3.0),('c',4,5,6)])` → `None` (was a truncated 3-row result).

### MINOR — the `to_list()`/`tolist()` exemption cost was undocumented · FIXED (docstring)

Records wrapped in a numpy array are read as a series and come back `None`. Intentional,
now stated so it is not rediscovered as a bug.

### MINOR — the new "anti-drift locks" compare `normalize_series` with itself · FIXED (comment)

`_model_values` *is* `normalize_series` and `count_winning_trades` *is*
`normalize_series`, so the equality cannot fail unless that one function is wrong. It is
a smoke lock (neither call raises, the result is non-empty), not a two-reader drift lock.
The comment now says so. The pre-existing fabricated-series locks remain the ones that
would catch a real disagreement.

### NIT — no boundary regression test · FIXED

The retracted off-by-one claim was a boundary claim nobody had measured. 1826
exact-midnight-UTC stamps are now pinned.

---

## Claims audit

| Claim | Verdict | Evidence |
|---|---|---|
| The `dict` previously returned `None` | confirmed | base `series.py` loaded from git; real 1.228.0 `realized_pnls` → `{'P-1': 10.0, 'P-2': -4.0, 'P-3': 0.0}` → `None` |
| Nine chart builders were plotting epoch nanoseconds | confirmed | 9 `_extract_frame` call sites: `returns.py` ×6, `equity.py` ×1, `drawdown.py` ×2. Pre-change `count_winning_trades` on a `returns()` dict = 2 of 2, i.e. a −1% return counted as a win |
| `57 passed, 1 skipped` | confirmed | reproduced verbatim in both venvs |
| The one skip is deliberate and required | confirmed | `hasattr(analyzer, "record_trade")` is `False` on 1.228.0; the assertion (`n == 1` after add+record) cannot run on that build |

### My own retracted claim was wrong twice over

I reported an off-by-one-day defect in `_record_date`, then retracted it as my own mental
arithmetic. The conclusion was right; **my retraction's stated arithmetic was also wrong**.

```
delta = 1_700_086_400_000_000_000 - 1_700_000_000_000_000_000
      = 86_400_000_000_000 ns = 86_400 s = 1_440 min = 24 h = one day
```

My retraction wrote "86,400 seconds = 14 minutes 24 seconds". 86,400 s is 1,440 minutes,
not 14 — I divided 1,440 by 100 and kept the digits. So the two fixture timestamps **are**
one day apart, `['2023-11-14','2023-11-15']` is correct, and both the original report and
my retraction of it were wrong. There is no defect; `4c3157fe` changes nothing here.
1826 exact-midnight-UTC stamps are now pinned by a test so this cannot be re-litigated by
hand a third time.

Two arithmetic slips in public comments on one leaf, both on the same two numbers, both
caught only because someone re-ran the computation. The third time will be a test, and
now it is.

---

## Out of scope, stated as opinion

- **Convert at the boundary.** `nautilus_runner.py:366` is the right place to adapt the
  analyzer's output. The duck-typing in `stats/series.py` is the right *interim* fix and
  the wrong end state. That is **DIG-462** (already `in_review` with the Code Reviewer),
  and this leaf correctly did not touch it.
- **`ARCHITECTURE.md` is stale.** The contract changed materially and root `AGENTS.md`
  requires an update after a behaviour change. The file is human-locked and DIG-842's
  exception covers only L8's three sentences, so it cannot ride in this diff. It should
  ride with **L8**, which already edits that paragraph.
- **`//` over `/`.** Cosmetic; provably changes no output here. Left alone.
- **DCO on the base, resolved by someone else mid-review.** The L6 commits carried
  `Co-Authored-By` without `Signed-off-by`, which was the one failing check on PR #5132. The
  L6 branch was rewritten underneath this one during the review round with `Signed-off-by`
  on all five commits, so the gap is closed. That rewrite is also why this branch needed a
  rebase; nothing here was changed to accommodate it.

---

## Gate

```
pytest -m unit tests/dq/test_honesty_series.py tests/dq/test_charts.py
  digiquant venv (nautilus 1.228.0)   62 passed, 1 skipped
  root venv       (nautilus 1.223.0)   61 passed, 2 skipped, 0 failed
pytest -m unit tests/dq/test_tearsheet_honesty.py   22 passed
pytest -m unit tests/dq/test_nautilus_runner.py     27 passed
ruff check + ruff format --check                  All checks passed / 4 files formatted
scripts/generate_ci_path_filters.py --check        ci path filters OK
```

Red/green per commit, all `Signed-off-by`:

| commit | result |
|---|---|
| `021f7c144` test | 13 failed, 44 passed, 1 skipped (pristine `series.py`) |
| `8c847bcb6` feat | 57 passed, 1 skipped |
| `12808bc10` CI wiring + version guard | 57 passed, 1 skipped |
| `3777ca4e7` review fixes | 62 passed, 1 skipped |

The three tests added for the review findings were checked against the pre-fix source
(`git checkout 808f54869 -- stats/series.py charts/trades.py`): **3 failed**, then pass
on `4c3157fe`.

## The one thing outside the leaf's source-file list

`a0e58bce3` edits `.github/workflows/test-nautilus.yml` and `scripts/ci_paths.yaml`. The
analyzer-record tests import nautilus inside the test, so the plain `digiquant / test`
lane — which installs **without** the nautilus extra on purpose, per #42 — collected them
and skipped them, while `nautilus-smoke`, which has nautilus, selected neither test file.
Result: **the leaf's 7 required cases ran in no CI lane at all** — #1501 reached through
`importorskip` rather than a module-level import. The remedy is the two-place rule
`tests/dq/conftest.py` already documents, so both files are listed in both places and
`ci.yml` regenerated.