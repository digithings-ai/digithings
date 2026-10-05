# Fresh-context review — PR #5134, commit `93807d0cf`

- **Reviewer:** subagent (fresh context, did not author this code)
- **Subject:** `93807d0cf` — "test(digiquant): pin the engine's real 3-column row, not just a literal (DIG-937)"
- **Parent:** `a79d4eb17` (reviewed previously, BLOCKERS=0)
- **Worktree:** `.worktrees/task/937-l1-corrective`, branch `task/937-l1-corrective-normalizer-sees-analyzer-records`
- **Scope:** one added test function `test_the_engine_really_emits_three_column_rows_with_a_real_timestamp` (39 lines) plus the commit message. Nothing else.
- **Verdict:** **APPROVE** — 0 blockers, 0 important, 2 minor, 2 nit

The test does what it says. The central claim was measured, not inferred, and it is true.
The commit message's numbers all reproduce. Nothing in the delta is wrong.

---

## Severity counts

| Severity | Count |
|---|---|
| blocker | 0 |
| important | 0 |
| minor | 2 |
| nit | 2 |

---

## Environment verification (done first, because two hazards were flagged)

**Import resolution — the root `conftest.py` is NOT what repoints the mapping.** It is a
one-line docstring (`conftest.py:1`: `"""Root conftest: optional path setup. Packages are
found via venv editable install."""`). The actual mechanism is `pythonpath` in `pytest.ini:5`,
which prepends `<worktree>/digiquant/src` to `sys.path`. That is why the venvs' editable
installs do not win. Measured, not assumed — a probe test printed `series.__file__` under
each build:

```
1.223.0  ->  /Users/chrisstefan/Code/digithings/.worktrees/task/937-l1-corrective/digiquant/src/digiquant/stats/series.py
1.228.0  ->  (same worktree path)
1.230.0  ->  (same worktree path)
```

All three suites load **this worktree's** source. This corrects the hazard note in the review
brief, not the commit.

**`__pycache__` hazard was real and was honoured.** `rm -rf tests/dq/__pycache__ .pytest_cache`
was run before every single run below, including every mutation probe. The repo does have a
live `digiquant/src/digiquant/stats/__pycache__` that I also cleared when mutating
`series.py`.

---

## Q1 — Is the central assertion true, and did I measure it?

**Yes, and I measured it directly.** I did not run the test and infer; I interrogated the
engine on all three builds:

```
1.223.0  type=dict   value={'P-1': 10.0}                     record_trade=False  add_position_return=False
1.228.0  type=dict   value={'P-1': 10.0}                     record_trade=False  add_position_return=True
1.230.0  type=list   value=[('P-1', 1700000000000000000, 10.0)]
        row type=tuple  len=3  col types=['str', 'int', 'float']
        record_trade=True   add_position_return=True
        add_trade doc: "Records a trade's PnL realized at `ts_event`."
```

So the commit message's measured block is accurate: `list[(str, int, float)]` on 1.230.0,
middle column exactly the `ts` stamped, `dict {pid: pnl}` on 1.223.0/1.228.0, and the
`add_trade` 3-arg form. The `pnl == 10.0` assertion also holds — the third column is the
money value, not the timestamp.

## Q4 — Do the commit message's claims match what reproduces?

**Every number reproduces.** The gate counts are stated without naming the file selection, so
I brute-forced the selection across all combinations of the five candidate files on all three
builds. Exactly one combination matches all three rows:

```
pytest tests/dq/test_honesty_series.py tests/dq/test_charts.py -q

1.223.0 -> 62 passed, 3 skipped     (author: 62 passed, 3 skipped)   MATCH
1.228.0 -> 63 passed, 2 skipped     (author: 63 passed, 2 skipped)   MATCH
1.230.0 -> 65 passed                (author: 65 passed, 0 skipped)   MATCH
```

(For the record, the three-file set `test_honesty.py test_honesty_series.py
test_tearsheet_honesty.py` gives 63/64/66 — a different, equally green gate. The author did
not miscount; they just did not record the selection. That is the M1 below.)

Also confirmed: `normalize_series` really is the downstream consumer the commit message names
— `digiquant/src/digiquant/charts/trades.py:26,42` and `charts/common.py:26` feed
`realized_pnls_series` into it, and `nautilus_runner.py:367` is where that series is produced.
The "catches it before the denominator silently empties" framing is accurate.

## Q2 — Can this test pass vacuously?

**Not on 1.230.0 — the build where it actually asserts anything.** The guard at
`test_honesty_series.py:251` only fires on `dict`, and `raw` is a `list` there, so no skip
path is taken. I attacked it two ways.

**a) Reverting each assertion, as the commit message claims.** Three of the four I could
reproduce exactly; the fourth is mis-stated (M2 below):

| Mutation | Result |
|---|---|
| `len(row) == 3` -> `== 2` (line 256) | FAILS — confirmed |
| expected date `"2023-11-14"` -> `"1970-01-01"` (line 264) | FAILS — confirmed |
| skip guard removed, on 1.228.0 | FAILS — confirmed (`isinstance({'P-1': 10.0}, list)` is False) |
| skip guard removed, on 1.223.0 | FAILS — confirmed (same reason) |
| `ts_event == ts` weakened to bare `assert ts_event` (line 259) | **PASSES** — see M2 |

**b) Would it still bite if `normalize_series` regressed?** This is the question that matters
most, because the leaf exists to prevent an *absent* denominator. I mutated the source under
the test:

| Mutation to `series.py` | Result |
|---|---|
| records path removed entirely (the DIG-843 state) | FAILS — `TypeError: cannot unpack non-iterable NoneType` |
| `ts_event` column ignored, date falls back to row index (line 132) | FAILS |
| `/` instead of `//` in `_record_date` | PASSES at this stamp — **expected**, see N2 |

The `/`-vs-`//` pass is not a hole in this test: `ts = 1_700_000_000_000_000_000` is an exact
whole second, where float and floor division agree by construction. The parent's
`test_day_boundaries_round_trip_at_the_nanosecond_edges` is what covers the sub-256ns window.
Two functions, two jobs — the split is correct.

**c) Engine-side regressions.** I substituted a fake `raw` to simulate what a future nautilus
might emit. Every dangerous shape fails loudly:

```
2-column list  [("P-1", 10.0)]                     -> FAILS
4-column row   [("P-1", ts, 10.0, 1)]              -> FAILS
empty list     []                                  -> FAILS
columns swapped [("P-1", 10.0, ts)]                -> FAILS
None                                                -> FAILS
dict (regression to old shape)                       -> SKIPS  <- M1
```

That last row is the one real finding below.

## Q3 — Is the skip correct on 1.223.0/1.228.0?

**Yes, and it should stay.** Those builds genuinely have no rows to pin — I measured
`dict {'P-1': 10.0}`. Asserting a 3-tuple against a dict would assert a shape the build does
not have, which is precisely the kind of fiction this module exists to prevent.

Nor does the skip leave the dict path untested: `test_case_1_engine_dict_shape_counts_every_row`
(`test_honesty_series.py:171`) and `test_case_1_records_dict_does_not_fall_through_to_its_keys`
(`:184`) both run on all three builds and cover it. The gate confirms it —
1.223.0 has 3 skips, and they are the two pre-existing build-capability skips plus this one.
The skip is narrow and correctly scoped.

---

## Findings

### M1 (minor) — a regression to `dict` on 1.230.0 silently skips instead of failing

`tests/dq/test_honesty_series.py:251-252`

```python
if isinstance(raw, dict):
    pytest.skip(f"this build returns a dict, not record rows: {type(raw).__name__}")
```

The guard keys on the *shape*, not on the *build*. On 1.230.0/1.228.0/1.223.0 that is the
right discriminator today, but if a future nautilus reverted 1.230.0 to the dict shape, this
test would **skip on the one build that is supposed to prove the row exists** — and the
regression would be invisible except as a skip count nobody reads.

Evidence — I forced `raw = {"P-1": 10.0}` on 1.230.0:

```
SKIPPED [1] test_honesty_series.py:252: this build returns a dict, not record rows: dict
1 skipped
```

Contrast every other regression shape, which fails loudly (table in Q2c). So the test is
strictly weaker against exactly the regression the commit message says it exists to catch
("A future nautilus that changes the row width fails here rather than silently emptying the
denominator").

Not a blocker: on that build `normalize_series`'s dict path is independently covered by
`test_case_1`, and `nautilus_runner.py:368` already coerces an empty series to `None`, so a
dict regression does not empty the denominator — the honesty guarantee holds via another
route. This is about the test's stated contract, not about production behaviour.

Suggested fix (optional, author may decline):

```python
import nautilus_trader
if isinstance(raw, dict) and tuple(map(int, nautilus_trader.__version__.split(".")[:2])) < (1, 230):
    pytest.skip(...)
```

or simpler and version-free: assert the build *can* produce rows rather than inferring it from
the shape it happened to return.

### M2 (minor, commit-message only) — the "ts_event is the ts" non-vacuity proof does not reproduce as written

Commit message, "Non-vacuous, four ways":

```
ts_event is the ts      fails
```

Reverting that assertion in the natural way — weakening `ts_event == ts` to a bare truthiness
check — **passes**:

```
1 passed    # assert ts_event, "the timestamp is the ts_event ..."
```

A bare truthiness check cannot fail here because the value is a large non-zero int. The
underlying claim is still sound, and I confirmed the assertion is genuinely load-bearing by
two mutations that *do* fail: `ts_event == 0` (`assert 1700000000000000000 == 0` — FAILS) and
`ts_event != ts` (`assert 1700000000000000000 != 1700000000000000000` — FAILS). So the test
is fine; the *proof as narrated* is the wrong demonstration. Suggest restating it as "if the
engine stamped a different ts, this fails" — which is what I actually verified.

### N1 (nit) — the gate file selection is not recorded

The commit message states three per-build counts with no command. Those counts are only
reproducible if you guess `test_honesty_series.py tests/dq/test_charts.py` — I had to
brute-force all 31 file combinations to find it. Naming the invocation would make the next
reviewer's verification a 5-second job instead of a search. (This is also why the brief's
claimed numbers looked wrong to me at first: the three-file set I guessed first gives
63/64/66, a different but equally green gate.)

### N2 (nit) — `test_the_engine_really_emits_three_column_rows_with_a_real_timestamp` is long

`:229` — **83** characters of test name. Not the longest in the file: `test_two_column_rows_fail_closed_rather_than_guessing_the_value_column` is 85 (`:354`) and `test_case_4_recorded_trade_replaces_the_added_one_for_one_round_trip` ties it at 83 (`:279`), so this is the third-longest of 29. Suggested: `test_the_engine_emits_three_column_rows_with_a_real_timestamp`. Purely cosmetic.

---

## Things I checked that are clean

- **`_add_trade`'s `try/except TypeError` fallback — relying on it here is sound.** I verified
  the exact mechanism rather than assuming. On 1.230.0 the 2-arg call raises
  `TypeError: PortfolioAnalyzer.add_trade() missing 1 required positional argument: 'realized_pnl'`,
  the fallback fires, and — importantly — the failed attempt leaves **no state behind**:
  `realized_pnls` is `None` after the failed 2-arg call, not a half-added row. So the
  try/except cannot silently double-add. On 1.223.0/1.228.0 the 2-arg call is the native form
  and `ts` is correctly ignored.
- **The engine does not dedupe `(pid, ts)`** — adding the same pair twice yields two rows
  (`[('P-1', ts, 10.0), ('P-1', ts, 99.0)]`). So the test's `len(raw) == 1` assertion is
  load-bearing rather than incidentally satisfied by engine-side collapsing.
- **Repo rules.** No capitalized `Digi*` in the new hunk or the commit message. No pandas.
  No pydantic. `ruff check` clean, `ruff format --check` clean, no line over 100 in the new
  hunk (the added hunk's longest is `:256` at 92 chars). Strict typing intact — the function returns `None`
  and the only untyped locals are `pyo3`/`usd`/`analyzer`/`raw`/`row`, matching the existing
  `_pyo3`/`_analyzer_with_trades` convention in the same file. Note the file's longest line
  overall is `:410` at exactly 100 — the `ruff.toml` limit, so compliant but with no headroom.
  All line numbers in this record are as of the reviewed commit `93807d0cf`; later commits
  (`5bb985d2f`) shift them.
- **File conventions.** Docstring style matches (imperative summary line, `` `` `` for code
  refs, then the "why"). Helper reuse is correct — the test needs a custom `ts`, which
  `_analyzer_with_trades` cannot supply since it hardcodes the default, so calling `_add_trade`
  directly is the right call and matches `test_case_4`'s pattern of building the analyzer
  inline.
- **CI reachability.** `.github/workflows/test-nautilus.yml:53` runs this file in the
  nautilus-gated lane, and `uv.lock:3874` pins `nautilus-trader = 1.230.0` — so CI runs the
  build where the assertions actually fire, not the skipping one. The premise is genuinely
  gated in CI, not just locally. The workflow comment at `:41-44` already anticipates this
  file by name.

---

## Verification commands

```bash
cd /Users/chrisstefan/Code/digithings/.worktrees/task/937-l1-corrective

# The author's gate, reproduced exactly on all three builds
for p in .venv/bin/python digiquant/.venv/bin/python \
         .claude/worktrees/sdca-strategy-refine/.venv/bin/python; do
  rm -rf tests/dq/__pycache__ .pytest_cache
  "$p" -m pytest tests/dq/test_honesty_series.py tests/dq/test_charts.py -q -p no:cacheprovider
done

# lint
.venv/bin/ruff check tests/dq/test_honesty_series.py
.venv/bin/ruff format --check tests/dq/test_honesty_series.py
```

All mutation probes were reverted; `git status --porcelain` is empty and `HEAD` is `93807d0cf`.
