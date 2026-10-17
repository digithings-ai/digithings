# Gold SDCA research records (#4804)

Carried from the gold research added to `digiquant/ARCHITECTURE.md` on
`chore/rescue-4804-gold-artifacts` (after the task/4804 tip). Develop has since
slimmed ARCHITECTURE.md, so these records live here instead. Paths such as
`.scratch/...` refer to research output; see `docs/research/sdca-gold-weekend-branch.md`.

**No-trend vote (gold v4, #4804).** `build_risk_index(..., valuation_weight=0.0)`
omits the valuation leg entirely — the same rule as zero-weight extras — so a
null valuation z contributes neither vote nor null mask. `resolve_sdca_risk_model("rolling_z",
..., rolling_z=z)` selects trailing mean-reversion rails (`RollingZRiskModel`:
causal rolling log-price mean ± z·std; the v4 seed uses window 90d / z 1.0, no
time trend). `indicator_display_name("valuation", model=...)` labels the leg per
rails: `btc_power_law` → "power law" (default, BTC charts unchanged),
`generic_valuation` → "valuation trend", `rolling_z` → "mean reversion". Note:
the engine walk-forward refits rails on the IS window only, which starves a
trailing-window operator of pre-history — the gold v4 gate scores rolling folds
through a gold-side causal concatenated-history loop (engine fitter protocol
untouched; window/z are fixed seed constants, trailing inputs ≤ t).

**Beat-both attempt (gold v5, #4804) — NEGATIVE, vote-level miss.** v5 froze a
secular vote (rolling-z 1260d ≈ 5yr half secular swing / z 1.0, m2/uup 0.5,
oscillators 0 — short-horizon votes sell the grind) and judged it against
beating lump AND flat on mean OOS. Result: flat +1.34% (beats), lump −12.45%
(miss); folds f0 +9.79/−26.76, f1 −8.60/+2.48, f2 +2.82/−13.08, feasible
T/T/T; sens UNSTABLE 2.63 (`sell_knee_risk:−5%`); frontier 0/432 feasible
shapes beat both — no curve in the searched space fixes it, so this is a vote
failure, not a winner-selection failure. No v5 tearsheet was built. Standing
implication: in gold's secular bull, cash-holding + profit-taking drag vs lump
is structural to the SDCA family, not tunable within it; beating lump needs a
different family (or accepting flat-DCA as the bar).

**Decoupled sell gate (gold v6, #4804) — NEGATIVE as-shipped; frontier
follow-up proposed as a NEW plan.** Mechanism is generic, not a gold
special-case: `run_backtest(..., sell_dates: set[date] | None = None)` vetoes
only the sell branch (a vetoed day holds exactly like a null-risk day but
keeps its negative rate in frame — visuals key off `daily_trade_usd` / fill
sell days, never rate sign); `SdcaStrategyConfig.sell_dates` + `on_bar`
mirror it; `None` default reproduces legacy exactly (BTC-identical). Gold
supplies mask CONTENT via `scripts/build_gold_sell_mask.py`: frozen strict
box z<=-2.0 & m>=1.5 (exploratory origin disclosed; re-freezing after results
is a plan violation), causal by construction (shipped `real_rate_z` trailing
1260d + trailing-1000d SMA mirror, truncation-equality asserted every build),
74 days spanning 2009-11-27..2020-08-06. Buy vote = v4 vote unchanged
(rolling-z 90d / z 1.0 + m2/uup 0.5 + weekly RSI / log-MACD / SMA-band 0.25;
v6 `search`/`gated_shape` blocks byte-identical to v4). Outcome
(`.scratch/gold_curve_search_v6.json`, causal rolling, holdout absent):
mean OOS vs flat +15.38% (beats) / vs lump −1.72% (miss); folds
f0 +33.20/−11.14 (73 mask days), f1 −5.84/+5.57 (ZERO mask days — pure
buy-and-hold-plus-oscillator-noise), f2 +18.77/+0.41 (1 day, 2020-08-06);
all feasible; sens UNSTABLE 2.75 (`buy_knee_risk:+5%`, same worst key as v4).
Robustness is report-only (8 box variants, same binary, selection untouched):
means cluster tight (flat +14.43..+15.38, lump −2.35..−1.72), none beats lump
— the miss is systematic, not a knife-edge. Verdict NEGATIVE: lump half
misses AND sens fails (flat half passes). Frontier-both is 144/1080 NONZERO
(vs v5 0/432) — shapes exist that beat both under this vote+mask, but the
winner-as-shipped is not one of them, so re-selecting among the frontier on
a lump-aware criterion is a NEW plan with its own bar, not this one.
Diagnostics: `scripts/build_gold_v6_diagnostic_tearsheet.py` renders the
masked full-history curve-sim run (slug `gold_sdca_v6`, fill sell days 34 vs
1344 curve-sign sell days — the veto in one number); `plot_gold_secular_legs.py`
adds `gold_mask_rug.svg` (full-history GLD close + 74-day rug + fire/silent
event labels). Preview served JSON + chart only — no `page.tsx` entry, because
pages are candidates and v6 is not one.

**Frontier reselect (gold, #4804) — Plan 16, BEATS-BOTH (conditional).**
Re-selected among the v6b frontier on the frozen criterion argmax
min(mean_flat, mean_lump) with tie-breaks higher-lump then lower-DD
(reading per-shape numbers then changing it would have been a violation;
≤3-attempt bound, attempt 1). Record (`.scratch/gold_reselect_v6.json`,
NOT recomputed in visuals): 144 eligible; selected rank #1 (buy 35/60,
sell 65/30, curvatures 1.0/1.0, single-knee; vote and 74-day strict-box
mask identical to v6): criterion min +3.85 = mean OOS vs flat +24.32 /
vs lump +3.85; fresh sens STABLE 1.63 (≤ 2.0, 48 neighbors, worst
`sell_knee_risk:−5%`); folds f0 +63.52/+9.09 (73 mask days), f1
−7.88/+3.28 (ZERO mask days), f2 +17.32/−0.81 (1 day); all feasible
(Rule-B frontier). Verdict BEATS-BOTH is conditional, carried with four
mandatory disclosures everywhere: (1) selected ON the reported metric —
expect optimism; (2) lump margin thin +3.85 with f2 lump −0.81; (3) f1
zero mask days (selection barely sees the mask there; mask evidence = f0
73d + v6 robustness); (4) ranks #2–#4 identical gated eval (mid-tier
projection tie). Diagnostics: `scripts/build_gold_reselect_diagnostic_tearsheet.py`
mirrors the v6 builder (same rails/backtest/overlays chain, display
constants $1,000 from 2010-01-01; slug `gold_sdca_v6_reselect`, full-history
masked curve-sim net +279.1% / dd −42.1% / 4210 bars / fill sell days 34);
`scripts/plot_gold_reselect_equity.py` adds `gold_reselect_equity.svg`
(stdlib SVG, same 960x440 pattern: reselected equity vs lump + flat with
the selection marked). Preview serves JSON + chart + a TEMP `page.tsx`
entry (allowed only on BEATS-BOTH; REVERT-BEFORE-MERGE, uncommitted).

**Reselect promotion branch-side (gold, #4804) — Plan 17, live-path proof.**
Three corrections ride the promotion branch: (Ruling 4) the entry's
`risk_model` was `generic_valuation` with 90/1.0 as dead pass-through —
corrected to `rolling_z` so the reselect rails are live; (Ruling 5) a
reviewed per-entry `trade_start` override at the `run_and_write` binding
site (gold `2010-01-01`, BTC/defaults fallback byte-identical, paired pin);
(Ruling 6) the publish path read `model.coefficients` unconditionally and
crashed (`AttributeError`) on the first real `RollingZRiskModel` through
`run_and_write` — provenance now records window/z params on the
rolling branch only (`getattr` detection; fitted BTC/generic notes
byte-identical, proven by unmodified-green suites). Live proof (verbatim
no-push `generate_tearsheets.py --strategy gold_sdca`, 1/1 succeeded):
Nautilus net +279.1% / dd −42.1%, 4210 bars 2010-01-04→2026-09-29, rails
rolling90/z1.0, v4 weights exact, fill sell days 34 = 34 (same
`dca_metrics` fill metric, not rate sign), vs flat +48.46 / vs lump +8.71
(rounding parity with the curve-sim diagnostic; rate-sign days exact
2261/1344/605). Known engine artifact, quoted not hidden: buy-fill days
308 live (Nautilus) vs 428 diagnostic (curve-sim) — units/cost-basis match
to ~4dp, so execution aggregation, not economics. Preview slug
`gold_sdca_reselect_live` (TEMP `page.tsx` entry, REVERT-BEFORE-MERGE,
uncommitted) — a new slug because a Nautilus live-path proof differs in
kind from the `gold_sdca_v6_reselect` curve-sim selection diagnostic. The
four Plan-16 disclosures ride along unchanged (selection-on-metric
optimism; thin +3.85 lump margin with f2 −0.81; f1 zero mask days; #2–#4
projection tie) plus holdout ABSENT (spent, never re-scored).

**Cycle-windows Stage-A + two-vote Stage-B gate (gold, #4804) — Plan 18,
NEGATIVE on both votes.** Pins frozen from documented history (peaks
2008-03-17 / 2011-09-06 / 2020-08-07 / 2026-09-29 incomplete top; troughs
2008-10-24 / 2015-12-17 / 2022-10-21; ±45d; `SdcaCycleWindows.gold_v1()`).
Stage-A overlap search (43M-combo grid, IN-SAMPLE — selects nothing
shippable; only the Stage-B gate judges): winner valuation-only (1.0, all
extras 0.0), separation 87.83; best valuation-free vote (steer-compliant
candidate) real_rate-only rank #49, separation 62.88, gap −24.95. Behavior
on the frozen reselect curve (2010-01-04→2026-09-29, 16.7yr; baseline 34
sells = 2.03/yr): V1 1 fill (0.06/yr, 0.03×) — NEGATIVE, does not
oscillate; V2 61 fills (3.65/yr, 1.79×) — oscillates. Stage-B
causal-rolling90 gate (1728 shapes × 4 windows, mask days 73/0/1, holdout
absent): V1 mean OOS flat +26.80 (beats) / lump +5.68 (beats), feasible
3/3, sens stable 0.17, frontier 560/1728 — benchmarks pass but behavior
fails, unshippable; V2 mean OOS flat +15.65 (beats) / lump −2.49 (MISS),
feasible 3/3, sens stable 0.25, frontier 0/1728 — NEGATIVE (failed: lump,
frontier-both). Correction (Task-4 review): the V1−V2 gap isolates the
WEIGHT VECTOR under identical rolling90 rails — NOT trend evidence; the
frozen trend rails appear nowhere in the gate; V1-as-gated is
trailing-anchor-only with trend-rails SELECTION LINEAGE as the caveat
(owner's call whether it disqualifies; moot — V1 fails the oscillation
requirement regardless). Verdict: NEITHER clears the combined bar — the
oscillation-vs-lump tension is now MEASURED (oscillating vote trails lump;
lump-beating vote never trades), not theorized. Visuals:
`scripts/plot_gold_stagea_verdict.py` renders `gold_stagea_verdict.svg`
(fills/yr + gate means vs both benchmarks + frontier); preview served JSON
+ charts only, no `page.tsx` entry (entry ONLY on BEATS-BOTH = NONE).

## Secular-leg firing verdict for gold phase-b decision (#4804, Plan 14a Task 3 — NO-GO)

Real-rate leg (DFII10 staged 5940 rows, 2003-01-02→2026-09-29; `real_rate_z` window-1260, no-flip washout, voteless default; 5480 valid z days; full-history deciles 10/25/50/75/90 = -2.115/-1.432/+0.128/+1.070/+1.743, clipped ±3.0) and 200w leg (causal completed-weeks, 1000d SMA, first-valid 2008-11-06, 4500-row series in untracked `digiquant/.scratch/gold_mayer_multiple.json`) fire as follows — judged read-only on the recorded Ruling-3 / Task-2 numbers, no new runs, no weight/window/threshold changes: | event | real-rate z | 200w multiple | — 2011-09 top: z −2.522 (below 10th-pct −2.115 → top-decile rich, rich side passes) / multiple 1.7159 (week-end 2011-09-02, close 183.24 / sma200w 106.7877); 2015-12 bottom: z +1.066 (≈75th-pct 1.070, vs 90th-pct +1.743 → NOT top-decile cheap, misses by 0.677) / multiple 0.7672; 2020-08 high: z −3.000 (clip floor) / multiple 1.4819; 2022-10 dip: z +2.252 / multiple 0.9836; now: z +1.530 (2026-09-29) / multiple 1.4707 (week-end 2026-09-25). Half-a (real-rate) FAILS: the bar needs top-decile cheap spanning the 2015 bottom AND top-decile rich spanning the 2011 top, and the 2015 reading (+1.066) sits at ~75th percentile, not top-decile (≥ +1.743). Half-b (200w) FAILS on selectivity: the 2011 level passes (1.7159 ≥ 1.5) but 349 grind-days sit above 1.5 outside the ±6mo 2011 window (2011-03-06→2012-03-06), i.e. 349/4500 = 7.76% ≥ 5% bar (5% budget = 225d; excess = 124d; all-valid-days >1.5 = 423/4500 = 9.4%; >1.7 outside = 154d, concentrated 2025-09-30→2026-05-14). Verdict: **NO-GO for phase-b engine design** — both halves fail, so no engine extension follows from this plan; COT / Dow-gold / CPI-oil legs stay recon-listed, not tasked.

