# Fresh-context review — PR #5134, delta `93807d0cf..a686348ea`

- **Reviewer:** subagent (fresh context, did not author this code)
- **Subject:** `5bb985d2f` "test(digiquant): gate the engine-row test on capability, not on shape (DIG-937)" and `a686348ea` "docs(digiquant): durable review record for PR #5134 at 93807d0cf"
- **Parent state:** `93807d0cf` (reviewed previously, APPROVE, 0 blockers) — not re-reviewed except to confirm the delta did not regress it
- **Worktree:** `.worktrees/task/937-l1-corrective`, branch `task/937-l1-corrective-normalizer-sees-analyzer-records`, HEAD `a686348ea`
- **Scope:** `tests/dq/test_honesty_series.py` (21 lines: `+import inspect`, skip guard rewritten, docstring rewritten) and `review-5134-engine-row-shape.md` (283 new lines)
- **Verdict:** **APPROVE** — 0 blockers, 1 important, 3 minor, 1 nit

The capability gate works. The hole M1 named is genuinely closed: I forced `realized_pnls` to
return a dict on 1.230.0 and the test **FAILED** at HEAD, where the same forced dict **SKIPPED**
at the parent. The skip is now keyed on something independent of the value under test, which is
the only property that makes a guard honest.

Two things are wrong, both in the docs commit, both about the review record rather than the test.

---

## Severity counts

| Severity | Count |
|---|---|
| blocker | 0 |
| important | 1 |
| minor | 3 |
| nit | 1 |

---

## Environment verification (done first — both flagged hazards honoured)

**Hazard 1, `__pycache__` — cleared before every run,** including every mutation probe. The
reverted-file and forced-dict probes each got their own `rm -rf tests/dq/__pycache__`.

**Hazard 2, path resolution — confirmed, and the review brief's framing is correct.** The root
`conftest.py:1` is a one-line docstring and repoints nothing. `pytest.ini:5` `pythonpath` is the
mechanism. Measured on all four builds:

```
1.223.0  ->  .worktrees/task/937-l1-corrective/digiquant/src/digiquant/stats/series.py
1.228.0  ->  (same worktree path)
1.230.0  ->  (same worktree path)
1.231.0  ->  (same worktree path)
```

All four suites load **this worktree's** source. No bleed from a venv editable install.

---

## Gate reproduction — every number in the brief is correct

`pytest tests/dq/test_honesty_series.py tests/dq/test_charts.py -q -p no:cacheprovider`

| Build | Measured | Brief claims | |
|---|---|---|---|
| 1.223.0 | 62 passed, 3 skipped | 62/3 | MATCH |
| 1.228.0 | 63 passed, 2 skipped | 63/2 | MATCH |
| 1.230.0 | 65 passed, 0 skipped | 65/0 | MATCH |

Skip reasons name the cause, not a symptom — `add_trade has no ts_event, so this build cannot
emit record rows` (`test_honesty_series.py:253`).

**1.230.0 control:** `1 passed`, not skipped.

**Lint:** `ruff check` → `All checks passed!`; `ruff format --check` → `1 file already formatted`
(ruff 0.16.0).

---

## Q1 — Does the capability gate close the shape-gate hole?

**Yes, and the hole is closed in the direction that matters.** I built a pytest plugin that
replaces `PortfolioAnalyzer.realized_pnls` with a wrapper returning `{pid: pnl}`, and ran the
one test both ways:

```
parent 93807d0cf, 1.230.0, forced dict:
  SKIPPED [1] test_honesty_series.py:252: this build returns a dict, not record rows: dict
  1 skipped

HEAD a686348ea, 1.230.0, forced dict:
  AssertionError: expected one row, got {'P-1': 10.0}
  1 failed
```

The forced-dict state is precisely "a nautilus reverted 1.230.0 to the dict shape." At the parent
it skipped; at HEAD it fails loudly. **M1 is fixed.**

### The residual hole — a rename still skips silently (I1)

The gate is now sound against the regression it was written for, but it is not sound against
*every* future shape change. It tests one string, `"ts_event"`, in one place. A build that still
emits rows but renames the parameter skips:

```
class RenamedButStillEmitsRows:
    def add_trade(self, position_id, event_ts, realized_pnl): ...

inspect.signature(...).parameters  ->  ['position_id', 'event_ts', 'realized_pnl']
"ts_event" in parameters          ->  False     # SKIP, silently, on a row-emitting build
```

Same silent skip if `ts_event` moves into `**kwargs`. The gate is capability-*adjacent*, not
capability-exact: it infers "can emit rows" from a parameter name.

This is materially better than the shape gate — the dict regression it was built for now fails,
and a rename is a far less likely change than a return-shape revert. But the commit message
overstates it as a general fix:

> "a build that accepts a timestamp must return one"

That implication does not hold for a renamed parameter. The docstring's version is precise and I
would keep it:

> "``add_trade`` gained its ``ts_event`` parameter in the same release that started returning
> rows, so it is the honest gate"

Fixing it properly means asserting on the *call*, not the name — attempt the 3-arg call and let
`TypeError` from `_add_trade` decide. That is already the mechanism `_add_trade` uses to support
both arities (`:144-150`), so the gate could be a row-count probe instead of a name probe. Not
required to merge; worth a follow-up if the leaf stays open.

---

## Q2 — Is `inspect.signature` reliable on a pyo3 method?

**Reliable, and deterministically so.** pyo3 exposes a real text signature, which is the best
case — `inspect` parses a declared string rather than guessing.

```
1.223.0  (position_id, realized_pnl)                    __text_signature__: '($self, position_id, realized_pnl)'
1.228.0  (position_id, realized_pnl)                    __text_signature__: '($self, position_id, realized_pnl)'
1.230.0  (position_id, ts_event, realized_pnl)          __text_signature__: '($self, position_id, ts_event, realized_pnl)'
1.231.0  (position_id, ts_event, realized_pnl)          __text_signature__: '($self, position_id, ts_event, realized_pnl)'
type(analyzer.add_trade) -> <class 'builtin_function_or_method'>   (all four)
```

**No run-to-run variance.** 200 consecutive `inspect.signature` reads on the same instance
returned exactly **1** distinct result on both a skipping build and a running build. The gate
cannot flake.

**Parameter-kind variants all still pass the gate,** which is the right behaviour:

```
(position_id, ts_event, /, realized_pnl=None)   -> gate passes   (positional-only)
(position_id, realized_pnl, *, ts_event=0)      -> gate passes   (keyword-only)
```

`.parameters` includes positional-only and keyword-only entries, so a signature that re-orders or
re-kindifies `ts_event` does not cause a spurious skip.

### Failure mode is loud, with one real exception

| Situation | Behaviour | Loud? |
|---|---|---|
| `add_trade` missing entirely | `AttributeError` | **yes** — verified in pytest |
| signature unavailable, py3.12 | `ValueError` | **yes** |
| signature unavailable, py3.13 | returns `()` → empty params | **NO — silent skip** |

The third row is the one to know about, and it is a Python-version difference, not a pyo3 one:

```
py3.12.12: inspect.signature(time.time)  ->  ValueError: no signature found for builtin
py3.13.12: inspect.signature(time.time)  ->  ()            # gate sees no ts_event -> SKIPS
```

Verified under pytest on both versions. So if a future nautilus ever dropped
`__text_signature__`, the test would **fail loudly** on the two 3.12 builds and **skip silently**
on the two 3.13 builds. It would not produce a false pass — a silent skip is still a skip — but
the coverage would quietly vanish on exactly the newer interpreters CI is moving toward.

I rate this **minor**, not important: all four installed builds declare `__text_signature__`, so
this needs a nautilus change that has no evidence of being planned. Flagging it because the
failure is version-asymmetric and therefore hard to notice.

---

## Q3 — Does `import inspect` break anything?

**No.** Checked all four ways:

- **Ordering** — `:10`, correctly sorted in the stdlib block: `inspect`, `math`, `re`, then
  `from datetime ...`. `ruff check` confirms (it runs `I001`).
- **Unused** — no, used at `:252`.
- **Collision** — no. No `def`/`class` named `inspect` anywhere in the file, and no `inspect`
  import in any conftest on the path.
- **Behaviour** — `import inspect` is stdlib, adds ~0 to import time, and the module docstring
  already claims "Stdlib only."

---

## Q4 — Do the commit messages claim anything I cannot reproduce?

**Every claim in `5bb985d2f` reproduces.** Checked each line of the remeasured block:

| Claim | Reproduced? | Evidence |
|---|---|---|
| 1.230.0 control, 1 passed | yes | `1 passed` |
| 1.230.0 forced dict, 1 FAILED | yes | `1 failed`, `AssertionError: expected one row, got {'P-1': 10.0}` |
| 1.228.0, 1 skipped, reason names cause | yes | `add_trade has no ts_event, so this build cannot emit record rows` |
| 1.223.0, 1 skipped, reason names cause | yes | same |
| gate 62/63/65 with the named selection | yes | table above |
| ruff check / format --check clean | yes | `All checks passed!` / `1 file already formatted` |

### The M2 retraction is accurate, and understates its own case

> "Reverting that assertion the natural way — `assert ts_event == ts` to bare `assert ts_event` —
> **PASSES**. A truthiness check cannot fail on a 1.7e18 int."

Verified against the live engine on 1.230.0:

```
raw: [('P-1', 1700000000000000000, 10.0)]
ts_event = 1700000000000000000   truthy? True
RETRACTION CLAIM: bare `assert ts_event` PASSES -> True
  ts_event == 0  -> False     # fails, as claimed
  ts_event != ts -> False     # fails, as claimed
SHIPPED ASSERT `ts_event == ts` PASSES
```

Every element of the retraction is true, including the two mutations it offers as the correct
demonstration. The retraction is honest about its own error and correctly identifies that the
*assertion* is sound while the *proof as narrated* was the wrong demonstration. This is the
behaviour that makes the rest of the commit message trustworthy, and I checked it first because a
retraction that is itself wrong would invalidate the record.

### One claim is overstated (see I1)

> "a build that accepts a timestamp must return one"

True for the builds that exist. Not true for a renamed parameter. The docstring's narrower
wording is correct; the commit message's is not.

---

## Q5 — Is `a686348ea` accurate about its own subject and verdict?

**Mostly. The verdict, the severity counts, the central measurement, and the gate counts are all
correct. Two supporting details are wrong, and both are in the nit/minor tier — neither touches
the verdict.**

Accurate, specifically checked:

- **Parent `a79d4eb17`** — `git rev-parse 93807d0cf^` → `a79d4eb17`. Correct.
- **Verdict and counts** — "APPROVE — 0 blockers, 0 important, 2 minor, 2 nit" matches the table
  and the four findings (M1, M2, N1, N2). Internally consistent.
- **Line refs at the parent** — every one I checked resolves: `:171` `test_case_1_engine_dict_shape…`,
  `:184` `test_case_1_records_dict_does_not_fall_through…`, `:229` the test def, `:251-252` the
  old guard, `:256` `len(row) == 3`, `:259` `ts_event == ts`, `:264` the date assert, `:417`
  `test_day_boundaries…`. All correct **against `93807d0cf`**, which is the right reference frame.
- **Build capability table** — `record_trade=False, add_position_return=False` on 1.223.0;
  `add_position_return=True` on 1.228.0. Both confirmed.
- **CI reachability** — `.github/workflows/test-nautilus.yml:53` does list
  `tests/dq/test_honesty_series.py`, and `uv.lock:3874` does pin `nautilus-trader = 1.230.0`. Both
  correct, and the point (CI runs the build where assertions fire) holds.
- **M1's own reproduction** — its transcript (`SKIPPED`, `:252`, "this build returns a dict, not
  record rows: dict") is byte-identical to what I got.

### Two errors (M3, M4 below)

The file is otherwise a careful, honest record — including the parts that cost the author
something (the M2 retraction, and the explicit correction of the brief's own hazard framing at
line 41-42). The errors below are arithmetic and attribution, not judgement.

---

## Findings

### I1 (important, commit message) — "a build that accepts a timestamp must return one" is not true as written

`5bb985d2f` commit message; gate at `tests/dq/test_honesty_series.py:252`

The implication holds for a parameter *named* `ts_event`. It fails for a rename or for
`ts_event` demoted into `**kwargs`, where the build still emits rows and the test still skips:

```
RenamedButStillEmitsRows  sig=(position_id, event_ts, realized_pnl)  gate=False  -> SKIP
TsEventInKwargs           sig=(position_id, realized_pnl, **kwargs)  gate=False  -> SKIP
```

This is the same class of defect as M1, one level down: M1 keyed the guard on the value under
test, this keys it on a name. The fix is a call-based probe rather than a name-based one —
`_add_trade` (`:144-150`) already distinguishes the arities via `TypeError`, so the gate could
assert on what the engine returned rather than on what the method is called:

```python
analyzer = pyo3.PortfolioAnalyzer()
ts = 1_700_000_000_000_000_000
try:
    analyzer.add_trade(pyo3.PositionId("P-1"), ts, pyo3.Money(10.0, usd))
except TypeError:
    pytest.skip("add_trade has no ts_event, so this build cannot emit record rows")
```

That gate skips only on an arity the build cannot accept, which is exactly the claim the skip
message already makes.

Not a blocker: the regression the commit set out to catch **is** caught (verified both
directions). This is about the claim being broader than the mechanism behind it. Fix the wording,
or the gate; either resolves it.

### M3 (minor, docs) — N2's character count is wrong, and it is the finding's whole basis

`review-5134-engine-row-shape.md:228-232`

> "63 characters of test name. Every other test in the file is descriptive but shorter
> (`test_returns_dict_is_no_longer_read_as_its_timestamps` is the longest at 56)."

Measured:

```
name under review: test_the_engine_really_emits_three_column_rows_with_a_real_timestamp = 68
test_returns_dict_is_no_longer_read_as_its_timestamps                            = 53
its rank: 14th of 29 test names in the file
```

Both numbers are wrong (63 vs **68**; 56 vs **53**), and the comparative claim is wrong in a way
that inverts the recommendation — the file already contains a longer test name:

```
test_two_column_rows_fail_closed_rather_than_guessing_the_value_column = 70   <- longest
test_the_engine_really_emits_three_column_rows_with_a_real_timestamp    = 68
```

So the reviewed name is **second-longest, not longest**. The suggested fix
(`test_the_engine_emits_three_column_rows_with_a_real_timestamp`, 63 chars) would make it shorter
than 21 other names — a cosmetic non-issue presented as the file's outlier. Cosmetic finding,
wrong arithmetic; the "purely cosmetic" self-assessment happens to be right.

### M4 (minor, docs) — the "no line over 100" evidence cites the wrong line and the wrong length

`review-5134-engine-row-shape.md:250-251`

> "no line over 100 in the new hunk (longest is the `:264` assert at 88)"

Measured in the new hunk at `93807d0cf`:

```
:256   92 chars   assert isinstance(row, tuple) and len(row) == 3, ...
:252   88 chars   pytest.skip(f"this build returns a dict, not record rows: ...")
:264   76 chars   assert dates == ["2023-11-14"], "the ts_event column, ..."
```

`:264` is 76 characters, not 88. The 88 belongs to `:252` — the skip line, not an assert. The
conclusion (**no line over 100**) is correct and `ruff` agrees; only the citation is wrong. The
92-char line at `:256` is the real longest and is still under 100.

Pattern worth noting: both M3 and M4 are evidence claims in the "checked clean" section, where a
reviewer's most likely failure mode is asserting a clean result without re-deriving the number
underneath it. The findings themselves were fine.

### N1 (nit) — the review file's own gate counts still name no command

`review-5134-engine-row-shape.md:266-281`

Its N1 correctly faults `93807d0cf` for recording counts without the invocation. The review file
then records the counts in its own body (lines 79-81) and only supplies the command in a
verification appendix at the bottom. Following its own advice costs one line at `:79`. Noted for
consistency, not as a defect — the appendix does carry the command.

---

## Things I checked that are clean

- **The delta did not regress the parent.** `git diff 93807d0cf..a686348ea --stat` is 2 files,
  296 insertions, 8 deletions. The only behaviour change is the skip guard; every assertion in the
  test body (`ts_event == ts`, `pnl == 10.0`, the date assertion, `len(raw) == 1`) is untouched
  and all still pass on 1.230.0. No production code touched.
- **1.231.0 is a fourth build the commit messages never mention.** Its run is
  `15 failed, 50 passed` (65 collected — the same selection as the other builds), and all 15
  failures are `plotly` missing from that venv (`ModuleNotFoundError: No module named 'plotly'`),
  untouched by this delta (`git diff 93807d0cf..a686348ea -- tests/dq/test_charts.py` is empty).
  Run alone, the file this delta changes is `29 passed`, and the capability-gated test is
  `1 passed` — not skipped. So the newest build also emits rows, which strengthens the M1
  diagnosis rather than weakening it. Omission, not error.
- **Repo rules — lowercase.** Case-sensitive scan of the entire delta for `Digi[A-Z]`:
  **no matches**. All `digiquant`/`digithings` references are lowercase.
- **Repo rules — polars only, no pandas.** No `+` line in the diff's test changes mentions
  pandas, polars, or pyarrow.
- **Repo rules — pydantic v2.** Not touched; no model in this delta.
- **Repo rules — ruff line length 100.** `ruff.toml:5` sets `line-length = 100`. Longest line in
  the changed function is 92 (`:261`), the new skip line is 87 (`:253`). Clean under both `ruff
  check` and `ruff format --check`.
- **Repo rules — strict typing.** The test still annotates `-> None`. `inspect` is untyped at the
  boundary, which is unavoidable for a pyo3 probe; the file's existing `pyo3`/`usd`/`analyzer`
  convention covers it.
- **Docstring rewrite is accurate.** Every claim in the new docstring at `:238-247` reproduces:
  rows are `list` of `(str, int, float)` triples, column 1 is the stamp, and the dict shape holds
  on 1.223.0/1.228.0 (measured `{'P-1': 10.0}`).
- **The skip message names a cause, not a symptom.** "add_trade has no ts_event, so this build
  cannot emit record rows" — actionable and accurate for the two builds that take it. The
  overreach is in the commit message's generalisation (I1), not in this string.
- **`_add_trade`'s `try/except TypeError` fallback remains correct.** The gate now runs *before*
  `_add_trade`, so on 1.228.0/1.223.0 the fallback path is no longer exercised by this test — but
  `_analyzer_with_trades` still calls it, so the path is covered by other tests in the file.
- **Worktree clean.** `git status --porcelain` empty, HEAD `a686348ea`, test file byte-identical
  to HEAD. All mutation probes reverted.

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

# the decisive comparison: forced dict, parent vs HEAD
# (plugin wraps PortfolioAnalyzer.realized_pnls to return {pid: pnl})
git show 93807d0cf:tests/dq/test_honesty_series.py > tests/dq/test_honesty_series.py
rm -rf tests/dq/__pycache__
"$PY1230" -m pytest "tests/dq/test_honesty_series.py::test_the_engine_really_emits_three_column_rows_with_a_real_timestamp" \
  -q -p no:cacheprovider -p forced_dict      # -> 1 skipped
git checkout tests/dq/test_honesty_series.py
rm -rf tests/dq/__pycache__
"$PY1230" -m pytest "tests/dq/test_honesty_series.py::test_the_engine_really_emits_three_column_rows_with_a_real_timestamp" \
  -q -p no:cacheprovider -p forced_dict      # -> 1 failed

/Users/chrisstefan/Code/digithings/.venv/bin/ruff check tests/dq/test_honesty_series.py
/Users/chrisstefan/Code/digithings/.venv/bin/ruff format --check tests/dq/test_honesty_series.py
```