---
name: market-forex-edit
description: Patch-update the forex segment when triage signals localized change (edit mode).
---

# Forex Edit Skill — document_delta patch

Update an **existing** forex document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"forex"`.
Patch paths: `/headline`, `/bias`, `/dxy_trend`, `/policy_divergence`, …

## Inputs

- `section_index` + `prior_document`, `macro_regime`, `phase1_signals`, `triage_reason`
- Ground DXY/major-pair claims with data tools when patching trend fields.

## Rules

- Surgical ops only; keep `dxy_trend` literals (`stronger` / `weaker` / `range`) valid.
