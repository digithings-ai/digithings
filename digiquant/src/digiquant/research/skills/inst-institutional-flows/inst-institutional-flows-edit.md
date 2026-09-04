---
name: inst-institutional-flows-edit
description: Patch-update institutional flows when triage signals localized change (edit mode).
---

# Institutional Flows Edit Skill — document_delta patch

Update an **existing** `inst-institutional-flows` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"inst-institutional-flows"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Surgical ops only; keep `flow_direction` literals valid.
