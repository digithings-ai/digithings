---
name: market-thesis-exploration-full
description: Full rewrite of market thesis exploration from digest + segments.
---

# Market Thesis Exploration (H2)

Propose **market** theses (`thesis_kind=market`) grounded in the daily digest and research segments.

## Existing-opinion check

`active_theses` is the current thesis register. Before emitting a proposal, compare its core
market mechanism and risk with every active row whose `thesis_kind` is `market`:

- Same mechanism/opinion: emit one `action: "update"`, reuse its exact `thesis_id`, set
	`existing_thesis_id` to that ID, and preserve its `topic_key`.
- Genuinely distinct mechanism/opinion: emit `action: "create"`, omit
	`existing_thesis_id`, and assign a new stable `topic_key`.
- Different evidence, wording, catalyst detail, sector examples, or confidence does not make
	a new opinion. Update the existing thesis and merge the useful evidence.
- A `PAUSED` topic remains the same opinion. Do not create a replacement. Update it only when
	evidence warrants explicit reactivation in H1; otherwise omit it from H2 proposals.
- Emit at most one proposal for each `topic_key`. Never split one opinion into several theses.

`topic_key` is a lowercase kebab-case identity for the durable opinion, not the day's title.
It remains stable when the title, statement, evidence, or confidence changes.

Each thesis needs: `thesis_id`, `topic_key`, `action`, `existing_thesis_id` when updating,
`title`, `direction`, `statement`, `validation_criteria` (≥1), and
`invalidation_criteria` (≥1). Optional `confidence`, `horizon`, headwinds/tailwinds, and
bull/bear cases.

Output JSON matching `MarketThesisExplorationOutput`.
