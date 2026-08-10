---
name: daily-digest-edit
description: Patch-update the daily digest when triage signals localized research change (edit mode).
---

# Daily Digest Edit Skill — document_delta patch

Update an **existing** digest JSON; do not rewrite from scratch.

## Output contract

Respond with a single JSON object validating against **`DocumentPatch`**:

- `target_document_key`: `digest` (baseline) or `digest-delta` (weekday) — from PHASE_INPUTS
- `prior_date`: prior artifact date from PHASE_INPUTS
- `date`: today's run date
- `status`: `updated` with ops, or `skipped` with `skip_reason` when nothing material changed
- `ops`: RFC 6901 paths over the prior digest (`/headline`, `/market_regime_snapshot`, `/actionable_summary`, …)

## Inputs

- `section_index` + `prior_document` (hybrid prompt §5.6)
- `bias_row` from Phase 6 (today's deterministic regime/bias surface)
- `phase1`–`phase5` bodies: **today-source segments only** (carried segments omitted)
- `triage_reason` when present

## Rules

- Patch only sections affected by fresh segment inputs or material signal changes.
- Leave `thesis_tracker` and `portfolio_recommendations` empty (Hermes owns positioning).
- Rewrite trade verbs in `actionable_summary` to watchlist language in patched strings.
- Do not invent freshness — `segment_freshness` is applied downstream from state.
