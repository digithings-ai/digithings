# HOLD — PrimeMarket (PMT) access recipe

**Status:** HOLD — do not implement, do not publish
**Date:** 2026-10-05
**Authority:** Counsel memo DIG-461 revision 2
**Related:** DIG-478 (parent, Counsel, blocked on Chris), DIG-503 (this freeze), DIG-461 (Counsel memo), DIG-443 (Security)

---

## What is held

| Item | Location | Reason |
|------|----------|--------|
| Package **P22** — `twelve-x` research producer confirm | `docs/plans/adr-0030/packages/P22-twelve-x-research-producer.md` | Would publish the PrimeMarket scrape path into the public repo |
| `twelve_x/nodes/scrape.py` mapping | `digifetch/ARCHITECTURE.md` lines 180–182, 198, 206, 249 | Contains the worked access recipe for PrimeMarket |

## Why

The research vendor **Prime Terminal / PrimeMarket** (`https://prime-terminal.com/terms-of-use`, retrieved 2026-10-04T21:39Z, sha256 `92be603b367d7d721591e60062388c898102519d664425afafe772953e7deeea`) prohibits the access method in **Section 12**:

> "Users are expressly prohibited from accessing, collecting, extracting, reproducing, or using data from Prime Terminal through any automated or unauthorized means."
>
> "...you may not: scrape, crawl, spider, or harvest data from the platform; use bots, scripts, APIs (unless officially provided by us), browser automation, or similar technologies to access or collect data; ... **create competing products or services using Prime Terminal content** ..."

> "Any unauthorized extraction or use of platform data constitutes a **material breach** of these Terms."

Section 11 requires "our prior written consent" for reproduction or derivative works, and licenses the platform "solely for your personal or internal business use".

**The risk is not that we read their data. It is that we publish the recipe for reading it, in a public repository, under our own name, permanently.**

## What is NOT held

- The generic `digifetch` library (`digifetch/`) — it ships no vendor access and no vendor authorisation; you bring your own.
- The private `twelve-x` repo (`digithings-ai/twelve-x`) — this hold applies only to the public `digithings-ai/digithings` repository.
- The `twelve-x-primemarket-heartbeat` cron job in `apps/digithings-cron/` — that is part of a client deliverable and is Chris's decision on DIG-478 card `295f3d75`.

## Hold lift conditions

This hold lifts **only when both** are true:

1. **DIG-478 is decided** — Chris chooses path A, B, or C on card `295f3d75`.
2. **Counsel confirms exposure is resolved** — a written memo from Counsel stating the publication risk no longer applies.

Until both conditions are met, no agent shall implement P22, no PR shall merge the `twelve_x/nodes/scrape.py` mapping, and no documentation shall add PrimeMarket-specific examples to public files.

## Escalation

If a published release or roadmap commitment depends on ADR-0030 shipping the PMT packages, escalate to Chris immediately.