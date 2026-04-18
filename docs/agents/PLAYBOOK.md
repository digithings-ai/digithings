# Agent playbook (sub-agent routing)

Use this when driving **Cursor** or similar tools that support delegated tasks. Map the situation to a sub-agent type so work stays parallel and token-efficient.

## When you are stuck on *where* code lives

- **Explore:** broad codebase search, file discovery, “how does X work?” before editing.
- **Scope:** one component directory at a time when possible (see [COMPONENT_ROUTING.md](COMPONENT_ROUTING.md)).

## When CI is red

- **CI watcher / logs:** fetch failing job logs, identify first root failure, propose minimal fix.
- **Shell:** run `pytest -m unit`, `ruff check`, or targeted tests after a fix.

## When the change is mechanical across many files

- **Plan first** (short step list), then **shell** for batch checks; avoid editing unrelated packages.

## When the task is doc-only

- Follow [digithings-doc-pr skill](../agent-skills/digithings-doc-pr/SKILL.md) and [docs/agent-backlog/AUTOMERGE.md](../agent-backlog/AUTOMERGE.md) if using `automerge-docs`.

## When touching auth, crypto, or live trading

- **Stop** and escalate to a human. Do not use doc auto-merge labels. See [AGENTS.md](../../AGENTS.md) and [SECURITY.md](../../SECURITY.md).

## Order of reading (every session)

1. [AGENTS.md](../../AGENTS.md)
2. [ROADMAP.md](../../ROADMAP.md)
3. `{component}/AGENTS.md` then `{component}/ARCHITECTURE.md` ([COMPONENT_ROUTING.md](COMPONENT_ROUTING.md) maps prefix → files)
4. [docs/agent-backlog/INDEX.md](../agent-backlog/INDEX.md) for queued themes/issues
