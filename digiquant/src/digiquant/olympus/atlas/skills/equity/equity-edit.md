---
name: market-equity-edit
description: Patch-update the US equity overview when triage signals localized change (edit mode).
---

# Equity Edit Skill — document_delta patch

Update an **existing** equity segment document; do not rewrite from scratch.

## Output contract

Respond with a single JSON object validating against **`DocumentPatch`**:

- `target_document_key`: `"equity"`
- `prior_date` / `date` from PHASE_INPUTS
- `status`: `updated` with ops, or `skipped` with `skip_reason` when nothing material changed
- `ops`: RFC 6901 paths over the prior body (`/headline`, `/bias`, `/spy_trend`, `/market_breadth`, `/factor_leader`, `/material_findings`, …)

## Inputs

- `section_index` + `prior_document` (hybrid prompt §5.6)
- `macro_regime`, `phase1_signals`, `phase4_asset_classes` — today's upstream bodies
- `triage_reason` when present

## Rules

- Patch only fields affected by fresh macro, alt-data, or asset-class signals.
- Use data tools for SPY/QQQ/IWM technicals before patching trend/breadth fields.
- Keep `SegmentReport` literals valid (`bias`, `spy_trend`, `market_breadth`, `factor_leader`).
