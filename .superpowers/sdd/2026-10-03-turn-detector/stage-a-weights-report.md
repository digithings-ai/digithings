# Stage A weight calibration for GLD — both approved pin sets (#4804)

Worktree: `.worktrees/4804-gold-pin-sets`, branch `chore/4804-gold-pin-sets`.
Research-only. Stage A only. No performance claim anywhere in this report.

---

## 1. Read-first records

Files read before writing anything:

| Record | What it settled |
|---|---|
| `digiquant/src/digiquant/strategies/sdca/stage_a.py` (192 lines) | `optimize_stage_a_weights` sweeps the **full** `itertools.product(valuation_grid × grid**len(names))`; `require_extras=True` skips rows with no enabled extra; combos whose `cycle_overlap_score` raises are skipped, not fatal; empty grid → `ValueError`. `risk_from_weighted_z` **consumes** z vectors, calibrates nothing. `_BAND_BONUS = 25.0`, `ACCUMULATE_RISK_MAX = 35.0`, `DISTRIBUTE_RISK_MIN = 80.0`. |
| `digiquant/src/digiquant/strategies/sdca/cycle_windows.py` | `kind_on(day)` scans windows linearly; `gold_v1()` = 6 pins, `gold_v2()` = 20, both ±45d. |
| `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` | `SdcaCompositeWeights` has 16 non-negative fields; `_at_least_one_positive` raises `ValueError` on all-zero; `enabled_extras()` is the "which legs are on" read. |
| `digiquant/scripts/fit_gold_indicators.py` (1615 lines) | `anchor_z(date_s, price_s)` = shipped `rolling_z` rails at rolling 90d / z 1.0; `build_z` dispatches to the **shipped** z-functions; `best_row` = max *signed* separation; `candidate_pool` filters `verdict == "keep"`. |
| `digiquant/scripts/run_gold_pin_set_fits.py` (807 lines) | The by-path harness-load pattern; the fits-artifact shape (`sets.<label>.indicator_reads` + nested `fits.indicators.<name>.rows`). |
| `digiquant/scripts/plot_gold_pin_sets_v2.py` (662 lines) | The hand-rolled-SVG pattern to mirror; the `close`-vs-`open` column trap is called out in its own docstring. |
| `digiquant/.scratch/gold_pin_set_fits.json` | The 14 fitted indicators × 2 pin sets, every scored grid row, `best_overall`, and the capture read. **Read, not re-derived.** |
| `tests/dq/strategies/sdca/test_stage_a.py`, `test_gold_pin_set_fits.py` | The local script-import convention (`importlib` by file path, not a package module). |

**Measured before designing:** `anchor_z` over the 5,499-bar GLD calendar takes 0.02 s;
one `risk_from_weighted_z` + `cycle_overlap_score` evaluation takes **5.6 ms**. That
number is what makes the search-pool decision below arithmetic rather than a guess.

---

## 2. What was built (glue only)

| File | Role |
|---|---|
| `digiquant/scripts/run_gold_stage_a_weights.py` | Reads best-fitted params from the fits artifact → builds each z via the harness's `build_z` → hands them to the **shipped** `optimize_stage_a_weights`. Four runs. Writes `.scratch/gold_stage_a_weights.json`. |
| `tests/dq/strategies/sdca/test_gold_stage_a_weights.py` | 20 pins, including an **independent re-sweep** of the weight grid. |
| `digiquant/scripts/plot_gold_stage_a_weights.py` | Hand-rolled stdlib SVG, four panels. |
| `digiquant/ARCHITECTURE.md` | Appended to the SDCA section. |

**No existing src file was edited.** `stage_a.py`, `fit_gold_indicators.py`,
`cycle_windows.py`, `composite_risk.py`, `indicator_catalog.py` are all untouched;
no grid, `valuation_grid`, `ACCUMULATE_RISK_MAX`, `DISTRIBUTE_RISK_MIN`,
`_BAND_BONUS` or 0.5 capture bar was changed; the indicator grid sweep was not
re-run; nothing was tuned after seeing an objective. No `nautilus_trader` import,
no pandas, polars only, ruff line length 100.

---

## 3. RED → GREEN

Fail-first was done by moving the runner out of the tree and running the new
spec file against its absence.

**RED** (runner moved to a temp hold, `pytest -q`):

```
collected 20 items
tests/dq/strategies/sdca/test_gold_stage_a_weights.py ..F.............F.  [ 90%]
..                                                                       [100%]
FAILED test_gold_stage_a_weights.py::test_the_search_names_actually_reach_the_sweep
FAILED test_gold_stage_a_weights.py::test_the_reported_btc_sdca_shape_is_the_published_composite
========================= 2 failed, 18 passed in 1.32s =========================
```

(the first RED pass, before the runner existed at all, was `1 failed, 19 errors` —
the whole file errored on the missing module.)

**GREEN** (after two real fixes — a wrongly-shaped `build_extra_z` fixture and a
label assertion that did not match the wording actually shipped):

```
collected 20 items
tests/dq/strategies/sdca/test_gold_stage_a_weights.py ..................  [ 90%]
..                                                                       [100%]
============================= 20 passed in 1.45s ==============================
```

Both RED failures were genuine test bugs, found by the tests, not papered over.

### The six required pins, and where each lives

| Pin | Test | Note |
|---|---|---|
| (a) grid agreement | `test_the_winner_is_the_argmax_of_an_independently_swept_full_grid` (parametrized ×2) | The test re-implements `valuation_grid × grid**n` itself, scores with the shipped `cycle_overlap_score`, and asserts **both** the argmax weights **and** `num_evaluations` match. Includes an **inverted** third leg, so a grid that quietly skipped a name would pick different weights. This is the pin that catches a silently-narrowed grid. |
| (b) `require_extras=True` never zero extras | `test_require_extras_true_never_returns_zero_enabled_extras` | Fixture is deliberately one where valuation-only is the *best* row, so the setting has to work to leave a leg on. |
| (c) no-non-degenerate excluded AND recorded | `test_a_leg_with_no_non_degenerate_fit_is_excluded_and_recorded`, `test_an_excluded_leg_is_never_passed_as_a_missing_series` | The second one asserts `risk_from_weighted_z` **raises** on a positive weight with no series — the failure the wiring is avoiding. |
| (d) `require_extras=False` DOES allow valuation-only | `test_require_extras_false_allows_the_valuation_only_result`, `test_the_two_settings_are_genuinely_different_runs_not_one_result_twice` | Second test also pins `REQUIRE_EXTRAS_SETTINGS == (False, True)`. |
| (e) determinism | `test_two_identical_runs_serialize_byte_identically` | Byte-identical JSON from two independent runs. |
| (f) clean `ValueError` | `test_a_missing_fits_artifact_is_a_clean_refusal_not_a_re_derivation`, `test_a_set_payload_without_the_reads_block_is_an_error_not_a_blank_cell`, `test_an_unapproved_pin_set_label_is_refused`, `test_windows_that_never_overlap_the_risk_series_raise_value_error`, `test_the_runner_has_no_bare_assert_statements` | The last one scans the runner source for bare `assert` — an `AssertionError` nobody recognises is not a failure mode. |

Load pattern: **the local script-import one** — `importlib.util.spec_from_file_location`
by path, matching `test_gold_pin_set_fits.py`, because the runner lives under
`digiquant/scripts/` and not on `src`'s package path.

---

## 4. The four-run console table (verbatim)

```
GOLD STAGE A VARIABLE-WEIGHT CALIBRATION — BOTH PIN SETS, BOTH require_extras
pin set    req_extras  objective    spread  trough_f   peak_f   evals  weights
------------------------------------------------------------------------------
gold_v1         False   128.7594   84.0786    0.8404   0.9468     728  val=1 (valuation-only)
gold_v1          True   121.9177   76.8380    0.8564   0.9468     726  val=1 real_rate=0.5
gold_v2         False   111.3160   71.8337    0.8173   0.7620    6560  val=1 (valuation-only)
gold_v2          True    99.3702   61.3980    0.7933   0.7256    6558  val=1 sma_band=0.5
```

Both settings, both pin sets, always. `require_extras=False` returns
**valuation-only** on both pin sets — a legitimate finding, reported rather than
buried, which is exactly why `require_extras=True` runs beside it.

---

## 5. `btc_sdca` shape comparison

Published `btc_sdca` reference: `valuation=1.0, m2=0.5, dxy=0.5, weekly_macd=0.5,
weekly_rsi=0.25` (SMA band and BTC/ETH RS at 0) — **five legs, four of them
partial-weight.** Reported for shape comparison only; nothing was copied from it,
tuned toward it, or benchmarked against it.

| | legs | partial-weight legs |
|---|---|---|
| published `btc_sdca` | 5 | 4 (0.5 / 0.5 / 0.5 / 0.25) |
| gold `gold_v1`, `require_extras=True` | 2 | 1 (`real_rate=0.5`) |
| gold `gold_v2`, `require_extras=True` | 2 | 1 (`sma_band=0.5`) |
| gold, `require_extras=False` (both sets) | 1 | 0 (valuation-only) |

**Gold's winners do not have the same shape as the precedent — they collapse to
valuation plus at most one 0.5 leg**, and on both pin sets the `require_extras=True`
row scores *below* its own valuation-only row (121.92 vs 128.76 on `gold_v1`; 99.37
vs 111.32 on `gold_v2`). That is the finding. It has not been tuned away, and the
feasibility narrowing of the search pool (§6) is the one thing that could have
caused it, so it is flagged rather than buried.

---

## 6. Exclusions, with reasons

`search_names` is the frozen `verdict == "keep"` pool — the same filter
`candidate_pool()` already applies in `fit_gold_indicators.py`. Two reasons are
recorded per name; both appear in the JSON artifact and on the console.

**`gold_v1`** — searched: `real_rate`, `ig_oas`, `nfci`, `gld_slv`, `sma_band`.

| excluded | reason | detail |
|---|---|---|
| `uup`, `gvz`, `hy_oas`, `breakeven_5y`, `gdx_gld`, `m2`, `walcl` | frozen verdict != keep | `verdict 'drop'` on negative best separation (−2.4225 … −0.0241) — outside the frozen keep pool |
| `weekly_rsi` | no non-degenerate grid row | 2 scored rows, every one degenerate; verdict `degenerate_pass` |
| `weekly_macd` | no non-degenerate grid row | 4 scored rows, every one degenerate; verdict `degenerate_pass` |

**`gold_v2`** — searched: `real_rate`, `ig_oas`, `nfci`, `gld_slv`, `walcl`,
`weekly_macd`, `sma_band`.

| excluded | reason | detail |
|---|---|---|
| `uup`, `gvz`, `hy_oas`, `breakeven_5y`, `gdx_gld`, `m2` | frozen verdict != keep | `verdict 'drop'` on negative best separation (−1.5625 … −0.4252) |
| `weekly_rsi` | no non-degenerate grid row | 2 scored rows, every one degenerate; verdict `degenerate_pass` |

`weekly_macd` is searched on `gold_v2` but excluded on `gold_v1` — it has 2
non-degenerate rows there and 0 on `gold_v1`. The exclusion is a property of the
pin set, not a hardcoded list.

**The feasibility decision, stated as a decision.** The shipped optimizer sweeps the
full `itertools.product`, so the 12 non-degenerate names would be `3^12 × 3 =
1,594,323` evaluations. At the **measured 5.6 ms** per evaluation that is ~2.5 h per
run, ~10 h for four runs. Narrowing along an already-ruled keep/drop line was
preferred to a sweep that never finishes, and it is recorded in the script's
`SEARCH_POOL_NOTE`, in the JSON artifact, on the console, and in `ARCHITECTURE.md` —
never applied silently. **This is the one choice that could bias §5's shape finding**,
and it is the reason the narrowing is reported alongside it rather than in a footnote.

---

## 7. DIAGNOSTIC, not the published keep/drop

The objective scored here is `cycle_overlap_score.objective` =
`spread + 25.0 × (trough_in_accumulate_frac + peak_in_distribute_frac)`, with the
frozen bands `accumulate ≤ 35.0` / `distribute ≥ 80.0` — a **shape diagnostic**
asking how well composite risk lines up with the pinned cycle windows.

The published Stage A keep/drop is `optimize_stage_a_by_backtest` on in-sample
`vs_flat_dca_pct` subject to a 10% capital-deployed floor and a 50% drawdown cap —
not vs-lump, not Sharpe, and not this objective. **This run does not constitute the
published keep/drop, and no weight in it is promoted on its strength.**

Also IN-SAMPLE twice over: each leg's params are a max over the frozen indicator
grid, and each weight is a max over the weight grid, both scored against windows
derived from the same GLD history the z-series are built from — a partly-selected
upper bound, not out-of-sample evidence. Windows are a scoring target, not execution
periods: no exposure floor, nothing about time in market.

**No return, Sharpe, drawdown, trade count or PnL is claimed anywhere** — not in the
script, the JSON artifact, the SVG, `ARCHITECTURE.md`, or this report.

Sequence: Stage A only. Stage B (`run_sdca_walk_forward`) freezes the weights, then
`regularize`. Research-only: nothing outside `.scratch/` written by the runner,
never `settings.json`, never `--push-supabase`, no live-trading path.

---

## 8. Chart

- Script: `digiquant/scripts/plot_gold_stage_a_weights.py` — hand-rolled stdlib SVG
  only, no matplotlib (not installed), mirroring `plot_gold_pin_sets_v2.py`.
- Four stacked panels (one per run), each with: the composite risk curve under that
  run's weights, the **35.0 / 80.0 band rails** drawn and labelled, and that panel's
  pin-set windows shaded (trough green / buy side, peak red / sell side) with the pin
  itself marked on the panel's top edge.
- Footer states in substance: IN-SAMPLE; the cycle-overlap objective is a DIAGNOSTIC;
  this is **NOT** a performance claim and **NOT** a backtest result; the risk axis is
  unitless composite risk, not a portfolio value, equity curve or allocation.
- Written to `apps/digiquant-web/public/gold_charts/gold_stage_a_weights.svg` and
  copied to `digiquant/.scratch/gold_pngs/` (both UNTRACKED). 122,945 bytes.
- **HTTP code: `200`** — `curl -s -o /dev/null -w '%{http_code}'`
  `http://127.0.0.1:4011/gold_charts/gold_stage_a_weights.svg`
- Regeneration note recorded in the commit: the 4011 dev server's cwd is the
  **sibling** worktree `.worktrees/task/4804-sdca-strategy-for-gold--gld/
  apps/digiquant-web`, not this one, so the file must be copied there for the URL
  to resolve. It was, and the 200 is from that served copy.

---

## 9. Verification

| Gate | Result |
|---|---|
| New spec file | **20 passed** |
| Full `tests/dq/strategies/sdca/` | **653 passed, 1 skipped, 1 failed** |
| The 1 failure | `test_gold_sell_mask.py::test_frozen_box_grounds_on_real_inputs` — `FileNotFoundError: digiquant/.scratch/gold_mayer_multiple.json`. **PRE-EXISTING**, the artifact is in no commit at base. NOT fixed, NOT worked around: the artifact was not committed and that test was not edited. |
| The 1 skip | `test_gold_pin_set_fits.py` side-effect probe, "no fits artifact present" — the probe wants an artifact absent to watch. Pre-existing behaviour. |
| `ruff check` (3 new files) | All checks passed |
| `ruff format --check` (3 new files) | 3 files already formatted |
| `make doc-check` | `check_doc_links: OK (448 markdown files scanned)` |

---

## 10. SHAs

| SHA | Commit |
|---|---|
| `aa696f245` | Calibrate the gold Stage A variable weights against both pin sets (#4804) — script + tests, one commit |
| `151a627f4` | Chart the four gold Stage A weight runs as four risk panels (#4804) — chart script, one commit |
| `4a8607700` | Document the gold Stage A weight calibration in the SDCA section (#4804) — `ARCHITECTURE.md`, one commit |
| `dc2688f7f` | branch tip before this work (clean cherry-picked Plan-22 branch) |

Untracked and deliberately not committed: `.scratch/gold_pin_set_fits.json`,
`.scratch/gold_pin_set_selection.json`, `.scratch/gold_stage_a_weights.json`,
`.scratch/gold_pngs/`, `apps/digiquant-web/public/gold_charts/`, and
`digiquant/data/price-history` (the symlinked CSVs — **never commit**).

---

## 11. Self-review

**What I verified myself rather than taking on trust:**
- The 5.6 ms/evaluation figure is measured on this machine against this calendar, not
  estimated — it is the whole basis of the search-pool narrowing.
- The GLD loader path is `load_sdca_ohlcv(symbols=["GLD-USD"], data_path=..., data_dir=None)`,
  which reads the `close` **column by name**. Column index 1 is `open`; reading that
  once already caused a wrong-date incident in this repo, so it is called out in the
  chart script's docstring too.
- Every exclusion was cross-read against the artifact rather than inferred: I dumped
  `sets.<label>.fits.indicators.<name>` for both pin sets and confirmed the
  degenerate/drop split, including that `weekly_macd` flips between sets.

**Where I made a judgement the owner may want to revisit:**
- The search-pool narrowing (§6). It follows an existing frozen verdict rather than a
  new rule, and it is recorded everywhere — but it is still my call, and it is the
  one thing that could produce the narrow shape in §5. If the owner wants the full
  12-name sweep, that is ~10 h of compute and a decision worth making explicitly.
- Using the **capture read** (`best_grid_row`, largest `|separation|`) as the params
  source rather than `best_overall`. That is what the artifact's `indicator_reads`
  block holds, and it is the row "that speaks for the indicator" under Engine 2b
  Ruling 2 — but note it is fitted by magnitude, so for `ig_oas` (direction `-1` on
  both sets) it lands on a **negative** row while `best_overall` would land on a
  positive one. Since `SdcaCompositeWeights` cannot take a negative weight, an
  inverted leg cannot be expressed in this engine at all, which is a real limitation
  worth stating rather than papering over.

**Concerns:**
1. **Both pin sets prefer valuation-only.** The `require_extras=True` rows score
   *below* their valuation-only counterparts on both sets. Under this diagnostic that
   says the frozen keep-pool extras add no cycle-window overlap beyond the rolling-z
   anchor. That is a finding about the objective, not about the extras' merit, and it
   is emphatically **not** a keep/drop — the published backtest objective is untouched.
2. **The objective is in-sample twice.** Params fitted on the scored history, then
   weights fitted on the same scored history. Upper bound, not skill.
3. **The chart's risk panel is a shape, not a book.** Unitless composite risk. It must
   never be read as an equity curve or an allocation, and the footer says so.
4. **`num_evaluations` differs by 2 between the two settings** on both pin sets (728 vs
   726; 6560 vs 6558). That is `require_extras=True` skipping the two valuation-only
   rows per `valuation_grid` value — arithmetic, not an anomaly, and it is exactly what
   pin (a) cross-checks against the independent sweep.