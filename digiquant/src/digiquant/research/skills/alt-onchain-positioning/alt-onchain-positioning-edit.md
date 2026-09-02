---
name: alt-data-onchain-positioning-edit
description: Patch-update on-chain cohort positioning when triage signals localized change (edit mode).
---

# On-Chain Positioning Edit Skill — document_delta patch

Update an **existing** `alt-onchain-positioning` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-onchain-positioning"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`
- `shared_context.data_layer.market_context.onchain_positioning` for fresh Hyperdash divergence

## Rules

- Patch only when preflight on-chain data or triage reason indicates cohort shift.
- Keep stance and divergence literals valid.
