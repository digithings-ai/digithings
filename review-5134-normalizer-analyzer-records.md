# Review — PR #5134 · `normalize_series` must see analyzer records (DIG-937)

Reviewer: **fresh-context subagent, PR #5134** — adversarial pass, did not write this code
Subject (commits reviewed): `021f7c144` · `8c847bcb6` · `12808bc10` · `3777ca4e7` · `98becb57b` · `542141db6`
Base: `e631d9a32` (`task/5121-l6-----chart-path-delegates-counting-to-`, PR #5132 / DIG-848)
Head reviewed: `542141db6`

**Verdict: SHIP.** `VERDICT: BLOCKERS=0`

Severity counts: **0 blocker · 0 important · 4 minor · 2 nit**

> An earlier review artifact (`98becb57b`) covered the pre-fix head `8c847bcb6` and raised
> two majors. Both are fixed in `3777ca4e7` and both were re-verified fixed by measurement
> (see "Re-verification of the earlier findings"). This pass is a **fresh, independent**
> review of the current head, re-deriving every claim from the engine rather than trusting
> either artifact. It supersedes the earlier one; that record remains in history at
> `98becb57b`.

---

## The defect, and whether it was real

`normalize_series` is the single honest denominator. Its only production caller,
`nautilus_runner.py:364-368`, stores pyo3 analyzer output **unconverted**:

```python
result["returns_series"]       = analyzer.returns()          # nautilus_runner.py:364
rp = analyzer.realized_pnls(USD)
result["realized_pnls_series"] = rp if rp is not None and len(rp) > 0 else None
```

Measured on the installed build, neither is a series — both are plain `dict`s:

```
>>> analyzer.realized_pnls(USD)   ->  {'P-1': 10.0, 'P-2': -4.0, 'P-3': 0.0}     (dict)
>>> analyzer.returns()            ->  {1700000000000000000: 0.03, 1700086400000000000: -0.01}
```

Under the pre-fix function a `dict` fell through to `list(series)` (a dict has `.values`
but no `.index`, which is the only thing that saved the old duck-typing), yielding position-id
strings; `float()` failed on every row and the function returned `None`. Loaded the base
file from git and confirmed:

```
base series.py + a real 1.228.0 realized_pnls dict  ->  None
base series.py + the new tests                      ->  15 failed, 47 passed, 1 skipped
```

So `honest_rate.n` was `None` on **every** supported build — an absent envelope rather than
a guarded one. The defect is real and the fix direction (recognise records before the series
probes) is right.

## The `returns()` claim, verified by measurement

The PR body says `returns()` listed into its keys yields epoch nanoseconds, "so every row
counted as a win". That is exactly right, and it was a **false public win rate**, not a
cosmetic issue:

```
returns()                    = {1700000000000000000: 0.03, 1700086400000000000: -0.01}
OLD normalize_series(returns) -> (['0','1'],   [1.7e+18, 1.7000864e+18])   n=2 k=2  win_rate=100.0%
NEW normalize_series(returns) -> (['2023-11-14','2023-11-15'], [0.03, -0.01])  n=2 k=1  win_rate=50.0%
```

A −1% return was being counted as a win, on the path feeding `charts/returns.py` (6
`_extract_frame` call sites), `equity.py` (1) and `drawdown.py` (2).

## End-to-end, on real engine output

Built a real tearsheet through `create_tearsheet()` with a genuine analyzer's
`realized_pnls()` and `returns()` as input, and compared base vs head:

| | plotly figures rendered | chart sections broken |
|---|---|---|
| base L6 (`e631d9a32`) | 14 | 15 |
| head (`542141db6`) | **22** | **0** |

All 13 chart builders return a real `Figure` on real analyzer input (9 on `returns()`,
4 on `realized_pnls()`). The 3 remaining `chart-unavailable` hits in the HTML are CSS
class *declarations*, not failures — confirmed by locating each occurrence in context.

And the point of the leaf, end to end:

```
engine dict  {'P-1': 10.0, 'P-2': -4.0, 'P-3': 0.0, 'P-4': 2.5}
k=2  n=4  ->  estimate=0.5  CI=(0.150, 0.850)  refused=True
donut centre: "REFUSED  n=4"
```

Before the fix `k` was `None`, so that envelope did not exist. It does now, with a real
denominator.

---

## Findings

### MINOR 1 — a 2-column row still fabricates a value if the number is *not* last

`_records_from` (`digiquant/src/digiquant/stats/series.py:84`) reads
`row[-1]` as the value for both widths. A 3-column `(pid, ts_event, pnl)` row is
unambiguous. A 2-column row is not: it could be `(pid, pnl)` or `(pid, ts)`, and a
nanosecond `ts_event` is an `int`, so type does not disambiguate. On the `pid, ts` reading:

```
normalize_series([("P-1", 1_700_000_000_000_000_000)])
  -> (['0'], [1.7e+18])        a fabricated PnL of 1.7e18, counted as a win
```

**Not reachable** — no build in reach emits 2-column rows (verified: 1.223.0 and 1.228.0
both return `dict`; the 1.230.0 shape per the brief is 3-column). The author declares this
openly in the PR body and asks for the EM's ruling, which is the right handling.

Why it is still a finding: every other ambiguous input in this module **fails closed**
(unhashable key → `None`, 4-column row → `None`, no finite values → `None`). This one path
instead invents a number. It is the single place the module can produce a wrong answer
rather than an absent one, and the blast radius is the honesty guard itself. Fail closed
on 2-column rows until a build emits them and the shape is known — or keep last-column and
say so in the docstring rather than only in the PR body.

### MINOR 2 — a repeated key in a 2-column row silently drops an observation

`_from_records` (`series.py:101`) keys the collapse on `(key, ts_event)`. For a
2-column row `ts_event` is always `None`, so the key degenerates to `key`:

```
normalize_series([("P-1", 10.0), ("P-1", -3.0)])  ->  (['0'], [-3.0])     n=1, not 2
```

Two rows, two real observations, one counted. Same unreachability as MINOR 1 — 1.223/1.228
return a `dict`, which the engine has already keyed by pid, so the engine collapses it
itself (measured: `add_trade` twice on one pid → `{'P-1': -3.0}`). It is a consequence of
MINOR 1 rather than an independent defect, and both disappear together if 2-column rows are
rejected or pinned to a known reading.

### MINOR 3 — a plain list of 2/3-element tuples is now a record, where it used to be nothing

`_records_from` (`series.py:84`) accepts any bare iterable whose rows are 2- or 3-element
tuples/lists. A list whose *values* happen to be pairs is now read as records:

```
                                  OLD      NEW
xy pairs      [(0.5,0.7),(0.6,-0.2)]  None  (['0','1'], [0.7, -0.2])
ohlc rows     [(1,2,3),(4,5,6)]      None  (['0','1'], [3.0, 6.0])
list-of-lists [[1,2],[3,4]]          None  (['0','1'], [2.0, 4.0])
```

The change is from *fail closed* to *fabricate*. I checked every producer of the only two
values that reach this function — `returns_series` and `realized_pnls_series`, both set at
`nautilus_runner.py:364`/`368` and consumed only by `charts/` — and **no caller passes a
list of tuples**, so this is latent rather than live. It is worth finding because
`normalize_series` is a shared helper with a growing caller set, and the widening is
silent. The docstring already discloses the *opposite* cost (records inside a
`to_list()`/`tolist()` container come back `None`); disclosing this direction too would
close the contract.

### MINOR 4 — `except Exception` now also swallows record-path failures, whole-series

`normalize_series` wraps everything in `except Exception: return None`
(`series.py:176`). That is pre-existing and defensible for a chart boundary. Two
record-path consequences, both fail-closed and both worth knowing:

```
unhashable key   normalize_series([([1,2], 1_700_000_000_000_000_000, 10.0)])  -> None
malformed sibling normalize_series([("P-1", ns, 10.0), ("P-2",)])            -> None
```

One bad key or one malformed sibling discards **every** good row, so a single unusual
position id takes the honest denominator from *guarded* to *absent* — the exact regression
this leaf exists to prevent. Not reachable from the analyzer (position ids are strings), and
the alternative (partial results) would be worse for a denominator. Recording it so the
choice is a decision rather than an accident; the record path has its own narrow guards
(`_record_date` catches `OverflowError/OSError/ValueError`) and could reasonably narrow
the blanket catch the same way.

### NIT 1 — `ts_event` is assumed to be nanoseconds, unvalidated

`_record_date` divides by 1e9 with no unit check. Wrong-unit input produces a plausible
but wrong date rather than a rejection:

```
nanoseconds  1.7e18 -> 2023-11-14   (correct)
microseconds 1.7e15 -> 1970-01-20
millis       1.7e12 -> 1970-01-01
seconds      1.7e9  -> 1970-01-01
```

Correct for every reachable build (nautilus `ts_event` is `UnixEpochNano` throughout), and
`n`/`k` are unaffected — this is a chart-axis label only. `_MIN_NS_STAMP` already rejects
small ints, so the residual risk is a *large* wrong-unit stamp.

### NIT 2 — `digiquant/ARCHITECTURE.md` is not updated

Root `AGENTS.md` requires `{component}/ARCHITECTURE.md` to be updated after an interface or
behaviour change, and this changes `normalize_series`'s input contract materially
(0 occurrences of the record-shape contract in that file today). The file is human-locked
and DIG-842's recorded exception covers only L8's three sentences, so it cannot ride in
this diff. The author's routing — land it with L8, which already edits that paragraph — is
correct, and it is the reason this is a nit and not an important.

---

## Verified as correct, having been doubted

- **`k > n` is structurally impossible.** `k` is `#{v > 0}` computed over the same
  `values` list whose length is `n`. Tried to force it with repeated pairs where the last
  occurrence flips sign — n=1, k=1 at every variation. No input found.
- **A round trip cannot be double-counted.** Two `add_trade` calls on one pid, measured on
  the real 1.228.0 engine, collapse in the engine itself: `{'P-1': -3.0}`. On the 1.230.0
  literal rows, `("P-1", ts, 10.0), ("P-1", ts, 7.0)` → `[7.0]`, n=1.
- **Breakeven is a loss.** `pnl == 0.0` does not count; mutation M9 below turns 7 tests red.
- **`None`/empty never becomes a fabricated zero.** `None`, `{}`, `[]`, `iter(())`, an
  analyzer with no trades (`realized_pnls` → `None`) all → `None`. Never `num_trades`.
- **Non-finite rows are dropped on the record path**, and the engine genuinely cannot emit
  one: `add_trade(pid, Money(nan))` raises `ValueError: invalid f64 for 'amount', was NaN`.
  So the literal NaN fixture is the only way to reach that branch — correctly pinned.
- **An iterable is consumed exactly once**, including the generator case, where the shape
  probe could have eaten the first record before values were read.
- **No pandas/polars/pyarrow import in `stats/`** — the module still imports only `math`,
  `datetime`, `typing`.
- **`strict=True` zip behaviour is unchanged**; the record path returns before the zip.
- **`_MIN_NS_STAMP` is well calibrated.** The floor is 1000 s, so it rejects row indices
  while accepting any real date: 1999-01-01, 2001-01-01 and 2023-01-01 all normalise
  correctly. The engine does accept sub-floor stamps (`add_position_return(500, …)` stores
  key `500`), and those correctly fall back to a position label rather than `1970-01-01`.
- **`bool` is excluded** from both `_finite_or_none` and `_ns_stamp` — it is an `int`
  subclass, and `True` would otherwise become `1970-01-01T00:00:01`.
- **Absurd and negative stamps are handled.** `10**30` → `None` via `OverflowError`;
  negative → a real pre-epoch date; `float` stamps → `None` (not a silent int coercion).
- **The author's claim that the pre-existing anti-drift lock could not fail is correct.**
  With the dict guard removed, the *pre-existing* `test_anti_drift_lock_holds_for_every_series_shape`
  (all 3 params) still passes, because both sides delegate to the one function that is
  blind; only the new `test_anti_drift_lock_holds_for_analyzer_built_records` fails. Two
  mutually blind readers cannot fail a lock between them.
- **Case 4's skip reason is accurate on both installed builds.** `hasattr(analyzer,
  "record_trade")` is `False` on 1.223.0 *and* 1.228.0, and no attribute containing
  "record" exists on either.
- **Case 4's body is correct on a build that has `record_trade`.** Simulated a 1.230
  analyzer (3-arg `add_trade`, `record_trade`, `realized_pnls` returning 3-tuples):
  all three assertions pass, and the recorded `4.0` is the value that survives.
- **The `_add_trade` arity probe cannot mask a real error.** On a 3-arg build each trade
  costs 6 calls (a failed 2-arg, then a 3-arg) but the failed call adds nothing, so N is
  unaffected; and non-arity errors propagate — a NaN amount raises `ValueError`, which
  `except TypeError` does not catch.
- **Last-occurrence-wins survives the unfurled counterfactual.** If a 1.230 build returned
  *both* rows for an add+record pair rather than folding them, last-wins still yields the
  recorded value and still collapses to n=1. The divergence is safe under both readings.

## The two declared divergences, judged

**1. "Recorded-wins precedence" → last-occurrence-wins.** The author's argument holds. A
returned row carries no provenance for whether it came from `add_trade` or `record_trade`,
so no implementation can distinguish them from the return value alone. 1.223/1.228 key by
pid and collapse in the engine (measured above); on 1.230 the engine folds `add_trade` into a
later `record_trade`, so a repeated pair reaching this function means `record_trade` ran
twice — and last-wins is right there too, since the later call is the current truth. I
could not construct a case where last-wins silently loses a recorded value. **Correct call,
correctly declared.**

**2. The 2-column row read as `(key, value)` with the number last.** The author states this
is an unverifiable assumption and asks for a ruling. On reachability they are right: no
build in reach emits 2-column rows, and last-column is the only reading consistent with both
reachable shapes (`(pid, pnl)` and `(ts, return)`). **But I would have it fail closed
instead** (MINOR 1) — not because last-column is likely wrong, but because an unreachable
guess that produces a fabricated `1.7e18` win is the wrong default for a module whose whole
purpose is refusing to invent a number. Reject 2-column rows until one is observed.

## Non-vacuity experiments

Every mutation was applied to a **copy** of the source in a scratch tree outside the
worktree, with `-o pythonpath=…` so the mutated copy is the module under test (the repo's
`pytest.ini` sets `pythonpath`, which otherwise wins over `PYTHONPATH` — verified by
printing `digiquant.stats.series.__file__` from inside pytest). Restored via a saved copy and
confirmed green after each.

| # | mutation | result |
|---|---|---|
| M1 | dict guard removed (`isinstance(series, dict)` → `False`) | **6 failed**, 56 passed, 1 skipped |
| M2 | dedupe by `key` alone (DIG-920's false "one row per position id") | **15 failed**, 47 passed, 1 skipped |
| M3 | first-occurrence-wins instead of last | **1 failed**, 61 passed |
| M4 | fabricate an empty series instead of `None` (req-5 violation) | **4 failed**, 58 passed |
| M5 | 3-column value from `row[0]` instead of `row[-1]` | **10 failed**, 52 passed |
| M6 | date back to `str(ts_event)[:10]` | **4 failed**, 58 passed |
| M7 | `_MIN_NS_STAMP` floor removed (regresses the 1970 fix) | **1 failed**, 61 passed |
| M8 | all-rows `_records_from` weakened back to first-row-only | **1 failed**, 61 passed |
| M9 | `count_winning_trades` `> 0` → `>= 0` (breakeven becomes a win) | **7 failed**, 55 passed |

Red baseline for the whole defect: base-L6 `series.py` + the current tests →
**15 failed, 47 passed, 1 skipped**.

Worktree verified clean afterwards (`git status --porcelain` empty, HEAD `542141db6`); all
scratch files removed.

## Required cases

| # | case | verdict | note |
|---|---|---|---|
| 1 | engine dict → n=len(dict), k=count(pnl>0) | **satisfied** | real analyzer on 1.223.0 *and* 1.228.0; M1 red |
| 2 | one row per distinct `(pid, ts_event)` | **satisfied** | M2 red (15 failures); distinct-ts rows give n=3 |
| 3 | repeated pair counts once, last wins | **satisfied** | M3 red; both the literal rows and the real engine |
| 4 | recorded trade replaces the added one | **satisfied where reachable** | skip reason verified accurate on both builds; body verified by simulation (3/3 assertions) |
| 5 | breakeven is a loss | **satisfied** | M9 red (7 failures, incl. `test_breakeven_trade_is_not_a_win`) |
| 6 | `None`/empty never a fabricated zero | **satisfied** | M4 red |
| 7 | guarantees survive the record path | **satisfied** | M1/M2/M5 red; NaN fixture is the only reachable form and is pinned |

## Gate

```
pytest -m unit tests/dq/test_honesty_series.py tests/dq/test_charts.py
  digiquant venv (nautilus 1.228.0)   62 passed, 1 skipped
  root venv       (nautilus 1.223.0)   61 passed, 2 skipped
     (2nd skip: add_position_return absent on 1.223.0)
pytest -m unit tests/dq/test_tearsheet_honesty.py test_nautilus_runner.py test_honesty.py
                                      64 passed
ruff check + ruff format --check      All checks passed / 4 files already formatted
scripts/generate_ci_path_filters.py --check   ci path filters OK
```

Two real nautilus builds are installed and both are green (1.223.0 and 1.228.0) — a genuine
cross-version check, since the leaf's whole premise is a version-dependent return type.
1.230.0 is CI-only and cannot be checked locally.

## Re-verification of the earlier findings

Both majors from `98becb57b` were re-tested from scratch against `542141db6`:

- **MAJOR 1 (fabricated 1970 dates from a row index)** — fixed. `normalize_series({1: 10.0})`
  and `[(1, 10.0)]` now return `(['0'], [10.0])`, a position label. `_ns_stamp` +
  `_MIN_NS_STAMP` is the fix and M7 confirms it is load-bearing.
- **MAJOR 2 (three builders never delegated)** — fixed, and I found this independently
  before reading the earlier artifact. `_build_trade_pnl_distribution_chart`,
  `_build_per_trade_pnl_bars` and `_build_cumulative_trade_pnl` all returned
  `ChartUnavailable` on the real engine dict before `3777ca4e7` and return `Figure` now, via
  the shared `_finite_values()` that delegates to `normalize_series`. The earlier claim that
  `charts/trades.py` "already delegates" was indeed false for three of five builders.

## Out of scope, stated as opinion

- **Convert at the boundary.** `nautilus_runner.py:364-368` is the right place to adapt
  analyzer output; the duck-typing in `stats/series.py` is the right interim fix and the
  wrong end state. The brief forbids touching that file here, and that is the right call.
- **CI files are outside the brief's allowed list, and are justified.** `12808bc10` edits
  `.github/workflows/test-nautilus.yml`, `.github/workflows/ci.yml` and
  `scripts/ci_paths.yaml`. Without them the 7 required cases would execute in **no CI lane**
  at all: the tests `importorskip` nautilus inside the test body, so the plain lane (no
  nautilus extra, by design per #42) collects them and skips them, while `nautilus-smoke`
  selected neither file. This is exactly the two-place rule `tests/dq/conftest.py:36-40`
  documents for #1501, and both places are updated. Verified:
  `generate_ci_path_filters.py --check` passes.
- **`542141db6` is a genuine CI-only fix**, not churn: widening the lane exposed that
  `test_charts.py` called the 2-arg `add_trade`, which fails on the 1.230.0 that
  `uv.lock` installs for that lane. Probing the arity (as `test_honesty_series.py` already
  did) is right and better than pinning a version `pyproject.toml` deliberately leaves open
  (`nautilus_trader>=1.190,<2`).
- **Merging.** Stacked on `task/5121-l6-…` (PR #5132), which is itself unreviewed, so this
  cannot be merge-ready until the stack below lands. Not my call to make.

## Recommended before merge

Nothing blocking. Two cheap improvements if the author wants them: reject 2-column rows
until one is observed (MINOR 1, which also removes MINOR 2), and document the
tuple-as-value widening in the `normalize_series` docstring alongside the already-documented
container-exemption cost (MINOR 3).
