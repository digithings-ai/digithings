# Architecture Decision Records (ADRs)

Short, immutable decisions. **Add a new file** with the next number: `NNNN-short-title.md`.

Use the template: [0000-template.md](0000-template.md).

Link ADRs from [docs/agent-backlog/INDEX.md](../agent-backlog/INDEX.md) when they govern ongoing work.

Current high-water mark: **0035** ([0035-tenant-lock-flag-fails-closed.md](0035-tenant-lock-flag-fails-closed.md), Accepted) — a non-boolean `lockSessionControls` in the tenant corpus map fails closed to locked, with a warning naming the tenant and the JSON type.
