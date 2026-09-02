---
name: alt-data-politician-signals-edit
description: Patch-update politician-trade alt-data when triage signals localized change (edit mode).
---

# Politician Signals Edit Skill — document_delta patch

Update an **existing** `alt-politician-signals` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-politician-signals"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Append/remove list ops for new filings; do not rewrite unchanged trade lists.
