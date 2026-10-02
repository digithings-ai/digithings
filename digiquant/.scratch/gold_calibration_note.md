# Gold calibration note — Task 4, Plan 4 (#4804)

Untracked analysis. No code changed, nothing applied. Every value below needs
owner accept before any library edit, preset-bar change, or override-on-record
promotion. BTC precedent: `btc_optimized` was promoted with overrides on
record, not by moving library bars — same fork applies here.

## Derivation rule (veto attribution)

Gate feasibility is `is_feasible` (`walk_forward.py:287-293`): feasible iff
`capital_deployed_pct >= floor` (default 10.0, `walk_forward.py:50`) AND
`max_drawdown_pct <= cap` (default 50.0, `walk_forward.py:51`). The gate script
passes no objective, so defaults hold — current bars are floor 10 / cap 50 /
sens 2.0 (`SENSITIVITY_SPIKE_PCT`, `walk_forward.py:37`; stable iff
maxΔ <= bar, `optimize.py:420`).

The writer records per fold only OOS-vs-flat, dd, and the feasible flag —
NO deployed value, NO veto field (`run_gold_curve_search.py:212-220`). So:

- fold with dd > 50 and feasible=false → dd-cap veto (determinable).
- fold with dd <= 50 and feasible=false → floor veto BY ELIMINATION (the only
  other clause). The exact deployed value is UNMEASURED from the record.
- sensitivity worst-neighbor key + per-neighbor ΔOOS are absent (script says so
  at `run_gold_curve_search.py:252-253`; develop has no worst-neighbor
  attribution). Knee-cliff attribution is UNMEASURED — not asserted.

Verdict: vetoing BAR measurable by elimination; veto magnitudes (deployed %,
worst-neighbor key) unmeasurable from record. Nothing below invents them.

## Counterfactual table 1 — per-fold status at CURRENT bars

| variant | fold | OOS vs flat | dd | feasible | vetoing bar (rule above) |
|---|---|---|---|---|---|
| deep | F0 | +10.85% | 5.47% | false | floor (dd 5.47 <= 50 excludes cap) |
| deep | F1 | −9.14% | 24.49% | true | — (feasible AND negative) |
| deep | F2 | +15.29% | 18.76% | true | — |
| full | F0 | +2.37% | 1.49% | false | floor (dd 1.49 <= 50 excludes cap) |
| full | F1 | −8.43% | 24.45% | true | — (feasible AND negative) |
| full | F2 | +15.19% | 18.75% | true | — |
| v1 | F0 | +38.20% | 7.35% | false | floor (dd 7.35 <= 50 excludes cap) |
| v1 | F1 | −11.19% | 26.05% | true | — (feasible AND negative) |
| v1 | F2 | +16.54% | 18.77% | true | — |

No dd veto anywhere (max dd 26.05, v1 F1). Every infeasible fold is a floor
veto by elimination. Every F1 is feasible and negative — no bar touches that.

## Counterfactual table 2 — floor sweep {10, 5, 0} (cap 50, sens 2.0 held)

Feasibility recomputed as deployed >= floor AND dd <= 50. Deployed is
unrecorded: F0 deployed known only as < 10; F1/F2 deployed known as >= 10
(feasible at floor 10 with dd <= 50). Mean OOS is invariant — `_mean_oos`
averages ALL folds regardless of flags (`optimize.py:294-297).

| variant | fold | floor 10 | floor 5 | floor 0 |
|---|---|---|---|---|
| deep F0 (+10.85, dd 5.47) | infeas | INDETERMINATE (deployed < 10, vs 5 unknown) | feas* |
| deep F1/F2 | feas | feas (deployed >= 10 >= 5) | feas |
| full F0 (+2.37, dd 1.49) | infeas | INDETERMINATE | feas* |
| full F1/F2 | feas | feas | feas |
| v1 F0 (+38.20, dd 7.35) | infeas | INDETERMINATE | feas* |
| v1 F1/F2 | feas | feas | feas |

\* floor 0 vacuous provided deployed >= 0 (pathological negative-deployed
case not excluded by the record; no evidence for it). Mean OOS unchanged at
every cell: deep +5.67 / full +3.04 / v1 +14.52.

## Counterfactual table 3 — cap sweep {50, 55, 60} (floor 10, sens 2.0 held)

All recorded dd (5.47/24.49/18.76; 1.49/24.45/18.75; 7.35/26.05/18.77) sit
below 50 already. Raising the cap changes ZERO flags in all 9 fold-cells.
Exactly computable: NO CHANGE at 55, NO CHANGE at 60.

## Counterfactual table 4 — sens sweep {2.0, 4.0, 6.0} (floor 10, cap 50 held)

Rule stable iff maxΔ <= bar. Recorded maxΔ: deep 2.40, full 3.87, v1 3.86
(neighbors 47 each; no per-neighbor data).

| variant | maxΔ | 2.0 | 4.0 (margin) | 6.0 |
|---|---|---|---|---|
| deep | 2.40 | unstable | stable (+1.60) | stable |
| full | 3.87 | unstable | stable (+0.13 — thin) | stable |
| v1 | 3.86 | unstable | stable (+0.14 — thin) | stable |

## Sensitivity attribution

Worst-neighbor key: UNMEASURED from record (absent from both v2 JSONs and the
v1 log; writer limitation, not an oversight to fill by guessing). Per-neighbor
Δmetric vs ΔOOS: UNMEASURED. The knee-cliff hypothesis (2.0 bar measures grid
discreteness, not economic instability) is therefore UNRESOLVED — it can be
neither confirmed nor refuted from this record. Structural facts that survive
without it: deep maxΔ 2.40 exceeds the bar by only 0.40 (grid-noise scale);
full/v1 maxΔ ~3.87 exceeds it by ~1.87 (larger, still unassigned). Winner knees
sit on adjacent grid entries (buy_knee 45 ∈ {30,45,60}, sell_knee 50 ∈
{50,65,80}) with the gate evaluating a single-knee projection of a mid-tier
search winner — a geometry where ±5% bumps plausibly bite, but plausibility is
not attribution. A rerun emitting per-neighbor deltas would settle it; this
task does not rerun.

## Headline the tables force

Broadening hurt: mean OOS +14.52 (v1) → +5.67 (deep) → +3.04 (full). F1
negative in all three (−11.19 / −9.14 / −8.43) while feasible. NO bar change
moves any OOS number or flips any F1 sign — bars relabel feasibility and
stability only. What bars CAN fix: the F0 floor veto on strong folds (floor
→ 0 admits deep F0 +10.85, full F0 +2.37, v1 F0 +38.20 — all vetoed on sizing
with dd ≤ 7.35, not on risk) and the sensitivity grid-noise label (sens → 4.0
stabilizes all three, with thin-margin caveat on full/v1). The promotion
decision — despite F1-negative and despite broadening hurting the mean — is
NOT a bar decision and is not made here.

## RECOMMENDATION (owner-accept required; nothing applied)

1. floor 10 → 0, gold scope. Cells: deep F0 (+10.85, dd 5.47), full F0 (+2.37,
   dd 1.49), v1 F0 (+38.20, dd 7.35) — all floor-vetoed by elimination with dd
   far under the cap, so each veto is sizing, not risk. Floor 5 is NOT
   recommended: Table 2 shows F0 at floor 5 INDETERMINATE (deployed unmeasured),
   so 5 buys no provable fix; 0 admits F0 exactly (modulo pathological
   negative deployed, no evidence). dd cap remains the risk rail.
2. cap 50 HOLD. Cells: Table 3, all 9 fold-cells NO CHANGE at 55/60; max
   recorded dd 26.05 leaves 23.95pp margin. No evidence for moving it.
3. sens 2.0 → 4.0, gold scope, WEAK (bar-fitting risk flagged). Cells: deep
   2.40 clears by 1.60; full 3.87 and v1 3.86 clear by 0.13/0.14 — thin enough
   that 4.0 looks fitted to the data, and the knee-cliff rationale is
   UNMEASURED from record (no worst-neighbor key). Accept 4.0 as noise-margin
   or hold 2.0 and carry the unstable label — owner picks, on the record.
4. NO bar change fixes F1-negative (deep −9.14, full −8.43, v1 −11.19, all
   feasible) or the broadening-hurt ranking (+14.52 → +5.67 → +3.04, means
   invariant to bars). Any promotion despite those is an override-on-record
   decision per the BTC precedent, not a calibration outcome — owner-accept
   required, separate task. This task applies nothing.
