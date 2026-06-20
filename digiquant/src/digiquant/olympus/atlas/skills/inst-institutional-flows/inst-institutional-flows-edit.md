---
name: inst-institutional-flows-edit
description: Patch-update institutional flows when triage signals localized change (edit mode).
---

# Institutional Flows Edit Skill — document_delta patch

Update an **existing** `inst-institutional-flows` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"inst-institutional-flows"`.
Patch paths: `/headline`, `/bias`, `/flow_direction`, `/largest_sector_inflow`, `/largest_sector_outflow`, `/notable_filings`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Surgical ops only; keep `flow_direction` literals valid.
