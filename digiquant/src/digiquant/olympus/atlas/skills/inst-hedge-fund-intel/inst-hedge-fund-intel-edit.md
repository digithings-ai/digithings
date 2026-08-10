---
name: inst-hedge-fund-intel-edit
description: Patch-update hedge-fund intel when triage signals localized change (edit mode).
---

# Hedge Fund Intel Edit Skill — document_delta patch

Update an **existing** `inst-hedge-fund-intel` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"inst-hedge-fund-intel"`.
Patch paths: `/headline`, `/bias`, `/tracked_funds_count`, `/top_signals`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Append/remove list ops for new signals; do not rewrite unchanged fund reads.
