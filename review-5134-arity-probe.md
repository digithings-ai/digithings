# Fresh-context review — PR #5134, delta `a686348ea..6d52bdfb1`

- **Reviewer:** subagent (fresh context, did not author this code)
- **Subject:** `49e3d9f1f` "test(digiquant): probe add_trade's arity instead of reading its signature" and `6d52bdfb1` "test(digiquant): narrow the arity probe so only add_trade can raise it"
- **Prior state:** `a686348ea` (docs only). `93807d0cf` / `5bb985d2f` reviewed in earlier rounds, not re-reviewed except to confirm no regression.
- **Worktree:** `.worktrees/task/937-l1-corrective`, branch `task/937-l1-corrective-normalizer-sees-analyzer-records`, HEAD `6d52bdfb1`
- **Scope:** 3 files — `tests/dq/test_honesty_series.py` (the test), `review-5134-capability-gate.md` (new, 426 lines), `review-5134-engine-row-shape.md` (11 lines edited). No production code.
- **Verdict:** **APPROVE** — 0 blockers, 0 important, 3 minor, 2 nit

The delta does what it says. The behavioural probe closes the hole the previous round proved
(`forced dict` on 1.230.0 → **FAILS** at HEAD), it closes the rename hole the previous round
flagged as I1, and `6d52bdfb1`'s narrowing is real and complete for the statements it moved.
Every gate number, every per-test number, and every lint claim in both commit messages
reproduces.

Three things are wrong, all in the records rather than in the shipped test. **The shipped test
needs no change.** One of the three is a numeric correction that the delta got wrong while
claiming to correct numbers — and it overwrote a value the previous round had right.

---

## Severity counts

| Severity | Count |
|---|---|
| blocker | 0 |
| important | 0 |
| minor | 3 |
| nit | 2 |

---

## Environment verification (done first — both flagged hazards honoured)

**Hazard 2, path resolution — confirmed; the brief's framing is correct.** `conftest.py:1` is a
one-line docstring and repoints nothing; `pytest.ini:5` `pythonpath` is the mechanism. Measured
on all four builds by importing inside a collected test:

```
1.223.0  ->  .worktrees/task/937-l1-corrective/digiquant/src/digiquant/stats/series.py
1.228.0  ->  (same worktree path)
1.230.0  ->  (same worktree path)
1.231.0  ->  (same worktree path)
```

All four suites load **this worktree's** source. No bleed from a venv editable install.

**Hazard 1, `__pycache__` — `rm -rf tests/dq/__pycache__ .pytest_cache` before every single
run**, including every mutation probe.

---

## Gate reproduction — every number in the brief is correct

`pytest tests/dq/test_honesty_series.py tests/dq/test_charts.py -q -p no:cacheprovider`

| Build | Measured | Brief claims | |
|---|---|---|---|
| 1.223.0 | 62 passed, 3 skipped | 62/3 | MATCH |
| 1.228.0 | 63 passed, 2 skipped | 63/2 | MATCH |
| 1.230.0 | 65 passed, 0 skipped | 65/0 | MATCH |
| 1.231.0 (`test_honesty_series.py` alone) | 29 passed | 29 passed | MATCH |

1.231.0 with both files is `15 failed, 50 passed` (65 collected — the same selection); every
failure is `ModuleNotFoundError: No module named 'plotly'` in that venv, and
`git diff a686348ea..6d52bdfb1 -- tests/dq/test_charts.py` is empty. Not a delta effect.

**Per-test:**

```
1.230.0  control                                  1 passed
1.231.0  control                                  1 passed
1.230.0  forced dict on realized_pnls             1 FAILED  AssertionError: expected one row, got {'P-1': 10.0}
1.231.0  forced dict on realized_pnls             1 FAILED  AssertionError: expected one row, got {'P-1': 10.0}
1.228.0  3-arg rejected                           1 skipped  :265 add_trade rejects a ts_event, so this build cannot emit record rows
1.223.0  3-arg rejected                           1 skipped  :265 add_trade rejects a ts_event, so this build cannot emit record rows
```

**Lint:** `ruff check` → `All checks passed!`; `ruff format --check` → `1 file already formatted`
(ruff 0.16.0). Longest line in the changed hunk is `:265` at 90, under the `ruff.toml:5`
`line-length = 100`.

---

## Q1 — Is the skip robust now?

**The regression it was written for is caught, and the rename hole is genuinely closed.** I drove
the shipped test function against synthetic engines installed into `sys.modules` (each scenario
builds `pyo3.Currency` / `PositionId` / `Money` / `PortfolioAnalyzer` itself and returns
whatever rows it wants):

```
A rows + renamed positional  event_ts                -> PASS     <- I1 is closed
B rows + ts_event KEYWORD-ONLY                       -> SKIP     residual
C rows + ts_event in **kwargs                        -> SKIP     residual
D no ts_event (genuinely dict build)                 -> SKIP     correct
E accepts 3 args but body TypeError                  -> SKIP     residual
F accepts 3 args, DISCARDS ts                        -> FAIL  AssertionError: the timestamp is the ts_event …
G accepts 4 args (arity grew again)                  -> SKIP     residual
I add_trade absent entirely                          -> FAIL  AttributeError: 'AnalyzerNoAddTrade' object has no attribute 'add_trade'
```

Scenario **A** is the important one. The previous round's I1 — "a build that still emits rows but
renames the parameter to `event_ts` skips silently" — no longer holds: the probe asks the engine
what it accepts, so the parameter's *name* is irrelevant. And the introspection failure mode the
commit message names is real and correctly characterised:

```
py 3.12  inspect.signature(time.time)  ->  ValueError: no signature found for builtin
py 3.13  inspect.signature(time.time)  ->  ()          # would have skipped
```

The remaining triggers (B, C, E, G) are in m1 below. None of them is reachable from any of the
four installed builds, and every one requires a deliberate nautilus API change.

---

## Q2 — Can the `except TypeError` still mask a real error?

**`6d52bdfb1` closed the statement-scope hole completely.** Its commit message claims only that,
and it is true. Constructing `pyo3.Money(10.0, usd)` to raise `TypeError` now fails loudly:

```
Money() itself raises TypeError, rows build  ->  FAIL  TypeError: Money(): cannot convert 'Decimal' to float
```

The same scenario against `49e3d9f1f`'s wider `try` skips. So the narrowing is real, and its
message ("Anything they raise fails loudly") reproduces exactly.

**It did not make the `except` arity-specific, and it cannot — pyo3 raises `TypeError` for
argument *type conversion* too.** Measured on the real builds, `add_trade` on 1.230.0/1.231.0:

```
3-arg, int ts (SHIPPED)  OK      realized=[('P-1', 1700000000000000000, 10.0)]
ts as datetime           TypeError: 'datetime.datetime' object cannot be interpreted as an integer
ts as float              TypeError: 'float' object cannot be interpreted as an integer
money as float           TypeError: 'float' object is not an instance of 'Money'
pid as str               TypeError: 'str' object is not an instance of 'PositionId'
2-arg (arity)            TypeError: … missing 1 required positional argument: 'realized_pnl'
4-arg (arity)            TypeError: … takes 3 positional arguments but 4 were given
```

Only the last two are arity. So a build that still emits rows but **reorders** `add_trade`'s
parameters (`position_id, realized_pnl, ts_event`) makes this exact call raise
`TypeError: 'float' object is not an instance of 'Money'` — and the test skips on the very build
whose job is to prove rows exist. That is the honest statement of what `6d52bdfb1` left open, and
it is m1 below.

The `TypeError` the two old builds actually raise is unambiguous, which is what the commit
message claims and what it measures:

```
1.223.0  3-arg TypeError: PortfolioAnalyzer.add_trade() takes 2 positional arguments but 3 were given
1.228.0  3-arg TypeError: PortfolioAnalyzer.add_trade() takes 2 positional arguments but 3 were given
1.223.0  realized_pnls BEFORE: None   AFTER: None      <- nothing half-added
1.228.0  realized_pnls BEFORE: None   AFTER: None
```

So the skip is for the right reason on both builds that take it, and the analyzer is untouched.

---

## Q3 — Could the test pass for the wrong reason on 1.230.0?

**I could not construct one.** The failure directions I forced:

| Mutation | Outcome |
|---|---|
| `realized_pnls` forced to `{pid: pnl}` (the actual regression) | FAIL — `expected one row, got {'P-1': 10.0}` |
| `add_trade` accepts 3 args but silently discards the stamp | FAIL — `the timestamp is the ts_event …` |
| `add_trade` removed entirely | FAIL — `AttributeError` (loud, not a skip) |
| rows as `list` not `tuple` | FAIL — `isinstance(row, tuple)` is strict |
| a second row appended | FAIL — `len(raw) == 1` |

`dates == ["2023-11-14"]` genuinely discriminates the `ts_event` column from the row index: an
index-derived date for row 0 would be `1970-01-01`. `values == [10.0]` pins magnitude. The
production consumer (`nautilus_runner.py:366-368`) hands `realized_pnls` straight to
`normalize_series`, which is exactly the two-step contract this test pins. Nothing else.

The one gap is n1.

---

## Q4 — Commit-message claims

**`49e3d9f1f` — every behavioural claim reproduces.** Checked each line of the remeasured block
and each line of the I1 retraction:

| Claim | Reproduced? | Evidence |
|---|---|---|
| `__text_signature__` `(position_id, realized_pnl)` on 1.223.0/1.228.0, `(…, ts_event, …)` on 1.230.0 | yes | read off all four live builds |
| gate `False` on 1.223.0/1.228.0, `True` on 1.230.0 | yes | follows from the signatures above |
| a pyo3 method with no `__text_signature__` raises `ValueError` on 3.12, returns `()` on 3.13 | yes | py3.12 `ValueError`, py3.13 `()` — measured |
| the old builds' `TypeError` is `"takes 2 positional arguments but 3 were given"` | yes | exact string, both builds |
| the analyzer is left untouched (`realized_pnls` still `None`) | yes | measured before/after, both builds |
| control / forced-dict / skip / gate / ruff block | yes | all six, table above |

**The retraction of "a build that accepts a timestamp must return one" is accurate**, and the fix
actually resolves the failure mode the retraction names: a renamed-but-row-emitting build now
**passes** (scenario A) where the name gate skipped. That is the right response to a retraction —
not just withdrawing the sentence but closing the hole behind it.

**`6d52bdfb1` — every claim reproduces.** The pre-narrowing spurious skip (Money raising
`TypeError`), the post-narrowing loud failure, and the whole "Unchanged:" block including
`1.231.0 29/0 on the module this leaf touches`. No overclaim: it says the constructions were moved
out, not that the `except` is arity-specific.

**One claim is wrong** — see m2.

---

## Findings

### m1 (minor, mechanism) — the skip keys on `TypeError`, not on arity; pyo3 raises `TypeError` for type conversion

`tests/dq/test_honesty_series.py:262-265`

The probe is a large real improvement on the name gate — scenario A closes I1 outright, and the
`__text_signature__` / Python-version asymmetry is gone. What survives is that
`except TypeError` cannot distinguish *"this build takes fewer arguments"* from *"this build took
the arguments but rejected one's type"*, and the second is a live pyo3 behaviour (Q2's table).

Scenarios that skip on a row-emitting build: keyword-only `ts_event` (B), `**kwargs` (C), arity
grown to 4 (G), **parameters reordered** (a real `TypeError: 'float' object is not an instance
of 'Money'`), and any `TypeError` raised inside `add_trade`'s body (E).

Severity: **minor, not important**, and this is a deliberate disagreement with the previous
round's calibration of I1 as *important*. I1's trigger set was "any rename" — a single plausible
API change. This trigger set is narrower and each member needs a deliberate signature change; the
failure mode is lost coverage, never a false green (a skip is a skip); and none is reachable from
any installed build. It should not block. The one-line tightening, if the leaf is reopened:

```python
try:
    analyzer.add_trade(position_id, ts, money)
except TypeError as exc:
    # pyo3 raises TypeError for arity *and* for per-argument type conversion
    # ("'float' object is not an instance of 'Money'"), so match on arity only.
    if "positional argument" not in str(exc) and "required positional" not in str(exc):
        raise
    pytest.skip("add_trade rejects a ts_event, so this build cannot emit record rows")
```

A throwaway analyzer for the probe plus a check that the probe *did something* would be strictly
better again, since it would gate on an observed effect rather than on an exception type.

### m2 (minor, docstring) — "Asking the engine … has no such failure mode" is absolute, and there is one

`tests/dq/test_honesty_series.py:246-252`, and the skip string at `:265`

The new docstring correctly dismantles the signature gate. Its closing sentence does not hold:

> Asking the engine whether it accepts a timestamp has no such failure mode.

There is such a failure mode — a keyword-only `ts_event`, a `**kwargs` `ts_event`, a re-order, or
an arity that grows past 3 all make "whether it accepts a timestamp" answer *no* on a build that
still emits rows. Same family as the overclaim I1 was raised for, one clause softer. The skip
string at `:265` inherits it: "add_trade rejects a ts_event, so this build cannot emit record
rows" asserts a capability the mechanism only infers.

Suggested: "Asking the engine whether it accepts a timestamp is insensitive to the parameter's
*name*, which is the failure mode that mattered here."

### m3 (minor, docs) — the N2 correction is wrong on five of six numbers, and overwrote a correct one

`review-5134-engine-row-shape.md:230`

`49e3d9f1f` states it "corrects two arithmetic errors". One of the two is fully correct (below).
The other replaces the previous round's already-correct `68` with a wrong `83`, and adds four
wrong numbers. Measured against `93807d0cf` (the commit the file says it cites):

| Claim in `49e3d9f1f` | Measured | |
|---|---|---|
| test name is **83** characters | **68** | wrong — 83 is the length of the whole `def test_…() -> None:` line at `:229` |
| `test_two_column_rows_fail_closed_rather_than_guessing_the_value_column` is **85** | **70** | wrong |
| … at **`:354`** | **`:343`** | wrong |
| `test_case_4_recorded_trade_replaces_the_added_one_for_one_round_trip` ties it at **83** | **68** | wrong (it does tie — at 68) |
| … at **`:279`** | **`:268`** | wrong |
| **third-longest of 29** rather than longest | tied **#2** of 29 | partly right — "not the longest" is correct, the ordinal is not |

The original N2 said `63`, which is `83 - 20`; the correct subtraction is `83 - 15 = 68`. The
correction simply dropped the subtraction rather than fixing it, so the file went `63 → 68 (right)
→ 83 (wrong)`. The right text is "68 characters, tied with `test_case_4_…` at `:268` for
second-longest; `test_two_column_rows_…` at `:343` is longer at 70."

For the record, the previous round's own M3 was also wrong on the ordinal — it measured the name
length correctly as `68` but put the test "14th of 29". Both rounds guessed the rank; the
measured answer is tied #2.

Cosmetic finding, arithmetic-only, and it cannot affect the shipped test. But it lives in the
"checked clean" section of a durable record whose whole value is that its numbers were measured,
and it was written by the commit whose stated purpose was correcting numbers. Worth one commit.

### The other correction in `49e3d9f1f` is fully correct — leave it alone

`review-5134-engine-row-shape.md:246-253`. Every figure re-derived against `93807d0cf`:

```
:252   88 chars   pytest.skip(f"this build returns a dict, not record rows: …")     <- the 88, as claimed
:256   92 chars   assert isinstance(row, tuple) and len(row) == 3, …                <- longest in the hunk, as claimed
:264   76 chars   assert dates == ["2023-11-14"], …                                 <- 76, as claimed
:410  100 chars   normalize_series([("P-1", 1_700_000_000_000_000_000, 10.0), …])   <- file's longest, at exactly the limit
```

The added note that line numbers are as of `93807d0cf` because later commits shift them is also
necessary and correct:

```
93807d0cf   def=229  first_skip=252  ts_assert=259
5bb985d2f   def=230  first_skip=253  ts_assert=264
6d52bdfb1   def=229  first_skip=265  ts_assert=274
```

### n1 (nit) — `pnl == 10.0` cannot enforce the docstring's `float`

`tests/dq/test_honesty_series.py:239`, `:275`

The docstring promises "a `list` of `(str, int, float)` triples", but `10 == 10.0` and
`[10] == [10.0]` are both `True` in Python, so a build returning an integer pnl passes and the
`float` half of the claim is unenforced. Harmless — `normalize_series` coerces to `float`
downstream, and `isinstance(row, tuple)` already pins the strict part that matters. Pre-existing
from `93807d0cf`, not in the delta. If you want the claim enforced, `assert isinstance(pnl,
float)`.

### n2 (nit) — no trailing newline on the file the delta adds

`review-5134-capability-gate.md` — `\ No newline at end of file`. The sibling
`review-5134-engine-row-shape.md` has one. No lint enforces it here (no markdownlint config at
root, none in workflows), so this is cosmetic only.

---

## Things I checked that are clean

- **The delta did not regress `93807d0cf` or `5bb985d2f`.** `git diff 93807d0cf..6d52bdfb1 --
  tests/dq/test_honesty_series.py | grep -E 'assert |normalize_series\('` returns **nothing** —
  not one assertion in the test body changed. Every assertion (`ts_event == ts`, `pnl == 10.0`,
  `position_id == "P-1"`, the date assertion, `len(raw) == 1`) is byte-identical to the reviewed
  parent and passes on both row-emitting builds.
- **No production code touched.** `git diff --name-only a686348ea..6d52bdfb1 -- digiquant/src
  tests/dq/test_charts.py` is empty. `normalize_series` is untouched.
- **`import inspect` removed, and correctly.** No `inspect` use remains in the file, so dropping
  the import at `49e3d9f1f` leaves nothing dangling; `ruff check` (which runs `I001`) is clean.
- **No `Digi[A-Z]` anywhere in the delta** (case-sensitive scan) — lowercase naming rule holds in
  prose, docstrings, and both commit messages.
- **Polars-only rule holds.** No added line mentions pandas, polars, pyarrow, or pydantic. The
  test module's "Stdlib only" docstring claim is still true.
- **Strict typing holds.** The test still annotates `-> None`; `pyo3` / `usd` / `analyzer` /
  `raw` / `row` remain untyped locals, matching the file's existing `_pyo3` /
  `_analyzer_with_trades` convention at the same pyo3 boundary.
- **Ruff line length 100 holds.** `ruff.toml:5` sets it; longest changed line is 90.
- **Dead code check.** `_add_trade` (`:143`) is still called from `_analyzer_with_trades`
  (`:158`), so the `try/except TypeError` arity fallback it exists for is still exercised by
  other tests in the file. Removing this test's call to it did not orphan it.
- **Skip reason names a cause, not a symptom.** `"add_trade rejects a ts_event, so this build
  cannot emit record rows"` is accurate for both builds that take it (Q2). Its overreach is the
  generalisation in m2.
- **Worktree clean.** `git status --porcelain` empty at HEAD `6d52bdfb1`; the test file is
  byte-identical to HEAD; every mutation probe was reverted.

---

## Recommended follow-up (none of it blocks merge)

One commit on this branch, docs only:

1. `review-5134-engine-row-shape.md:230` — apply the m3 numbers (`68`, tied #2 of 29, `:343`/
   `:268`).
2. `tests/dq/test_honesty_series.py:252` and `:265` — soften the absolute wording per m2.
3. Optional, if the leaf reopens: the arity-matching `except` per m1.

The shipped test itself should not change.

---

## Verification commands

```bash
cd /Users/chrisstefan/Code/digithings/.worktrees/task/937-l1-corrective

for p in /Users/chrisstefan/Code/digithings/.venv/bin/python \
         /Users/chrisstefan/Code/digithings/digiquant/.venv/bin/python \
         /Users/chrisstefan/Code/digithings/.claude/worktrees/sdca-strategy-refine/.venv/bin/python; do
  rm -rf tests/dq/__pycache__ .pytest_cache
  "$p" -m pytest tests/dq/test_honesty_series.py tests/dq/test_charts.py -q -p no:cacheprovider
done

# 1.231.0 alone
rm -rf tests/dq/__pycache__ .pytest_cache
/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld/.venv/bin/python \
  -m pytest tests/dq/test_honesty_series.py -q -p no:cacheprovider

# the decisive comparison: forced dict on the row-emitting build
cat > /tmp/forced_dict.py <<'EOF'
import nautilus_trader.core.nautilus_pyo3 as p
p.PortfolioAnalyzer.realized_pnls = lambda self, currency: {"P-1": 10.0}
EOF
rm -rf tests/dq/__pycache__ .pytest_cache
PYTHONPATH=/tmp /Users/chrisstefan/Code/digithings/.claude/worktrees/sdca-strategy-refine/.venv/bin/python \
  -m pytest "tests/dq/test_honesty_series.py::test_the_engine_really_emits_three_column_rows_with_a_real_timestamp" \
  -q -p no:cacheprovider -p forced_dict   # -> 1 failed

# the doc arithmetic, as of the commit the record cites
git show 93807d0cf:tests/dq/test_honesty_series.py > /tmp/asof938.py
python3 -c "
import re
src = open('/tmp/asof938.py').read().splitlines()
print([(len(m.group(1)), i) for i, l in enumerate(src, 1)
       if (m := re.match(r'def (test_\w+)\(', l))][:3])
print([(i, len(src[i-1])) for i in (252, 256, 264, 410)])
"

/Users/chrisstefan/Code/digithings/.venv/bin/ruff check tests/dq/test_honesty_series.py
/Users/chrisstefan/Code/digithings/.venv/bin/ruff format --check tests/dq/test_honesty_series.py
```
