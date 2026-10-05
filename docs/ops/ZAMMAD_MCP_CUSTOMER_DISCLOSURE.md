# zammad MCP customer-data disclosure

**Status:** masked in production. **Override:** available, needs a named
holder. **Owner of the decision:** CTO (Chris Stefan). **Raised by:** Security,
DIG-1063, from the Art. 9 egress inventory (DIG-984).

## What this decides

The zammad MCP server reads real customer support tickets. Before DIG-1063
(#4944) every formatter showed customer names, email addresses, organizations
and internal notes in full, because the OCC demo wanted readable transcripts.
The demo is **live** — the server runs in the `digithings-stack` Cloudflare
Container and is reachable on `https://graph.digithings.ai/_stack/mcp/zammad/*`
(key-gated, fail-closed 401) — so the demo is not a safe reason to leave the
corpus unmasked by default.

The default is now **masked**: customers render as a stable pseudonym
(`customer #<id>`), organizations and article authors are dropped, and internal
notes are not returned. The pseudonym keeps rankings, grouping and the
customer-history drill-down working while carrying no name, email or email
domain, and it is stronger than the partial mask this server used before #4944,
which still exposed the email domain — for a B2B helpdesk the domain is the
customer's company.

`customer #7` is **pseudonymised, not anonymised**: it is still a stable pointer
to a natural person in the controller's own helpdesk, so it remains Art. 4(1)
personal data. What it removes is the direct identifier, and with it the model can
no longer name or contact the customer.

Names and email addresses are **Art. 4(1)** personal data. The defect was
**Art. 5(1)(c)** data minimisation, not Art. 9 — the Art. 9 filter (DIG-959) is
scoped to the eight Art. 9(1) special categories and will not touch this
corpus. DIG-1063 does not wait on DIG-959.

## The override, as an accepted risk

| | |
|---|---|
| Risk | Unmasked mode sends real customer names, email addresses, organizations and internal notes to the model, and transcripts of that data are retained per provider policy. |
| Why anyone might accept | Demo and evaluation sessions read better with real names; a trainer can point at an actual customer conversation. |
| **Accepted by** | **\<name\> — \<role\> — \<date\>** *(fill this in before setting `unmasked` anywhere)* |
| Control | `ZAMMAD_MCP_CUSTOMER_DISCLOSURE=unmasked` **plus** `ZAMMAD_MCP_UNMASK_APPROVER="<name>"`. Without the approver the server stays masked and logs why. |
| Blast radius if abused | Every OCC chat session on the affected deployment. Read-only: no write path exists in this server. |
| Re-open if | The demo is retired; a non-demo tenant is pointed at the unmasked server; the corpus is found to reach a new destination; or the retention position of the model providers changes. |

Security's standard applies: demo convenience is a legitimate reason to unmask;
"it was written that way and nobody revisited it" is not. Hence the approver
variable — the name is part of turning the override on, so it cannot be lost.

## What is still unmasked

- **Free text in tickets** — titles, subjects, bodies and the ticket-level
  `Note:` line are not scrubbed, and `jira_assignee` passes through unscrubbed.
  Masking here covers structured fields only: a name or address written into a
  message body still reaches the model. DIG-959 is scoped to the eight Art. 9(1)
  special categories and will not close this, so free-text scrubbing needs its
  own issue and its own owner.
- **The `occ_tickets` digisearch index** — `scripts/index_occ_tickets.py`
  indexes the same corpus with full names and emails, tagged `[internal]`, and
  the OCC assistant searches it with every question. That path is owned by the
  indexing and digisearch layers, not by the MCP server, so DIG-1063 does not
  close it.
- **`digillm`** — the same corpus reaches model providers on a separate path.

## Where the decision lives in code

`scripts/zammad_mcp/privacy.py` is the single place that decides. Formatters and
the server ask it; none of them reads the environment variables directly, so
there is no second opinion to keep in sync. See
[`scripts/zammad_mcp/README.md`](../../scripts/zammad_mcp/README.md) § Privacy &
exposure for the per-path behaviour, and the stack wiring in
`apps/digithings-stack-cloudflare/`.
