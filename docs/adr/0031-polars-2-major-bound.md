# ADR 0031: Bind the polars major in all three consumers, then take 2.0 deliberately

**Status:** accepted
**Date:** 2026-10-08
**Decider:** Architect

## Context

`polars` 2.0.0 shipped 2026-10-06. Three packages in this repo depend on it:

- `digigraph/pyproject.toml:14` — `"polars>=1.0"`
- `digiquant/pyproject.toml:18` — `"polars>=1.0"`
- `digisearch/pyproject.toml:21` — `"polars>=1.0"`

Root `uv.lock` pins `polars 1.43.1` (+ `polars-runtime-32 1.43.1`).

`>=1.0` is not a floor, it is a claim that every future major is acceptable. The lock
is the only thing currently preventing a bare `uv lock --upgrade` from crossing the
major boundary, and the lock is exactly the artifact a routine refresh rewrites. Same
defect class as DIG-1514 / DIG-1515.

This ADR answers the question raised in DIG-2276: take 2.0 now on an `rnd/` branch and
report the breakage surface, or pin `<2` and defer.

## Evidence

All measurements taken 2026-10-08 against worktree HEAD `8accbb296`, except where noted.

### Release facts (CONFIRMED — read from the PyPI JSON APIs)

- `polars` latest = `2.0.0`, wheel uploaded `2026-10-06T11:44:04Z`, sdist `11:51:29Z`.
- `requires_python = ">=3.10"`. All four of our `pyproject.toml` files require `>=3.12`,
  so the floor is compatible.
- `requires_dist` (unconditional) is exactly one entry: `polars-runtime-32==2.0.0`.
- `polars-runtime-32 2.0.0` ships 8 `cp310-abi3` wheels: macOS x86_64 + arm64,
  manylinux x86_64/aarch64, musllinux x86_64/aarch64, windows amd64/arm64.
  **No platform gap** against the `polars-runtime-32 1.43.1` wheel set already locked.

### Our surface (CONFIRMED — counted from the tree)

- **181 files** execute `import polars` / `from polars`: 93 in package sources
  (digiquant 68, digigraph 21, digisearch 4) plus 6 in `scripts/`; 88 in tests.
- Every use is `import polars as pl` followed by `pl.<attr>`.
  **`from polars import X` occurs zero times.** There is no name-injection surface.
- **37 distinct `pl.*` symbols** are used across the repo.
- Regression net: **149 test files import polars and hold 1338 test functions**,
  of which only 2 carry a `skip`/`xfail` marker.

### Symbol probe (CONFIRMED — executed, not read)

Built a venv on the repo's own 3.12.12 interpreter, installed `polars==2.0.0`, and
`hasattr`-probed all 37 symbols:

```
PRESENT 37 / MISSING 0 / total 37
PRESENT BUT DEPRECATION-WARNED: (none)
```

The whole import-time API surface survives the major.

### Upstream breaking-change triage (HIGH confidence — read from the `py-2.0.0` release notes)

The release flags six breaking changes. Measured against our tree, **none of the six
reach our code**:

| Upstream change | Our exposure |
| --- | --- |
| SQL window fns over grouped rows / QUALIFY order (#29746) | 0 — no `SQLContext`, no `pl.SQL`, no `pl.sql` |
| SQL exact numeric literals → `Decimal`, `%`/DIV truncate (#29536) | 0 — same |
| Deterministic expression plugins opt into CSE/CSPE (#29428) | 0 — no `register_plugin_function` / `register_io` |
| Parquet `ENUM` type reads as `pl.String` (#29331) | 0 — zero occurrences of `pl.Enum` in the repo |
| More map operations (#29296) | additive |
| Deprecate `cut`/`qcut` (#29329) | 0 — neither symbol used |

### Risks that are *not* under the breaking-changes heading (the real surface)

These are behavioural changes filed under other headings. This is where an upgrade
actually costs us:

1. **Count-guarded sums become null on empty input (#29668).** 20 `.sum()` call sites
   across 13 files. In risk/portfolio aggregation a `0` becoming `null` is a numeric
   change, not a crash. Highest correctness risk in the set.
2. **Ragged rows now raise instead of silently dropping values (#29258).** 3
   `from_dicts` sites; 104 files construct `pl.DataFrame(...)`. Our data-ingest paths
   (macro, ETF flows, onchain) are the plausible originators. Fails loud, which is an
   improvement, but it converts a silent truncation into a thrown error.
3. **`is_in` casts the needle exactly or not at all (#29486).** 5 call sites / 4 files.
   A mismatched-dtype `is_in` that used to coerce may now raise.
4. **Out-of-core enabled by default at 80% of RAM, 64 GB disk budget (#29741, #29734).**
   The repo sets **no** `POLARS_*` environment variable and calls no polars tuning
   function, so there is no existing configuration to preserve — but large market-data
   scans and backtests can now silently spill to disk and run slow instead of failing
   fast. This is a performance-observability change, not a correctness one.
5. **`digiquant/src/digiquant/nautilus_runner.py:36` — `_POLARS_DT_ERRORS`.** This tuple
   catches `AttributeError, TypeError, ComputeError, InvalidOperationError` around
   `diffs.dt.total_microseconds().median()` and silently returns `"1-DAY"`. A new
   exception class there would escape a function written never to raise.
   **Tested and NOT reproduced:** run against 1.43.1 and 2.0.0 on all three dtypes that
   path can receive (int-µs, string, date), the except clause catches identically in
   both versions. Recorded here because the shape is a genuine latent hazard for future
   polars majors, not because 2.0 triggers it.

## Decision

Two things, in this order. The second is conditional on the first and on the tests.

**1. Bind the major in all three consumers, now.** Change `polars>=1.0` to
`polars>=1.43,<2` in `digigraph`, `digiquant`, and `digisearch`, and refresh the lock.

This is the actual defect and it is independent of whether 2.0 is ever adopted. With a
bounded floor, the next major becomes a decision the build forces us to make rather
than one a routine `uv lock --upgrade` makes for us. It also matches the version we
have actually validated.

**2. Then take 2.0 deliberately, in one step, with the five risks above as the test
checklist.**

Taking it now rather than deferring is justified by the evidence, not by optimism:

- 37/37 symbols present, zero deprecations — the import surface is a non-issue.
- 0 of the 6 flagged breaking changes touch our code.
- The five real risks are *testable*, and we hold 1338 tests across the files that
  exercise them, with 2 skips. That net is the reason to take the upgrade, and it is
  the reason a time-boxed prototype was the wrong instrument: the assessment was never
  the expensive part.

Deferral was the more expensive option here, because it forfeits the upgrade while the
regression net is wide, and leaves `>=1.0` — the real bug — unfixed for another cycle.

We do **not** simply bump the floor to `>=2`: the five behavioural changes are not
covered by an import-time check, so the major boundary must be crossed under the test
suite, not under a lock refresh.

## Consequences

**Positive:**

- A polars major can no longer arrive unannounced. `uv lock --upgrade` fails loudly
  instead of silently changing dataframe semantics under three packages.
- If 2.0's behaviour changes do bite, they are found by 1338 existing tests rather than
  by a production number moving.
- The floors state what we have actually validated (`1.43`) rather than the fiction `1.0`.

**Negative / tradeoffs:**

- We take on the five behavioural risks now. Risk 1 (empty sums → null) and risk 2
  (ragged rows now raise) are the two most likely to need code changes, and risk 4
  (silent disk spilling) can degrade backtest wall-clock without any test failing.
- `polars>=1.43,<2` means we hold ourselves to 1.x until 2.0 is merged. That is the
  point of the bound, but it is a real constraint on a library that ships often.
- The `is_in` and ragged-row changes may surface in code paths with no test coverage.
  Test coverage of the *import* surface is 100%; coverage of the *behaviour* surface
  is not measured here.

## Follow-up

The breakage-surface report DIG-2276 asked for is the Evidence section above; it does
not need an `rnd/` branch. What remains is one implementation change — the bounded
floor plus the lock refresh — and then the 2.0 upgrade as separate work.

## Links

- Related issues: DIG-2276 (this decision), DIG-1514, DIG-1515 (same non-binding-floor class)
- Upstream: `polars` `py-2.0.0` release notes, release id 385394861
- ADR index: `docs/adr/README.md`