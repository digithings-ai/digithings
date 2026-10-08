# Review — PR #5232 test kit at `dbbbcc9fb`

| field | value |
|---|---|
| reviewer | QA (agent `2070ef88-9002-422c-ae3d-781c5bbfcada`), with the CodeReview skill |
| subject | PR #5232, head `dbbbcc9fb3818701ae08b38676d786602e6d7afb`, branch `DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync` |
| issue | DIG-2383 (re-verification), parent DIG-1659 (original review) |
| method | mutation testing, 43 hand-built mutants over 4 batches, plus a coverage cross-reference and equivalent-mutant adjudication for every survivor |
| suite at review | 727 passed in 14.73s (independently re-established; my DIG-1659 baseline was 680) |
| **verdict** | **NOT CLEAN.** G1–G7 closed, both open items closed, **4 new gaps** (G8 load-bearing) |

## Verdict on DIG-1659

**NOT CLEAN, with 11 named gaps.** G1–G7 are closed. G8–G11 are new.

Merge is not mine to decide. PR #5232 stays a **draft**; merging into `develop` is EM + CTO +
merge queue.

## Severity counts

| severity | count | ids |
|---|---|---|
| load-bearing | 1 | G8 |
| real gap | 2 | G10, G11 |
| coverage nit (guard rejection branch unexecuted, but the guard is protected) | 1 | G9 |
| closed | 9 | G1–G7, open item 1, open item 2 |

## Mutation totals

43 mutants across 4 batches. **33 CAUGHT, 10 SURVIVED.** Of the 10 survivors:

- **4 equivalent mutants** — no observable difference exists for any test to assert
  (G6a, G6b, CZ4, AD4). Not gaps.
- **2 acknowledged dead code** — `curve_optimize.py:352` and `:467`, the unreachable
  `sell_max_rate > 0.0` lines the author documented in the renamed F1 test.
- **4 real gaps** — G8, G9, G10, G11.

Every survivor was adjudicated for equivalence before being named a gap. That discipline is
the correction to my own G6 mistake, where I reported an equivalent mutant as a gap.

---

# G8 — `fast_crash_vol` sign is unpinned (LOAD-BEARING)

`indicator_catalog.py:531` — `return (-z).alias("fast_crash_vol")`.

Mutant: `(-z)` -> `(z)`. **Survives all 727 tests**, including the author's own
`TestFastCrashVol::test_vol_spike_is_sell_favourable`.

That test asserts only `min(present) < 0.0` over `z[60:100]`, and that passes under both signs:

| variant | `min(z[60:100])` | why |
|---|---|---|
| original `(-z)` | `-3.0` | the burst saturates the `clip(-3.0, 3.0)` |
| mutant `(z)` | `-8.819e-05` | the burst saturates to `+3.0`, and the window minimum then comes from near-zero post-wash calm bars |

`min(x) < 0` is satisfied by *any* negative value anywhere in the window. It never asserts the
spike itself is negative. Every other assertion in the class is invariant under `z -> -z`:
`test_decays_back_to_zero_once_swings_shrink` (|z[-1]| = 8.3e-05 both), `test_bounded_to_three`,
`test_flat_price_is_flat_zero`, `test_aliased_and_uses_the_default_windows` (null prefix and
last-non-null only), `test_windows_are_tunable` (null/non-null positions only),
`test_length_mismatch_rejected` (raises before any z).

Measured on the author's fixture (226 bars, burst at indices 61..95, peak realized vol at 80):

| window | original (min, max) | mutant (min, max) |
|---|---|---|
| `z[60:100]` (author's) | -3.000000, +0.000088 | -0.000088, +3.000000 |
| `z[61:95]` (burst only) | -3.000000, **-1.453621** | **+1.453621**, +3.000000 |
| `z[76:85]` (peak-vol +-4) | -2.424922, -1.810759 | +1.810759, +2.424922 |

**Why this is load-bearing.** `fast_crash_vol` is the only research extra reachable without an
external source pair — it reads `btc_price` alone. Its docstring states the sign exists so
"an unusual vol spike reads sell/de-risk-favorable". A flip makes the composite *buy* crashes,
and nothing in 727 tests notices.

**Fix — any one of these passes the original and rejects the mutant** (verified, see
`g8_actionable.py`):

```python
assert all(v < 0.0 for v in z[61:95] if v is not None)   # every burst bar is negative
assert max(v for v in z[61:95] if v is not None) < -1.0  # burst saturates negative
assert z[80] < 0.0                                       # the peak-vol bar itself is negative
```

The first is the strongest: `orig=True, mut=False`. The author's window is too wide — `z[60:100]`
includes 5 post-burst calm bars whose near-zero values dominate the `min`.

# G9 — `align_to_dates` duplicate-date policy is unpinned (coverage nit)

`indicator_catalog.py:289` — `.unique(subset=["date"], keep="last")`.

Mutant: `keep="last"` -> `keep="first"`. Survives. **Observable in 6 of 8 adjudication cases**
(`duplicates-adjacent`, `duplicates-interleaved`, `all-same-date`; both `forward_fill` True and
False), always differing at index 0.

No test in the kit supplies duplicate source dates, so neither the dedup policy nor the
existence of the dedup is pinned. Severity is a nit rather than a gap because the code is
correct — the defect is that nothing would catch it becoming incorrect.

# G10 — the onchain log transform is unpinned, and its test is a tautology for it

`_log_ratio_sign_flipped_z` (shared by all four Bitview families). Mutant: drop the `.log()`.
Survives.

Two causes, both measured:

1. **The family tests use a degenerate window.** At `window=2, min_samples=1` a geometric input
   gives an *identical* rolling z on the log and level paths — always `+-0.7071067812`
   (= `+-1/sqrt(2)`), verified for `geom(40,1.01)`, `geom(40,0.99)`, `geom(120,1.001)`,
   `geom(120,1.05)`. Numerator and denominator both collapse to a constant offset, so the two
   paths coincide exactly.
2. **`test_log_transformed_not_level` asserts the wrong property.** It asserts scale invariance
   under `x37` on a geometric ramp. Scale invariance holds for **both** paths — it is
   homogeneity of the rolling z, since `mu` and `sigma` each scale linearly. The assertion is
   real but cannot fail for a level-based implementation. Its name and docstring ("a ratio is
   log-transformed first, so the z is scale-invariant") overstate what it checks.

**A distinguishing input exists at production windows.** At `window=30/min_samples=15` and
`window=90/min_samples=20` the log and level paths differ, on both a geometric ramp and a
multiplicative-spike input (flat 100 with a 4-day 900x burst at indices 118..122: equal at
`window=2`, different at 30/15 and 90/20). The source docstring's actual justification — "a
bull-market spike would otherwise dominate a level-based rolling std" — is testable with a
multiplicative jump at production windows. A ramp/scale test is not.

# G11 — the `fast_crash_vol` warmup contract is unpinned

`indicator_catalog.py:528` — `log_ret.rolling_std(window_size=window, min_samples=min_samples)`.
Mutant: `min_samples` -> `1`. Survives, and is **not** an equivalent mutant.

Measured at production defaults (`window=14, min_samples=7, z_window=90, z_min_samples=20`):

| | original | mutant |
|---|---|---|
| first non-null z index | **26** | **21** |
| differing positions on the author's own fixture | — | **64**, last at index 95 (len 226) |

Indices 96..225 are identical, which is why a tail-only assertion (`z[-1] == approx(0.0)`)
cannot see it. The defect is confined to the warmup and burst region.

Why it survives:

- `test_aliased_and_uses_the_default_windows` asserts `all(v is None for v in z[:20])`. The
  mutant's first non-null is 21, so `z[:20]` is still all null. The test's own comment states
  the real contract ("14d realized vol needs 7 returns, then a 90d z needs 20") but the
  assertion only pins 20 where the true answer is 26. A bound chosen to pass, not to pin.
- `test_windows_are_tunable` asserts `z[4] is None` and `z[7] is not None`. Under the mutant the
  first non-null moves to 5, so both hold.

Note this is the same *kind* of contract the author did pin for the Wilder RSI
(`TestWilderRsiWarmup`, leading `length - 1` positions null, caught 18 ways by the joint
mutant). It is unpinned here only.

**Fix:** assert the exact first non-null index — `assert z[26] is not None` and
`assert all(v is None for v in z[:26])` — for the default windows, and the analogous exact
index for the tunable case.

---

# What is closed

## G1–G7 — all seven hold

| finding | mutant | failures |
|---|---|---|
| G1 calendar-delay sign flip | `apply_calendar_delay`: `- timedelta` -> `+ timedelta` | **5** |
| G2 beats-baseline inverted | `> baseline.buy_mean_risk + 1e-9` -> `- 1e-9` | 1 |
| G3 valuation guard deleted | `_require_extra_name`: delete the dedicated branch | 1 |
| G4 fast_crash_vol dropped | `weight_search._extra_weight_names()` derivation | **3** |
| G5 weekly cutoff strict | `<= last_daily` -> `< last_daily` | **3** |
| G6 Wilder joint warmup | both sides `min_periods` -> `1` | **18** (author said 16) |
| G7 trough/peak inclusivity | `<=` -> `<` and `>=` -> `>` | 2 and 2 |

**G6 — I was wrong, the author was right.** My survivor (`avg_loss` `min_periods=length` -> `1`)
is an equivalent mutant. With `adjust=False`, polars' `ewm_mean` `min_periods` gates which
values are *emitted*, not computed; leading nulls propagate through `avg_gain / avg_loss`, so
each side's own warmup masks the other's absence. I verified this independently rather than
accepting it — 144 claim-checks over lengths 2/3/5/14/30/50 x 8 input cases (including
degenerate divide-by-zero inputs), NaN-aware comparison: **0 observable differences**.
G6 is closed. My original finding was a bad finding on my part.

Two author counts are stale but immaterial: G6c is 18 failures, not 16; `m2` default `0.0 -> 1.0`
is 92 failures, not 44.

## Both open items are closed

`rs_eth_fast` validator and `TestDefaultMatchesPowerLawOnly` — **CAUGHT 12 / SURVIVED 0** across
4 mutants for open item 1 and 5 for open item 2.

| mutant | failures |
|---|---|
| fast leg reuses `slow_window` | 6 |
| slow leg uses `fast_window` | 3 |
| **silently clamps `min_samples` instead of raising** (my own vacuity check) | 4 |
| blend `name` changed | 2 |
| `m2` default non-zero | 92 |
| `valuation` default doubled / halved | 5 / 5 |
| `fast_crash_vol` default non-zero | 80 |
| `_at_least_one_positive` guard off | 1 |

The raise-tests are **not** vacuous: making `rs_eth_confluence_z` silently clamp
(`min_samples = min(min_samples, window)`) instead of raising breaks 4 of them.

On the author's `valuation 1.0 -> 2.0` count of "exactly 1": they measured inside their own
class. Cross-suite it is **5 failures in 5 files**, of which 4 are pre-existing develop tests.
So the new test is partly redundant with develop coverage. Fine — not a gap.

## The 3 uncovered PR lines are guard rejection branches, not correctness gaps

Coverage over the whole `sdca` package is 89%. Cross-referencing uncovered lines against lines
**added by this PR** (merge-base `f0dd82a6d`, `git diff -U0`):

| file | PR-added lines | PR-added and uncovered |
|---|---|---|
| `curve_optimize.py` | 500 | 2 (352, 467) |
| `indicator_catalog.py` | 492 | **0** |
| `price_oscillators.py` | 470 | **0** |
| `weight_search.py` | 269 | **0** |
| `stage_a.py` | 259 | 1 (403) |

**1990 PR-added executable lines under `digiquant/`; 3 never executed.** All three are
rejection branches that no test reaches — yet removing or weakening each guard *is* caught
(2, 1 and 4 failures respectively). Coverage nits, not correctness gaps. All 11 uncovered lines
in `indicator_catalog.py` are pre-existing develop code, confirmed by diff-position analysis.

## I retract my own "largest untested surface" claim

I told the author that `indicator_catalog.py`'s non-weights regions — the 7 new families,
`rs_eth_confluence_z`, `causal_rolling_z`, `align_to_dates`, `build_extra_indicators` — "remain
unmeasured… this is the largest untested surface in the PR." **That was wrong.** All 492 lines
this PR adds to that file are executed. The claim was mine, from my DIG-1659 review, and the
coverage cross-reference refutes it.

What survives from that region is not "unmeasured" but "executed and still under-asserted":
G10, G11 and the `TestWilderRsiWarmup` pinning are all *pass rate* findings, not coverage
findings. Executing a line is not the same as a test noticing when the line is wrong. That is
the entire point of this review, and it is where G8 lives.

---

# Still not claimed, and not closed by this commit

- My sign-flip blind spot is not ruled out across ~5,500 lines. I closed 7 of the families
  (onchain 11 failures, fear/greed 4, rs_eth 1, dxy 1, m2 1) — but `fast_crash_vol` was the one
  that got through. That is the residual risk, and G8 is its measured size.
- No repo-wide `make test-unit`. Scope is one package.
- The four breaking rewires stay deferred, each still pinned by its own test.
- Money and rates: no `Decimal` added. Correct — the SDCA backtest chain is float by design on
  `develop` and the execution boundary is untouched.

# Evidence

All under `/Users/chrisstefan/Code/digithings/.paperclip/qa-reviews/DIG-2383/`:

| file | what |
|---|---|
| `mut.py`, `mut2.py` | the harness; `mut2.py` also records how many tests failed and which |
| `g1-g7.json` / `.results.json` | batch 1, 12 mutants |
| `batch2.json` / `.results.json` | batch 2, 12 mutants (open items) |
| `batch3a.json`, `batch3b.json` | batches 3a and 3b, 19 mutants (shared helpers, families, sign flips) |
| `g6_equiv_check.py` | G6 equivalent-mutant adjudication, 144 checks |
| `batch3a_survivor_check.py` | CZ4 / AD4 / AD1 adjudication, 216 checks |
| `fcv_sign_check.py` | G8 root cause |
| `g8_actionable.py` | G8 discriminating-assertion search |
| `on2_log_check.py` | G10 root cause |
| `fcv3_check.py`, `fcv3_where.py` | G11 adjudication and localization |

Every mutation was reverted with `git checkout --` immediately. The author's worktree was
`TREE CLEAN` at `dbbbcc9fb` before, during and after.
