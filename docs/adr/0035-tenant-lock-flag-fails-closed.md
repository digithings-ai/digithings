# ADR-0035 — a non-boolean tenant lock flag fails closed to locked

**Status:** Accepted (2026-10-20).
**Date:** 2026-10-20
**Author:** Software Architect (board seat), from the Code Reviewer's finding on DIG-4459.
**Raised by:** DIG-4590 (child of DIG-4576).
**Amends:** the parsing of `lockSessionControls` in `digigraph/src/digigraph/corpus_routing.py`, and the `DIGI_TENANT_CORPUS_MAP` row of `digigraph/ARCHITECTURE.md` §10.2 plus the new §6.12.

## Context

Two surfaces read the same operator field, `lockSessionControls`, and they disagreed on what
counts as a value.

- The digichat registry validator (`apps/digichat/src/lib/embed-tenants.ts`) rejects anything
  that is not a real boolean: `"lockSessionControls must be a boolean"`. A JSON `null` is rejected
  too, because `typeof null === "object"`.
- The digigraph side parsed the same field as
  `lock = value.get("lockSessionControls", value.get("lock_session_controls", False))` and then
  stored `lock_session_controls=lock is True`. Under that comparison every non-`True` value —
  the string `"true"`, the number `1`, and `null` — silently became **False**, i.e. **unlocked**.

The flag is not cosmetic. It hides a tenant's session model picker, its MCP upsert/remove and
its tool toggle (`graph/research.py`), and it reaches graph state only through
`http_api/context.py`, which writes it unconditionally and server-side, so a client body can
never set it. A one-character typo in an operator's map therefore turned a tenant isolation
control off, and the operator saw nothing: the entry parsed, the request succeeded, and the
session controls came back. A present `lockSessionControls: null` was a second path to the same
outcome, because `.get(key, default)` only consults the default when the key is **absent**.

The wider map contract (DIG-4459) already separates two kinds of problem: an **unrecognised key**
is a forward-compatibility problem and must warn, while a **bad value for a known key** is a
safety problem and must fail closed. This field is a known key, so it is the second kind.

## Decision

**A non-boolean `lockSessionControls` fails closed to LOCKED for that tenant entry.** The entry is
kept, the flag is forced to `True`, and a warning names the tenant slug, the field and the JSON
type — never the value.

The three alternatives were rejected for measured reasons:

- **Skip the entry.** A missing entry defaults to unlocked *and* loses the tenant's corpus
  routing, so skipping would both fail open and re-point the corpus — the exact CWE-639 bypass
  that this module's own docstring exists to prevent.
- **Raise `TenantCorpusMapError` (HTTP 503).** One tenant's typo would take down corpus routing
  for every tenant in the deployment. That is a wider blast radius than the defect, and more than
  "never silently unlock" asks for.
- **Accept the value as written.** This is the defect.

The two surfaces keep the **same acceptance rule** (only a real boolean) and differ only in
failure model: the registry is one document, so a bad value refuses the whole registry; the
corpus map is per-tenant entries, so a bad value degrades one entry. They are not
interchangeable — digigraph must not inherit a whole-document refusal — but they must not
disagree about what a value *is*.

## Consequences

- **Positive:** a typo can no longer silently unlock a tenant. The safe state for a
  session-control flag is locked, and it is reached without taking any other tenant offline. The
  warning carries the slug, the field and the type, so the operator can find the entry.
- **Positive:** the entry's other fields survive. `digisearch_index` and `vault_path_prefix` are
  untouched, so a bad lock value never re-points a corpus.
- **Negative / tradeoffs:** a malformed flag is not an error the operator sees as a failed
  deployment. The map still loads and the tenant still serves — with the controls hidden, which
  is the intended locked state, but it is a **degradation, not a refusal**. The warning is the
  only signal. The alternative — refusing the deployment — was judged a wider blast radius than
  the defect warrants.
- **Negative / tradeoffs:** digigraph and the digichat registry now disagree on the *mechanism*
  of refusal (per-entry fail-closed versus whole-document throw) while agreeing on the
  *acceptance rule*. Anyone adding a field to this map must decide which model applies, and the
  answer is per-tenant for the corpus map.
- **Negative / tradeoffs:** a `null` value is now a locked tenant rather than an unlocked one.
  That is a behaviour change for any operator who wrote `null` meaning "off"; the map's contract
  says an absent key means off, and a present `null` is a bad value, not an absent one.
- Acceptance: pinned by `tests/dg/test_corpus_routing.py` — a non-boolean string, int, float,
  `null`, list and object all become locked; a real boolean passes through unchanged; the
  offending entry is not dropped.

## Links

- Related issues: DIG-4590 (this change), DIG-4576 (parent review), DIG-4459 (tenant corpus
  map contract), DIG-2366 (the CWE-639 bypass this module fails closed against).
- Supersedes: nothing. The tenant corpus map contract (DIG-4459) is unchanged; this ADR
  decides the one field's failure mode inside it.
- Amends: `digigraph/src/digigraph/corpus_routing.py` (the `_parse_map` lock branch and the
  module docstring), `digigraph/ARCHITECTURE.md` (new §6.12 and the `DIGI_TENANT_CORPUS_MAP`
  row).
- Not indexed in `docs/agent-backlog/INDEX.md`: this ADR records one field's failure mode and
  opens no ongoing workstream, so it does not govern ongoing work the way the indexed ADRs do.
