# sdca-gold-weekend: one branch for the gold SDCA work

Built 17 Oct 2026 from `origin/develop` (c7c164c25). It pulls together the SDCA and
gold work that hadn't reached develop yet. Nothing was deleted from the source
branches, and PR #5777 is still open.

## What came from where

| Source | What was carried |
| --- | --- |
| `DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync` | Stage A dual-timeframe search (`stage_a.py`), continuous/wide-knee/dead-zone curve searches (`curve_optimize.py`), per-oscillator period searches (`weight_search.py`), on-chain extras in `indicator_catalog.py`, plus tests |
| `claude/sdca-full-recalibration` (PR #5777, DIG-1581) | Recalibration rounds 1-4: ablation, baseline evaluator, feasibility-aware curve scoring, quantile-rails non-crossing fix, M2 causal-EMA smoothing, RSI curve power 3.5, `extra_windows` plumbing, round/blend/diagnostic scripts, RESEARCH_STATE ledger, specs and plans |
| `chore/rescue-4804-gold-artifacts` (includes all of `task/4804-sdca-strategy-for-gold--gld`) | Gold work after the task/4804 tip: sell-mask (`build_gold_sell_mask.py`, sell-dates veto in backtest and Nautilus), reselect provenance, `gold_v1` cycle pins, `real_rate` leg, indicator fitting, v4/v5/v6/reselect/stage-A diagnostic builders, gold plans, gold preset/settings entries, small research results in `digiquant/.scratch/` (100 KB or less each) |
| `task/4804-sdca-strategy-for-gold--gld` | Nothing on its own: it's already in develop or covered by the rescue branch |
| `DIG-1667-sdca-stranded-ports`, `DIG-1597-sdca-port-work` | Nothing unique: already in develop or in the DIG-1597 port branch |

## Adaptations

- `#5777` used the old `power_law` weight name. It now uses develop's `valuation` name (`valuation=`, `.valuation`, `valuation_weight`).
- Develop's own `run_full_recalibration.py` and `run_dual_timeframe_composite_search.py` are unchanged. The PR #5777 versions sit beside them as `*_recal_v1.py`.
- Gold research notes that the rescue branch added to `digiquant/ARCHITECTURE.md` are now in `docs/research/gold-sdca-architecture-records.md`, because develop slimmed that file.
- Test pins were updated for the gold extras now on develop, and for the `capital_deployed_peak_pct` field.

## Left out on purpose (still on the source branches)

- Generated tearsheet JSONs, about 110 MB in total: `apps/digiquant-web/public/strategies/btc_sdca_*.json` (#5777) and `gold_sdca*.json`/`gld_sdca_candidate.json` (rescue). Also `public/gold_charts/*.svg`, top-level `.scratch/`, and `digiquant/.scratch` files over 100 KB.
- The web wiring that only displays those files: the #5777 `sdca-recalibration` page and comparison component, the extra slugs, and the rescue branch's "TEMPORARY local-preview, REVERT BEFORE ANY MERGE" fallback in `tearsheet-view.tsx`.
- ADR 0030 (MCP tool naming), which has nothing to do with SDCA.

To restore any of them locally:

    git checkout origin/chore/rescue-4804-gold-artifacts -- apps/digiquant-web/public/strategies/gold_sdca.json
    git checkout origin/claude/sdca-full-recalibration -- apps/digiquant-web/public/strategies/btc_sdca_round4.json
