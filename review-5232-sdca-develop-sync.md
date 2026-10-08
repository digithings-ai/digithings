# Review: PR #5232 — SDCA research port for DIG-1597 (leaves 1–5)

- **Reviewer:** QA agent (`2070ef88-9002-422c-ae3d-781c5bbfcada`), in-session review; did not author the change. Reassigned from Code Reviewer (`c59332b4`, paused with "Process lost") by CoS.
- **Subject:** PR digithings-ai/digithings#5232 (draft), head `d369411e5` on `DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync`, base `develop` @ `f0dd82a6`, author `chrizefan` (Quant). 14 commits, +5514/−13, 10 files.
- **Issue:** DIG-1659.
- **Scope reviewed (honest scope, per Quant's own framing):** *are the five ported modules correctly ported onto develop's current shape?* — **not** "is the SDCA subsystem fully migrated". 41 of 47 differing files are not in this PR (9 branch-only, 19 superseded, 13 stale); the stranded remainder is DIG-1667.
- **Verdict:** **changes requested** — the port itself is sound and well-pinned, but the branch cannot merge as it stands (2 real merge conflicts against current `develop`, 2 of 5 leaves already superseded). Leaves 3–5 are genuinely new payload and are green. Merge authority stays with EM + CTO; QA does not merge.
- **Severity counts:** critical 1 · major 3 · minor 3 · info 4

Verification performed:

- Baseline suite against PR head `d369411e5`: **670 passed, 1 skipped** in ~16s (`test_tearsheet_charts.py:343` skips — matplotlib not installed locally). Quant's "680 passed" figure counts the 10 tests in `test_onchain_valuation.py`, which I had to `--ignore` only because `httpx` is absent from the local venv — that file is **not** a PR defect. Both numbers are correct for what they measure; report them together.
- **40 mutation tests** injected into the PR's source and reverted each (worktree `git status` clean, byte-compared after every batch).
- `ruff check` + `ruff format --check` clean on all 10 PR files.
- **Trial merge of PR head into current `origin/develop` (`e65884b8f`) performed, conflicts resolved, full sdca suite re-run: 687 passed, 1 skipped.** `ruff` clean on both resolved files. Details in M1.

---

## Critical

### M1 — The branch does not merge into `develop`; 2 of 5 leaves are already superseded, and one conflict resolution *silently reverts* a develop-side fix if taken naively

PR #5232 is `mergeable_state: dirty`. It is based on `f0dd82a6`; `origin/develop` has advanced 44 commits to `e65884b8f`. A real `git merge` produces **two content conflicts**:

- `digiquant/src/digiquant/strategies/sdca/weight_search.py` (3 hunks)
- `tests/dq/strategies/sdca/test_price_oscillators_confluence.py` (add/add)

The second one is the important one, because it is a trap rather than a conflict. Develop's copy of `test_price_oscillators_confluence.py` (567 lines) is an **older, weaker** version: it lacks `TestBlendWeightContract` entirely and hard-codes `long_term_weight=0.5` in its `_blend` helper, so it cannot see the `medium_term_weight = long_term_weight` defect that class was written to catch. The PR's copy (666 lines) is a strict superset — the only lines unique to develop's side are the superseded docstring, the two-line `_blend` signature, and one `long_term_weight=0.5` argument. **`git checkout --ours` is the correct resolution here; `--theirs` silently deletes the test that closes the CoS's named gap.** Whichever way it is resolved, the resolution must be recorded in the PR, not left to whoever rebases.

`weight_search.py` conflicts because develop's DIG-1598 commit `b5580b336` appended `optimize_stage_1_survivor_weights` (a `(0,1]`-grid, OOS-ranked, `is_feasible`/`objective_score`-filtered search) at exactly the point where this PR appends `OscillatorPeriodScore` / `search_oscillator_periods_by_backtest`. The resolution is a union: keep both functions, union the `walk_forward` import set (develop contributes `is_feasible` and `objective_score`, which the PR's version drops), and union `__all__`. I verified this empirically:

```
# qa-merge-test worktree: merge origin/develop into d369411e5, resolve both conflicts
$ grep -c optimize_stage_1_survivor_weights  digiquant/.../weight_search.py   -> 2
$ grep -c search_oscillator_periods_by_cycle_overlap digiquant/.../weight_search.py -> 3
$ grep -c TestBlendWeightContract tests/.../test_price_oscillators_confluence.py -> 2
$ pytest tests/dq/strategies/sdca/ -q -> 687 passed, 1 skipped in 15.68s
$ ruff check / format --check on both resolved files -> clean
```

**The rebase is mechanical and I have proven the resolution is sound. What is missing is that nobody has done it.** Required before this can merge: rebase onto `e65884b8f` (or merge `develop` in), resolve `weight_search.py` as the union described, resolve the confluence test as `--ours`/superset, and re-run the sdca suite. I am not asking for a rebase-and-pr as part of this review — only that the branch owner does it and re-requests review, because the merge result is a materially different tree from what I reviewed.

### M2 — `indicator_catalog.py`: resolving the conflict by taking the PR side reverts a live develop fix

Not listed by GitHub as a conflicted path (it auto-merges), which is precisely why it is dangerous. `develop`'s `b5580b336` added `_full_calendar_values()` and rewrote `m2_liquidity_z` / `dxy_z` to compute YoY and rolling-z on the **full FRED/DXY calendar**, then align onto BTC days — the docstring is explicit that doing the shift after an inner join onto Coinbase BTC days "amputates leading Coinbase years" / "charges the 90-day warmup a second time". The PR branch was cut before that commit and carries the **old** implementations.

`git diff origin/develop -- …/indicator_catalog.py` on the PR head shows 71 lines whose entire content is the *deletion* of develop's fix. A naive "take the branch" resolution — the reflex when a branch looks like a port — would ship that regression. The auto-merge happens to keep develop's side here (the PR touches neither function body in a way that conflicts), but the tree still needs an explicit check, because the file is in the PR's 10-file payload and any future rebase could land differently. **Assert in the resolution that develop's full-calendar `m2_liquidity_z`/`dxy_z` survive.**

### M3 — Leaves 1 and 2 are already on `develop` and byte-identical; only leaves 3–5 are real payload

This is not a defect but it changes what "approve" would mean, so it must not be discovered after merge. Leaves 1 and 2 landed via **PR #5239** (DIG-1550 stranded-work stack, merged as `d1d050341`, carrying DIG-1597 commits `bc3260d3a`, `9afb5ca78`, `be9f708a6`, `a1a035384` and DIG-1598's `b5580b336`). File-by-file comparison of PR head against current `develop`:

| file | status |
|---|---|
| `sdca/price_oscillators.py` | **identical to develop** |
| `tests/…/test_indicator_catalog_research_extras.py` | **identical to develop** |
| `sdca/indicator_catalog.py` | differs 71 lines — develop ahead (see M2) |
| `tests/…/test_price_oscillators_confluence.py` | differs — develop's is the **older** version (see M1) |
| `sdca/stage_a.py` | differs 259 — PR adds `optimize_stage_a_weights_combined*`, absent on develop |
| `sdca/curve_optimize.py` | differs 509 — PR adds `continuous_shape_ok`, `search_wide_knee_curve`, `sweep_dead_zone_width`, `score_dead_zone_width`, `dead_zone_shape_params`, all absent on develop |
| `sdca/weight_search.py` | differs 311 — PR adds `search_oscillator_periods_by_backtest`, `search_oscillator_periods_by_cycle_overlap`, `_require_extra_name`, `_extra_weight_names` |
| `tests/…/test_stage_a_combined.py` | **new in this PR** (not on develop) |
| `tests/…/test_weight_search_periods.py` | **new in this PR** (not on develop) |
| `tests/…/test_curve_optimize.py` | differs 296 — develop's dropped the PR's additions |

So the effective payload is leaves 3, 4, 5 plus the three new/extended test files. The PR description should say so, because "+5514 lines, 5 leaves" materially overstates what is landing. **Recommend the branch be rebased and the PR re-scoped to leaves 3–5** rather than merged as a five-leaf port.

---

## Minor

### m1 — `fast_crash_vol_z`'s sign convention is genuinely unpinned (live PR-authored test debt)

`indicator_catalog.py:530` returns `(-z).alias("fast_crash_vol")` — vol spike → negative risk, i.e. contrarian like `dxy_z` and `fear_greed_z`. Removing the negation is a real behaviour change and **no test fails** (670 passed). `TestFastCrashVol::test_vol_spike_is_sell_favourable` (`test_indicator_catalog_research_extras.py:545-552`) asserts only `min(present) < 0.0` over `z[60:100]`; I checked numerically that the *unflipped* series still dips to about `-0.0001` inside that window, so the assertion passes either way. Contrast `dxy_z` (mutation → 1 failed, `test_indicator_catalog.py:349`) and `fear_greed_z` (→ 4 failed), both of which are properly pinned.

This is the same 17th survivor Quant recorded in the PR's own confluence-test docstring, described there as "a deliberate neutral control — a no-op dtype coercion". That description does not match what is actually there: the surviving mutant is a **sign flip on a contrarian indicator**, not a dtype coercion. Since `test_indicator_catalog_research_extras.py` is part of this PR's payload, this is the PR's test debt to close, not pre-existing debt. Fix is one assertion — pin the sign, e.g. assert the spike window is predominantly negative (`sum(present) < 0`) rather than merely dipping below zero.

### m2 — `beats_baseline_concentration`'s four individual guards are untested in isolation

`curve_optimize.py:347`. Removing the function wholesale is caught (2 failures), but deleting **any one** of its guards — both deep-fill-fraction guards, the `buy_mean_risk` guard, the `sell_mean_risk` guard, the `sell_frac_deep` guard — gives **670 passed**. I probed each remaining guard directly and each still returns `False` for the case it is meant to reject, so this is under-discrimination, not a bug: `test_curve_optimize.py:439` varies all four fields together, so no test isolates one rule. Four mutants, one test shape. Worth one parameterised test that moves one field at a time.

### m3 — `continuous_shape_ok`'s trailing `sell_max_rate > 0.0` is effectively dead code

Changing `return shape.sell_max_rate > 0.0` → `return True` gives 670 passed. `SdcaCurveShape.sell_max_rate` is `Field(ge=0.0, le=100.0)` (`curve_shape.py:51`), so the only falsy value is `0.0` — and `CURVE_SEARCH_BOUNDS["sell_max_rate"] = (3.0, 40.0)` already excludes that from every searched candidate. Either drop the clause or keep it with a comment saying it is unreachable through the search bounds, so the next reader does not have to re-derive this.

---

## Info

### i1 — Two known open items Quant recorded rather than fixed, both accepted

1. `TestOscillatorSpecRsEthFast` has no counterpart. The branch's `SdcaOscillatorSpec` carried `rs_eth_window` / `rs_eth_fast_window` / `rs_eth_fast_min_samples` plus a validator raising `ValueError` when `fast_min_samples > fast_window`; develop's spec has no `rs_eth_*` fields at all and `rs_eth_confluence_z` (`indicator_catalog.py:534`) takes them as plain kwargs with no validation. Porting the validator would have been a *behaviour change* on develop, not a port — correct call to leave it out of this PR, but it is a real capability regression that needs a home (DIG-1667 is the obvious one).
2. `TestDefaultMatchesPowerLawOnly` is neither ported nor pinned. Nothing on record states that develop's default composite (only `valuation` non-zero) was a deliberate choice. `TestDormantNames::test_published_defaults_are_untouched` and `test_default_weights_materialize_nothing` pin the *values*; neither pins the *decision*.

### i2 — The four deferred breaking rewires are correctly deferred and correctly pinned

`valuation`→`power_law` rename, rewiring `build_extra_indicators` onto the confluence functions, trimming `PRICE_OSCILLATOR_NAMES`, moving `causal_rolling_z` into `composite_risk` — each has its own leaf, and each is pinned as *still deferred* in two places: `test_weight_search_periods.py:819 test_deferred_power_law_rename_is_not_ported` and `test_stage_a_combined.py:187 test_the_branch_valuation_to_power_law_rename_is_still_deferred` (loops 6 functions asserting `"power_law"` absent from their signatures). `price_oscillators.py:793 price_oscillator_z_vectors` still returns exactly develop's three keys, confirming the rewire was not applied by accident. This is the right way to stage a breaking rename and I want it on the record as such.

### i3 — Dormancy is properly pinned in both directions

`TestDormantNames::test_not_published` (parametrized over `RESEARCH_ONLY_NAMES`, checks all 4 published tuples) and `::test_published_tuples_are_exactly_develops` (asserts `MACRO_INDICATOR_NAMES == ("m2","rs_eth","dxy")`, `PRICE_OSCILLATOR_NAMES == ("weekly_rsi","weekly_macd","sma_band")`, and the 6-name `EXTRA_INDICATOR_NAMES`). `SdcaCompositeWeights` has `valuation: Field(1.0, ge=0.0)` as its only non-zero default; every research-only weight and every oscillator weight is `Field(0.0, ge=0.0)`. Flipping the `valuation` default to `0.0` fails 32 tests. The published surface genuinely cannot move without a test failing.

One harmless survivor: `enabled_extras`'s `> 0.0` → `!= 0.0` gives 670 passed, which is expected — every field is `ge=0.0`, so the two are equivalent. Noted only so it is not mistaken for a gap later.

### i4 — Mutation coverage: what the suite actually pins

**Caught (30 of 34 mutants, with failure counts):**

| area | mutant | failures |
|---|---|---|
| `weight_search.py` | unknown-name guard disabled (`_require_extra_name`) | 2 |
| `weight_search.py` | drop forced `probe_weight` | 4 |
| `weight_search.py` | solo weight zeroed in cycle-overlap search | 7 |
| `weight_search.py` | rank on *worst* candidate by IS | 2 |
| `weight_search.py` | candidate z-series never used (by-backtest) | 7 |
| `weight_search.py` | candidate z-series never used (cycle-overlap) | 6 |
| `weight_search.py` | empty-`param_candidates` guard removed | 1 |
| `indicator_catalog.py` | `fear_greed_z` sign flip removed | 4 |
| `indicator_catalog.py` | `dxy_z` sign flip removed | 1 |
| `indicator_catalog.py` | non-positive pre-log nulling → `1.0` | 2 |
| `indicator_catalog.py` | `fast_crash_vol` log→plain returns | 1 |
| `indicator_catalog.py` | `_FAST_CRASH_VOL_WINDOW` 14 → 90 | 1 |
| `indicator_catalog.py` | `fear_greed_z` forward-fill disabled | 2 |
| `indicator_catalog.py` | length-mismatch guard removed | 1 |
| `price_oscillators.py` | `causal_rolling_z` ±3 clip removed | 1 |
| `price_oscillators.py` | sigma floor removed | 9 |
| `price_oscillators.py` | `agreement_frac` min/max → max/min | 6 |
| `price_oscillators.py` | silent-leg treated as disagreement | 1 |
| `price_oscillators.py` | null-leg passthrough dropped | 5 |
| `price_oscillators.py` | `medium_term_weight = long_term_weight` | 5 |
| `indicator_catalog.py` | `_at_least_one_positive` body removed | 20 (collection) |
| `indicator_catalog.py` | `valuation` default 1.0 → 0.0 | 32 |
| `stage_a.py` | strict → non-strict objective comparison | 1 |
| `stage_a.py` | `_weight_complexity` valuation term removed | 2 |
| `stage_a.py` | `_is_better` tie-break → always False | 1 |
| `stage_a.py` | `_floor_candidates` floor moved to end | 1 |
| `stage_a.py` | `_floor_candidates` floor ≤ 0 check removed | 2 |
| `curve_optimize.py` | `continuous_shape_ok` bounds loop widened to knee keys | 6 |
| `curve_optimize.py` | `shape_from_bounds_ok` reads one item only | 1 |

**Survivors (4):** the three in m1–m3 above, plus `apply_calendar_delay` (`curve_optimize.py:492`) — flipping `<= cutoff` to `> cutoff`, or removing its negative-delay `ValueError`, both give 670 passed, and **no test in the repo references the function**. That one is *not* a blocker: it is develop-side pre-existing code that this PR only re-exports in `__all__`. It is worth a test on develop, but not on this PR.

Two things this campaign confirms about the CoS's original concern: the `medium_term_weight` gap **is** genuinely pinned (5 failures), and the unknown-name guard **is** genuinely pinned in both call paths — and usefully, when the guard is disabled the suite still fails, but with `"Value error, at least one indicator weight must be positive"` instead of the expected pydantic error. That is exactly the accidental trip `TestUnknownIndicatorNameIsRejected` was written to distinguish, and the message-contains + not-`PydanticValidationError` + `built == []` assertions do their job.

### i5 — `optimize_stage_a_weights_combined*` uses `>` with no parsimony tie-break, and that is asserted

`stage_a.py`: `optimize_stage_a_weights` uses `_is_better` (with tie-break); `..._combined` and `..._multi_ratio` use plain `>`. This is deliberate and pinned at `test_stage_a_combined.py:432` — "the floor — not a parsimony tie-break — is what keeps them there." Confirmed correct on both sides of the merge: develop's `stage_a.py` has `_weight_complexity` and `_is_better` intact, so the two code paths remain distinguishable after resolution.

---

## Recommendation

1. **Do not merge as-is.** Re-request review after the branch owner rebases onto `e65884b8f` and resolves the two conflicts as described in M1 (union for `weight_search.py`, superset/ours for the confluence test) and asserts develop's full-calendar `m2_liquidity_z`/`dxy_z` survive (M2). The resolution is mechanical — I ran it end to end and the sdca suite is green at 687 passed, 1 skipped.
2. **Re-scope the PR description to leaves 3–5.** Leaves 1–2 are already on develop via #5239 and byte-identical; the +5514/5-leaf framing overstates what lands.
3. **Fix m1 in this PR** (`test_vol_spike_is_sell_favourable` should pin the sign, not just dip below zero) and correct the confluence-test docstring's description of the 17th survivor — it is a sign flip on a contrarian indicator, not a dtype coercion.
4. m2/m3 are follow-ups; m2 can reasonably become one parameterised test.
5. DIG-1667 remains the home for the 41 stranded files and for the `rs_eth_fast_min_samples` validator (i1).

QA does not merge. Merges into `develop` are EM + CTO.