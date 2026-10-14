# Review: PR #4792 (SDCA cycle-4 promotion slice)

- Reviewer: fresh-context subagent (`ses_f11271411fferzGCTaWjv6mCBv`), 2026-09-29
- Subject: `claude/sdca-btc-promo-slice` (c60fb0400) → `develop`, 9 files +440/-37
- Verdict: **APPROVE** (0 high / 0 medium / 3 low)

## Verification (reviewer-ran, all pass)

- None-path rate math bit-identical vs old formulas over 10,001 risk points (max abs diff 0.0).
- Promoted shape valid: mid-knees 15<45, 85>50, dead zone 45<50, nodes monotonic, mid rates exactly half-max.
- Test pins tight and green (92 passed in touched files).
- No secrets/PII, no live-trading paths, no settings.json in the file list.

## Findings

1. (low) `btc_optimized_provenance.json` `best_params` used research-branch key
   names (`power_law_weight` + 21 keys unknown to develop's 7-key
   `SdcaCompositeWeights`) — **fixed**: rewritten to full 10-key shape +
   develop `valuation_*` names, zero-valued research-only keys dropped, note
   appended. No programmatic consumer of `best_params` exists.
2. (low, docs) `METHOD.md` named modules absent on develop without marking
   them as research-branch ports — **fixed**: scope note added,
   `optimize_stage_a_weights_combined` and `_MID_TIER_KEYS` locations
   corrected, stale `curve_optimize` re-export comment in `curve_shape.py`
   corrected.
3. (low, disclosed, not fixed) `walk_forward.shape_from_params` on develop
   drops mid-tier keys, so the +43.21% gate record is not reproducible from
   this slice alone. Already disclosed in PR body as deferred follow-up
   (walk-forward passthrough + scorer rewrite). Same family:
   `curve_optimize.py` 6-key persist helpers would silently drop mid-tier
   fields — also follow-up.

<!-- in-session-review -->
