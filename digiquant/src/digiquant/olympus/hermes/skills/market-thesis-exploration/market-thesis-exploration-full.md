---
name: market-thesis-exploration-full
description: Full rewrite of market thesis exploration from digest + segments.
---

# Market Thesis Exploration (H2)

Propose **market** theses (`thesis_kind=market`) grounded in the daily digest and research segments.

Each thesis needs: `thesis_id`, `title`, `direction`, `statement`, `validation_criteria` (≥1), `invalidation_criteria` (≥1). Optional `confidence`, `horizon`, headwinds/tailwinds, bull/bear cases.

Output JSON matching `MarketThesisExplorationOutput`.
