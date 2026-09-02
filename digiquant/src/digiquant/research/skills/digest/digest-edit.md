---
name: daily-digest-edit
description: Patch-update the daily digest briefing when triage signals localized research change (edit mode).
---

# Daily Digest Edit Skill — document_delta patch

Update an **existing** digest briefing; do not rewrite from scratch.

## Output contract

Respond with a single JSON object validating against **`DocumentPatch`**:

- `target_document_key`: `digest` (baseline) or `digest-delta` (weekday) — from PHASE_INPUTS
- `prior_date`: prior artifact date from PHASE_INPUTS
- `date`: today's run date
- `status`: `updated` with ops, or `skipped` with `skip_reason` when nothing material changed
- `ops`: RFC 6901 paths over the prior digest. Patch **`/body`** (the markdown
  briefing). You may also patch `/regime_label`. Do not invent `/headline` or
  `/bias` slots on new runs.

## Inputs

- `section_index` + `prior_document` (hybrid prompt §5.6)
- `bias_row` from Phase 6 (today's deterministic regime/bias surface)
- `subsections` — today's topical markdown (when the subsection agents ran)
- `prior_digests` — last two full briefing bodies
- `triage_reason` when present

## Rules

- Patch only sections of `body` affected by fresh subsection inputs or material signal changes.
- Keep the briefing markdown. Do not restore JSON slots (`bias`, `headline`, Signals).
- Rewrite trade verbs in patched strings to watchlist language.
- Do not invent freshness — `segment_freshness` is applied downstream from state.
