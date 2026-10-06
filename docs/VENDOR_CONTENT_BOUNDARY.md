# Vendor-Content Boundary

**Status:** Proposed — for the board's review
**Date:** 2026-10-05 (revised 2026-10-06)
**Author:** CTO, on Counsel's review
**Related:** DIG-503 (publication freeze), DIG-478 (parent, Counsel), DIG-461 (Counsel memo), DIG-1194 (Security)

> `DIG-###` are internal issue-tracker IDs, not resolvable in this public
> repository; each is cited so the reasoning is traceable internally.

---

## Purpose

**Before code that touches a third party's data, terms, endpoint, or access
method is merged into a repository, someone checks that vendor's terms and
records the answer with a retrievable artefact.**

We failed this check on PrimeMarket. The recorded answer — that the vendor was
fine with us using their data — was dated 2026-08-01 and carried no artefact: no
URL, no saved copy, no hash. It was written on the belief that the terms "could
not be retrieved", when they were at `/terms-of-use` all along. A boundary
requiring a retrievable source and a saved artefact would have caught it.

---

## Scope

The control keys on **the content of the change, not on which repository it
lands in.** This is the whole point: the exposure was created when a plan moved
vendor-specific code from a private repository toward a public one, so a rule
that switches off at the repository boundary does not catch the failure mode it
was written for.

### Applies to

Any change, in **any** repository — public or private — that:

1. Adds or changes code that **makes network calls to a third-party host**
   (scraping, API, webhook, browser automation).
2. Adds or changes **selectors, URLs, endpoints, authentication flows, or
   pagination logic** specific to a third party.
3. Adds or changes **vendor-specific configuration constants** (e.g., a
   `<VENDOR>_*` environment-variable prefix).
4. Adds or changes **documentation that describes how to access a specific
   vendor's data** (worked examples, runbooks, architecture mappings).

**Where the change is destined to become public raises the stakes; it does not
switch the requirement off.** Code that meets condition 1–4 is in scope whether
it opens in `digithings-ai/digithings` or in `digithings-ai/twelve-x`, and
whether or not it ever ships.

### Excluded

- **Generic library code** that is vendor-agnostic (e.g., the `digifetch`
  engine: `browser_session`, `HttpFetcher`, `RateLimiter`, `RetryPolicy`, SSRF
  guard). The library ships no vendor access and no vendor authorisation; you
  bring your own.
- **Internal services** we own (digikey, digigraph, digiquant, digisearch,
  digitrace, digivault, digiclaw, digibase).
- **Test fixtures / mocks** that do not encode real vendor endpoints or
  credentials.

### Mirror requirement for private repositories

A private repository runs the same checklist, and keeps its evidence in the same
form. Two things differ: the artefact stays in private storage (see **Storage**
below), and the decision record is private.

`digithings-ai/twelve-x` and other client repositories are in scope. The
decision recorded on DIG-478 closed one pipeline. It is not a substitute for
this boundary, and it was never one — the boundary is what stops the next
pipeline being written.

### Retroactive note

This boundary applies **prospectively**. An audit of **Gloomber** (flagged in
DIG-503, owned by Security as DIG-1194) applies the same boundary to the same
cookie-replay pattern.

---

## Required Checklist (per vendor, per access method)

Before a change touching a vendor merges, the author (or reviewer) completes
this checklist and attaches it as a PR comment:

### Before step 1: read the data licence, not the repository's `LICENSE`

**This is the mistake we have made twice, so it is a step of its own rather
than a note.**

Every vendor in this boundary ships an open-source SDK and a separately-licensed
data product. Gloomberb's terms put MIT on the source code and said in the same
paragraph that the terms govern "the data and content we provide" (§2). Reading
the repository's `LICENSE` tells you nothing about the data licence — it is a
different document, from a different grantor, covering a different subject.

Three corollaries that each cost us time:

- **A wrapper is ours, the credential is theirs.** Wrapping a vendor SDK but
  authenticating with a copied browser session does not change whose terms
  govern. The transport does not launder the credential.
- **A licence claim inherited from a repo is an assumption wearing a citation.**
  If our code asserts a data licence, that assertion needs the vendor's terms
  behind it, not a note in a sibling module. See the
  [LuxAlgo record](vendor-terms/luxalgo/INDEX.md), where an unverified "CC0"
  claim sits next to a guard that only covers the code licence.
- **"Client brings their own account" must come from the vendor's terms.** It was
  permitted in Gloomber's §12 ("for yourself **or for users who have their own
  access**"). That reading is Gloomber's and does not transfer without reading
  theirs.

### Where the record lives

Step 6 writes to `docs/vendor-terms/<vendor>/INDEX.md`, indexed from
[`docs/vendor-terms/INDEX.md`](vendor-terms/INDEX.md). The standing line lives
there too:

> No third-party data access merges without a `docs/vendor-terms/<vendor>/INDEX.md`
> entry. The check runs when the integration is proposed, not at review time.

| Step | Action | Evidence Required |
|------|--------|-------------------|
| 1 | **Locate the vendor's current Terms of Use / ToS / API Terms / Developer Agreement.** | URL + retrieval timestamp (ISO 8601 UTC). |
| 2 | **Save a retrievable artefact** (PDF or complete HTML) of the terms page to private storage. | Location in private storage + sha256 in the PR comment. **Not committed to this repository.** |
| 3 | **Read the artefact for the relevant clauses.** Search for: scraping/crawling/spidering prohibitions, automation/bot prohibitions, API restrictions, "competing products/services" clauses, derivative-work claims, consent requirements for reproduction, permitted-use scope (personal/internal vs commercial). | Quote the relevant sections verbatim in the PR comment with section numbers. |
| 4 | **Classify the access method** against the terms: **Permitted** (explicitly allowed, e.g., official API with key), **Prohibited** (explicitly forbidden), or **Unclear** (silent, ambiguous, or "contact us"). | Classification + reasoning in the PR comment. |
| 5 | **Escalate if Prohibited or Unclear.** Tag Counsel and Security on the PR and request a recorded position. | A recorded position from Counsel or Security (memo, issue, or PR comment). |
| 6 | **Record the decision** in the vendor's terms record. | For a public repository: an entry in `docs/vendor-terms/<vendor>/INDEX.md`. For a private one: the equivalent private record. |

### On step 5, precisely

Step 5 asks for **a recorded position, not a signature.** Counsel advises and
does not approve; a gate phrased as "do not merge until Counsel signs off"
invents a power the role does not have, and a gate that cannot be satisfied
either gets ignored or stalls every vendor-touching PR. Both are worse than
escalating. What step 5 actually blocks is a **Prohibited or Unclear
classification reaching a merge with nobody consulted.**

---

## Artefact Standards

- **Format:** PDF preferred (print-to-PDF from browser, preserving all text).
  HTML accepted if PDF fails (save complete page with assets).
- **Hash:** sha256 recorded in the PR comment and in the vendor's terms record.
- **Retrieval:** Must be reproducible — the URL must still serve the same
  content, or the saved artefact is the source of truth for what we saw.
- **Storage:** The saved artefact is **not** committed to this repository. Store
  it in private internal storage with restricted access. This public repository
  records only the terms URL, the ISO 8601 UTC retrieval timestamp, the sha256
  of the saved artefact, and the verbatim text of the clauses relevant to the
  access method, with section numbers.

That record carries every evidentiary property an artefact would — the URL, the
timestamp, the hash, the quoted clauses, reproducibility — and omits the
republication of a counterparty's full document. A counterparty in a dispute
should not have their terms copied into our public tree by our own policy, and a
document that exists to keep vendor material out of the public tree should not
instruct authors to put it there. That combination is a rule whose compliance
defeats its purpose.

`digithings-ai/digithings-ops` is the intended private home for artefacts.

### What this repository does and does not publish

Publish: the vendor's name, the terms URL, the retrieval timestamp, the sha256,
and the verbatim text of the clauses that bear on the access method, with
section numbers.

Do not publish: the access method itself, selectors, endpoints, request
shapes, credentials, or the counterparty's full terms document.

Those are different things and the distinction is load-bearing. Quoting §12
because it prohibits what you are about to do is the record that justifies your
decision. Describing §12's subject is the exposure.

---

## Enforcement Gates

| Gate | When | Mechanism |
|------|------|-----------|
| **Code Review** (now) | Every PR | Reviewer asks: "Does this touch a third party? If yes, where is the checklist?" |
| **CI Gate** (future) | On PR open | A script (`scripts/check_vendor_terms.py`) scans for new vendor-specific constants/selectors/URLs and fails if no matching terms-record entry exists. |
| **Owner** (always) | Release cut | Release checklist includes "All vendor-touching changes since last release have a terms-record entry." |

---

## Example: PrimeMarket

What we should have done on 2026-08-01, and did not. This table is the shape of
the record; it is deliberately incomplete on the one axis that matters.

| Field | Value |
|-------|-------|
| Vendor | Prime Terminal / PrimeMarket |
| Access method | (withheld — recorded in the private terms record) |
| Terms URL | `https://prime-terminal.com/terms-of-use` |
| Retrieved | 2026-10-04T21:39Z |
| Artefact | Private storage. Not in this repository. |
| sha256 of the saved artefact | `92be603b367d7d721591e60062388c898102519d664425afafe772953e7deeea` |
| Relevant clauses | §11 (reproduction and derivative works require prior written consent; licence is personal/internal only), §12 (prohibits automated or unauthorised access, scraping, crawling, browser automation, and creating competing products or services) |
| Classification | **Prohibited** |
| Decision (2026-08-01, the decision that should have been made) | Freeze publication. Hold the research-producer package and the `twelve_x/nodes/scrape.py` mapping. |
| Current state | DIG-478 decided — path C, continue and accept the risk, 2026-10-05. That decision does not lift the freeze and does not depend on it; the hold lifts only on Counsel's written confirmation that the publication exposure is closed. |
| Decider | the board |
| Counsel memo | document `12476ad7-f45e-4ebc-8d9b-ceb41af268fb` (DIG-461, through Amendment C). Cited by document id rather than as "DIG-461 revision 2" because the memo key currently resolves to a forked, incomplete document — see DIG-1357. |

**What is missing from this table is the point.** On 2026-08-01 the row that
existed was a conclusion — "the vendor is fine with us using their data" — with
no URL, no timestamp, no hash, and no quoted clause. That is what made it
worthless: it could not be checked, could not be re-checked later, and could
not be shown to anyone. **A conclusion without the clause it rests on is an
assumption wearing a citation.**

Two further notes on what this example does *not* do.

The access-method row is withheld, and the clauses that matter are quoted. That
is not a contradiction to be smoothed over. Publishing §12 is what makes the
Prohibited classification reviewable; publishing the method is the harm. The
rule is the distinction, not a compromise between them.

The clause list names §11 and §12 and stops. It does **not** name the
credential-share clause in the same terms, and that omission is deliberate —
Counsel's recommendation, recorded here so that nobody later reads the gap as an
oversight and "completes" it. That clause is the one where our own conduct is
the issue and the client's account is the thing at stake; naming it in a public
repository would record, under our own name, that we hold a credential to a
client's account. It adds exposure and it changes nothing about the
classification, because §12 alone carries "Prohibited". **The public record
needs to justify the decision, not to be complete.**

The artefact is in private storage and this repository does not say where.
Counsel's review was that a policy should not instruct anyone to copy a
counterparty's full terms document into a public tree, least of all as its
opening act for a counterparty in an unresolved dispute. Agreed. The hash is
public, so anyone can verify we are describing the document we actually read,
without us republishing it.

---

## Questions for the board

1. **Adopt this boundary?** If yes, file a follow-up for the CI gate script and
   the `CONTRIBUTING.md` update.
2. **Scope?** Any repository, public or private, that meets conditions 1–4. Is
   there a repository you want excluded, on the record?

**Answered, not open.** Counsel's position on the two that were theirs: the
Gloomber audit is correctly homed with Security as DIG-1194; and the escalation
path is Counsel and Security for a recorded position, with no further signatory
required. Adding one would recreate the defect fixed in step 5 — a gate nobody
can satisfy is a gate that gets ignored.

---

## Appendix: Why this matters

- **Public repos are permanent.** A published recipe cannot be recalled. GitHub
  does not truly delete history.
- **Terms change.** A saved artefact with date and hash proves what we saw
  *when we merged*.
- **Counsel cannot advise on what they cannot see.** "The terms could not be
  retrieved" is not a defensible position when the URL returns 200.
- **The pattern is systematic.** PrimeMarket and Gloomber both use
  cookie-replay. A boundary catches the class, not just the instance.
- **A policy that contradicts itself gets copied.** One table withholding a
  field while the next publishes it teaches an author nothing except which row
  to skim.