# LuxAlgo — terms record

**Vendor:** LuxAlgo Global, LLC (Delaware)
**Classification:** **CC0-1.0 CONFIRMED for the trackers dumps (Security, 2026-10-06)** — two families limited · redistribution question still open · see [Classification status](#classification-status)
**Record opened:** 2026-10-06 · **CTO**
**Related:** DIG-1318 · DIG-1447 (three live trackers tools) · DIG-1251 (Counsel's ruling that *bounds* these tools — it is not their origin, and their absence from `REFUSED_TOOLS` is not a clearance)

---

## Access method

**Live, on `develop`, already integrated.** This is the vendor's own documented
hosted interface, not a replayed browser session.

Per [VENDOR_CONTENT_BOUNDARY.md](../../VENDOR_CONTENT_BOUNDARY.md#what-this-repository-does-and-does-not-publish),
the endpoint, request shapes and tool inventory are **not published here**. They
are named only in aggregate, because the fact that an access exists at all is
the finding:

| Fact | Detail |
|---|---|
| Interface | Hosted MCP server, streamable HTTP / JSON-RPC |
| Reaches the vendor | Yes. The endpoint and tool inventory live in the code, not here. |
| Kill switch | `LUXALGO_ENABLED` — default ON, fails closed |
| Context handling | `LUXALGO_CONTEXT` injected server-side, so client PII is not sent to the vendor |
| Wrapped tools | 14 — 8 library, 3 edge, 3 trackers. Asserted in `tests/dq/test_mcp_luxalgo_tools.py:191`. |
| Existing guard | `scripts/check_luxalgo_license_boundary.py` |

**CONFIDENCE: CONFIRMED**, read from the repository. Every string here is
already public in `digiquant/src/digiquant/data/luxalgo/client.py`, so nothing
is disclosed by naming the category; the endpoint string itself is withheld to
keep this folder consistent with its own policy and with the Bloomberg record.

This record therefore is not preventive for LuxAlgo. It is corrective on one
point and prospective on another, and it says so: DIG-1318 describes the position
as "no LuxAlgo access exists in code", and that is not true. The check arrived
late, which is the failure mode the issue was written to prevent.

### What is deliberately not wrapped

`library_get_source_code` (Pine indicator source, CC BY-NC-SA 4.0) is not
exposed. A guard keeps it off every surface while `LUXALGO_COMMERCIAL_LICENSE`
is unset, and the flag defaults OFF.

`broker_*` is also not wrapped, for a different reason: broker credentials are
never sent to the hosted MCP, so those calls are local mirrors under
`digiquant/src/digiquant/brokers/` and do not reach the vendor at all.

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

| Field | Trackers dump licence |
|---|---|
| Artefact | `https://github.com/LuxAlgo/market-trackers-data` — `LICENSE` at `main` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T08:50:50Z |
| sha256 | `a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499` |
| Size | 7,048 bytes |
| SPDX | `CC0-1.0` (GitHub licence detection agrees) |
| Artefact location | public — the repository is `private: false` |

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

> LuxAlgo never asks for or stores your brokerage password; connections use
> read-only API keys you create, or tokens issued after you sign in directly
> with your broker or with our data partner **Plaid**.

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
values with attribution: `"Sourced from LuxAlgo Library"` in the digiquant
attribution payload, plus the Edge Stats and Market Trackers tool families.
Whether attributing a value inside our product is redistribution is **the
question for Counsel**, and it is Unclear until answered.

Not a LuxAlgo-data surface: the dashboard chart at `/research/vela-spike` uses
the Apache-2.0 `@luxalgo/vela` charting library, and its bars are annotated
"Sourced from Gloomberb" (`apps/dashboard/app/research/vela-spike/page.tsx:104`).
That is a code licence and a different vendor's data. It belongs in this folder
only as the trap-1 example: an Apache-2.0 library is not a data licence.

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

### The claim that has now been checked — **CC0-1.0 CONFIRMED**

Security read the primary source on 2026-10-06 and the answer came back
**positive**, not negative. This section replaces the "never been checked"
framing it was written under.

The artefact nobody in this thread had read is the repository itself, named by
our own code as the fallback `source_url`
(`digiquant/src/digiquant/data/luxalgo/attribution.py`, `LUXALGO_TRACKERS_URL`):

| Field | Value |
|---|---|
| Artefact | `https://github.com/LuxAlgo/market-trackers-data` — `LICENSE` at `main` |
| Read (ISO 8601 UTC) | 2026-10-06T08:50:50Z |
| sha256 | `a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499` |
| Size | 7,048 bytes — verbatim CC0 1.0 Universal legal code |
| SPDX | `CC0-1.0` (GitHub's own detection on that repository) |
| Repository state | `private: false`, org `LuxAlgo`, created 2026-08-24, last push 2026-09-24 |

The README's licence section states the same thing in the vendor's words: *"The
data in this repository is dedicated to the public domain under CC0 1.0
Universal. The underlying records are US-government public records; the
normalized form stays as unencumbered as its sources. Use it for anything,
commercial or not, no attribution required."*

**The tension this record raised resolves in the claim's favour.** The "may not
be redistributed" sentence is under the heading **Market Data & Delays**, and
every sentence in that block is scoped to quote and price data — "In **Vela**,
U.S. equities data is real-time from the Cboe EDGX exchange…", "**Market pages
on luxalgo.com** use data from providers including…". Cboe EDGX, CME Group via
Databento, Financial Modeling Prep, Massive and Twelve Data are quote and price
feeds. The trackers feeds are public-record extracts from a separate public
repository the vendor CC0-dedicated. The hypothesis stated when this issue was
filed — that these datasets are public-record derived while the clause covers a
different surface — **holds**.

Per dataset family, which is how the verdict is recorded (six families, not
one; see §[Per-family classification](#per-family-classification) below).

### Per-family classification

| Family | Upstream dir | Primary source | Verdict |
|---|---|---|---|
| insider-transactions | `insider/transactions/` | SEC EDGAR Form 4 | **CC0-1.0 CONFIRMED** |
| thirteenf-holdings | `thirteenf/holdings/` | SEC EDGAR Form 13F-HR | **CC0-1.0 CONFIRMED** |
| gov-contracts | `contracts/awards/` | USAspending | **CC0-1.0 CONFIRMED** |
| lobbying-filings | `lobbying/filings/` | Senate LDA API | **CC0-1.0 CONFIRMED** |
| congress-trades | `congress/trades/` | House Clerk, Senate eFD | **CC0-1.0 CONFIRMED** as licence · **commercial use restricted by statute** |
| short-volume | `short-volume/daily/` | FINRA | **UNCLEAR** — upstream terms unresolved · with Counsel |

The four plain confirmations do not rest on the vendor's assertion alone.
EDGAR filings, House Clerk and Senate disclosure reports, Senate LDA and
USAspending records are **works of the US federal Government**, which 17 U.S.C.
§105 places outside the scope of US copyright. That is a stronger basis than a
vendor's CC0 dedication, and it means these four would survive a dispute about
the vendor's own rights.

**congress-trades carries a limit no licence can supply.** The rows are 13107(c)
disclosure reports. 5 U.S.C. §13107(c)(1)(B) restricts their use for a
commercial purpose, and §13107(c)(2) runs to whoever obtains or uses the report.
A CC0 dedication is a waiver by the affirmer; it cannot waive a statutory use
prohibition, and it cannot move the exposure to the vendor. Counsel classified
this data class refused (DIG-1472). **The dataset is in service by business
decision dated 2026-10-06 against that advice, which is not a clearance** —
recorded at `LUXALGO_TRACKERS_ALLOWED_DATASETS` and pinned by
`tests/dq/test_congress_trades_statute_and_ingest_provenance.py`.

**short-volume is Unclear, and this is where the CC0 grant runs out.** FINRA is
a **private self-regulatory organisation**, not a federal records custodian
like the other four. Its short-sale-volume compilation carries FINRA's own
terms, and CC0 §4(b)–(c) is explicit about what that means: the affirmer makes
no warranty of title or non-infringement and disclaims responsibility for
clearing other people's rights. LuxAlgo cannot license what it does not hold.
This is exactly the failure mode Counsel predicted — *"Form 4 and 13F data are
republished third-party data and may carry upstream redistribution terms
regardless of what LuxAlgo asserts about its own dump."* Routed to Counsel.

### The defect this record was filed against

The original finding was that our code asserts a licence nobody had read. That
was right, and the claim turned out to be true — which means the finding's real
consequence is not "the claim was false" but **the claim was unqualified**.

Every trackers surface shipped "CC0 public-record dumps" with no per-family
caveat: `attribution.py`'s `LUXALGO_TRACKERS_LICENSE_NOTE`, the three
`TOOL_NOTES` entitlement sentences, the `luxalgo_trackers_datasets` MCP
docstring, and the orchestrator tool description. A reader — human or model —
concludes CC0 makes congress-trades fine. It does not. That is the same defect
shape `tool_refusals.py` was fixed for under DIG-1479: the §13107 note reached
the refusal module and never reached the attribution constants.

Fixed 2026-10-06 (DIG-1464): the classification now lives in
`digiquant/src/digiquant/data/luxalgo/attribution.py` as
`LUXALGO_TRACKERS_DATA_LICENSE`, `LUXALGO_TRACKERS_LICENSE_ARTEFACT` and
`LUXALGO_TRACKERS_DATA_CAVEATS`, and every trackers licence and entitlement
note renders the caveats via `trackers_data_caveat`. The guard is
surface-wide: a file that says CC0 for trackers data without naming a limit
fails `test_no_user_visible_cc0_claim_is_left_unqualified`. That guard closes
the wider hole this issue found — **nothing in the tree checked the data
licence at all**, while `scripts/check_luxalgo_license_boundary.py` and
`license_guard.py` cover the *code* licence only.

### The specific claim that has never been checked

Our code asserted that the trackers datasets are **"CC0 public-record dumps"**,
with `provenance.sourceUrl` on every row, and the entitlement note repeated it.
Three tools expose them (`luxalgo_trackers_datasets`, `_latest`, `_ticker`), and
**six ingest datasets** sit behind them: congress-trades
(`trackers_ingest.py`) plus insider-transactions, thirteenf-holdings,
short-volume, lobbying-filings and gov-contracts (`trackers_wave2_ingest.py`).

That was our own assertion, in our own code, made without anyone reading the
LuxAlgo terms — exactly trap 1 from the [intake record](../INDEX.md): a licence
claim inherited from a repository rather than read from the vendor. **It has now
been checked; see [above](#the-claim-that-has-now-be-checked--cc0-10-confirmed).
The claim is CONFIRMED, and what was wrong with it was its unqualifiedness.**

Retained for the audit trail, superseded by the sections above: the ToS states
that market data "includes data licensed from third parties" and names
Cboe EDGX, CME Group via Databento, Financial Modeling Prep, Massive and Twelve
Data — all commercial market-data businesses, none a public-record source — and
states the data "may not be redistributed". Our own code said the hosted MCP is
the transport while "the dumps are the source of record". On that reading the
claim looked unverified. It was not false; the clause simply covers a different
surface.

---

## Classification status

**The trackers data licence is signed by Security: CC0-1.0, per family, as
tabulated above (2026-10-06).** Clauses recorded, quoted and hashed. Two items
remain open and both are Counsel's, because Security's classification is about
the licence and theirs is about what we may do with it.

1. **short-volume upstream terms (UNCLEAR → Counsel).** FINRA is a private SRO,
   not a federal records custodian, so the CC0 grant reaches LuxAlgo's own
   normalisation and not FINRA's compilation. Counsel to give a recorded
   position: keep, refuse, or condition on FINRA's own redistribution terms.
   Raised as a child of DIG-1464.
1b. ~~Is congress-trades data refusable as a matter of statute?~~ **Answered.**
   Counsel ruled the data class refused under 5 U.S.C. 13107(c)(1)(B) on
   DIG-1472 (CONFIRMED). The dataset remains in service by business decision
   dated 2026-10-06 against that advice — a decision to accept the
   §13107(c)(2) exposure, not a clearance. DIG-1479 records it at
   `LUXALGO_TRACKERS_ALLOWED_DATASETS`.
2. **Does rendering LuxAlgo-sourced values with attribution inside our product
   count as redistribution** under the ToS, and which tier covers it —
   Business Tier within its §1.6 limits, or an Enterprise Agreement? Still open
   (Counsel). Note the trackers dumps are a separate question from the Library
   surfaces this clause was written about, and their CC0 dedication does not
   answer it for anything the vendor delivers over the hosted MCP.
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