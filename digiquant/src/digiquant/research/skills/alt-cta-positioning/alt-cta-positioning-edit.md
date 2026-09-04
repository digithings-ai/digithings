---
name: alt-data-cta-positioning-edit
description: Patch-update CTA positioning alt-data when triage signals localized change (edit mode).
---

# CTA Positioning Edit Skill — document_delta patch

Update an **existing** `alt-cta-positioning` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-cta-positioning"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Surgical ops only; keep systematic stance literals valid.
