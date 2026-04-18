---
name: digithings-backlog
description: Maintain the hybrid agent backlog (INDEX + GitHub Issues) for the DigiThings monorepo.
---

# DigiThings backlog skill

## When to use

You are filing work, closing a theme, or orienting a fresh agent session on **what to do next**.

## Steps

1. Read [docs/agent-backlog/README.md](../../agent-backlog/README.md) and [INDEX.md](../../agent-backlog/INDEX.md).
2. For new granular work, open a GitHub Issue using the **Agent task** template (label `agent-task`, plus `component:...` and `risk:...`).
3. Add or update a row in **INDEX.md** linking the theme to those issue URLs.
4. If a decision is involved, add an ADR under [docs/adr/](../../adr/README.md) and link it from INDEX.

## Do not

- Put secrets or client data in INDEX or issues.
- Mark `risk:high` items as doc-only auto-merge candidates.
