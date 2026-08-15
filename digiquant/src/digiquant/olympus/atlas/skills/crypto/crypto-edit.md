---
name: market-crypto-edit
description: Patch-update the crypto segment when triage signals localized change (edit mode).
---

# Crypto Edit Skill — document_delta patch

Update an **existing** crypto document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"crypto"`.
Patch paths: `/headline`, `/bias`, `/btc_trend`, `/btc_dominance`, `/funding_rate_bias`, …

## Inputs

- `section_index` + `prior_document`, `macro_regime`, `phase1_signals`, `triage_reason`
- Use data tools and any injected `web_grounding` before patching price/trend fields.

## Rules

- Surgical ops only; keep `btc_trend` and `funding_rate_bias` literals valid.
- Mandatory δ segment — prefer patch over full rewrite when prior exists.
