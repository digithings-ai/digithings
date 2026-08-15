---
name: pm-rebalance-decision
description: >
  DEPRECATED for daily path (PR 4c). Use ``pm-direction`` (H7) for direction + rank and
  H8 risk sizing for weights. Kept for historical reference and simulator overrides only.
---

# PM Rebalance Decision (deprecated)

**Daily Hermes runs use `pm-direction` (H7) + H8 risk sizing.** This skill emitted
weight-bearing `RebalanceDecision` payloads from Phase 7D — that path is removed from
the thesis-first graph.

See `skills/pm-direction/pm-direction-full.md` for the authoritative H7 skill.

