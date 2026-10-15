# ADR 0032: Bind the polars major below 2.0, and fix the date-normalisation contract

**Status:** accepted
**Date:** 2026-10-09
**Decider:** Architect

## Revision history

An earlier draft of this ADR (2026-10-08, commit `0e178f61b9`) reached the opposite
conclusion on Decision 2 — "take 2.0 now". That draft rested on an **import-surface**
probe: 37 of 37 `pl.*` symbols present, zero deprecations, and none of the six flagged
upstream breaking changes reachable from our tree. It was never paired with a run of
the behavioural suite.

Two measurements taken 2026-10-09 then contradicted the inference:

- Running the digiquant polars-touching suite on both versions gave **+132
  regressions, 0 fixes** on 2.0.0 against a 1.38.1 baseline.
- An independent count of the affected call sites gave **67 sites across 22 files**,
  not the 14 sites across 6 files the first handover reported.

An import probe cannot observe either number. The 2026-10-08 evidence is retained below
because it is sound; only the conclusion drawn from it was wrong. The five behavioural
risks it identified are no longer a reason to upgrade now — they are the acceptance
checklist for the day it is taken.

## Context

`polars` 2.0.0 shipped 2026-10-06. Three packages depend on it:

- `digigraph/pyproject.toml:14` — `"polars>=1.0"`
- `digiquant/pyproject.toml:18` — `"polars>=1.0"`
- `digisearch/pyproject.toml:21` — `"polars>=1.0"`

Root `uv.lock` pins `polars 1.43.1` (and `polars-runtime-32 1.43.1`).

`>=1.0` is not a floor, it is a claim that every future major is acceptable. The lock
is the only thing currently preventing a routine `uv lock --upgrade` from crossing the
major boundary, and the lock is exactly the artifact such a refresh rewrites. Same
defect class as DIG-1514 / DIG-1515.

This ADR answers the question raised in DIG-2276: take 2.0 now and report the breakage
surface, or bind below 2 and defer.

A second question was routed here with it. polars 2.0 removes implicit `str` -> `Date`
casting, and `data/prices/merge.py` is the normative R2-versus-live merge rule
(section 3.2). Whether `canonical_date` becomes the single date-normalisation boundary
is an interface-contract decision, not a rename, so it is decided here.

## Evidence

### Release and platform surface — measured 2026-10-08 at HEAD `8accbb296`

Retained from the prior draft. Read from the PyPI JSON APIs and counted from the tree.

- `polars` latest = `2.0.0`, wheel uploaded `2026-10-06T11:44:04Z`.
- `requires_python = ">=3.10"`; all four of our `pyproject.toml` files require
  `>=3.12`, so the floor is compatible.
- `requires_dist` (unconditional) is one entry: `polars-runtime-32==2.0.0`.
- `polars-runtime-32 2.0.0` ships 8 `cp310-abi3` wheels covering the same platforms as
  the locked 1.43.1 wheel set. **No platform gap.**
- 181 files execute `import polars`; every use is `import polars as pl`, and
  `from polars import X` occurs zero times, so there is no name-injection surface.
- 149 test files import polars and hold 1338 test functions, only 2 of them skipped.
- `hasattr`-probe of all 37 `pl.*` symbols used in the repo against 2.0.0:
  **present 37, missing 0, deprecated 0.** The import-time surface survives the major.

None of the six breaking changes in the `py-2.0.0` release notes reach our code:
SQL window functions and exact-numeric literals (no `SQLContext`, no `pl.SQL`),
expression-plugin CSE (no plugin registration), Parquet `ENUM` reads (no `pl.Enum`),
map operations (additive), `cut`/`qcut` deprecation (neither symbol used).

### Behavioural surface — measured 2026-10-09

This is the part the import probe could not see.

Two clean venvs, Python 3.12.12, identical non-polars dependencies, the same 65
polars-touching files under `tests/dq/`, 1002 tests collected:

| polars | failed | passed | skipped |
| --- | --- | --- | --- |
| 1.38.1 (baseline) | 48 | 896 | 62 |
| 2.0.0 | 180 | 764 | 62 |

**Delta: +132 regressions, 0 fixes.** The 48 baseline failures are network-mock and
live-fetch tests, identical in both runs. Worst new file:
`test_market_data_parity.py` with 38 — the market-data correctness net.

The cost is concentrated in two undocumented removals, which is why the release-note
triage above reads clean while the suite does not:

1. **`min_periods` removed, renamed `min_samples`.** 26 call sites across 7 files in
   `digiquant/src`. The `min_samples` spelling is accepted on both 1.38.1 and 2.0.0, so
   the rename is source-compatible on the read side and this is mechanical.
2. **Implicit `str` -> `Date` casting removed.** All `cast(pl.Date)` and `to_datetime`
   sites total **41 across 22 files** in `digiquant/src` alone.

Counted call sites in `digiquant/src` for both changes: **67 across 22 files**, spanning
`cli/`, `data/onchain/`, `data/prices/`, `indicators/`, `mcp_server.py`, `research/`, and
`strategies/sdca/`. That is a cross-module migration, not a version bump.

Three corrections to the first handover's readings, each executed rather than inferred:

- **The yanked pin is not an outage.** `polars-runtime-32` 1.43.1 *is* yanked on PyPI
  (1.38.1 and 1.44.2 are not). But a cold-cache `uv pip install polars-runtime-32==1.43.1`
  **succeeds**, emitting only `warning: ... is yanked`, and `uv lock --check` exits 0. A
  yank withdraws a version from *selection*, not from *download*. Hygiene, not breakage.
- **The `str` -> `Date` break is loud, not silent.** Executing the real `merge.py:13`
  shape on both versions: 1.38.1 raises `InvalidOperationError` on a malformed date, and
  2.0.0 raises `InvalidOperationError` with *"casting from string to date is not
  supported"*. There is no silent path through the break. The silent-corruption risk is
  created by the **fix**, if someone reaches for `strict=False` — which is why Decision 3
  forbids it.
- **The two fixes interact.** `correlation.py:50` already branches on
  `schema.get("date") != pl.Date`, so some frames reach the merge boundary with `date`
  already typed. A branchless `.str.to_date()` would raise on exactly those frames. The
  dtype branch is required, not defensive.

### Behavioural risks for when 2.0 is taken

Retained from the prior draft. These are not covered by an import check and are the
checklist the migration must satisfy:

1. **Count-guarded sums become null on empty input (#29668).** 20 `.sum()` sites across
   13 files. In risk and portfolio aggregation a `0` becoming `null` is a numeric change,
   not a crash. Highest correctness risk in the set.
2. **Ragged rows now raise instead of silently dropping values (#29258).** 3
   `from_dicts` sites; 104 files construct `pl.DataFrame(...)`. Data-ingest paths
   (macro, ETF flows, onchain) are the plausible originators.
3. **`is_in` casts the needle exactly or not at all (#29486).** 5 sites across 4 files.
4. **Out-of-core enabled by default at 80% of RAM (#29741, #29734).** The repo sets no
   `POLARS_*` variable and calls no tuning function, so there is nothing to preserve —
   but large scans and backtests can silently spill to disk and run slow with no test
   failing.
5. **`nautilus_runner.py:36` `_POLARS_DT_ERRORS`** catches
   `AttributeError, TypeError, ComputeError, InvalidOperationError` and silently returns
   `"1-DAY"`. Tested against 1.43.1 and 2.0.0 on all three dtypes that path receives, the
   clause behaves identically in both. Recorded as a latent hazard for future majors, not
   as a 2.0 defect.

## Decision

**1. Bind the major in all three consumers: `polars>=1.43,<2`.**

The bound is the deliverable. A decision *not* to upgrade does not hold, because the next
`uv lock --upgrade` re-reads the same open floor and crosses the major anyway. Only a
declared ceiling closes it.

The floor is raised from the fiction `1.0` to `1.43`, the version the lock actually
pins and the only major-line version we have validated. Measured: a fresh resolve of
the bare requirement `polars` selects **2.0.0**; `polars>=1.43,<2` selects **1.44.2**.

This also retires the yank in the same change — 1.44.2 is newer than the locked 1.43.1
and is not yanked.

**2. Defer polars 2.0. Do not bump to `>=2.0`.**

The 2026-10-08 draft argued the opposite: that deferral forfeited the upgrade while the
regression net was wide, and that the import surface being intact meant the assessment
was never the expensive part. The assessment turned out to be cheap, and the answer
different. 132 behavioural regressions against 67 changed call sites in 22 files is
migration work on the scale of a cross-module epic, and the market-data parity net is
the thing that would be reporting the breakage.

**3. `canonical_date` is the single date-normalisation boundary.**

The contract, so the polars 2.0 migration has one place to change:

| Aspect | Contract |
| --- | --- |
| Boundary | Every frame entering `merge_history_live` or `apply_settled_close` is `canonical_date`-normalised first. No other module casts dates for merge purposes. |
| Inbound format | `str`, ISO-8601 `YYYY-MM-DD` |
| Internal dtype | `pl.Date` — never `str`, never `pl.Datetime` for daily bars |
| Parse | `.str.to_date(strict=True)`, **branched on the existing dtype**: `str` parses, already-`Date` passes through |
| Sentinels | `manifest_as_of` and `as_of` arrive as `datetime.date` objects |
| Forbidden | `strict=False` anywhere in this path |

`strict=True` is load-bearing: `strict=False` on `["2026-01-01","01/02/2026","not-a-date"]`
returns `[date(2026,1,1), None, None]`. A silently dropped bar shifts the merge window
and corrupts the R2-versus-live result without raising.

Sentinels must be `datetime.date` because `pl.lit(<str>).cast(pl.Date)` fails on **both**
1.38.1 and 2.0.0 — a string literal is not comparable to a date column under either
version, so this is a pre-existing constraint the migration must not break.

## Exit condition

Both, and neither is date-based. A date would be re-litigated on every heartbeat.

1. The `min_periods` -> `min_samples` rename and the `str` -> `Date` migration land
   across all 67 sites behind a green suite, and the five behavioural risks above are
   each explicitly checked.
2. Decision 3 is implemented and pinned by tests.

When taken, it must be its own task branch with the full suite as the gate — **not a
Renovate bump**. Renovate will offer `>=2.0` and cannot judge it.

## Consequences

**Positive:**

- A polars major can no longer arrive unannounced. `uv lock --upgrade` fails loudly
  instead of silently changing dataframe semantics under three packages.
- The floors state what we have actually validated (`1.43`) rather than the fiction `1.0`.
- The yanked 1.43.1 pin is retired by the same change.
- The date-normalisation contract is written down before the migration that must obey
  it, so `merge.py` has one defined shape to converge on.

**Negative / tradeoffs:**

- `polars>=1.43,<2` holds us to the 1.x line until the migration lands. That is the
  point of the bound, and a real constraint on a library that ships often.
- The bound also admits the next 1.x minor. Refreshing the lock to 1.44.2 is itself an
  untested minor bump and must be gated by the same suite (see DIG-2564).
- Coverage of the *import* surface is 100%; coverage of the *behaviour* surface is not
  measured. The five risks may surface in paths with no test.
- Decision 3 does not itself fix the 41 cast sites. It fixes where they must be fixed,
  which is the part that was undecided.

## Evidence limits

- The behavioural baseline is **1.38.1, not the locked 1.43.1** (yanked, and
  unresolvable in the pinned configuration). 1.43.1 sits between 1.38.1 and 2.0.0, so
  the +132 delta is a conservative figure for 1.43.1, not an exact one.
- `langgraph`, `ccxt`, `mcp` and `nautilus_trader` were not installed, so 3 files were
  excluded from collection and 4 skipped — identically in both runs, so the delta stands.
- **Only `digiquant` was executed against 2.0.0.** Digigraph and digisearch declare the
  same open floor and receive the same bound, but the 67-site count does not include
  them and no suite was run for either.
- No fixes were attempted in the measurement; the +132 is the unfixed cost.
- Import-surface and platform figures are from the 2026-10-08 draft at HEAD `8accbb296`
  and were not re-run for this revision.

## Links

- Related issues: DIG-2276 (this decision), DIG-1514, DIG-1515 (same open-floor class),
  DIG-2564 (the bounded floor and lock refresh)
- Supersedes: the 2026-10-08 draft of ADR 0031 in commit `0e178f61b9`, which decided
  Decision 2 the other way on import-surface evidence alone
- Upstream: `polars` `py-2.0.0` release notes, release id 385394861
- ADR index: `docs/adr/README.md`