# Agent backlog (hybrid)

**Index (themes + links):** [INDEX.md](INDEX.md)  
**Generated snapshot (optional CI):** [generated-snapshot.md](generated-snapshot.md) — created by `.github/workflows/agent-backlog-snapshot.yml` when configured.

## Model

1. **Git** holds narrative and decisions: this folder, [Architecture](../../ARCHITECTURE.md), [ROADMAP](../../ROADMAP.md), [docs/adr/](../adr/README.md).
2. **GitHub Issues** hold granular work items (scoped, testable tasks).
3. **INDEX.md** maps themes to issues so agents clone once and know what to pull next.

## Labels (recommended)

| Label | Meaning |
|--------|---------|
| `agent-task` | Suitable for a coding agent; has clear acceptance criteria |
| `component:digigraph` / `digiquant` / `digisearch` / `digiclaw` / `digismith` / `digikey` / `digibase` / `digichat` | Primary code area |
| `risk:low` / `risk:med` / `risk:high` | `high` = needs human review before merge |
| `docs-only` | Markdown/doc changes only (see [AUTOMERGE.md](AUTOMERGE.md)) |

Create additional labels as needed (e.g. `blocked`, `good-first-agent`).

## Opening an issue

Use **New issue → Agent task** (`.github/ISSUE_TEMPLATE/agent_task.yml`) so acceptance criteria and doc expectations are filled in.

### Third-party data access

> **No third-party data access merges without a [`docs/vendor-terms/<vendor>/INDEX.md`](../../docs/vendor-terms/INDEX.md) entry. The check runs when the integration is proposed, not at review time.**

If the issue adds, changes or documents a call to someone else's data, endpoint,
authentication flow or vendor-specific constant, say so in the intake — name the
vendor in the template's third-party field. The entry is written first, then the
implementation. Review time is the expensive point: by then the access method is
already described in the diff, so a finding costs a rewrite instead of a
conversation.

Two things worth knowing before you start: the boundary and the steps are in
[`docs/VENDOR_CONTENT_BOUNDARY.md`](../../docs/VENDOR_CONTENT_BOUNDARY.md), and
the vendor's terms do **not** have to be compatible with an open-source `LICENSE`
in its repository — they are a different document about a different subject. See
the [vendor terms index](../../docs/vendor-terms/INDEX.md).

**Reading a vendor's public terms is not outreach.** Contacting a vendor is
Chris's decision and does not follow from filing this issue.

## Definition of done

- [ ] Code matches constraints in [AGENTS.md](../../AGENTS.md) (Polars, Nautilus, LangGraph patterns, MCP-first for new capabilities, etc.).
- [ ] Tests added or updated (`pytest -m unit` for library changes; e2e when stack-related).
- [ ] Relevant `DIGIxxx.md` (and [ARCHITECTURE.md](../../ARCHITECTURE.md) if interfaces/ports change) updated.
- [ ] No secrets in commits; follow [SECURITY.md](../../SECURITY.md).
- [ ] **Never** change live-trading execution paths without explicit human approval ([AGENTS.md](../../AGENTS.md)).
- [ ] If this issue touches third-party data, a [`docs/vendor-terms/<vendor>/INDEX.md`](../../docs/vendor-terms/INDEX.md) entry exists with a signed Security classification.

## Security gates

- **SECURITY.md** is excluded from doc-only auto-merge unless maintainers choose otherwise ([AUTOMERGE.md](AUTOMERGE.md)).
- High-risk or auth/crypto changes: do **not** label `automerge-docs`; require human review.

## Sub-agent playbooks

See [docs/agents/PLAYBOOK.md](../agents/PLAYBOOK.md) and [COMPONENT_ROUTING.md](../agents/COMPONENT_ROUTING.md).

## Skills (copy into your IDE)

Templates live under [docs/agent-skills/](../agent-skills/README.md).
