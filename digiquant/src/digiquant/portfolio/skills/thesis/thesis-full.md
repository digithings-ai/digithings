---
name: thesis-full
description: Daily review of active market theses — confidence, criteria, status.
---

# Thesis Review (H1)

Review every thesis in `active_theses`. Refresh confidence (0.0–1.0), validation/invalidation criteria, and status.

## Rules

- Review **market** theses already in `active_theses`. Reuse those exact `thesis_id` values.
- Do not invent thesis ids. Do not emit `vehicle-{ticker}` or misspellings (`veicle-*`)
  as reviewed market theses — vehicle-local rows are written by H5.
- Emit `reviewed_theses` with one entry per active **market** thesis.
- `new_status` must be one of: ACTIVE, MONITORING, CHALLENGED, CLOSED, INVALIDATED, PAUSED, NEW.
- When any **invalidation criterion** is observably hit, set `new_status=CHALLENGED` and list hits in `challenged_by`.
- CLOSED requires `resolution` win|loss and evidence.
- INVALIDATED requires non-empty `reason`.

## Output

JSON body matching `ThesisReviewOutput`: `reviewed_theses`, optional `new_candidate_theses`, `notes`.

Use `query_research` / `query_portfolio` when tools are available.
