# ADR-0031 — Vendor-content boundary for public repositories

**Status:** Proposed
**Date:** 2026-10-05
**Author:** OSS Researcher (per DIG-503)
**Related:** DIG-503, DIG-478, DIG-461 (Counsel memo)

## Context

The digithings monorepo is public (`digithings-ai/digithings`, `visibility: public`). We integrate with third-party data vendors (PrimeMarket, Trading Economics, Gloomberb, etc.) whose Terms of Use may prohibit automated access, scraping, or publishing access methods.

In DIG-503, Counsel identified that the PrimeMarket (Prime Terminal) Terms of Use explicitly prohibit the access method our code uses (Section 12: "Users are expressly prohibited from accessing, collecting, extracting, reproducing, or using data from Prime Terminal through any automated or unauthorized means... create competing products or services using Prime Terminal content"). The access recipe was already published in `digifetch/ARCHITECTURE.md`, and a plan (ADR-0030 P22) would have published more of it.

The recorded assurance we had — "PrimeMarket is fine with us using their data" (2026-08-01, `docs/superpowers/specs/2026-08-01-market-context-integration-design.md`) — had no artefact behind it and was written on the belief that the terms "could not be retrieved", when they were publicly available at `/terms-of-use` all along.

## Decision

Before code that touches a third party's **data, terms, endpoint, or access method** is merged into a public repository, the following check must be performed and recorded:

1. **Retrieve the vendor's current Terms of Use / Terms of Service / API Terms** (or equivalent) from the vendor's public website.
2. **Save a retrievable artefact** (archived copy, screenshot, or saved HTML with timestamp and SHA-256 hash).
3. **Record the answer** in a structured format:
   - Vendor name
   - URL of terms reviewed
   - Date of review
   - SHA-256 of the artefact
   - Specific clauses relevant to automated access, scraping, derivative works, competing products
   - Conclusion: **Allowed** / **Prohibited** / **Unclear — needs Counsel**
   - If Prohibited or Unclear: the specific access method that is affected
4. **Store the record** in the repository under `docs/vendor-terms/` with a filename pattern: `<vendor>-<yyyymmdd>.md`.

The check is a **merge gate** for any PR that:
- Adds or modifies vendor-specific selectors, URLs, endpoints, or authentication flows in public code/docs
- Adds or modifies a scraper, fetcher, or access method for a third-party source
- Documents a worked example using a specific vendor's platform

The gate is satisfied when the record exists and is referenced in the PR description. If the conclusion is "Prohibited" or "Unclear — needs Counsel", the PR must not be merged to a public branch until Counsel clears it or the vendor-specific code is moved to a private repository.

## Consequences

**Positive**
- Prevents accidental publication of prohibited access methods
- Creates an auditable trail for Counsel and compliance
- Forces early engagement with vendor terms before code lands

**Negative / tradeoffs**
- Adds a step to PRs that touch vendor integrations
- Requires maintaining a `docs/vendor-terms/` directory
- May slow down initial integration work

## Implementation

1. Create `docs/vendor-terms/` directory.
2. Add a PR template check (or CI gate) that flags PRs touching `digifetch/`, `digiquant/data/`, `twelve-x/` (if public), or any scraper/access code for the vendor-terms check.
3. The first record to create is for PrimeMarket (Prime Terminal), based on the Counsel memo `counsel-memo` on DIG-461 revision 2 and the archived copy at `https://prime-terminal.com/terms-of-use` (retrieved 2026-10-04T21:39Z, sha256 `92be603b367d7d721591e60062388c898102519d664425afafe772953e7deeea`).
4. A follow-up record for Gloomberb (`term.gloom.sh`) should be created, as the same cookie-replay pattern is documented in `docs/ops/gloomberb-session-cookie.md` and `digiquant/src/digiquant/data/gloomberb/client.py`.

## Links

- DIG-503: Freeze publication of the PrimeMarket access recipe
- DIG-478: Parent issue (Counsel, blocked on Chris)
- DIG-461: Counsel memo on PrimeMarket Terms
- `digifetch/ARCHITECTURE.md` — vendor-content boundary note added
- `digifetch/AGENTS.md` — vendor-content boundary note added
- `docs/plans/adr-0030/README.md` — hold on P22
- `docs/plans/adr-0030/packages/P22-twelve-x-research-producer.md` — hold on P22