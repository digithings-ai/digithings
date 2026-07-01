---
name: market-international-edit
description: Patch-update the international equities segment when triage signals localized change (edit mode).
---

# International Edit Skill — document_delta patch

Update an **existing** international document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"international"`.
Patch paths: `/headline`, `/bias`, `/asia_stance`, `/europe_stance`, `/em_stance`, …

## Inputs

- `section_index` + `prior_document`, `macro_regime`, `phase1_signals`, `triage_reason`
- Use `web_grounding` (when injected) for non-US session color before patching stance fields.

## Rules

- Surgical ops only; keep regional stance literals (`bullish` / `bearish` / `neutral`) valid.
