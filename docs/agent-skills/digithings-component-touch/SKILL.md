---
name: digithings-component-touch
description: Before editing a DigiThings component, load the right DIGIxxx.md and test commands.
---

# DigiThings component touch skill

## When to use

You are about to change Python, TypeScript, or config under a service directory.

## Steps

1. Read [AGENTS.md](../../../AGENTS.md) (global rules).
2. Open [docs/agents/COMPONENT_ROUTING.md](../../agents/COMPONENT_ROUTING.md) and find your **Prefix** row.
3. Read the linked **Doc** file end-to-end for the area you edit.
4. Run the listed **Tests** after substantive changes; prefer `pytest -m unit` from repo root for Python.
5. Update the same **Doc** if public interfaces, ports, or env vars change.

## Hard stops

- No live-trading changes without explicit human approval ([AGENTS.md](../../../AGENTS.md)).
- No pandas; use Polars for data work.
