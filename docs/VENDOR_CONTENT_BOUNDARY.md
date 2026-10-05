# Vendor-Content Boundary for Public Repositories

**Status:** Proposed — for Chris's review
**Date:** 2026-10-05
**Author:** OSS Researcher (DIG-503)
**Related:** DIG-503 (PrimeMarket freeze), DIG-478 (parent, Counsel, blocked on Chris), DIG-461 (Counsel memo), DIG-443 (Security)

---

## Purpose

This document defines a boundary for the public `digithings-ai/digithings` repository: **before code that touches a third party's data, terms, endpoint, or access method is merged, someone checks that vendor's terms and records the answer with a retrievable artefact.**

We failed this check on PrimeMarket. The recorded answer — "PrimeMarket is fine with us using their data" (2026-08-01, in `docs/superpowers/specs/2026-08-01-market-context-integration-design.md`) — had no artefact behind it and was written on the belief that the terms "could not be retrieved", when they were at `/terms-of-use` all along. A boundary requiring a retrievable source and a saved artefact would have caught it.

---

## Scope

### Applies to

Any PR merging into a **public** repository (currently `digithings-ai/digithings`, `digithings-ai/digichat`, `digithings-ai/digiskills`, `digithings-ai/digivault`) that:

1. Adds or changes code that **makes network calls to a third-party host** (scraping, API, webhook, browser automation).
2. Adds or changes **selectors, URLs, endpoints, authentication flows, or pagination logic** specific to a third party.
3. Adds or changes **vendor-specific configuration constants** (e.g., `PRIMEMARKET_*`, `GLOOMBER_*`).
4. Adds or changes **documentation that describes how to access a specific vendor's data** (worked examples, runbooks, architecture mappings).

### Explicitly excluded

- **Generic library code** that is vendor-agnostic (e.g., `digifetch` engine: `browser_session`, `HttpFetcher`, `RateLimiter`, `RetryPolicy`, SSRF guard). The library ships no vendor access and no vendor authorisation; you bring your own.
- **Private repositories** (e.g., `digithings-ai/twelve-x`, client deliverables). They have their own governance.
- **Internal services** we own (digikey, digigraph, digiquant, digisearch, digitrace, digivault, digiclaw, digibase).
- **Test fixtures / mocks** that do not encode real vendor endpoints or credentials.

### Retroactive note

This boundary applies **prospectively**. A separate audit for **Gloomber** (flagged in DIG-503) will be opened as a follow-up issue — the same cookie-replay pattern appears in `docs/ops/gloomberb-session-cookie.md`, `docs/superpowers/plans/2026-09-16-gloomber-session-cookie-runbook.md`, `digiquant/src/digiquant/data/gloomberb/client.py:180-184`. Security should probably look with you.

---

## Required Checklist (per vendor, per access method)

Before a PR touching a vendor merges to a public repo, the author (or reviewer) must complete and attach this checklist as a PR comment:

| Step | Action | Evidence Required |
|------|--------|-------------------|
| 1 | **Locate the vendor's current Terms of Use / ToS / API Terms / Developer Agreement.** | URL + retrieval timestamp (ISO 8601 UTC). |
| 2 | **Save a retrievable artefact** (PDF or complete HTML) of the terms page. | File saved to `docs/vendor-terms/<vendor>/<vendor>-terms-<YYYY-MM-DD>.pdf` (or `.html`). Record sha256 in the PR comment. |
| 3 | **Read the artefact for the relevant clauses.** Specifically search for: scraping/crawling/spidering prohibitions, automation/bot prohibitions, API restrictions, "competing products/services" clauses, derivative-work claims, consent requirements for reproduction, permitted-use scope (personal/internal vs commercial). | Quote the relevant sections verbatim in the PR comment with section numbers. |
| 4 | **Classify the access method** against the terms: **Permitted** (explicitly allowed, e.g., official API with key), **Prohibited** (explicitly forbidden), or **Unclear** (silent, ambiguous, or "contact us"). | State classification + reasoning in PR comment. |
| 5 | **Escalate if Prohibited or Unclear.** Tag Counsel and Security in the PR. Do not merge until Counsel signs off in writing (comment or linked memo). | Counsel sign-off reference (memo ID, date, or PR comment). |
| 6 | **Record the decision.** Add an entry to `docs/vendor-terms/<vendor>/INDEX.md` with: vendor, access method, classification, artefact hash, decision date, decider (GitHub handle), Counsel memo ref if any. | INDEX.md updated in the same PR. |

---

## Artefact Standards

- **Format:** PDF preferred (print-to-PDF from browser, preserving all text). HTML accepted if PDF fails (save complete page with assets).
- **Naming:** `docs/vendor-terms/<vendor>/<vendor>-terms-<YYYY-MM-DD>.pdf` (e.g., `docs/vendor-terms/prime-terminal/prime-terminal-terms-2026-10-04.pdf`).
- **Hash:** sha256 recorded in `INDEX.md` and the PR comment.
- **Retrieval:** Must be reproducible — the URL must still serve the same content (or the artefact is the source of truth).
- **Storage:** Committed to the repo (public). Do not store credentials or secrets.

---

## Enforcement Gates

| Gate | When | Mechanism |
|------|------|-----------|
| **Code Review** (now) | Every PR | Reviewer asks: "Does this touch a third party? If yes, where is the checklist?" |
| **CI Gate** (future) | On PR open | A script (`scripts/check_vendor_terms.py`) scans for new vendor-specific constants/selectors/URLs and fails if no matching `INDEX.md` entry exists. |
| **Owner** (always) | Release cut | Release checklist includes "All vendor-touching changes since last release have INDEX.md entries." |

---

## Example: PrimeMarket (what we should have done)

| Field | Value |
|-------|-------|
| Vendor | Prime Terminal / PrimeMarket |
| Access method | Browser session → cookie hand-off → AJAX POST → S3 PDF download |
| Terms URL | `https://prime-terminal.com/terms-of-use` |
| Retrieved | 2026-10-04T21:39Z |
| Artefact | `docs/vendor-terms/prime-terminal/prime-terminal-terms-2026-10-04.pdf` |
| sha256 | `92be603b367d7d721591e60062388c898102519d664425afafe772953e7deeea` |
| Relevant clauses | §11 (reproduction/derivative works require prior written consent; license is personal/internal only), §12 (expressly prohibits automated/unauthorized access, scraping, crawling, browser automation, creating competing products/services) |
| Classification | **Prohibited** |
| Decision | Freeze publication (DIG-503 Task A). Hold P22 and `twelve_x/nodes/scrape.py` mapping. Await DIG-478 decision + Counsel confirmation. |
| Decider | (pending Chris) |
| Counsel memo | DIG-461 revision 2 |

---

## Questions for Chris

1. **Adopt this boundary?** If yes, I'll file a follow-up to add the CI gate script and update CONTRIBUTING.md.
2. **Scope of "public repo"?** Currently `digithings-ai/digithings`, `digichat`, `digiskills`, `digivault`. Add/remove?
3. **Retroactive Gloomber audit?** Separate issue or fold into this?
4. **Private repo policy?** Should `twelve-x` adopt a mirror boundary, or is Counsel's DIG-478 decision sufficient there?
5. **Escalation path?** Counsel + Security in PR comments is the proposal. Any other required signatories?

---

## Appendix: Why this matters

- **Public repos are permanent.** A published recipe cannot be recalled. GitHub does not truly delete history.
- **Terms change.** A saved artefact with date+hash proves what we saw *when we merged*.
- **Counsel cannot advise on what they cannot see.** "The terms could not be retrieved" is not a defensible position when the URL returns 200.
- **The pattern is systematic.** PrimeMarket and Gloomber both use cookie-replay. A boundary catches the class, not just the instance.