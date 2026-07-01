---
name: market-bonds-edit
description: Patch-update the bonds segment when triage signals localized change (edit mode).
---

# Bonds Edit Skill — document_delta patch

Update an **existing** bonds document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"bonds"`.
Patch paths: `/headline`, `/bias`, `/yield_curve_shape`, `/two_ten_spread_bps`, `/credit_ig_spread_bps`, `/credit_hy_spread_bps`, `/material_findings`, …

## Inputs

- `section_index` + `prior_document`, `macro_regime`, `phase1_signals`, `triage_reason`
- Use `get_macro_series` / data tools before patching spread or curve fields.

## Rules

- Surgical ops only; keep yield-curve and spread literals valid.
