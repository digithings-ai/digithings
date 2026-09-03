# Prompt + structured-output walk (#3424)

Companion to DigiGraph product graphs (#3415). Walk each digiquant research /
portfolio node with Chris: current prompt, current output, agree keep vs
reconsider vs prose. Machine catalog:
`digiquant.dashboard.prompt_walk_inventory.prompt_walk_inventory()`.

## Rules

- Product name is **digiquant** only (no Olympus / Atlas / Hermes / Kairos).
- Keep structured outputs where they are the contract (ids, weights, orders,
  H7 direction/rank/confidence).
- Prefer prose where structured JSON destroys signal (notably H6 deliberation —
  see `docs/reviews/2026-08-06-olympus-pipeline-review.md` OLY-REV-004).
- Do this in the same pass as DigiGraph hosting; do not wait for a second epic.

## Seed nodes (update as walked)

| node_id | stance | note |
|---------|--------|------|
| research/preflight | n_a | no LLM |
| research/triage | keep | skip/edit/full |
| research/phase1-sentiment | reconsider | segment JSON vs memo |
| research/phase7-digest | reconsider | report prose + structured bias/ids |
| portfolio/h5-asset-analyst | reconsider | forecast must survive |
| portfolio/h6-deliberation | prose_preferred | preserve disagreement |
| portfolio/h7-pm-direction | keep | H8 contract |
| portfolio/h8-risk-sizing | keep | weights |
| portfolio/h9-commit-run | keep | booker |

## Next with Chris

1. Expand inventory to every A1–A4 / H1–H9 skill slug.
2. For each node: paste current skill prompt + sample output; agree change.
3. Land prompt/skill edits on this branch after DigiGraph dry path is green.
