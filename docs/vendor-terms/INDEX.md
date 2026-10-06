# Vendor terms records

**Status:** Active — intake gate
**Owner:** CTO owns the intake line. Security owns the checklist.
**Governing policy:** [../VENDOR_CONTENT_BOUNDARY.md](../VENDOR_CONTENT_BOUNDARY.md)

---

## The standing line

> **No third-party data access merges without a `docs/vendor-terms/<vendor>/INDEX.md`
> entry. The check runs when the integration is proposed, not at review time.**

Review time is the expensive point. By then the code is written and the access
method is described in the diff, so the finding costs a rewrite instead of a
conversation. The PrimeMarket and Gloomberb failures were both discovered at the
review step, after publication.

---

## What needs an entry

Any change, in any repository, public or private, that adds or changes:

1. Network calls to a third-party host.
2. Selectors, URLs, endpoints, authentication flows or pagination logic for a
   specific third party.
3. Vendor-specific configuration constants (a `<VENDOR>_*` env prefix).
4. Documentation describing how to reach a specific vendor's data.

Generic vendor-agnostic library code and our own internal services are out of
scope. Full scope and exclusions: [VENDOR_CONTENT_BOUNDARY.md](../VENDOR_CONTENT_BOUNDARY.md).

## The three traps

These are the specific mistakes we have already made. Read them before reading a
vendor's repository.

**1. An open-source licence on the code is not a licence on the data.** Every
vendor in this folder ships an open-source SDK and a separately-licensed data
product. Gloomberb's terms put MIT on the source code and said in the same
paragraph that the terms govern "the data and content we provide" (§2). Reading
a repository's `LICENSE` tells you nothing about the data. Our own
[LuxAlgo record](luxalgo/INDEX.md) is the worked example: our guard
(`LUXALGO_COMMERCIAL_LICENSE`) covers the *code* licence (CC BY-NC-SA indicator
source) and says nothing about the *data* licence, while a sibling module
asserts the data is CC0 without any of us having read the vendor's terms.

**2. Wrapping a vendor SDK does not launder a copied credential.** If the
wrapper is ours and the credential is a browser session we replay, the terms are
still theirs. The transport does not change who is authenticating.

**3. "The client brings their own account" needs the vendor's terms to say so.**
It is the shape most likely to be permitted, and it was permitted in Gloomber's
§12 ("for yourself **or for users who have their own access**"). That reading is
Gloomber's. It does not transfer to another vendor without reading theirs.

**And a fourth, cheap to state:** where a vendor offers a documented API key,
MCP server or developer interface, that is the access method to build on. A
cookie is the fallback of last resort and is never the design.

---

## The steps

1. Locate the vendor's current terms, API terms or developer agreement.
   Record URL + ISO 8601 UTC retrieval timestamp.
2. Save the artefact to private storage (`digithings-ai/digithings-ops`) and
   record its sha256. **Not committed to this repository** — see
   [Artefact Standards](../VENDOR_CONTENT_BOUNDARY.md#artefact-standards).
3. Quote the clauses that bear on the access method, verbatim, with section
   numbers, in the vendor's `INDEX.md`.
4. Security classifies the access method **Permitted / Prohibited / Unclear**.
5. Anything Unclear or Prohibited goes to Counsel for a recorded position before
   implementation. Security does not guess, and Counsel does not assert exposure
   they cannot evidence.
6. Record the decision here.

A vendor's terms can change in place with no new URL and no announcement, so an
entry carries a **re-retrieve date**, not only a retrieval date. When the sha256
no longer matches, re-read and re-record; do not assume the old clauses hold.

**No vendor outreach.** Reading a vendor's public terms is not contacting them.
Asking a vendor for permission, a licence or a partnership is Chris's decision,
and it stays his.

---

## Records

| Vendor | Access method | Classification | Retrieved |
|---|---|---|---|
| [Bloomberg](bloomberg/INDEX.md) | none in code; no credential held; no contact | **pending Security** | 2026-10-06 |
| [LuxAlgo](luxalgo/INDEX.md) | hosted MCP (`https://mcp.luxalgo.com/mcp`), 8 wrapped tools | **pending Security** | 2026-10-06 |

"Pending Security" means the clauses are recorded and quoted but nobody has
signed a classification yet. Under step 5 that blocks implementation on anything
that adds access — it does not block the record existing, which is the point of
writing it early.

---

> `DIG-###` are internal issue-tracker IDs, not resolvable in this public
> repository; each is cited so the reasoning is traceable internally.