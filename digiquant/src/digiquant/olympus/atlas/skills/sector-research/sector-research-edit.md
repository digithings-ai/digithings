---
name: sector-research-edit
description: Patch-update a single GICS sector report when triage signals localized change (edit mode).
---

# Sector Research Edit Skill — document_delta patch

Update an **existing** sector document for `phase_inputs.segment` / `sector_config.slug`; do not rewrite from scratch.

## Output contract

Respond with a single JSON object validating against **`DocumentPatch`**:

- `target_document_key`: the sector slug from PHASE_INPUTS (`segment` or `sector_config.slug`, e.g. `sector-technology`)
- `prior_date` / `date` from PHASE_INPUTS
- `status`: `updated` with ops, or `skipped` when nothing material changed
- `ops`: RFC 6901 paths (`/headline`, `/bias`, `/relative_strength_vs_spy`, `/sub_segment_leader`, `/driver_confirmation_count`, `/conviction`, …)

## Inputs

- `section_index` + `prior_document`
- `sector_config`, `macro_regime`, `phase1_signals`, `equity_overview`
- `triage_reason` when present

## Rules

- Patch only drivers/stance fields affected by ETF moves, earnings, or upstream regime shifts.
- Ground ETF/ticker claims with `query_data` on `sector_config.etfs` and `top_tickers`.
- Preserve valid `SectorReport` literals (`relative_strength_vs_spy`, `conviction`, `bias`).
