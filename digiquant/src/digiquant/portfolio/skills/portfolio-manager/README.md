---
name: portfolio-manager
description: Portfolio construction and rebalance decision skill package
---

# Skill Package — Portfolio Manager

- **Entry file**: `skills/portfolio-manager/SKILL.md`
- **Canonical output schemas**:
  - `templates/schemas/rebalance-decision.schema.json`
  - `templates/schemas/deliberation-transcript.schema.json`
  - `templates/schemas/asset-recommendation.schema.json`

DB-first: publish artifacts to Supabase `documents.payload` and record execution into `position_events`.

