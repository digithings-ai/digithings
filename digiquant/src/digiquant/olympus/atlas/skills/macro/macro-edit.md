---
name: market-macro-edit
description: Patch-update the macro regime document when triage signals localized change (edit mode).
---

# Macro Edit Skill — document_delta patch

You are updating an **existing** macro segment document, not writing from scratch.

## Output contract

Respond with a single JSON object validating against **`DocumentPatch`** (`doc_type=document_delta`):

- `schema_version`: `"1.0"`
- `date`: today's run date (from PHASE_INPUTS)
- `prior_date`: the prior artifact date (from `prior_date` in PHASE_INPUTS)
- `target_document_key`: `"macro"`
- `status`: `"updated"` when you emit ops; `"skipped"` only when nothing material changed
- `ops`: RFC 6901 JSON Pointer paths rooted at `/` over the **prior document** shape
  (e.g. `/growth`, `/regime_label`, `/headline`, `/portfolio_implications`)
- Each op needs a short `reason` citing the delta signal or data that changed

Use **`set`** ops for scalar fields; **`append`** / **`remove`** sparingly for lists.

## Grounding (hybrid prompt §5.6)

1. Read `section_index` — one-line summaries of every top-level prior field.
2. Read `prior_document` excerpts for fields triage marked stale (full JSON for those keys).
3. Use `triage_reason` and PHASE_INPUTS delta signals (phase1_outputs, price moves) to decide what to patch.
4. Do **not** rewrite unchanged sections — emit ops only for stale/moved fields.
5. If a cross-section dependency is missing from the bundle, note it in op `reason` and patch conservatively.

## Tools

Same as full macro skill when provided: `get_macro_series` first; `web_grounding` only when injected.

## Quality bar

- Patched body must remain a valid macro regime report (4-factor literals unchanged in meaning).
- Prefer surgical updates over blanket `/headline` rewrites when only one factor moved.
