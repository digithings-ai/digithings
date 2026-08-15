---
name: alt-data-ai-portfolios-edit
description: Patch-update AI-portfolio proxy alt-data when triage signals localized change (edit mode).
---

# AI Portfolios Edit Skill — document_delta patch

Update an **existing** `alt-ai-portfolios` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-ai-portfolios"`.
Patch paths: `/headline`, `/bias`, `/per_account`, `/consensus_longs`, `/sector_tilt`, `/divergences`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Patch account reads and consensus only when new X posts or triage signal warrants it.
- Treat as soft proxy — do not override macro/data-driven downstream reads.
