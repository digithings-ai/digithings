# FINRA — terms record

**Vendor:** Financial Industry Regulatory Authority (a **private** US
self-regulatory organisation, not a federal records custodian)
**Classification:** **PROHIBITED — commercial redistribution (Counsel, 2026-10-06)** ·
see [Counsel's position](#counsels-position) · triggers the
[`short-volume`](../luxalgo/INDEX.md#per-family-classification) row
**Record opened:** 2026-10-06 · **Counsel** (DIG-1521)
**Related:** DIG-1521 (the question) · DIG-1464 (the trackers classification that
routed it here) · DIG-1318 (the vendor-terms programme) · DIG-1479 (allowlist)

---

## Why this vendor is in the folder

Not because we integrate with FINRA. **We do not, and the first remediation this
record supports is to stop serving the data at all.** FINRA is here because
`short-volume`, one of the six LuxAlgo trackers families, is a normalised extract
of a FINRA compilation, and our product serves it commercially.

That distinction matters, so it is stated first: this is a **title** record, not an
access-method record. There is no endpoint, no credential, no request shape here.
The question is whether FINRA's terms permit the use we are already making of
copies someone else took.

---

## The access methods FINRA offers, and what each permits

FINRA publishes this data three ways. All three were read. They do not agree with
each other on permissibility, which is normal: each is a different grant.

| # | Route | Instrument | Commercial redistribution? |
|---|---|---|---|
| 1 | Web download / interactive grid | FINRA Website Terms of Use + the Short Sale Volume Data User Guide's own notice | **No** — non-commercial only |
| 2 | Query API (`Reg SHO Daily Short Sale Volume`, Equity) | FINRA API Terms of Service **+ Specific Terms for Equity Data** | **No** — capped at non-commercial End User use, and **No Charge** |
| 3 | Written permission | FINRA's copyright permission process | Not yet sought. Chris's decision. |

FINRA states the relationship between routes 1 and 2 in its own API terms, and it
matters: the Specific Terms outrank the general API terms (§2 Order of
Precedence), and the Website Terms of Use say that where they conflict, the
"Other FINRA Terms" govern. So the **most permissive** instrument FINRA publishes
is route 2's Specific Terms — and that one is still not enough for us.

---

## Artefacts

Retrieved by byte-level fetch (not text extraction) on 2026-10-06, so the sha256
values below are over the served bytes and can be re-checked directly.

| Field | Website Terms of Use |
|---|---|
| URL | `https://www.finra.org/terms-of-use` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `6b5d5beaece48e2eb109e295c9b5279568a80e7d4d401ad21c9fd68d7cca67e8` |
| Size | 90,964 bytes |
| Stated effective date | "Last modified: November 9, 2023" |
| Artefact location | private internal storage. **Not committed here.** |

| Field | API Terms of Service |
|---|---|
| URL | `https://developer.finra.org/finra-api-terms-service` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `57b6f72a4438c83db7deb9b6bea4b503f6b192159f9a6a307f591366da808a93` |
| Size | 64,583 bytes |
| Stated effective date | Last updated 2026-03-19 |
| Artefact location | private internal storage |

| Field | Specific Terms for Equity Data |
|---|---|
| URL | `https://developer.finra.org/specific-terms-equity-data` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `a2ebf98d349b104d28a453bc08de70cdd124a76bc120d493fcf8506c3c1e5aa6` |
| Size | 39,169 bytes |
| Stated effective date | Last updated 2022-12-20 |
| Why it is recorded first | **§2 of the API terms makes Specific Terms the controlling instrument.** |
| Artefact location | private internal storage |

| Field | Short Sale Volume catalogue entry |
|---|---|
| URL | `https://www.finra.org/finra-data/browse-catalog/short-sale-volume` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `e4fac3825d077c37836d048331e708825cbcf067ab5cfe38b693ea7029a88af1` |
| Size | 81,542 bytes |
| Artefact location | private internal storage |

| Field | Short Sale Volume Daily Data User Guide |
|---|---|
| URL | `https://www.finra.org/sites/default/files/2020-12/short-sale-volume-user-guide.pdf` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `6c01acebfc5219249be44882bfcb7d4cd1f0514e6ac8a7840a782227c1bc4205` |
| Size | 867,251 bytes |
| Stated effective date | © 2020; "updates implemented as of February 23, 2026" |
| Why it is recorded | It carries **its own** reproduction notice, independent of the Website Terms of Use. |

| Field | Copyright permission page |
|---|---|
| URL | `https://www.finra.org/contact-finra/permission-use-finra-copyrighted-material` |
| Retrieved (ISO 8601 UTC) | 2026-10-06T09:38Z |
| sha256 | `86393b484cf0062574d0eb23fc0deed1d7030454f91fbe4719ed7fce90676401` |
| Size | 75,902 bytes |

**Re-retrieve by 2027-04-06.** A terms page can change in place with no new URL
and no announcement, which is the failure mode this folder's intake gate exists to
catch. FINRA re-states these documents periodically and the download files change
shape (the fractional-share update landed February 2026), so the hashes are a
tripwire, not a formality.

**The artefacts are not in this repository.** Republishing a counterparty's full
document is the thing
[VENDOR_CONTENT_BOUNDARY.md](../../VENDOR_CONTENT_BOUNDARY.md) exists to prevent.
What preserves the evidence is reproducibility: URL + ISO 8601 timestamp + sha256 +
the verbatim clauses below, and any of us can re-fetch and re-hash.

---

## Clauses read

Quoted verbatim from the artefacts above, with FINRA's own section letters. Every
quote below was checked character-for-character against the served bytes, not
against a search snippet or a summary.

### The dataset's own terms row (catalogue entry)

> Terms of Use
>
> Data is free for non-commercial use. See Terms of Use

"Free" and "non-commercial" are both in that one row. That is FINRA's own summary
of the grant, on the page that describes this dataset.

### The User Guide's independent notice

> No part of this publication may be reproduced, stored in a retrieval system, or
> transmitted in any form by any means—electronic, mechanical, photocopying,
> recording, or otherwise—without prior written permission from FINRA.

> © 2020 Financial Industry Regulatory Authority, Inc. All rights reserved.

This is a second, self-contained permission requirement attached to the data
guide itself, so it applies to the file format documentation and by the same
reason to the files described by it, independently of whether the Website Terms of
Use are the operative instrument.

### Website Terms of Use — Permitted Uses

> Subject to Restrictions, below, and any other restrictions in these Terms of
> Use, the content and material provided through the FINRA Website shall be used
> ONLY for your own non-commercial personal or professional use.

**ONLY.** There is no carve-out for redistribution anywhere in this instrument.

### Website Terms of Use — Restrictions (the ones that decide it)

> **a.** decompile, reverse engineer, disassemble, modify, distribute, or create
> derivative works or improvements from the FINRA Website or any portion thereof,
> or attempt to discover any source code, protocols, or other trade secrets in the
> FINRA Website;

> **d.** develop or create a database of data using the FINRA Website, except as
> expressly permitted by any other terms of use on the FINRA Website;

> **e.** use any process to monitor or copy the FINRA Website in bulk, or use any
> data mining, scraping or harvesting tools (including robots), or any similar
> data-gathering or extraction tools;

> **i.** create derivative works or improvements from the FINRA Website;

> **m.** use any portion of the FINRA Website in the development of any software
> program or in conjunction with any machine learning, neural network, deep
> learning, predictive analytics or other artificial intelligence computer or
> software program, including, without limitation, by using any portion of the
> FINRA Website in conjunction with a model, algorithm, or process that is
> designed to predict trades for or within an individual portfolio, fund, or other
> investment vehicle;

> **o.** use the FINRA Website for any purposes for which you have not been
> granted written permission by FINRA;

**Restriction (m) is the one that would end this on its own, and it is worth
reading twice.** We are an AI company. We serve this data to a model. Restriction
(m) does not care who copied the bytes or under what claim; it forbids *use in the
development of any software program* and *use in conjunction with any AI
program*. Even a hypothetical clean copy of FINRA's own file, lawfully obtained
through a permission we do not have, is not the right to this product.

### Website Terms of Use — Copyright and fair use

> The works of authorship contained in the FINRA Website, including, but not
> limited to, all design, text, sound recordings, and images—are owned, except as
> otherwise expressly stated, by FINRA and may not be copied, reproduced,
> transmitted, displayed, performed, distributed, rented, sublicensed, uploaded,
> posted, framed, altered, stored for subsequent use, or otherwise used in whole
> or part in any manner without FINRA's prior written consent, except to the
> extent that such use constitutes "fair use" under the Copyright Act of 1976
> (17 U.S.C. § 107), as amended, and then, only with notices of FINRA's
> proprietary rights.

**Fair use is the defence the industry reaches for here, and it is the weakest
thing in the file.** §107 is a factor test, and the factors run against us on every
axis that matters: the use is **commercial** (factor 1), we take the **whole**
compilation rather than a part (factor 3), our product **substitutes for** the
licensed or free product a user would otherwise pull from FINRA (factor 4), and
the data is not "freely available to the public" in the §107(3)(A) sense because
FINRA attaches conditions to its availability. And note the last clause: FINRA
does not grant fair use, it permits it **only** where we carry notices of FINRA's
proprietary rights — a further affirmative burden, and one our current surfaces do
not meet in full.

### Website Terms of Use — Enforcement

> … any other rights or remedies, to immediate injunctive or equitable relief from
> a court of competent jurisdiction and may obtain any order restraining any
> threatened or future unauthorized use or loss in each case, on use of affidavit
> evidence or otherwise, and without furnishing proof of actual damages or
> posting a bond or other surety.

Choice of law is New York; exclusive jurisdiction is the state and federal courts
in New York County. The aggregate liability cap ($100) protects FINRA, not us —
it is the price of our indemnity to FINRA for "any claim that information,
content, or data provided to you by FINRA … infringe … copyrights … rights in
data and databases."

**Read the exposure shape honestly: capped damages, uncapped injunction, and we
carry the indemnity.** A $100 cap does not make a $0 product safe. The realistic
worst case is not a damages claim, it is an injunction landing before the public
launch in early 2027, plus whatever a member firm's compliance program decides to
do with a vendor distributing data its own policy says may not be redistributed.

### API Terms of Service — order of precedence (§2)

> In the event of a conflict among the foregoing, the order of precedence is as
> follows (in descending order of control): **Specific Terms**, these general
> terms, the API Program Terms.

This is why the Equity Specific Terms are the instrument that matters, and why
route 2 must be read as a package rather than picking whichever term is friendlier.

### API Terms of Service — the grant (§3.2)

> Subject to these Terms, FINRA hereby grants to Developer a nonexclusive,
> non-transferable (except as set forth in Section 13.1), **non-sublicensable**,
> limited license to access and use the Licensed APIs to access and use the
> Licensed Data.

Non-sublicensable, and the redistribution right that does exist is granted by the
Specific Terms, not here.

### API Terms of Service — restrictions (§3.3)

> Developer shall not … **(c)** use the Licensed Materials to create any
> algorithm, product, or service that competes with FINRA's products or services,
> **(d)** use any process other than the Licensed APIs to monitor or copy the
> Licensed Materials in bulk, or use any data mining, scraping, or harvesting tools
> (including robots), or any similar data-gathering or extraction tools, or
> **(e)** access or use the Licensed Materials in a manner that would be typically
> categorized as a **bulk distributor or a service bureau**. Without limiting
> anything in this Section 3.3, Developer shall not … **(ii)** use the Licensed
> Materials for any purposes for which Developer has not been granted written
> permission by FINRA, … **(v)** remove, obscure, make illegible, or alter any
> original copyright or other notices, **(vi)** contest, challenge, or otherwise
> make any claim or take any action adverse to FINRA's ownership of, or interest
> in, the Licensed Materials.

Two of these deserve a second look. **§3.3(e) "bulk distributor or a service
bureau"** is a description of what serving this dataset to paying customers
through a hosted API is. And **§3.3(vi)** — no action "adverse to FINRA's
ownership of, or interest in, the Licensed Materials" — is what forbids relying
on a CC0 dedication that FINRA never made.

### API Terms of Service — ownership (§5.1) and Resultant Data (§1.6, §5.2)

> Developer acknowledges that, as between the Parties, FINRA owns all rights,
> including all intellectual property rights, in and to the Licensed Materials. If
> Developer acquires any rights, including any intellectual property rights, in
> the Licensed Materials, Developer hereby irrevocably assigns to FINRA all such
> rights for no additional consideration.

> "**Resultant Data**" means any data produced by Developer through processing
> Licensed Data, which data is substantially different from the original Licensed
> Data and which has been processed in a manner that third parties are unable to
> identify (through reverse engineering or otherwise) the Licensed Data from which
> the Resultant Data was derived.

> 5.2 Resultant Data. Unless otherwise specified in the Specific Terms, as between
> the Parties, and subject to FINRA's rights in the Licensed Materials, Developer
> will own all rights in …

**This is the clause our "we normalised it, so it is ours" argument runs into, and
it fails on both prongs.** A daily short-sale series keyed by
`Trade Facility / Date / Symbol / Short Volume / Short Exempt Volume / Total
Volume` — the exact field set in FINRA's own User Guide — is not "substantially
different from the original Licensed Data." It is the original Licensed Data with
the rows sorted. And the re-identification prong is worse: a per-security,
per-date aggregate is trivially reverse-mapped to FINRA's file by anyone who
downloads the same day. Neither prong of §1.6 is satisfied, so **this is not
Resultant Data at all.** It is the Licensed Data under a different filename.

### Specific Terms for Equity Data — the redistribution grant (2.2, 2.3, 2.4)

This is the only redistribution permission FINRA publishes. It is three words
away from fitting us, and those three words are why this is a ruling rather than
an Unclear.

> **2.2 Internal Use.** Developer and its Authorized Users may access and use the
> Equity Data only for Developer's non-commercial personal or professional use.

> **2.3 Redistribution.** Developer may redistribute the Equity Data and any
> derivative data or Resultant Data to third party end users ("End Users") for
> such End Users' **non-commercial personal or professional use only**, subject to
> the following:

> **(a) Attribution.** Developer shall clearly identify FINRA as the owner and
> source of that Equity Data including any derivative or Resultant Data derived
> therefrom.

> **(b) No Charge.** Developer may not charge or collect from an End User any fee
> for such End User's receipt and use of the Equity Data. For the avoidance of
> doubt, Developer may distribute Equity Data in conjunction with other
> fee-liable data distributed by Developer **provided that there is no additional
> or incremental fee charged for the Equity Data**.

> **(c) No Further Redistribution.** End Users shall not be permitted to further
> redistribute the Equity Data received from Developer.

> **(d) Compliance Efforts.** Developer shall take commercially reasonable efforts
> to ensure that End Users receiving Equity Data from Developer comply with the
> applicable terms and conditions set forth herein (for example, by requiring End
> Users to enter into agreements with Developer that require such compliance).

> **2.4** Developer is permitted to create derivative data and Resultant Data …

**Two independent caps, and we fail both.**

1. **"non-commercial personal or professional use only"** — that is the End User's
   permitted use. A paying digithings customer is not a non-commercial user, and a
   customer using the data to inform a trading decision is not making personal or
   professional use of a free public statistic; they are consuming it inside a
   commercial product.
2. **"No Charge"** — and note how carefully FINRA drafted the avoidance-of-doubt
   sentence. Bundling with fee-liable data is allowed **"provided that there is no
   additional or incremental fee charged for the Equity Data."** That sentence is
   not a loophole we can thread. It asks whether the data itself is free to the
   user. In a metered, subscription-priced product where `short-volume` is one of
   six dataset families behind `luxalgo_trackers_latest` and
   `luxalgo_trackers_ticker`, the honest answer is no: the user's fee buys access
   to it.

And §2.4 does not rescue us. It grants the *ability* to create derivative and
Resultant Data, and it sits in the same instrument whose §2.3 imposes the caps.
Derivative data inherits the parent term's limits — that is what "subject to the
following" in 2.3 means. Separately, as set out above, our data is not Resultant
Data at all under §1.6.

### The permission route exists, and FINRA describes it

> Individuals and organizations interested in using FINRA-copyrighted material
> must obtain permission from FINRA.

The same page asks the applicant to state "**Would there be any commercial use?
If so, what would be the sale price?**" — FINRA's own form recognises that
commercial use is a permission case to be granted, not a default entitlement. It
also lists End-User redistribution questions ("Who is the audience?", "How would
you distribute it?"), so the route exists; it is simply not free.

---

## Counsel's position

> **PROHIBITED.** Commercial redistribution of the `short-volume` family, as
> currently implemented, is not permitted by any FINRA term we can reach. **Not**
> because the CC0 is defective as a document, and **not** because there is some
> clause nobody has read yet — but because **every** route FINRA publishes stops
> at non-commercial use, and one of them additionally stops at no-charge use.

**Confidence: CONFIRMED** that the published FINRA terms do not permit this use.
Confidence on the recommendation: **CONFIRMED**, because it holds under every
branch of the one unknown (below).

### The question was two questions, and only the first was real

Security framed it as: *can the affirmer convey what it does not own?* The answer
is **no** — but that framing is downstream, and it is not what decides this.

The upstream question is whether FINRA permits commercial redistribution of its
short-sale compilation **at all**, including to parties who acquired it lawfully.
The answer is no. Four instruments say so independently: the catalogue's own
"free for non-commercial use" row, the Website Terms' "ONLY for your own
non-commercial personal or professional use", the User Guide's own "without prior
written permission", and the Equity Specific Terms' non-commercial **and** no-charge
caps. The CC0 question never gets a chance to matter, because the underlying data
could not have been redistributed commercially by anyone.

**This is the useful part of the answer, because it means the vendor conversation
is not where this gets solved.** A better CC0 from LuxAlgo, a negotiated
distribution deal with LuxAlgo, or a fresh dedication would all change the
*document* without changing the *restriction*. Only FINRA's written permission
changes the restriction.

### Why each escape route fails

| Route | Result | Why |
|---|---|---|
| **Fair use, 17 U.S.C. §107** | Fails | Commercial use; whole compilation; substitutes for the source; and FINRA's ¶(b) permits it only with notices of its proprietary rights. |
| **CC0 from LuxAlgo** | Fails | CC0 is a waiver by the affirmer. §4(b) disclaims warranty of title and non-infringement; §4(c) disclaims any responsibility for clearing other persons' rights or obtaining consents. LuxAlgo cannot waive FINRA's restrictions, and LuxAlgo's own grant is not the source of FINRA's copyright. |
| **"We normalised it"** | Fails | API ToS §1.6 Resultant Data requires data "substantially different from the original" **and** not re-identifiable. A sorted per-symbol per-date volume series is neither. |
| **"FINRA published it, so it's public domain"** | Fails | FINRA is a private SRO. **17 U.S.C. §105 does not reach it** — that is the whole reason this family is different from the other five, and it is the crux of the case. |
| **"An SEC rule required publication, so anyone may use it"** | Fails | FINRA publishes "Pursuant to a U.S. Securities and Exchange Commission request." A regulatory directive to publish is not a copyright licence to third parties, and FINRA's own terms are what govern downstream use. |
| **Exchange market-data licences** | Not available | FINRA states the files "are not consolidated with exchange data" and that a complete picture requires combining FINRA's TRF/ADF/ORF files **with each exchange's own file**. The exchange licences (the CTA/UTP/OPRA class) therefore do not reach this compilation. There is no exchange-side grant to lean on. |
| **FINRA tolerates free sites that republish** | Fails | FINRA's investor page notes that "some websites might redistribute the Short Sale Volume Daily File." Awareness is not permission, and those sites are themselves bound by the non-commercial term. Tolerated free republication is not a commercial licence. |
| **Written permission from FINRA** | **Open** | The only route that works. Not sought. Chris's decision. |

### The one thing I cannot close from public sources, and why it does not change the answer

There is one residual unknown: **whether LuxAlgo holds a private, negotiated
commercial redistribution licence from FINRA.** No public source would disclose
it, and there is no outreach from this lane — LuxAlgo is a live vendor
relationship and that contact is Chris's decision.

The recommendation is the same either way, which is why this is a ruling and not a
deferral:

- **If LuxAlgo holds no such licence** (the likely case, given the catalogue page
  presents the data as free and non-commercial for everyone), then it cannot
  lawfully have published a commercially redistributable dump, our copy is
  unlicensed, and **remove the family**.
- **If LuxAlgo does hold one** — say a limited internal-use or research licence —
  then the CC0 is an **over-grant relative to it**, and the CC0's own §4(b)–(c)
  is precisely the clause that disclaims responsibility for the gap. LuxAlgo would
  have warranted nothing about the FINRA layer, and would have told us so in the
  licence we would be relying on. **Still remove the family**, because what we
  would have is a licence that does not survive being re-sold to paying customers.

There is no branch on which the CC0 carries the commercial right we are using.

### What I am not deciding

I advise; I do not sign, send, or decide. So, plainly:

- **This is a legal position, not a product decision.** What Chris does with it is
  his call, and `congress-trades` already set the precedent that a dataset may
  stay in service by business decision against Counsel's advice — which is a
  decision to accept a documented exposure, **not** a clearance, and is recorded as
  such at `LUXALGO_TRACKERS_ALLOWED_DATASETS`.
- **The remediation I state** is: remove `short-volume` from
  `LUXALGO_TRACKERS_ALLOWED_DATASETS` and stop serving it. If Chris elects to keep
  it, the caveat string must state Counsel's *ruled* position rather than
  "unresolved", so users are told the data is not cleared for the use being made of
  it. Security's existing guards
  (`test_no_user_visible_cc0_claim_is_left_unqualified`,
  `test_every_trackers_tool_note_carries_the_caveat`) are the right instrument and
  should stay in place either way.
- **Outreach is not mine.** Written permission from FINRA, and any commercial term
  with LuxAlgo, are Chris's decisions. Nothing in this record contacts either
  party.

### Risk if I am wrong

If some route exists that I have not found, it is almost certainly a negotiated
FINRA licence — the terms themselves say permission is available on request. The
cost of being wrong in the conservative direction is small and bounded: one
dataset family out of six is unavailable, `short-volume` is one field of analytics
among several, and no other family depends on it. The cost of being wrong the
other way is an injunction before the public launch, a §107 case we would lose on
the factors, and a data-licence representation we cannot support. **The asymmetry
is not close.**

---

## The caveat text this record requires in the product

What we tell users about the terms of the data we serve is a legal artefact, so
the wording is stated here rather than left to whoever edits the string. The
current `LUXALGO_TRACKERS_DATA_CAVEATS["short-volume"]` in
`digiquant/src/digiquant/data/luxalgo/attribution.py` says the upstream terms
are **"unresolved"**. They are not — this record resolves them. It also says the
durable question is "the upstream FINRA redistribution terms, which no vendor
licence answers", which is now wrong in the other direction: the answer does not
turn on a vendor licence at all.

Two consequences, and only these two:

1. **The caveat must state the position, not the doubt.** It has to carry, in
   substance: FINRA permits no commercial redistribution of this compilation on
   any published route; **Specific Terms for Equity Data §2.3** is the decisive
   clause, capping End Users' use at *"non-commercial personal or professional
   use only"* **and "No Charge"**, with even bundled distribution clean only
   where there is *"no additional or incremental fee charged for the Equity
   Data"*; and the CC0 grant cannot cure any of it, because **§4(b)–(c)** is the
   affirmer disclaiming warranty of title and any duty to clear other people's
   rights or obtain their consents.
2. **Nothing may present the family as cleared**, and that has to stay in the
   same breath as the licence note, on every surface. Security's guards
   (`test_no_user_visible_cc0_claim_is_left_unqualified`,
   `test_every_trackers_tool_note_carries_the_caveat`) stay green on every branch
   of the decision. The caveat **wording** changes; the guard may not be deleted
   or weakened. If the family is removed, the guard has to keep passing with it
   absent rather than by being skipped around.

Whether the family stays in service is the business decision, and it does not
change this wording. A family kept in service against this advice is a dated
decision to accept a documented exposure — **not** a clearance — which is the
form the `congress-trades` caveat already takes.

---

## Clauses this record does *not* support reading

Stated so nobody over-reads it later:

- Nothing here says FINRA data may never be used commercially. It may be, under a
  written permission that includes redistribution. That route is open and unused.
- Nothing here says the User Guide's field list or the file format is unprotectable
  as an idea. We are not redistributing the guide; we are redistributing the data.
- Nothing here says anything about FINRA's *equity short interest* data or its
  other catalogues, which have their own terms and are not in our allowlist. If
  one is ever proposed, this record is the starting point, not the answer.
- Nothing here decides whether the **other five** trackers families are clear.
  They are, on a different and stronger basis — 17 U.S.C. §105 — recorded in the
  [LuxAlgo record](../luxalgo/INDEX.md#per-family-classification).

---

> `DIG-###` are internal issue-tracker IDs, not resolvable in this public
> repository; each is cited so the reasoning is traceable internally.