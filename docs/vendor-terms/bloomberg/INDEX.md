# Bloomberg — terms record

**Vendor:** Bloomberg L.P. ("BLP")
**Classification:** **pending Security** — see [Classification status](#classification-status)
**Record opened:** 2026-10-06 · **CTO**
**Related:** DIG-1318 · DIG-503 (publication freeze, PrimeMarket) · DIG-461 (Counsel memo)

---

## Access method

**No Bloomberg data integration.** No credential is held, no vendor API is
called, no vendor contact has been made. This record exists because a
partnership and a data-sourcing arrangement have been *proposed* (Chris,
2026-10-05), and the check is cheap now and expensive later.

Nothing in this record describes how to reach Bloomberg data. There is no recipe
to withhold.

**One scoped reference, which is not nothing.** `bloomberg.com` appears as a
retrieval domain in
`digiquant/src/digiquant/research/config/search_domains.yaml:40`, under the
`alt-sentiment-news` segment, and that file passes through to the web-grounding
tool's `include_domains` (`research/data/web_grounding.py:3-4`). That is a
scoped search over news pages, not a data feed: we do not hold an entitlement,
and no Bloomberg content is pulled and stored.

Whether a search provider's retrieval against a named third party is
attributable to us is Security's call, not this record's, and it is recorded
here rather than answered. It meets conditions 1 and 2 of the
[scope test](../INDEX.md#scope-test), which is why it is written down at all.

## Artefact

| Field | Value |
|---|---|
| Terms URL | `https://www.bloomberg.com/notices/tos/` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T03:44:42Z |
| Re-verified | 2026-10-06, byte-identical, sha256 unchanged |
| sha256 of saved HTML | `33af25936933d1e9ae0920777aa64e1ef3182b15430233203eacb3aaaad15faa` |
| Size | 188,148 bytes |
| Effective date | **Not stated on the page.** The only date in the body is 2023-07-31, and it is the anchor for the §30-day arbitration opt-out window, not a terms effective date. |
| Artefact location | Private. Not committed here. **The private home named in the policy is not a safe place for it** — see [Where the artefact lives](../INDEX.md#where-the-artefact-lives). |

The hash, not the date, is what carries the evidentiary weight here: with no
effective date on the page we cannot say the terms have not changed, only that
the bytes we read are the bytes we recorded. That is why the re-retrieve rule
exists.

### Second URL, and why it is not the artefact

`https://data.bloomberg.com/tos` returns HTTP 200 and 2,363 bytes of
JavaScript-gated shell — the served page body extracts to 19 characters of text
("Oops! Looks like JavaScript is disabled"). sha256
`319ac9cdafd5cba66c7b2364074097679a2e0d3119dd8e0d0ca8adcefe76d1af`.

It is recorded here so the next person does not spend an hour discovering that a
200 is not a retrievable document. It is **not** the artefact, because there is
nothing in it to read. Its marketing text states the data terms scope over "all
application programming interfaces ("APIs"), software development kits, sample
code, developer tools" and materials made available "via other public
repositories of software" — which is the scope point below, taken from the page's
own description rather than from the terms themselves. **UNSURE**: the operative
Bloomberg Data Terms text has not been read by anyone here. Retrieving it needs a
JavaScript-capable fetch.

---

## Clauses read

Quoted verbatim from the artefact above. Section numbers as printed.

**§3 Restrictions on Use**

> You shall not use or attempt to use any "scraper," "robot," "bot," "spider,"
> "data mining," "computer code," or any other automate device … without the
> prior express written consent of BLP.

**§4 License**

> You acquire absolutely no rights or licenses in or to the Service … other than
> the limited right to utilize the Service in accordance with the TOS.

**Competing use** (within §3's restrictions)

> … in any manner that could compete with the business of Bloomberg or any of its
> suppliers.

**Redistribution of derived output**

> You may not recirculate, redistribute or publish the analysis and presentation
> included in the Service without BLP's prior written consent.

**No mirroring**

> … you may not archive, cache, or mirror any Bloomberg.com Web page or portions
> of a Web page.

**No licence by implication**

> Nothing contained in the TOS or on this site should be construed as granting, by
> implication, estoppel or otherwise, any license or right to use any Service in
> any manner without the prior written consent …

*(Ellipses mark elided text, not paraphrase. Full clause text is in the private
artefact. Every quote in this section was checked character-for-character against
the saved artefact.)*

---

## Engineering read — not a classification

Three things follow from the text above, and Security owns whether they add up
to Permitted, Prohibited or Unclear.

1. **Any automated retrieval is off the table without written consent.** §3 names
   "computer code" and "any other automate device", not just crawlers. It is
   written broadly enough to reach a programmatic pull as well as a scraper.
   It is *analogous to* what stopped PrimeMarket and Gloomberb, not the cause:
   PrimeMarket failed on its own §11/§12
   ([VENDOR_CONTENT_BOUNDARY.md](../../VENDOR_CONTENT_BOUNDARY.md)), and Gloomberb
   was refused under 5 U.S.C. 13107(c)(1)(B) (`tool_refusals.py`). No Bloomberg
   clause has stopped anything here, because no Bloomberg access has been taken.
2. **The default licence is use-in-accordance-with-the-TOS.** §4 grants nothing
   else. It is not a data licence, not a redistribution right and not an
   embedding right.
3. **The proposed shape collides with two named clauses.** Sourcing market data
   and embedding it in a product we sell is "recirculate, redistribute or
   publish the analysis and presentation included in the Service", and it sits
   against the competing-use prohibition. That reads as **Prohibited** absent a
   written agreement, and as **Unclear** rather than Prohibited only if Bloomberg
   would in fact sign one — which nobody here knows.

**The documented interface exists**, which is what makes the "prefer a
documented interface" rule satisfiable rather than aspirational:
`https://developer.bloomberg.com/` is Bloomberg's developer portal, and BLP
product access is granted by entitlement agreement rather than by self-service.
Any Bloomberg work should be built on an entitlement under a signed agreement,
not on retrieval. **CONFIRMED** that the portal exists; **UNKNOWN** what an
entitlement would permit, because no agreement has been sought or read.

---

## Classification status

**Pending Security.** Clauses are recorded, quoted and hashed. Nobody has signed
a classification. Security owns that step (DIG-1318 acceptance criterion 3);
Counsel takes anything Unclear or Prohibited before implementation.

Two questions are already shaped for whoever picks this up:

- Does §3's "any other automate device" reach an entitled, contractually-granted
  API pull, or does an entitlement carve it out? The answer is in the
  entitlement agreement, not in the public ToS.
- Does the proposed "showcase their product and my product, and embed it" shape
  survive §3's competing-use prohibition and §4's redistribution restriction
  without written consent?

**No outreach.** Reading public terms is not contacting Bloomberg. Sounding them
out about a partnership, a licence or an entitlement is Chris's decision.

---

> `DIG-###` are internal issue-tracker IDs, not resolvable in this public
> repository; each is cited so the reasoning is traceable internally.