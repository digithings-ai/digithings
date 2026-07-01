---
name: market-commodities-edit
description: Patch-update the commodities segment when triage signals localized change (edit mode).
---

# Commodities Edit Skill — document_delta patch

Update an **existing** commodities document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"commodities"`.
Patch paths: `/headline`, `/bias`, `/oil_trend`, `/gold_trend`, `/industrial_metals_trend`, …

## Inputs

- `section_index` + `prior_document`, `macro_regime`, `phase1_signals`, `triage_reason`
- Ground energy/metals claims with data tools before patching trend fields.

## Rules

- Surgical ops only; keep trend literals (`bullish` / `bearish` / `neutral`) valid.
