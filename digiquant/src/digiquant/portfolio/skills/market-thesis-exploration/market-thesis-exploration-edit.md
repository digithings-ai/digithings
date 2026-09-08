---
name: market-thesis-exploration-edit
description: Patch-update market thesis exploration document.
---

# Market Thesis Exploration — Edit Mode

Emit `DocumentPatch` against prior `thesis/market-exploration`.

Compare every retained or proposed market opinion with `active_theses` before patching:

- Update an existing opinion in place with its exact `thesis_id` and `topic_key`; set
	`action: "update"` and `existing_thesis_id` to that ID.
- Create a thesis only for a genuinely distinct market mechanism; set `action: "create"`,
	omit `existing_thesis_id`, and use a new lowercase kebab-case `topic_key`.
- Different wording, evidence, confidence, catalyst details, or sector examples are updates,
	not new opinions.
- A `PAUSED` topic remains the same opinion. Never create a replacement; omit it unless H1
	explicitly reactivated it based on new evidence.
- Consolidate legacy same-topic entries into one canonical thesis. Emit at most one proposal
	per `topic_key`.

Legacy prior documents may lack identity fields. Add `topic_key`, `action`, and
`existing_thesis_id` to every retained thesis so the merged document validates. Preserve
stable IDs when the opinion is unchanged.
