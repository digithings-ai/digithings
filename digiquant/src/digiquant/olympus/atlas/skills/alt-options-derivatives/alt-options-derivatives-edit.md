---
name: alt-data-options-derivatives-edit
description: Patch-update options/derivatives alt-data when triage signals localized change (edit mode).
---

# Options & Derivatives Edit Skill — document_delta patch

Update an **existing** `alt-options-derivatives` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-options-derivatives"`.
Patch paths: `/headline`, `/bias`, `/vix_level`, `/vix_term_structure`, `/dealer_gamma`, `/put_call_ratio`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`
- Ground vol complex fields with data tools (`get_macro_series` / vol series) before patching.

## Rules

- Surgical ops only; keep VIX term-structure and dealer-gamma literals valid.
