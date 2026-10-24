---
name: alt-data-politician-signals-edit
description: Patch-update politician official-signals alt-data when triage signals localized change (edit mode).
---

# Politician Signals Edit Skill — document_delta patch

Update an **existing** `alt-politician-signals` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-politician-signals"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`

  There is no `web_grounding` for this segment (DIG-1252); do not describe a search you did not make.

## Rules

- Same scope limit as the parent skill (DIG-1252, Counsel ruling DIG-1251): official policy
  and regulatory signals only. Do **not** add, restore, or maintain individual STOCK Act
  trade-level detail — no tickers, no amounts, no buy/sell side, no transaction or filing dates,
  no per-member trade lists.
- **A prior body written before DIG-1252 may still contain a `## Congressional trades`
  section. Remove it** rather than patching it forward; do not carry it across.
- Patch only what changed; leave untouched sections alone.
