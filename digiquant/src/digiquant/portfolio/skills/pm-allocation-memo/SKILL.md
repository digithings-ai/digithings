---
name: pm-allocation-memo
description: >
  Fresh JSON memo after per-ticker deliberation: T−1 context, turnover discipline, target weights
  rationale, links to deliberation keys. Track B Phase 6 before portfolio-manager Phase B/C.
---

# PM Allocation Memo

Publish **`pm_allocation_memo`** after all **`deliberation_transcript`** rows and **`deliberation_session_index`** for `{{DATE}}`.

## Inputs

- **`deliberation_session_index`** for the date
- Each per-ticker transcript’s `body.final_decisions`
- **Prior day** `positions` or `rebalance_decision` / `portfolio.json` for T−1 weights
- **`config/investment-profile.md`** — turnover, risk, mandate language

## Output

- Schema: `templates/schemas/pm-allocation-memo.schema.json`
- **`document_key`:** `pm-allocation-memo/{{DATE}}.json`
- **`meta.prior_snapshot_date`:** T−1 date used
- **`meta.deliberation_index_key`:** `deliberation-transcript-index/{{DATE}}.json` (or null if legacy)
- **`body.narrative`:** synthesis across tickers
- **`body.turnover_discipline`:** how you limited day-over-day change vs prefs
- **`body.target_weights_rationale[]`:** per ticker with optional `deliberation_document_key`

Validate and publish with `--doc-type-label "PM Allocation Memo"`.

Hand off to `skills/portfolio-manager/SKILL.md`.
