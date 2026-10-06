# LuxAlgo — terms record

**Vendor:** LuxAlgo Global, LLC (Delaware)
**Classification:** **pending Security** — see [Classification status](#classification-status)
**Record opened:** 2026-10-06 · **CTO**
**Related:** DIG-1318 · DIG-1447 (three live trackers tools) · DIG-1251 (origin)

---

## Access method

**Live, on `develop`, already integrated.** This is the vendor's own documented
hosted interface, not a replayed browser session:

| Field | Value |
|---|---|
| Interface | Hosted MCP server, streamable HTTP / JSON-RPC |
| Endpoint | `https://mcp.luxalgo.com/mcp` |
| Kill switch | `LUXALGO_ENABLED` — default ON, fails closed |
| Cache | 900s TTL |
| Context | `LUXALGO_CONTEXT` injected server-side, so client PII is not sent to the vendor |
| Wrapped tools | 8 (`library_*`, `edge_*`, `trackers_*`, `broker_*`) |
| Existing guard | `scripts/check_luxalgo_license_boundary.py` |

**CONFIDENCE: CONFIRMED** for the interface shape, read from the repository.

This record therefore is not preventive for LuxAlgo. It is corrective on one
point and prospective on another, and it says so: DIG-1318 describes the position
as "no LuxAlgo access exists in code", and that is not true. The check arrived
late, which is the failure mode the issue was written to prevent.

### What is deliberately not wrapped

`library_get_source_code` (Pine indicator source, CC BY-NC-SA 4.0) is not
exposed. A guard keeps it off every surface while `LUXALGO_COMMERCIAL_LICENSE`
is unset, and the flag defaults OFF.

---

## Artefacts

| Field | Value |
|---|---|
| Terms URL | `https://www.luxalgo.com/legal/terms-of-service/` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T03:44:42Z |
| Re-verified | 2026-10-06, byte-identical, sha256 unchanged |
| sha256 of saved HTML | `cad4afb7b7d7545f2c299c2c07b6ed761bcf7ac8be8a0fcadf3d36af65c5fad0` |
| Size | 101,670 bytes |
| Effective date | Stated: **"Last updated: September 6, 2026"** |
| Artefact location | private — `digithings-ai/digithings-ops`. Not committed here. |

| Field | Licensing page |
|---|---|
| URL | `https://www.luxalgo.com/licensing/` |
| Retrieved | 2026-10-06T03:44:42Z |
| sha256 | `d0eb9bb73686694deecbc0f3a851b6fd9a2e6a576a73ed24359975b93636a4c5` |
| Size | 145,346 bytes |
| Effective date | Contractual: "effective upon Licensee's completion of checkout (the 'Effective Date')". Only free-text date in the body is 2026-09-21. |

Also retrieved and available in private storage, quoted below where relevant:
`https://www.luxalgo.com/legal/disclaimer/` (last updated September 5, 2026),
plus `/legal/privacy-policy/` and `/legal/cookies-policy/`. The guessed paths
(`/terms-of-use`, `/legal/terms-of-use`, `/terms-and-conditions`, `/about/terms`)
all 404 — recorded so nobody repeats the search.

---

## Clauses read

Quoted verbatim. Section numbers are as printed; where LuxAlgo's pages are not
numbered, the heading is given.

**Prohibited use** (ToS)

> … to spam, phish, pharm, pretext, spider, crawl, or scrape …

**Reproduction and distribution** (ToS)

> … must not reproduce, distribute, modify, create derivative works of, publicly
> display … without our express written permission …

**Reverse engineering** (ToS)

> … modify, adapt, translate, reverse engineer, decipher, decompile … any portion
> of the Services …

**Exhaustion clause** (ToS) — the clause that makes everything else a closed list

> Any use of the Services not expressly permitted by these Terms of Service is a
> breach of these Terms of Service and may violate copyright, trademark, and
> other laws.

**Market data — "Market Data & Delays"** (ToS) — the load-bearing one for us

> Market data on this site and within our products includes data licensed from
> third parties.

> In Vela, U.S. equities data is real-time from the Cboe EDGX exchange and futures
> data is real-time from CME Group, both licensed through **Databento**.

> Market pages on luxalgo.com use data from providers including **Financial
> Modeling Prep, Massive and Twelve Data**, and may be delayed.

> All data is provided "as is" without warranty from LuxAlgo, its data providers
> or the exchanges, should be verified independently before trading, and **may
> not be redistributed**.

Every provider named by the vendor is a commercial market-data business. None of
them is a public-record source, and none of them is CC0.

**Broker connections** (ToS)

> … use read-only API keys you create, or tokens issued after you sign in directly
> with your broker or with our data partner **Plaid** …

> LuxAlgo never asks for or stores your brokerage password.

**Licence scope** (Licensing page §1.1)

> "Software" means, collectively: (a) Vela™ Pro, LuxAlgo's proprietary extensions
> to the Vela charting library, including the integrated scripting engine,
> orderflow tools, official watermark-free builds, and associated tooling; (b)
> PineTS, LuxAlgo's Pine Script® compatible scripting engine …

Note (b): PineTS is inside the vendor's proprietary "Software" definition even
though we carry it as the Apache-2.0 open-source library. Both can be true — the
open-source licence permits what the commercial agreement describes — but it is a
useful reminder that "open source" and "the vendor licenses this to you" are
independent facts about the same component.

**Restriction on redistribution in source form** (Licensing page §2)

> … distribute, publish, disclose, or otherwise make available the Software in
> source form to any third party, including by posting to any public or
> third-party-accessible source repository, package registry, forum, paste or gist
> service, file-sharing network, or dataset; …

The clause that follows it is the carve-out, and it names the tier:

> … (b) distribute the Software as a standalone library, SDK, or development tool,
> or otherwise make the Software's APIs available to third-party developers,
> **except as expressly permitted at the Business Tier under Section 2.2(b)** …

**Business Tier grant** (Licensing page §2.2) — the tier that would cover an
embedded product

> Business Tier grant. Subject to payment and Section 3, LuxAlgo grants Licensee,
> during the Subscription Term, all rights in Section 2.1 for an unlimited number
> of Developers, plus the right to: (a) distribute the Software white-labeled and
> without attribution; (b) redistribute the Software as componentry within …

**Who may use which tier** (§1.6–1.7) — this is the part that decides it

> "Business Tier" means the license tier available for self-serve purchase at the
> published flat annual price, with no Annual Revenue ceiling and no Seat limit,
> restricted to Licensees whose Licensee Products have fewer than one hundred
> thousand (100,000) End Users and whose Annual Revenue is under …

> "Enterprise Tier" means the license tier documented in a separately executed
> written agreement between LuxAlgo and Licensee (an "Enterprise Agreement"),
> for Licensees that are not eligible for the Business Tier or that require
> rights, support, or terms beyond those in this Agreement.

Sale, resale, rental, leasing, lending and transfer of the Software are
prohibited (§2).

*(Ellipses mark elided text. Full text is in the private artefacts. Every quote
in this section was checked character-for-character against the saved artefacts.)*

---

## Engineering read — not a classification

**Access through the hosted MCP is the vendor's own documented product.** They
advertise it — "The whole ecosystem, served as tools" — alongside a Broker SDK
("Every broker, one schema, your keys"). Trap 2 does not apply: there is no
copied credential to launder, the keys stay local, and LuxAlgo never receives a
brokerage password. On the access question alone this looks like the permitted
shape Security's item 5 asks us to prefer. **LIKELY** — not CONFIRMED, because
nobody has signed a classification and the exhaustion clause means every answer
depends on whether a specific use is "expressly permitted".

**Redistribution is where it stops being obvious.** Three clauses point the same
way — no distribution without written permission, market data that "may not be
redistributed", and any unpermitted use is a breach. Our surfaces render LuxAlgo
values with attribution ("Sourced from LuxAlgo Library", the Edge Stats and Market
Trackers families, the dashboard chart at `/research/vela-spike`). Whether
attributing a value inside our product is redistribution is **the question for
Counsel**, and it is Unclear until answered.

The licensing page is more useful than it first looks, and it names its own
limits: **Business Tier** §2.2(b) grants redistribution of the Software as
componentry and white-labelled distribution, but §1.6 caps it at Licensee Products
under 100,000 End Users and an Annual Revenue ceiling. **Enterprise Tier** (§1.7)
is "documented in a separately executed written agreement". So the vendor has a
route for exactly the shape we would want, it is a negotiation rather than a
self-serve purchase, and there is nothing further to read until it exists.

`LUXALGO_COMMERCIAL_LICENSE` does not answer any of this: that flag governs the
*code* licence (CC BY-NC-SA indicator source) only, and is about as far from a
data licence as a flag gets.

### The specific claim that has never been checked

`digisearch/src/digisearch/trackers_ingest.py` and the attribution notes assert
that the three `luxalgo_trackers_*` datasets are **"CC0 public-record dumps"**,
with `provenance.sourceUrl` on every row, and the entitlement note repeats it.

**That is our own assertion, in our own code, made without anyone reading the
LuxAlgo terms.** It is exactly trap 1 from the [intake record](../INDEX.md): a
licence claim inherited from a repository rather than read from the vendor. The ToS
states that market data "includes data licensed from third parties" and names
Cboe EDGX, CME Group via Databento, Financial Modeling Prep, Massive and Twelve
Data — all commercial market-data businesses, none a public-record source. It
also states the data "may not be redistributed". Meanwhile our own code says the
hosted MCP is the transport while "the dumps are the source of record".
**The CC0 claim is therefore unverified, and for the market-data families it is
in tension with what the vendor actually publishes.**

This is the highest-value thing in this record. It is stated here rather than
fixed here: a data-provenance claim is Security's to classify and Counsel's to
sign off, and we should not silently re-label it either way before they do.

---

## Classification status

**Pending Security.** Clauses recorded, quoted and hashed. Nobody has signed a
classification. Security owns that step (DIG-1318 acceptance criterion 3);
Counsel takes anything Unclear or Prohibited before implementation.

Questions already shaped, in the order they should be answered:

1. **Is the CC0 assertion on the trackers datasets correct**, and if not, what
   licence is it actually under? (Security to classify; affects three live tools
   and two ingest modules.)
2. **Does rendering LuxAlgo-sourced values with attribution inside our product
   count as redistribution** under the ToS, and which tier covers it —
   Business Tier within its §1.6 limits, or an Enterprise Agreement? (Counsel.)
3. Is the free/anonymous entitlement tier itself permitted for our use, given the
   exhaustion clause?

Adjacent, and tracked separately: **DIG-1447** — three `luxalgo_trackers_*` tools
are live, declared `free`, and absent from `REFUSED_TOOLS` in
`digiquant/src/digiquant/tool_refusals.py`. Counsel's precondition there is an
access-log check on `POST /v1/orchestrator_invoke` for trackers-tool invocation,
which has not been run because nobody with log access has run it. That question
is about who called the tool, not about whether the licence permits it, and it
does not block this record.

**No outreach.** LuxAlgo is a live vendor relationship. Nothing here contacts
them. Any commercial licence discussion is Chris's decision.

---

> `DIG-###` are internal issue-tracker IDs, not resolvable in this public
> repository; each is cited so the reasoning is traceable internally.