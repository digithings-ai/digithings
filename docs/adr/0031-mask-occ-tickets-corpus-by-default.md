# 0031. Mask the `occ_tickets` corpus by default, behind the one disclosure switch

## Status

Proposed — 2026-10-05. This ADR records the floor Security decides on its own
authority (data minimisation of a corpus served to anonymous visitors) and names
the two points that are *not* Security's to close. It authorises the masking
change; it does not authorise rewriting the public git history, telling OCC, or
deciding the free-text name question. Those are marked human gates below.

**Deciders:** Security proposes; **CTO** decides the product trade-off (do OCC's
identity-dependent demo recipes justify unmasked detail in production?);
**Counsel** decides the Art. 32/33 notification question.

## Context

DIG-1063 masked the OCC customer data on the **zammad MCP tool** side. The
**retrieval** side was never in scope, and it is the side anonymous visitors
actually hit.

- `scripts/index_occ_tickets.py` builds the `occ_tickets` digisearch index. Its
  module docstring described the contract it implemented as "one Chunk per
  article with a body with full non-anonymized metadata (demo mode, same contract
  as the zammad MCP tools after #4944)". `build_ticket_chunks` wrote
  `customer`, `customer_name` and `organization` into chunk metadata, prefixed
  internal articles with `[internal]` and indexed them anyway, and inlined the
  article's `From:` address, subject and full body into the chunk text.
- `scripts/build_occ_tickets_seed.py` — "Demo mode: customer names and emails are
  stored in full and internal articles are tagged `[internal]` … **Do not run this
  outside a demo deployment.**" — turns the same function into a committed
  snapshot at `apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl`,
  which `apps/digichat-stack-cloudflare/container/seed_chroma.sh` re-ingests into
  Chroma on **every container cold boot**.
- The OCC tenant fans out over the whole index: `digisearchIndex: "occ_help,occ_tickets"`
  with RRF and no per-row filter, so reachability is 100% of rows.
- The tenant is served to the public. `infra/digichat-release/compose.profile-a-bundle.override.yml`
  sets `gateMode: "ungated"` for `occ.digithings.ai`, and
  `infra/digichat-digithings/README.md:51` states "Public chat is the ungated
  embed iframe". OCC is a live paying client, so "demo deployment" was not the
  deployment in use.
- The deployed `researchSystemPrompt` made all of this explicit and, in the
  model's words, *expected*: `occ_tickets` (semantic, multilingual, **full
  customer names/emails, internal notes tagged [internal]**) and customer
  names/emails "shown in full (demo mode)". So the retrieval layer would quote
  them on request.

### Measured exposure (counts only; no value was printed by the audit)

Of the 919 committed rows (185 tickets): **372** are `[internal]` staff notes,
**188** of those also carry a customer email, and **86** distinct customer
display names appear. **791** rows quote an email address somewhere in the
indexed text or metadata, drawn from **286** distinct addresses — 98.4% of them
on organisational domains, which is what real customers of a compliance centre
look like. That is Art. 4(1) personal data, not fixture data.

Projecting all 919 rows through the policy this ADR adopts (method: run the
committed rows through `privacy.py`'s own label/redact functions zone by zone —
header title, `Subject:`, body, metadata — counts only):

| | before | after |
|---|---|---|
| rows in the corpus | 919 | **547** |
| rows quoting an address (text or metadata) | 791 | **0** |
| distinct addresses in the corpus | 286 | **0** |
| distinct display names in metadata | 86 | **0** |
| rows carrying a customer display name in free text | — | **311 of 547** |

A live re-run was not possible (it needs `ZAMMAD_API_TOKEN`), so "after" is a
projection of the shipped payload, not a fresh backfill.

### Two open DIG-1063 implementations

PR #5148 and PR #5155 both mask the MCP side and both name `occ_tickets` as out
of scope. #5155 uses a bare boolean `ZAMMAD_DEMO_UNMASKED_PII=1`, with the
accepted-risk owner expressed in README prose. #5148 uses
`ZAMMAD_MCP_CUSTOMER_DISCLOSURE=unmasked` **plus a mandatory
`ZAMMAD_MCP_UNMASK_APPROVER=<name>`**, and puts that record in
`docs/ops/ZAMMAD_MCP_CUSTOMER_DISCLOSURE.md`. #5155's own review record lists
this file as "not covered by the demo override".

## Decision

**1. The corpus served to anonymous visitors is masked by default.** No customer
email, no customer display name in metadata, no `[internal]` staff note in the
`occ_tickets` index. Emails quoted inside free text become `email#<hash>`; a
customer is `customer #<id>`; a thread that had internal notes says
`[n internal note(s) withheld]` so the model reads the gap as withheld rather
than missing. Article ids and `article_index` stay on their **original**
positions, so masking does not renumber threads or orphan ids already in Chroma.

**2. One switch, one accepted-risk owner.** The demo override is the disclosure
switch from PR #5148 — the same two env vars the MCP tools read, requiring a
**named approver**. There is deliberately no second switch for this corpus, and
no way to reach unmasked ticket content without naming the person who accepted
the risk. `scripts/zammad_mcp/privacy.py` stays the single place that decides
whether customer identity may leave the helpdesk.

**3. The deployed prompt must be true.** All three pinned copies of the OCC
`researchSystemPrompt` (`wrangler.toml` `[vars]`, the `_FALLBACK_RE` literal in
`src/index.ts`, and the compose override) described the index as *not* masked.
They now describe the masked contract. `test_real_blobs_occ_prompt_parity` plus
the stale-string assertions in `tests/scripts/test_check_tenant_corpus_map.py`
and `tests/scripts/test_zammad_mcp_stack.py` keep the three copies equal and
keep them from drifting back into demo-mode prose.

**4. Free-text display names are left open, on purpose.** 311 of the 547
surviving rows still contain a customer display name the customer typed into
their own message ("Hallo Frau Müller, …"), and 71 of the 86 distinct names
survive that way. Detecting names in German and Spanish prose is a language
problem, not a pattern problem, and over-redaction would gut the corpus. This is
a product trade-off: **CTO decides**, per human gate below. Until then the
residual is pinned by a test
(`test_a_name_in_free_text_is_still_present`) so it cannot be lost in a refactor
by accident.

**5. This ADR does not settle the git-history exposure.** The payload landed in
`86cb1ec5d` (#4987, 2026-10-02) in a **public** repository and has never been
modified since, so it has been publicly retrievable for three days. Removing it
from the tip does not remove it from history, and the fix is a rewrite plus
clone/cache invalidation with its own consequences (forks, CI caches, every
consumer of those pins). **Counsel decides** whether that is a notifiable
personal data breach under Art. 32/33. As processor we would owe the client,
OCC, notification under Art. 33(2) without undue delay; that clock is a human
judgement, not an engineering one.

## Consequences

**Positive**

- The anonymous path stops serving customer email and staff-only notes. Two
  independent audits (`scripts/secrets_audit.py` for credentials, this test suite
  for identity) now cover the corpus builder.
- One switch governs both the MCP tools and the index, so "is OCC demo mode on?"
  has one answer with one owner named in it.
- Idempotence: `redact_addresses` on an already-redacted string is a no-op, so
  re-indexing over an existing collection cannot double-rewrite content.
- Fails closed. Every near-miss value of the disclosure var, and unmasking with
  no approver, stay masked.

**Negative / tradeoffs**

- `group_by=customer` now aggregates under pseudonyms — still correct for
  ranking, no longer readable as "who".
- `zammad_search_tickets customer.email:<addr>` can no longer be driven *from* a
  retrieved row, because the index no longer hands the model an address. A user
  who types an address in the question still works.
- The corpus drops from 919 to 547 rows, so a smaller share of the index is
  retrievable for internal-note questions.
- Answer quality on "history for <named customer>" degrades until the name
  question in (4) is decided.
- This ADR sits on top of PR #5148, which is **draft** and may be rewritten. If
  it is, `privacy.py` moves and this change follows it.

### Human gates (do not close without these)

1. **CTO** — re-affirm that the reversal of the #4944 demo contract is right for a
   live client, and decide whether OCC may keep any unmasked detail in
   production. If yes, that is `ZAMMAD_MCP_UNMASK_APPROVER=<name>` plus the
   record in `docs/ops/ZAMMAD_MCP_CUSTOMER_DISCLOSURE.md` — not a code change.
2. **CTO** — decide the free-text name question (311 rows).
3. **Counsel** — Art. 32/33 notification for the public-repo exposure since
   2026-10-02.
4. **Repo owner** — the `main`-side cutover: the payload is still on `main` and
   still ingested on every cold boot. A PR into `develop` does not stop either.

## Links

- Issues: DIG-1210 (this), DIG-1063 (the MCP-side masking, PRs #5148 / #5155),
  DIG-959 (free text), DIG-984 (Art. 9 egress inventory).
- Introduced by #4987 (`86cb1ec5d`), reviewed in `review-promote-occ-chat.md`.
- Policy: `scripts/zammad_mcp/privacy.py`; accepted-risk record:
  `docs/ops/ZAMMAD_MCP_CUSTOMER_DISCLOSURE.md`.
- Tests: `tests/scripts/test_index_occ_tickets_privacy.py`,
  `tests/scripts/test_check_tenant_corpus_map.py`,
  `tests/ds/test_multilingual_embedder.py`.